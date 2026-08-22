"""
groq_advisor.py - AI Report & Memo Synthesis for AuditIQ
"""

import os
import re
import json
import time
import random
from groq import Groq

try:
    import streamlit as st
except ImportError:  # Allows the helper module to run outside Streamlit.
    st = None

# Model routing is explicit so deterministic audit stages never spend LLM calls.
CLASSIFIER_MODEL = "openai/gpt-oss-safeguard-20b"
DRAFTER_MODEL = "openai/gpt-oss-20b"
CHECKER_MODEL = "openai/gpt-oss-20b"
EMERGENCY_FALLBACK_MODEL = "openai/gpt-oss-120b"

# Backwards-compatible alias for callers that imported the old constant.
MODEL_NAME = DRAFTER_MODEL

KNOWN_RULE_CODES = {
    "TXN-001", "TXN-002", "TXN-003", "TXN-004",
    "AGE-001", "AGE-002", "AGE-003",
    "GL-001", "GL-002",
    "AST-001", "AST-002", "AST-003",
}

DOMAIN_DISPLAY_NAMES = {
    "transactions": "Transactions",
    "ar_ap_aging": "Accounts Receivable / Accounts Payable Aging",
    "general_ledger": "General Ledger",
    "fixed_assets": "Fixed Assets",
}

def _get_groq_api_keys() -> list[str]:
    """Load up to four Groq keys from Streamlit secrets or environment variables."""
    secret_names = [f"GROQ_API_KEY_{index}" for index in range(1, 5)]
    keys = []

    for name in secret_names:
        value = os.environ.get(name)
        if not value and st is not None:
            try:
                value = st.secrets.get(name)
            except (FileNotFoundError, RuntimeError):
                value = None
        if value and str(value).strip():
            keys.append(str(value).strip())

    # Keep the conventional single-key name as a backwards-compatible fallback.
    fallback = os.environ.get("GROQ_API_KEY")
    if not fallback and st is not None:
        try:
            fallback = st.secrets.get("GROQ_API_KEY")
        except (FileNotFoundError, RuntimeError):
            fallback = None
    if not keys and fallback and str(fallback).strip():
        keys.append(str(fallback).strip())

    return list(dict.fromkeys(keys))


def get_groq_client():
    api_keys = _get_groq_api_keys()
    if not api_keys:
        raise ValueError(
            "No Groq API key was found. Add GROQ_API_KEY_1 through "
            "GROQ_API_KEY_4 to Streamlit secrets."
        )
    return Groq(api_key=random.choice(api_keys))

def format_currency(val: float) -> str:
    return f"₹{float(val):,.2f}"

def _call_groq_with_backoff(
    client,
    messages: list,
    model: str = DRAFTER_MODEL,
    max_retries: int = 4,
    temperature: float = 0.1,
):
    base_delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            err_msg = str(e).lower()
            if ("429" in err_msg or "rate limit" in err_msg) and attempt < max_retries:
                sleep_time = (base_delay * (2 ** attempt)) + random.uniform(0.1, 1.0)
                time.sleep(sleep_time)
            else:
                raise


def _call_with_emergency_fallback(client, messages: list, model: str = DRAFTER_MODEL, temperature: float = 0.1):
    """Use the requested model first; reserve 120b for an actual model failure."""
    try:
        return _call_groq_with_backoff(client, messages, model=model, temperature=temperature)
    except Exception:
        return _call_groq_with_backoff(
            client, messages, model=EMERGENCY_FALLBACK_MODEL, temperature=temperature
        )

def _check_hallucinations(text: str) -> list:
    problems = []
    if re.search(r'₹\d', text):
        problems.append("Text contains a currency figure, which is not allowed.")
    mentioned_codes = set(re.findall(r'\b[A-Z]{2,4}-\d{3}\b', text))
    invented = mentioned_codes - KNOWN_RULE_CODES
    if invented:
        problems.append(f"Text references unknown rule code(s): {sorted(invented)}")
    return problems

def _build_domain_payload(all_domain_data: dict):
    summary_stats = []
    by_domain = {}

    for file_name, file_info in all_domain_data.items():
        domain = file_info.get("category", "unknown")
        df = file_info.get("df")
        findings = file_info.get("findings", [])

        flagged_count = sum(1 for f in findings if f.get("status") == "FLAGGED")
        summary_stats.append({
            "file": file_name,
            "domain": domain,
            "rows": len(df) if df is not None else 0,
            "flagged_anomalies": flagged_count
        })

        by_domain.setdefault(domain, [])

        for item in findings:
            if item.get("status") != "FLAGGED":
                continue
            for flag in item.get("flags", []):
                rule_code = flag.get("rule_code", "UNKNOWN")
                amt = flag.get("amount", 0.0)

                if rule_code == "GL-001":
                    detected_value = (
                        f"Dr: {format_currency(flag.get('debit', 0.0))} / "
                        f"Cr: {format_currency(flag.get('credit', 0.0))}"
                    )
                elif rule_code == "AST-002":
                    detected_value = (
                        f"Book Value: {format_currency(flag.get('book_value', 0.0))} "
                        f"> Cost: {format_currency(flag.get('cost', 0.0))}"
                    )
                elif amt and amt > 0:
                    detected_value = format_currency(amt)
                else:
                    detected_value = "N/A"

                by_domain[domain].append({
                    "row_index": item.get("row_index"),
                    "rule_code": rule_code,
                    "severity": flag.get("severity", "HIGH"),
                    "description": flag.get("description", ""),
                    "detected_value": detected_value,
                    "remediation": flag.get("remediation", "Review supporting documentation."),
                })
    return summary_stats, by_domain

def _render_section_1(summary_stats: list) -> str:
    total_files = len(summary_stats)
    total_rows = sum(s["rows"] for s in summary_stats)
    total_anomalies = sum(s["flagged_anomalies"] for s in summary_stats)

    lines = [
        "## 1. Executive Summary & Verified Exposure",
        "",
        f"- **Exact Files Processed:** {total_files}",
        f"- **Exact Combined Row Count Across All Files:** {total_rows}",
        f"- **Exact Total Flagged Anomalies:** {total_anomalies}",
        "",
        "| Domain | Exact Rows | Exact Flagged Anomalies |",
        "|--------|------------|--------------------------|"
    ]
    for s in summary_stats:
        display = DOMAIN_DISPLAY_NAMES.get(s["domain"], s["domain"])
        lines.append(f"| {display} | {s['rows']} | {s['flagged_anomalies']} |")
    lines.append("")
    return "\n".join(lines)

def _escape_md(text: str) -> str:
    return str(text).replace("|", "\\|")

def _render_section_2_domain(domain: str, findings: list) -> str:
    display_name = DOMAIN_DISPLAY_NAMES.get(domain, domain)
    if not findings:
        return f"### {display_name}\n\n_No flagged anomalies in this domain._\n"
    lines = [
        f"### {display_name}",
        "",
        "| Row | Rule | Severity | Finding | Detected Value | Remediation |",
        "|-----|------|----------|---------|-----------------|-------------|"
    ]
    for f in findings:
        lines.append(
            f"| {f['row_index']} | {f['rule_code']} | {f['severity']} "
            f"| {_escape_md(f['description'])} | {_escape_md(f['detected_value'])} "
            f"| {_escape_md(f['remediation'])} |"
        )
    lines.append("")
    return "\n".join(lines)

def _render_section_2(by_domain: dict) -> str:
    parts = ["## 2. Multi-Domain Anomaly Register", ""]
    for domain in DOMAIN_DISPLAY_NAMES:
        if domain in by_domain:
            parts.append(_render_section_2_domain(domain, by_domain[domain]))
    for domain, findings in by_domain.items():
        if domain not in DOMAIN_DISPLAY_NAMES:
            parts.append(_render_section_2_domain(domain, findings))
    return "\n".join(parts)

def _render_section_3(client, by_domain: dict, max_retries: int = 2) -> tuple:
    domains_present = [DOMAIN_DISPLAY_NAMES.get(d, d) for d in by_domain if by_domain[d]]
    if not domains_present:
        return "## 3. Recommended Substantive Audit Procedures\n\n_No flagged anomalies requiring follow-up._\n", []

    prompt = f"""Write "## 3. Recommended Substantive Audit Procedures" as a numbered action plan for a forensic audit dossier.
Cover only these domains, which had flagged anomalies: {', '.join(domains_present)}.
Strict rules:
- Do NOT mention any currency amount or numeric threshold anywhere.
- Do NOT reference any rule code (e.g. "TXN-001") - discuss domains and general control weaknesses only, not specific rule identifiers.
- Do NOT invent new categories of risk beyond what a normal audit review of these domains would cover.
- Keep it concise: 1-2 sentences per domain."""

    warnings = []
    text = ""
    attempt = 0
    while attempt <= max_retries:
        text = _call_with_emergency_fallback(
            client, [{"role": "user", "content": prompt}], model=CHECKER_MODEL, temperature=0.1
        )
        issues = _check_hallucinations(text)
        if not issues:
            return text, []
        attempt += 1

    issues = _check_hallucinations(text)
    if issues:
        warnings.append(f"Section 3 integrity check failed after retries: {issues}")
    return text, warnings

def generate_consolidated_master_report(all_domain_data: dict, max_retries: int = 1):
    client = get_groq_client()
    summary_stats, by_domain = _build_domain_payload(all_domain_data)

    section_1 = _render_section_1(summary_stats)
    section_2 = _render_section_2(by_domain)
    section_3, warnings_3 = _render_section_3(client, by_domain, max_retries)

    report_text = (
        "# FORENSIC AUDIT EXECUTIVE DOSSIER\n\n"
        + section_1 + "\n---\n\n"
        + section_2 + "\n---\n\n"
        + section_3
    )
    return report_text, warnings_3

def generate_executive_memo(domain_name: str, findings: list):
    client = get_groq_client()
    prompt = f"Provide a executive summary for domain '{domain_name}' with findings: {json.dumps(findings)}"
    return _call_with_emergency_fallback(
        client, [{"role": "user", "content": prompt}], model=DRAFTER_MODEL, temperature=0.2
    )

def generate_5c_finding_memo(record_data: dict, domain_name: str, max_retries: int = 2):
    client = get_groq_client()
    prompt = f"""Generate a 5C audit note for row #{record_data['row_index']} in {domain_name}. Data: {json.dumps(record_data)}
Strict rules:
- Do NOT mention any currency amount or numeric threshold anywhere. (Rely on the UI data table to present the numbers).
- Do NOT invent or reference any rule code that is not explicitly provided in the Data context."""
    
    attempt = 0
    while attempt <= max_retries:
        text = _call_with_emergency_fallback(
            client, [{"role": "user", "content": prompt}], model=DRAFTER_MODEL, temperature=0.2
        )
        issues = _check_hallucinations(text)
        if not issues:
            return text
        attempt += 1
        
    return text + "\n\n*(Note: Sentry system could not fully verify strict numeric/code omission for this memo.)*"
