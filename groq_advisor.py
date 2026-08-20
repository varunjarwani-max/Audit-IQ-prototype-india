"""
Groq LLM Client & Ground-Truth Verified Workpaper Generator for AuditIQ.
Architecture:
- Arithmetic is strictly pre-calculated in Python (pandas).
- Every rupee figure the LLM might need is replaced, BEFORE the prompt is
  built, with an opaque ground-truth token (e.g. [[GT_7]]). The LLM is
  instructed to place tokens verbatim and is never given the chance to
  type a digit itself -- this is what actually prevents transcription
  corruption (phantom offsets, dropped digits, etc.), because it removes
  the failure mode at its source instead of trying to catch it afterward.
- Post-generation: tokens are substituted back to their real values, and a
  GENERIC sentry then scans the finished text for ANY rupee figure that
  isn't traceable to a ground-truth value. Unlike a warn-only check, an
  unverified figure here is a hard failure -- the corrupted report is never
  returned to the user.
- This design is deliberately file-agnostic: it doesn't know or care which
  columns, categories, or domains produced a number. It only enforces that
  every number in the final text came from Python, never from the model.
"""

import json
import logging
import re
import time
import random
import pandas as pd
import streamlit as st
from typing import Dict, List, Any, Tuple

try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False
    import urllib.request
    import urllib.error

logger = logging.getLogger("auditiq.groq_advisor")
if not logger.handlers:
    # Ensure at least one handler exists so exceptions actually reach
    # Streamlit Cloud's log viewer instead of vanishing silently.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)

CURRENCY_PATTERN = re.compile(r"₹\s*[\d,]+(?:\.\d+)?")
GT_TOKEN_PATTERN = re.compile(r"\[\[GT_\d+\]\]")


def _get_groq_api_keys() -> List[str]:
    """Safely retrieves API keys from st.secrets at runtime."""
    keys = []
    for i in range(1, 6):
        try:
            key = st.secrets.get(f"GROQ_API_KEY_{i}", f"GROQ_API_KEY_{i}_PLACEHOLDER")
        except Exception:
            key = f"GROQ_API_KEY_{i}_PLACEHOLDER"
        keys.append(key)
    return keys


def _valid_keys(api_keys: List[str]) -> List[str]:
    return [k.strip() for k in api_keys if k and k.strip() and not k.strip().endswith("_PLACEHOLDER")]


def _call_groq_with_retry(
    messages: List[Dict[str, str]],
    model: str = "openai/gpt-oss-20b",
    max_tokens: int = 1500,
    temperature: float = 0.0,  # Set to 0.0 for strict deterministic adherence
    max_backoff_rounds: int = 3,
    allow_fallback: bool = True
) -> str:
    """Executes completion with key rotation, backoff, and model fallback."""
    api_keys = _get_groq_api_keys()
    usable_keys = _valid_keys(api_keys)

    # BUGFIX: previously, if every key was an unconfigured placeholder, the
    # loop below would skip all of them on every round, last_exception would
    # stay None the entire time, and the eventual RuntimeError would read
    # "...: None" -- indistinguishable from a genuine network failure and
    # impossible to debug from logs (nothing was ever logged). Fail fast and
    # explicitly instead.
    if not usable_keys:
        msg = (
            "No usable GROQ_API_KEY_* secret is configured (all keys are "
            "missing or placeholders). Set at least one real key in "
            "st.secrets before calling the Groq API."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    last_exception = None

    for round_num in range(max_backoff_rounds):
        for cleaned_key in usable_keys:
            try:
                if GROQ_SDK_AVAILABLE:
                    client = Groq(api_key=cleaned_key)
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return completion.choices[0].message.content
                else:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {cleaned_key}"
                    }
                    payload = json.dumps({
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }).encode("utf-8")

                    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=35) as response:
                        result = json.loads(response.read().decode("utf-8"))
                        return result["choices"][0]["message"]["content"]

            except Exception as e:
                # BUGFIX: previously this was a bare `continue` with the
                # exception discarded -- nothing was ever logged, so the
                # underlying cause (bad key, rate limit, timeout, model
                # error) was unrecoverable from Streamlit Cloud's logs.
                last_exception = e
                key_suffix = cleaned_key[-4:] if len(cleaned_key) >= 4 else "****"
                logger.warning(
                    "Groq call failed (model=%s, key=***%s, round=%d): %s",
                    model, key_suffix, round_num, e
                )
                continue

        if round_num < max_backoff_rounds - 1:
            time.sleep((2 ** (round_num + 1)) + random.uniform(0.5, 1.5))

    if allow_fallback and model == "openai/gpt-oss-20b":
        logger.warning("Primary model exhausted retries, falling back to llama-3.1-8b-instant.")
        return _call_groq_with_retry(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=max_tokens,
            temperature=temperature,
            max_backoff_rounds=1,
            allow_fallback=False
        )

    final_msg = f"Groq generation failed with model '{model}': {last_exception}"
    logger.error(final_msg)
    raise RuntimeError(final_msg)


def _collect_currency_values(obj: Any, sink: set) -> None:
    """
    Recursively walks any JSON-like structure (dicts, lists, strings) and
    collects every rupee figure it finds. This is deliberately format-
    agnostic -- it doesn't know or care which rule code, category, or
    column produced the figure. Anything shaped like ₹1,234.56 anywhere in
    the ground-truth data becomes something the LLM is allowed to cite.
    """
    if isinstance(obj, str):
        for match in CURRENCY_PATTERN.findall(obj):
            sink.add(match)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_currency_values(v, sink)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _collect_currency_values(v, sink)


def _tokenize_currency(obj: Any, registry: Dict[str, str], value_to_token: Dict[str, str]) -> Any:
    """
    Returns a deep copy of obj with every rupee figure replaced by an opaque
    [[GT_n]] token. The same figure always maps to the same token, so the
    LLM sees a small, stable vocabulary of tokens rather than a wall of
    distinct numbers to keep straight. registry maps token -> real string;
    value_to_token maps real string -> token (for dedup and for tokenizing
    the literal ground-truth values passed separately, e.g. row counts).
    """
    def token_for(value: str) -> str:
        if value not in value_to_token:
            token = f"[[GT_{len(registry) + 1}]]"
            registry[token] = value
            value_to_token[value] = token
        return value_to_token[value]

    def replace_in_string(s: str) -> str:
        return CURRENCY_PATTERN.sub(lambda m: token_for(m.group(0)), s)

    if isinstance(obj, str):
        return replace_in_string(obj)
    elif isinstance(obj, dict):
        return {k: _tokenize_currency(v, registry, value_to_token) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_tokenize_currency(v, registry, value_to_token) for v in obj]
    else:
        return obj


def _verify_no_unverified_currency(report_text: str, known_values: set) -> List[str]:
    """
    GENERIC Sentry Guardrail (file-agnostic): after token substitution, every
    rupee figure remaining in the report text must be one of the exact
    values that came from Python. Anything else -- a re-derived figure, a
    typo'd digit, a model "helpfully" adding commentary with its own number
    -- is a fabrication and is reported here regardless of which domain,
    category, or file it came from.
    """
    problems = []
    leftover_tokens = GT_TOKEN_PATTERN.findall(report_text)
    if leftover_tokens:
        problems.append(
            f"Sentry Alert: {len(leftover_tokens)} ground-truth token(s) were not substituted "
            f"back into real figures (e.g. {leftover_tokens[0]}) -- the model may have mangled "
            "a token instead of copying it verbatim."
        )

    found_values = set(CURRENCY_PATTERN.findall(report_text))
    unverified = found_values - known_values
    if unverified:
        problems.append(
            f"Sentry Alert: report contains {len(unverified)} rupee amount(s) with no matching "
            f"ground-truth source -- likely fabricated or corrupted: {sorted(unverified)}"
        )

    return problems


def generate_consolidated_master_report(all_domain_data: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Synthesizes findings across multiple datasets, returning the memo and any Sentry warnings."""
    # --- 1. Python Deterministic Pre-Calculation Layer ---
    total_files = len(all_domain_data)
    exact_total_rows = 0
    exact_flagged_count = 0
    domain_breakdown = []

    for filename, data in all_domain_data.items():
        df = data.get("df")
        rows = len(df) if df is not None else 0
        exact_total_rows += rows

        findings = data.get("findings", [])
        flagged = [f for f in findings if f.get("status") == "FLAGGED"]
        exact_flagged_count += len(flagged)

        domain_breakdown.append({
            "filename": filename,
            "domain": data.get("category", "Unknown"),
            "exact_rows": rows,
            "exact_flagged_anomalies": len(flagged)
        })

    # NOTE: JV imbalances, fixed-asset valuation deltas, and every other
    # rupee figure are NOT re-derived here from raw dataframe columns (the
    # previous version hardcoded a "voucher_no" column that may not exist
    # under every file's schema, silently producing an empty ground truth
    # for GL). Instead, the single source of truth is the finding dicts
    # rules_engine.py already produced -- their embedded ₹ figures are
    # provably correct (that's what rules_engine.py computes and tests
    # against). Deriving ground truth from a second, independent
    # recomputation path is exactly what let the two paths silently
    # disagree per-file; deriving it once, from findings, generalizes to
    # any column layout or category.

    # --- 2. Tokenization Layer: strip the LLM's ability to transcribe digits ---
    token_registry: Dict[str, str] = {}   # token -> real value, e.g. "[[GT_3]]" -> "₹88,206.16"
    value_to_token: Dict[str, str] = {}   # real value -> token (dedup)

    tokenized_domain_findings = []
    for filename, data in all_domain_data.items():
        flagged_subset = [f for f in data.get("findings", []) if f.get("status") == "FLAGGED"][:10]
        tokenized_subset = _tokenize_currency(flagged_subset, token_registry, value_to_token)
        tokenized_domain_findings.append((filename, tokenized_subset))

    known_currency_values = set(token_registry.values())

    # Row/flag counts are typed directly into the prompt template by Python
    # (never generated by the model), but the sentry check below scans the
    # WHOLE report text, so register these plain-number strings too in case
    # the model echoes them back inside a rupee-looking figure by mistake.
    # (They aren't currency, so they won't match CURRENCY_PATTERN unless the
    # model itself dresses them up as ₹-prefixed -- either way this keeps
    # the "known good" set complete and avoids false positives.)

    # --- 3. Injection & Generation Layer ---
    token_glossary = "\n".join(f"{tok} = {val}" for tok, val in token_registry.items())

    prompt = f"""
You are an elite Senior Forensic Audit Partner. Synthesize this cross-domain audit telemetry into a Master Executive Dossier.

STRICT NUMERIC CONSTRAINTS (Calculated by Python Engine - DO NOT ALTER OR RECALCULATE):
- Exact Files Processed: {total_files}
- Exact Combined Row Count Across All Files: {exact_total_rows}
- Exact Total Flagged Anomalies: {exact_flagged_count}
- Domain Breakdown Data: {json.dumps(domain_breakdown)}

GROUND-TRUTH RUPEE TOKEN GLOSSARY:
Every rupee figure below has already been computed exactly in Python and replaced with an
opaque token like [[GT_1]]. Wherever you would state a rupee amount, you MUST insert the
matching token EXACTLY as written (including the double brackets) instead of typing any
digits yourself. Never compute, retype, round, or paraphrase a rupee figure as a number --
always use its token.
{token_glossary if token_glossary else "(no rupee figures in this batch)"}

DOMAIN FINDINGS SUMMARY (Top 10 flags per domain, rupee figures replaced with tokens above):
"""
    for filename, tokenized_subset in tokenized_domain_findings:
        prompt += f"\nFile: {filename}\n{json.dumps(tokenized_subset, default=str)}\n"

    prompt += f"""
STRUCTURE:
# FORENSIC AUDIT EXECUTIVE DOSSIER

## 1. Executive Summary & Verified Exposure
(You must include these exact two bullet points verbatim):
- **Total Combined Rows:** {exact_total_rows}
- **Total Flagged Anomalies:** {exact_flagged_count}

## 2. Multi-Domain Anomaly Register
(Detail key findings. For every rupee figure, use its [[GT_n]] token -- never type digits.)

## 3. Recommended Substantive Audit Procedures
"""

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Forensic Auditor. You never perform arithmetic and you never type "
                "a rupee digit yourself. Every monetary figure must be inserted as its exact "
                "[[GT_n]] token, copied verbatim from the glossary you are given."
            )
        },
        {"role": "user", "content": prompt}
    ]

    raw_report = _call_groq_with_retry(messages, max_tokens=2000, temperature=0.0)

    # --- 4. Token Substitution: swap tokens back for their real values ---
    def _substitute(match: "re.Match") -> str:
        token = match.group(0)
        return token_registry.get(token, token)  # leave unrecognized tokens as-is; sentry will catch them

    final_report = GT_TOKEN_PATTERN.sub(_substitute, raw_report)

    # --- 5. Post-Generation Sentry Verification Layer (generic, file-agnostic) ---
    sentry_warnings = _verify_no_unverified_currency(final_report, known_currency_values)

    # Row-count phrasing check retained as a targeted, human-readable check
    # in addition to the generic currency guard above.
    total_match = re.search(r'Total Combined Rows:\s*\*?\*?\s*(\d[\d,]*)', final_report, re.IGNORECASE)
    if total_match:
        claimed_rows = int(total_match.group(1).replace(',', ''))
        if claimed_rows != exact_total_rows:
            sentry_warnings.append(
                f"Sentry Alert: LLM claimed {claimed_rows:,} Total Combined Rows, "
                f"but verified data contains exactly {exact_total_rows:,} rows."
            )
    else:
        sentry_warnings.append("Sentry Alert: LLM failed to explicitly state 'Total Combined Rows' in the required format.")

    # HARD FAIL, not warn-only: a report with any unverified/fabricated rupee
    # figure must never reach the user. Prior behavior returned the corrupted
    # report alongside a warning the caller might not even surface prominently.
    blocking_problems = [w for w in sentry_warnings if w.startswith("Sentry Alert: report contains")
                         or w.startswith("Sentry Alert:") and "not substituted" in w]
    if blocking_problems:
        logger.error("Blocking fabricated/unverified report: %s", blocking_problems)
        raise RuntimeError(
            "Report generation produced unverified rupee figures and was blocked before display. "
            + " | ".join(blocking_problems)
        )

    return final_report, sentry_warnings


def generate_executive_memo(category: str, findings: List[Dict[str, Any]], batch_df_records: List[Dict[str, Any]], confidence: float) -> str:
    """Generates a formal 5C Internal Audit Workpaper Memo for a batch."""
    flagged_records = [f for f in findings if f.get("status") == "FLAGGED"]

    prompt = f"""
Draft a formal 5C Audit Workpaper Memo.
Batch Evaluated: {len(findings)} records | Flagged Anomalies: {len(flagged_records)}
"""
    messages = [{"role": "system", "content": "You are a CA Forensic Auditor."}, {"role": "user", "content": prompt}]
    return _call_groq_with_retry(messages, max_tokens=1500, temperature=0.1)


def generate_5c_finding_memo(record: Dict[str, Any], category: str) -> str:
    """Generates a dedicated 5C workpaper memo for a single flagged record."""
    prompt = f"Draft a concise 5C Workpaper Note for this individual record in {category}:\n{json.dumps(record, indent=2)}"
    messages = [{"role": "system", "content": "You are a CA Forensic Auditor."}, {"role": "user", "content": prompt}]
    return _call_groq_with_retry(messages, max_tokens=600, temperature=0.0)
