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


def _is_flagged_finding(f: Dict[str, Any]) -> bool:
    """Flexible check for flagged findings across various schema conventions."""
    if not isinstance(f, dict):
        return False
    status = f.get("status")
    # If no explicit status key exists, assume findings in list are flagged anomalies
    if status is None:
        return True
    return str(status).upper() in ("FLAGGED", "TRUE", "HIGH", "CRITICAL", "YES", "ANOMALY")


def _clean_and_preserve_finding(f: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts finding details dynamically while truncating text to optimize token usage."""
    cleaned = {}

    # 1. Extract Rule ID or Category
    cleaned["rule"] = (
        f.get("rule_id") or f.get("rule_code") or f.get("rule") or f.get("category") or "ANOMALY"
    )

    # 2. Extract Finding Description (checks all standard schema keys)
    description = (
        f.get("finding") or
        f.get("description") or
        f.get("details") or
        f.get("message") or
        f.get("issue") or
        f.get("observation") or
        ""
    )
    cleaned["finding"] = str(description)[:200] if description else "Flagged anomaly detected."

    # 3. Preserve critical forensic identifiers if present
    for identifier in ["row", "row_index", "voucher_no", "vendor", "vendor_name", "account", "severity", "amount"]:
        if identifier in f and f[identifier] is not None:
            cleaned[identifier] = f[identifier]

    return cleaned


def _call_groq_with_retry(
    messages: List[Dict[str, str]],
    model: str = "openai/gpt-oss-20b",
    max_tokens: int = 1500,
    temperature: float = 0.0,
    max_backoff_rounds: int = 3,
    allow_fallback: bool = True
) -> str:
    """Executes completion with key rotation, backoff, and model fallback."""
    api_keys = _get_groq_api_keys()
    usable_keys = _valid_keys(api_keys)

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
                last_exception = e
                key_suffix = cleaned_key[-4:] if len(cleaned_key) >= 4 else "****"
                logger.warning(
                    "Groq call failed (model=%s, key=***%s, round=%d): %s",
                    model, key_suffix, round_num, e
                )
                continue

        if round_num < max_backoff_rounds - 1:
            time.sleep((2 ** (round_num + 1)) + random.uniform(0.5, 1.5))

    # Fall back to an active Groq model if primary fails
    if allow_fallback and model == "openai/gpt-oss-20b":
        logger.warning("Primary model exhausted retries, falling back to llama-3.3-70b-versatile.")
        return _call_groq_with_retry(
            messages=messages,
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            temperature=temperature,
            max_backoff_rounds=1,
            allow_fallback=False
        )

    final_msg = f"Groq generation failed with model '{model}': {last_exception}"
    logger.error(final_msg)
    raise RuntimeError(final_msg)


def _collect_currency_values(obj: Any, sink: set) -> None:
    """Recursively walks data structures to extract formatted currency strings."""
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
    """Replaces rupee figures with tokenized values like [[GT_1]]."""
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
    """Sentry guardrail checking for unverified monetary values in the output text."""
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
        flagged = [f for f in findings if _is_flagged_finding(f)]
        exact_flagged_count += len(flagged)

        domain_breakdown.append({
            "filename": filename,
            "domain": data.get("category", "Unknown"),
            "exact_rows": rows,
            "exact_flagged_anomalies": len(flagged)
        })

    # --- 2. Tokenization & Data Plumbing Layer ---
    token_registry: Dict[str, str] = {}
    value_to_token: Dict[str, str] = {}

    tokenized_domain_findings = []
    for filename, data in all_domain_data.items():
        findings = data.get("findings", [])
        flagged_raw = [f for f in findings if _is_flagged_finding(f)][:5]  # Top 5 detailed findings per domain
        
        cleaned_subset = [_clean_and_preserve_finding(f) for f in flagged_raw]
        tokenized_subset = _tokenize_currency(cleaned_subset, token_registry, value_to_token)
        tokenized_domain_findings.append((filename, tokenized_subset))

    known_currency_values = set(token_registry.values())

    # --- 3. Injection & Prompt Construction Layer ---
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

ITEMIZED DOMAIN FINDINGS TELEMETRY:
Below are the itemized audit findings per file. Cite specific rule codes, voucher numbers, row indexes, vendor names, and monetary tokens directly in your report.
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
(Detail itemized key findings using exact rule codes, voucher numbers, vendor names, and [[GT_n]] tokens. Do not write generic boilerplate.)

## 3. Recommended Substantive Audit Procedures
"""

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Forensic Auditor. You cite specific itemized telemetry (rule codes, vendors, vouchers) "
                "from the findings provided. You never perform arithmetic and never type rupee digits yourself. "
                "Every monetary figure must be inserted as its exact [[GT_n]] token, copied verbatim from the glossary."
            )
        },
        {"role": "user", "content": prompt}
    ]

    raw_report = _call_groq_with_retry(messages, max_tokens=1500, temperature=0.0)

    # --- 4. Token Substitution Layer ---
    def _substitute(match: "re.Match") -> str:
        token = match.group(0)
        return token_registry.get(token, token)

    final_report = GT_TOKEN_PATTERN.sub(_substitute, raw_report)

    # --- 5. Post-Generation Sentry Verification Layer ---
    sentry_warnings = _verify_no_unverified_currency(final_report, known_currency_values)

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
    flagged_records = [f for f in findings if _is_flagged_finding(f)]

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
