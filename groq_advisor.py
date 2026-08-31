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
    "TXN-001", "TXN-002", "TXN-003", "TXN-004", "TXN-005", "TXN-006", "TXN-007", "TXN-008",
    "AGE-001", "AGE-002", "AGE-003", "AGE-004",
    "GL-001", "GL-002", "GL-003", "GL-004",
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
    return Groq(api_key=api_keys[0])


def _get_groq_clients():
    return [Groq(api_key=key) for key in _get_groq_api_keys()]

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
    """Rotate configured keys before reserving 120b for an actual model failure."""
    clients = [client] + _get_groq_clients()
    last_error = None
    for candidate in clients:
        try:
            return _call_groq_with_backoff(candidate, messages, model=model, temperature=temperature)
        except Exception as exc:
            last_error = exc
    for candidate in clients:
        try:
            return _call_groq_with_backoff(candidate, messages, model=EMERGENCY_FALLBACK_MODEL, temperature=temperature)
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Groq request failed without an error response.")

def _check_hallucinations(text: str) -> list:
    problems = []
    if re.search(r'(?:₹|\b(?:INR|Rs\.?|USD|EUR)\s*)[\d,]+(?:\.\d+)?', text, re.IGNORECASE):
        problems.append("Text contains a currency figure, which is not allowed.")
    if re.search(r'\b\d+(?:\.\d+)?\s*%', text):
        problems.append("Text contains an unsupported percentage.")
    mentioned_codes = set(re.findall(r'\b[A-Z]{2,4}-\d{3}\b', text))
    invented = mentioned_codes - KNOWN_RULE_CODES
    if invented:
        problems.append(f"Text references unknown rule code(s): {sorted(invented)}")
    unsupported_certainty = re.findall(
        r'\b(?:fraud(?:ulent)?|embezzlement|illegal|guilty|proven|confirmed fraud)\b',
        text,
        re.IGNORECASE,
    )
    if unsupported_certainty:
        problems.append("Text makes an unsupported legal or fraud conclusion.")
    return problems

def _build_domain_payload(all_domain_data: dict):
    summary_stats = []
    by_domain = {}

    for file_name, file_info in all_domain_data.items():
        domain = file_info.get("category", "unknown")
        df = file_info.get("df")
        findings = file_info.get("findings", [])

        flagged_row_count = sum(1 for f in findings if f.get("status") == "FLAGGED")
        finding_count = sum(len(f.get("flags", [])) for f in findings)
        summary_stats.append({
            "file": file_name,
            "domain": domain,
            "rows": len(df) if df is not None else 0,
            "flagged_rows": flagged_row_count,
            "findings": finding_count,
            "audit_as_of_date": file_info.get("audit_as_of_date"),
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
                    "source_file": file_name,
                })

    # One summary row per domain prevents duplicate domain lines and double-counted
    # file fragments while retaining source-file provenance in the register.
    aggregated = {}
    for stat in summary_stats:
        domain = stat["domain"]
        target = aggregated.setdefault(domain, {
            "domain": domain, "rows": 0, "flagged_rows": 0, "findings": 0,
            "audit_as_of_date": stat.get("audit_as_of_date"), "files": [],
        })
        target["rows"] += stat["rows"]
        target["flagged_rows"] += stat["flagged_rows"]
        target["findings"] += stat["findings"]
        target["files"].append(stat["file"])
    return list(aggregated.values()), by_domain

def _render_section_1(summary_stats: list) -> str:
    total_files = len(summary_stats)
    total_rows = sum(s["rows"] for s in summary_stats)
    total_flagged_rows = sum(s["flagged_rows"] for s in summary_stats)
    total_findings = sum(s["findings"] for s in summary_stats)
    audit_dates = sorted({s["audit_as_of_date"] for s in summary_stats if s.get("audit_as_of_date")})
    benchmark = ", ".join(audit_dates) if audit_dates else "Not supplied"

    lines = [
        "## 1. Executive Summary & Verified Exposure",
        "",
        f"- **Exact Files Processed:** {total_files}",
        f"- **Exact Combined Row Count Across All Files:** {total_rows}",
        f"- **Flagged Rows:** {total_flagged_rows}",
        f"- **Individual Rule Findings:** {total_findings}",
        f"- **Audit As-Of / Benchmark Date:** {benchmark}",
        "- **Counting Basis:** A flagged row is counted once; individual findings count every rule triggered on that row.",
        "- **Aging Method:** AGE-001 applies only to open/unpaid invoices more than 90 days past due. AGE-003 counts only open, past-due invoices by counterparty.",
        "- **Depreciation Method:** AST-003 uses the uploaded recognized method, a 365.25-day year, and flags positive book-value variance above 10% of cost after at least one year.",
        "- **Control Coverage:** Transactions include approval, round-number, structuring/split, three-way-match, duplicate-payment, negative-amount, and currency checks. GL includes supported voucher balancing, weekend manual entries, missing references, and period-end manual postings. Aging includes open overdue and chronic paid-late patterns.",
        "- **Zero-Hit Interpretation:** A documented rule absent from the register was evaluated but produced no findings for the uploaded data.",
        "",
        "| Domain | Rows | Flagged Rows | Individual Findings |",
        "|--------|------|--------------|---------------------|"
    ]
    for s in summary_stats:
        display = DOMAIN_DISPLAY_NAMES.get(s["domain"], s["domain"])
        lines.append(f"| {display} | {s['rows']} | {s['flagged_rows']} | {s['findings']} |")
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
        "| Source | Row | Rule | Severity | Finding | Detected Value | Remediation |",
        "|--------|-----|------|----------|---------|----------------|-------------|"
    ]
    for f in findings:
        lines.append(
            f"| {_escape_md(f.get('source_file', ''))} | {f['row_index']} | {f['rule_code']} | {f['severity']} "
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

def _render_section_3(by_domain: dict) -> tuple:
    """Render complete procedures deterministically so exports cannot truncate."""
    procedures = {
        "transactions": "Inspect approval evidence, vendor support, purchase orders, and related disbursements for authorization and possible invoice splitting.",
        "ar_ap_aging": "Confirm open balances directly with counterparties, inspect subsequent receipts or payments, reconcile status fields, and evaluate collection and expected-credit-loss actions.",
        "general_ledger": "Reperform voucher balancing, inspect support and approval for manual or weekend postings, and resolve reused or non-unique journal references.",
        "fixed_assets": "Inspect capitalization support, verify assigned depreciation methods and useful lives, recalculate depreciation through the disclosed audit date, and review additions and disposals for authorization.",
    }
    active_domains = [domain for domain, findings in by_domain.items() if findings]
    if not active_domains:
        return "## 3. Recommended Substantive Audit Procedures\n\n_No flagged anomalies requiring follow-up._\n", []

    lines = ["## 3. Recommended Substantive Audit Procedures", ""]
    for number, domain in enumerate(active_domains, start=1):
        display = DOMAIN_DISPLAY_NAMES.get(domain, domain)
        procedure = procedures.get(domain, "Inspect source records, approvals, reconciliations, and subsequent events supporting the identified exceptions.")
        lines.append(f"{number}. **{display}:** {procedure}")
    lines.extend(["", "## 4. Report Completion Statement", "", "This dossier includes every uploaded domain, all deterministic rule findings, the counting basis, and the benchmark methodology used for this run."])
    return "\n".join(lines), []

def generate_consolidated_master_report(all_domain_data: dict, max_retries: int = 1):
    summary_stats, by_domain = _build_domain_payload(all_domain_data)

    section_1 = _render_section_1(summary_stats)
    section_2 = _render_section_2(by_domain)
    section_3, warnings_3 = _render_section_3(by_domain)

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
