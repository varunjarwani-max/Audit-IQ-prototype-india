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


def check_sentry_integrity(report_text: str, formatted_findings: list) -> list:
    """
    Single unified Sentry pass. Extracts every currency figure in report_text
    and checks, for each one:
      (a) it is formatted with exactly two decimal places, and
      (b) its numeric value matches a real amount that was actually sent
          to the model in formatted_findings.

    Comparing by numeric value (not string) means formatting drift can't
    hide a hallucinated figure, and a genuinely correct figure that's
    merely mis-formatted can't be falsely flagged as fabricated.

    Returns a list of {"figure": str, "issue": str} problem dicts.
    Empty list means the report is clean.
    """
    valid_values = set()
    for f in formatted_findings:
        for key in ("formatted_amount", "formatted_debit", "formatted_credit",
                    "formatted_book_value", "formatted_cost"):
            v = f.get(key)
            if v and v != "N/A":
                try:
                    valid_values.add(round(float(v.replace("₹", "").replace(",", "")), 2))
                except ValueError:
                    continue

    pattern = r'₹\d{1,3}(?:,\d{3})*(?:\.\d+)?'
    problems = []

    for m in re.finditer(pattern, report_text):
        raw = m.group(0)
        numeric_str = raw.replace("₹", "").replace(",", "")

        try:
            val = round(float(numeric_str), 2)
        except ValueError:
            problems.append({"figure": raw, "issue": "unparseable"})
            continue

        has_two_decimals = "." in raw and len(raw.split(".")[-1]) == 2
        is_grounded = val in valid_values

        if not has_two_decimals:
            problems.append({"figure": raw, "issue": "missing_decimals"})
        if not is_grounded:
            problems.append({"figure": raw, "issue": "not_in_source_data"})

    return problems


def generate_consolidated_master_report(all_domain_data: dict, max_retries: int = 1):
    """
    Synthesizes the unified Master Report using Groq Llama 3.3.
    Enforces strict decimal formatting and source-grounding rules via the
    unified Sentry integrity check. If the check fails, retries generation
    up to max_retries times before returning the last attempt with warnings
    attached (so app.py can decide whether to block/redact it).
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
3. NEVER invent, estimate, or state a rule threshold, limit, or benchmark figure (e.g. a vendor billing cap) unless that exact number appears verbatim in the supplied JSON data below. If a rule's description contains no numeric threshold, do not add one — describe the finding qualitatively instead (e.g. "exceeds the applicable vendor billing threshold" with no number).
4. Do NOT include any internal metadata columns (e.g. debug tokens, ground-truth tokens, QA fields, "GT Token") in the output tables — only the columns explicitly requested in the structure below.
5. Do NOT cut off or truncate Markdown tables. Render all table rows completely through completion.
6. Every currency figure you write MUST be copied character-for-character from a "formatted_amount", "formatted_debit", "formatted_credit", "formatted_book_value", or "formatted_cost" value in the JSON below. Do not compute, round, or restate a number from memory.
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

    report_text = None
    finish_reason = None
    sentry_warnings = []
    integrity_issues = []

    attempt = 0
    while attempt <= max_retries:
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

        integrity_issues = check_sentry_integrity(report_text, formatted_findings)
        if integrity_issues:
            sentry_warnings.append(f"Sentry integrity check failed: {integrity_issues}")

        # Clean pass: stop retrying
        if not integrity_issues and finish_reason != "length":
            break

        attempt += 1

    return report_text, sentry_warnings
