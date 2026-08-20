"""
Groq LLM Client & Ground-Truth Verified Workpaper Generator for AuditIQ.
Architecture:
- Pre-calculates exact row counts and tokenizes rupee amounts.
- Unpacks nested rule engine flags ('flags' array) to extract granular rule codes.
- Verifies post-generation consistency with non-blocking Sentry guardrails.
- Exports: generate_consolidated_master_report, generate_executive_memo, generate_5c_finding_memo
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
        msg = "No usable GROQ_API_KEY_* secret is configured in st.secrets."
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
                continue

        if round_num < max_backoff_rounds - 1:
            time.sleep((2 ** (round_num + 1)) + random.uniform(0.5, 1.5))

    if allow_fallback and model == "openai/gpt-oss-20b":
        return _call_groq_with_retry(
            messages=messages,
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            temperature=temperature,
            max_backoff_rounds=1,
            allow_fallback=False
        )

    raise RuntimeError(f"Groq API call failed: {last_exception}")


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
    leftover_tokens = GT_TOKEN_PATTERN.findall(report_text)
    if leftover_tokens:
        problems.append(f"Sentry Note: {len(leftover_tokens)} token(s) remained raw in text.")

    found_values = set(CURRENCY_PATTERN.findall(report_text))
    unverified = found_values - known_values
    if unverified:
        problems.append(f"Sentry Note: Report contains unverified monetary figures: {sorted(unverified)}")

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
        unpacked = _unpack_nested_findings(data.get("findings", []))[:8]
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
(Detail itemized key findings using exact rule codes like TXN-004, GL-002, AST-001, voucher numbers, vendor names, and [[GT_n]] tokens.)

## 3. Recommended Substantive Audit Procedures
"""

    messages = [
        {"role": "system", "content": "You are a CA Forensic Auditor drafting an executive audit report."},
        {"role": "user", "content": prompt}
    ]

    try:
        raw_report = _call_groq_with_retry(messages, max_tokens=1500, temperature=0.0)
    except Exception as err:
        return f"# Error Generating Dossier\n\nFailed to connect to LLM provider: {str(err)}", [str(err)]

    final_report = GT_TOKEN_PATTERN.sub(lambda m: token_registry.get(m.group(0), m.group(0)), raw_report)
    sentry_warnings = _verify_no_unverified_currency(final_report, known_currency_values)

    return final_report, sentry_warnings


def generate_executive_memo(category: str, findings: List[Dict[str, Any]], batch_df_records: List[Dict[str, Any]], confidence: float) -> str:
    unpacked_findings = _unpack_nested_findings(findings)
    total_records = len(batch_df_records) if batch_df_records else len(findings)
    flagged_records = len(unpacked_findings)

    prompt = f"""
Draft a formal 5C Audit Workpaper Memo for domain '{category}'.
Batch Evaluated: {total_records} records | Flagged Anomalies: {flagged_records}

Sample Telemetry Findings:
{json.dumps(unpacked_findings[:5], indent=2, default=str)}

STRUCTURE REQUIREMENT:
- Condition: What was observed in the data telemetry.
- Criteria: Applicable accounting standard or control benchmark.
- Cause: Root driver of the variance.
- Effect: Financial and operational risk exposure.
- Corrective Action: Audit recommendations for remediation.
"""
    messages = [
        {"role": "system", "content": "You are a CA Forensic Auditor drafting a formal 5C Audit Memo."},
        {"role": "user", "content": prompt}
    ]
    try:
        return _call_groq_with_retry(messages, max_tokens=1500, temperature=0.1)
    except Exception as e:
        return f"Error generating 5C Memo: {str(e)}"


def generate_5c_finding_memo(record: Dict[str, Any], category: str) -> str:
    prompt = f"""
Draft a concise 5C Workpaper Note for this individual flagged record in category '{category}':
{json.dumps(record, indent=2, default=str)}
"""
    messages = [
        {"role": "system", "content": "You are a CA Forensic Auditor drafting an itemized finding note."},
        {"role": "user", "content": prompt}
    ]
    try:
        return _call_groq_with_retry(messages, max_tokens=600, temperature=0.0)
    except Exception as e:
        return f"Error generating item note: {str(e)}"
