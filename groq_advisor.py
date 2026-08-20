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
    Scans report text for monetary values and identifies formatting failures
    without regex backtracking bugs or false-positive truncation matches.
    """
    pattern = r'₹\d{1,3}(?:,\d{3})*(\.\d+)?'
    bad = []
    for m in re.finditer(pattern, report_text):
        decimal_part = m.group(1)
        # must exist and be exactly ".XX" (dot + 2 digits)
        if decimal_part is None or len(decimal_part) != 3:
            bad.append(m.group(0))
    return list(set(bad))


def generate_consolidated_master_report(all_domain_data: dict):
    """
    Synthesizes the unified Master Report using Groq Llama 3.3.
    Enforces strict decimal formatting rules and sufficient token limits to pass Sentry checks.
    """
    client = get_groq_client()

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
                    threshold = flag.get("threshold")
                    
                    formatted_findings.append({
                        "domain": domain,
                        "row_index": item.get("row_index"),
                        "rule_code": flag.get("rule_code"),
                        "severity": flag.get("severity"),
                        "description": flag.get("description"),
                        "formatted_amount": format_currency(amt) if amt > 0 else "N/A",
                        "formatted_threshold": format_currency(threshold) if threshold else None,
                        "remediation": flag.get("remediation", "Review supporting documentation.")
                    })

    system_prompt = """You are an Executive Forensic Auditor generating an Audit Master Dossier.

CRITICAL SENTRY VERIFICATION CONSTRAINTS:
1. ALL currency figures AND rule thresholds MUST use explicit two-decimal formatting (e.g. write '₹50,000.00', NEVER write '₹50,000' or '₹50000').
2. Every monetary figure in Section 1 (Executive Summary) MUST appear with identical decimal string formatting in Section 2 (Anomaly Register).
3. Do NOT cut off or truncate Markdown tables. Render all table rows completely through completion.
"""

    user_prompt = f"""Generate the Master Forensic Audit Report using this audited data:

Domain Summary:
{json.dumps(summary_stats, indent=2)}

Flagged Anomalies Detail:
{json.dumps(formatted_findings, indent=2)}

Structure your output into 3 Sections:
1. Executive Summary & Verified Exposure (Include combined counts, file metrics table, and exact exposure bullets with 2 decimals).
2. Multi-Domain Anomaly Register (Render Markdown tables categorized by domain: Fixed Assets, General Ledger, Accounts Receivable / Accounts Payable Aging, and Transactions).
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

    # Post-generation verification check using non-backtracking scanner
    unformatted_matches = check_sentry_formatting(report_text)
    sentry_warnings = []
    if unformatted_matches:
        sentry_warnings.append(
            f"Report contains unverified monetary figures lacking standard decimal precision: {unformatted_matches}"
        )

    return report_text, sentry_warnings


def generate_executive_memo(domain_name: str, findings: list):
    """Generates domain-level executive summary memo."""
    client = get_groq_client()
    prompt = f"Provide an executive summary for domain '{domain_name}' with findings: {json.dumps(findings)}"
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
