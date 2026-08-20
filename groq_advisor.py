"""
groq_advisor.py - AI Report & Memo Synthesis for AuditIQ
"""

import os
import re
import json
from groq import Groq


def get_groq_client():
    """Initializes and returns the Groq API client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing.")
    return Groq(api_key=api_key)


def format_currency(val: float) -> str:
    """Guarantees strict two-decimal currency formatting required for Sentry verification."""
    return f"₹{float(val):,.2f}"


def check_sentry_formatting(report_text: str) -> list:
    """
    Detects currency figures in report_text that are NOT formatted with
    exactly two decimal places. Backtracking-safe: captures the decimal
    group explicitly instead of using a lookahead, so a well-formatted
    number like ₹1,613,300.00 can never be partially matched.
    """
    pattern = r'₹\d{1,3}(?:,\d{3})*(\.\d+)?'
    bad = []
    for m in re.finditer(pattern, report_text):
        decimal_part = m.group(1)
        if decimal_part is None or len(decimal_part) != 3:  # must be ".XX"
            bad.append(m.group(0))
    return bad


def check_sentry_grounding(report_text: str, formatted_findings: list) -> list:
    """
    Detects currency figures in report_text that do NOT correspond to any
    real amount sent to the model. Catches fabricated/hallucinated figures
    even when they are perfectly formatted (e.g. an invented ₹50,000
    threshold that never appeared in the source data).
    """
    # Every legitimate amount the model was actually given
    valid_amounts = set()
    for f in formatted_findings:
        amt_str = f.get("formatted_amount")
        if amt_str and amt_str != "N/A":
            valid_amounts.add(amt_str)
        # also allow debit/credit/book_value/cost variants if present
        for key in ("formatted_debit", "formatted_credit",
                    "formatted_book_value", "formatted_cost"):
            v = f.get(key)
            if v:
                valid_amounts.add(v)

    pattern = r'₹\d{1,3}(?:,\d{3})*\.\d{2}'
    found_in_report = set(re.findall(pattern, report_text))

    ungrounded = sorted(found_in_report - valid_amounts)
    return ungrounded


def generate_consolidated_master_report(all_domain_data: dict):
    """
    Synthesizes the unified Master Report using Groq Llama 3.3.
    Enforces strict decimal formatting rules and sufficient token limits to pass Sentry checks.
    """
    client = get_groq_client()

    # Pre-process findings to guarantee exact numeric matching
    summary_stats = []
    formatted_findings = []

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

        for item in findings:
            if item.get("status") == "FLAGGED":
                for flag in item.get("flags", []):
                    amt = flag.get("amount", 0.0)
                    entry = {
                        "domain": domain,
                        "row_index": item.get("row_index"),
                        "rule_code": flag.get("rule_code"),
                        "severity": flag.get("severity"),
                        "description": flag.get("description"),
                        "formatted_amount": format_currency(amt) if amt > 0 else "N/A",
                        "remediation": flag.get("remediation", "Review supporting documentation.")
                    }
                    # Carry through any additional pre-formatted figures
                    # (debit/credit/book_value/cost) so the grounding
                    # check recognizes them as valid too.
                    for src_key, dst_key in [
                        ("debit", "formatted_debit"),
                        ("credit", "formatted_credit"),
                        ("book_value", "formatted_book_value"),
                        ("cost", "formatted_cost"),
                    ]:
                        if src_key in flag:
                            entry[dst_key] = format_currency(flag[src_key])
                    formatted_findings.append(entry)

    system_prompt = """You are an Executive Forensic Auditor generating an Audit Master Dossier.

CRITICAL SENTRY VERIFICATION CONSTRAINTS:
1. ALWAYS format every single currency figure with explicit two-decimal places (e.g. '₹60,000.00', NEVER write '₹60,000' or '₹60000').
2. Every monetary figure in Section 1 (Executive Summary) MUST appear with identical decimal string formatting in Section 2 (Anomaly Register).
3. NEVER invent, estimate, or state a rule threshold, limit, or benchmark figure unless it appears verbatim in the supplied JSON data below. If a rule's description does not include a numeric threshold, do not add one.
4. Do NOT include any internal metadata columns (e.g. debug tokens, ground-truth tokens, QA fields) in the output tables — only the columns explicitly requested in the structure below.
5. Do NOT cut off or truncate Markdown tables. Render all table rows completely through completion.
"""

    user_prompt = f"""Generate the Master Forensic Audit Report using this audited data:

Domain Summary:
{json.dumps(summary_stats, indent=2)}

Flagged Anomalies Detail:
{json.dumps(formatted_findings, indent=2)}

Structure your output into 3 Sections:
1. Executive Summary & Verified Exposure (Include combined counts, file metrics table, and exact exposure bullets with 2 decimals).
2. Multi-Domain Anomaly Register (Render Markdown tables categorized by domain: Fixed Assets, General Ledger, Accounts Receivable / Accounts Payable Aging, and Transactions. Columns: Row, Rule, Severity, Finding, Detected Value, Remediation — no other columns).
3. Recommended Substantive Audit Procedures (Numbered action plan).
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=4096,
        temperature=0.1
    )

    report_text = response.choices[0].message.content
    finish_reason = response.choices[0].finish_reason

    sentry_warnings = []

    if finish_reason == "length":
        sentry_warnings.append(
            "Report generation was truncated by max_tokens before completion. "
            "Increase max_tokens or shorten the input payload."
        )

    unformatted = check_sentry_formatting(report_text)
    if unformatted:
        sentry_warnings.append(
            f"Report contains monetary figures lacking standard decimal precision: {sorted(set(unformatted))}"
        )

    ungrounded = check_sentry_grounding(report_text, formatted_findings)
    if ungrounded:
        sentry_warnings.append(
            f"Report contains monetary figures not present in the verified source data (possible hallucination): {ungrounded}"
        )

    return report_text, sentry_warnings


def generate_executive_memo(domain_name: str, findings: list):
    """Generates domain-level executive summary memo."""
    client = get_groq_client()
    prompt = f"Provide a executive summary for domain '{domain_name}' with findings: {json.dumps(findings)}"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.2
    )
    return response.choices[0].message.content


def generate_5c_finding_memo(record_data: dict, domain_name: str):
    """Generates 5C audit memo (Condition, Criteria, Cause, Effect, Recommendation)."""
    client = get_groq_client()
    prompt = f"Generate a 5C audit note for row #{record_data['row_index']} in {domain_name}. Data: {json.dumps(record_data)}"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.2
    )
    return response.choices[0].message.content
