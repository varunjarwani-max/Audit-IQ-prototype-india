"""
Groq LLM Client & Ground-Truth Verified Workpaper Generator for AuditIQ.
Architecture:
- Pre-calculates exact row counts and tokenizes rupee amounts.
- Unpacks nested rule engine flags ('flags' array) to extract granular rule codes.
- Verifies post-generation consistency with strict Sentry guardrails.
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


def _unpack_nested_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unpacks rules_engine.py nested 'flags' list into flat finding dicts."""
    flat_list = []
    for rec in findings:
        if not isinstance(rec, dict):
            continue

        row_idx = rec.get("row_index")
        record_id = rec.get("record_id")
        flags = rec.get("flags", [])

        if isinstance(flags, list) and len(flags) > 0:
            for flag in flags:
                if isinstance(flag, dict):
                    flat_list.append({
                        "row": row_idx,
                        "record_id": record_id,
                        "rule": flag.get("rule_code") or flag.get("rule_name") or "ANOMALY",
                        "rule_name": flag.get("rule_name", ""),
                        "severity": flag.get("severity", "MEDIUM"),
                        "finding": flag.get("description") or flag.get("detected_value") or "Flagged anomaly detected.",
                        "detected_value": flag.get("detected_value", ""),
                        "expected": flag.get("expected", ""),
                        "remediation": flag.get("remediation", "")
                    })
        elif str(rec.get("status")).upper() == "FLAGGED":
            flat_list.append({
                "row": row_idx,
                "record_id": record_id,
                "rule": rec.get("rule_code") or rec.get("rule") or "ANOMALY",
                "finding": str(rec.get("description") or rec.get("finding") or "Flagged anomaly")[:200]
            })
    return flat_list


def _call_groq_with_retry(
    messages: List[Dict[str, str]],
    model: str = "openai/gpt-oss-20b",
    max_tokens: int = 1500,
    temperature: float = 0.0,
    max_backoff_rounds: int = 3,
    allow_fallback: bool = True
) -> str:
    api_keys = _get_groq_api_keys()
    usable_keys = _valid_keys(api_keys)

    if not usable_keys:
        msg = "No usable GROQ_API_KEY_* secret configured."
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
                    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cleaned_key}"}
                    payload = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}).encode("utf-8")
                    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=35) as response:
                        result = json.loads(response.read().decode("utf-8"))
                        return result["choices"][0]["message"]["content"]
            except Exception as e:
                last_exception = e
                continue
        if round_num < max_backoff_rounds - 1:
            time.sleep((2 ** (round_num + 1)) + random.uniform(0.5, 1.5))

    if allow_fallback and model == "openai/gpt-oss-20b":
        return _call_groq_with_retry(messages, model="llama-3.3-70b-versatile", max_tokens=max_tokens, temperature=temperature, max_backoff_rounds=1, allow_fallback=False)

    raise RuntimeError(f"Groq generation failed: {last_exception}")


def _tokenize_currency(obj: Any, registry: Dict[str, str], value_to_token: Dict[str, str]) -> Any:
    def token_for(value: str) -> str:
        if value not in value_to_token:
            token = f"[[GT_{len(registry) + 1}]]"
            registry[token] = value
            value_to_token[value] = token
        return value_to_token[value]

    if isinstance(obj, str):
        return CURRENCY_PATTERN.sub(lambda m: token_for(m.group(0)), obj)
    elif isinstance(obj, dict):
        return {k: _tokenize_currency(v, registry, value_to_token) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_tokenize_currency(v, registry, value_to_token) for v in obj]
    return obj


def _verify_no_unverified_currency(report_text: str, known_values: set) -> List[str]:
    problems = []
    leftover = GT_TOKEN_PATTERN.findall(report_text)
    if leftover:
        problems.append(f"Sentry Alert: {len(leftover)} ground-truth tokens were not substituted.")
    found = set(CURRENCY_PATTERN.findall(report_text))
    unverified = found - known_values
    if unverified:
        problems.append(f"Sentry Alert: report contains unverified rupee amounts: {sorted(unverified)}")
    return problems


def generate_consolidated_master_report(all_domain_data: Dict[str, Any]) -> Tuple[str, List[str]]:
    total_files = len(all_domain_data)
    exact_total_rows = 0
    exact_flagged_count = 0
    domain_breakdown = []

    for filename, data in all_domain_data.items():
        df = data.get("df")
        rows = len(df) if df is not None else 0
        exact_total_rows += rows

        raw_findings = data.get("findings", [])
        unpacked_findings = _unpack_nested_findings(raw_findings)
        
        # Unique rows flagged
        flagged_rows = len({f["row"] for f in unpacked_findings if f.get("row") is not None})
        exact_flagged_count += flagged_rows

        domain_breakdown.append({
            "filename": filename,
            "domain": data.get("category", "Unknown"),
            "exact_rows": rows,
            "exact_flagged_anomalies": flagged_rows
        })

    token_registry: Dict[str, str] = {}
    value_to_token: Dict[str, str] = {}
    tokenized_domain_findings = []

    for filename, data in all_domain_data.items():
        unpacked = _unpack_nested_findings(data.get("findings", []))[:8]  # Limit to top 8 unpacked findings
        tokenized_subset = _tokenize_currency(unpacked, token_registry, value_to_token)
        tokenized_domain_findings.append((filename, tokenized_subset))

    known_currency_values = set(token_registry.values())
    token_glossary = "\n".join(f"{tok} = {val}" for tok, val in token_registry.items())

    prompt = f"""
You are an elite Senior Forensic Audit Partner. Synthesize this cross-domain audit telemetry into a Master Executive Dossier.

STRICT NUMERIC CONSTRAINTS (Calculated by Python Engine):
- Exact Files Processed: {total_files}
- Exact Combined Row Count Across All Files: {exact_total_rows}
- Exact Total Flagged Anomalies: {exact_flagged_count}
- Domain Breakdown Data: {json.dumps(domain_breakdown)}

GROUND-TRUTH RUPEE TOKEN GLOSSARY:
{token_glossary if token_glossary else "(no rupee figures)"}

ITEMIZED DOMAIN FINDINGS TELEMETRY:
"""
    for filename, tokenized_subset in tokenized_domain_findings:
        prompt += f"\nFile: {filename}\n{json.dumps(tokenized_subset, default=str)}\n"

    prompt += f"""
STRUCTURE:
# FORENSIC AUDIT EXECUTIVE DOSSIER

## 1. Executive Summary & Verified Exposure
- **Total Combined Rows:** {exact_total_rows}
- **Total Flagged Anomalies:** {exact_flagged_count}

## 2. Multi-Domain Anomaly Register
(Detail itemized key findings using exact rule codes like TXN-001, AGE-001, GL-001, voucher numbers, vendor names, and [[GT_n]] tokens. Do not write generic boilerplate.)

## 3. Recommended Substantive Audit Procedures
"""

    messages = [
        {"role": "system", "content": "You are a Forensic Auditor. Cite specific rule codes (e.g. TXN-004, GL-002, AST-001) and vendor/row details from the telemetry."},
        {"role": "user", "content": prompt}
    ]

    raw_report = _call_groq_with_retry(messages, max_tokens=1500, temperature=0.0)

    final_report = GT_TOKEN_PATTERN.sub(lambda m: token_registry.get(m.group(0), m.group(0)), raw_report)
    sentry_warnings = _verify_no_unverified_currency(final_report, known_currency_values)

    total_match = re.search(r'Total\s+(?:Combined\s+)?Rows?[^0-9\n]*?(\d[\d,]*)', final_report, re.IGNORECASE)
    if not total_match:
        summary_header = "## 1. Executive Summary & Verified Exposure"
        verified_bullets = f"\n- **Total Combined Rows:** {exact_total_rows:,}\n- **Total Flagged Anomalies:** {exact_flagged_count:,}\n\n"
        if summary_header in final_report:
            final_report = final_report.replace(summary_header, summary_header + "\n" + verified_bullets)

    return final_report, sentry_warnings
