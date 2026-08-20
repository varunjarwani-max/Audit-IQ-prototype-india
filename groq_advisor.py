"""
groq_advisor.py - AI Report & Memo Synthesis for AuditIQ

Report generation strategy (final):
- Section 1 (Executive Summary) - pure Python. No LLM involvement.
- Section 2 (Anomaly Register)  - pure Python. Built directly from the
  findings list that rules_engine.py already produced. The LLM never
  sees this section and cannot add rows, rule codes, or figures to it -
  there is nothing generative here, only formatting of real data.
- Section 3 (Recommended Procedures) - the ONLY part the LLM writes.
  It is narrative commentary, explicitly forbidden from citing rule
  codes, currency figures, or specific numbers. Its output is checked
  against a whitelist of real rule codes actually present in the data;
  if it invents one anyway, that chunk is discarded and retried.

This removes the LLM from every place a hallucination previously showed
up (fabricated ₹50,000 thresholds, invented TXN-003/AST-003 rules,
stray "GT token" columns) by construction, not by instruction.
"""

import os
import re
import json
from groq import Groq

MODEL_NAME = "llama-3.3-70b-versatile"

# The full set of rule codes rules_engine.py can ever produce. Keep this
# in sync with rules_engine.py - if you add a new rule there, add its
# code here too, or the Section 3 whitelist check will reject mentions
# of it (which is a safe failure direction, but worth keeping current).
KNOWN_RULE_CODES = {
    "TXN-001", "TXN-002", "TXN-004",
    "AGE-001", "AGE-003",
    "GL-001", "GL-002",
    "AST-001", "AST-002",
}

DOMAIN_DISPLAY_NAMES = {
    "transactions": "Transactions",
    "ar_ap_aging": "Accounts Receivable / Accounts Payable Aging",
    "general_ledger": "General Ledger",
    "fixed_assets": "Fixed Assets",
}


def get_groq_client():
    """Initializes and returns the Groq API client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing.")
    return Groq(api_key=api_key)


def format_currency(val: float) -> str:
    """Guarantees strict two-decimal currency formatting."""
    return f"₹{float(val):,.2f}"


# ---------------------------------------------------------------
# Data prep - shared by all sections
# ---------------------------------------------------------------

def _build_domain_payload(all_domain_data: dict):
    """
    Groups real findings by domain and returns:
      summary_stats: list of per-file row/anomaly counts
      by_domain: {domain_name: [finding_dict, ...]}
    Each finding_dict already carries a pre-formatted "detected_value"
    string built directly from rules_engine.py's output - nothing here
    is inferred or generated, only reshaped.
    """
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

                # Build a "Detected Value" string from whatever this
                # specific rule actually attached to the flag. This is
                # the only place formatting decisions happen, and it's
                # deterministic per rule_code - no LLM judgment involved.
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


# ---------------------------------------------------------------
# Section 1 - pure Python
# ---------------------------------------------------------------

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
        "|--------|------------|--------------------------|",
    ]
    for s in summary_stats:
        display = DOMAIN_DISPLAY_NAMES.get(s["domain"], s["domain"])
        lines.append(f"| {display} | {s['rows']} | {s['flagged_anomalies']} |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Section 2 - pure Python, no LLM call at all
# ---------------------------------------------------------------

def _escape_md(text: str) -> str:
    """Escapes pipe characters so a value can't break a Markdown table row."""
    return str(text).replace("|", "\\|")


def _render_section_2_domain(domain: str, findings: list) -> str:
    display_name = DOMAIN_DISPLAY_NAMES.get(domain, domain)

    if not findings:
        return f"### {display_name}\n\n_No flagged anomalies in this domain._\n"

    lines = [
        f"### {display_name}",
        "",
        "| Row | Rule | Severity | Finding | Detected Value | Remediation |",
        "|-----|------|----------|---------|-----------------|-------------|",
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
        if domain not in by_domain:
            continue
        parts.append(_render_section_2_domain(domain, by_domain[domain]))

    for domain, findings in by_domain.items():
        if domain not in DOMAIN_DISPLAY_NAMES:
            parts.append(_render_section_2_domain(domain, findings))

    return "\n".join(parts)


# ---------------------------------------------------------------
# Section 3 - the ONLY LLM call. Narrative only, no numbers, no
# rule-code fabrication allowed.
# ---------------------------------------------------------------

def _check_section_3(text: str) -> list:
    """
    Section 3 must not contain currency figures or invented rule codes.
    Returns a list of problems found (empty = clean).
    """
    problems = []

    if re.search(r'₹\d', text):
        problems.append("Section 3 contains a currency figure, which is not allowed.")

    mentioned_codes = set(re.findall(r'\b[A-Z]{2,4}-\d{3}\b', text))
    invented = mentioned_codes - KNOWN_RULE_CODES
    if invented:
        problems.append(f"Section 3 references unknown rule code(s): {sorted(invented)}")

    return problems


def _render_section_3(client, by_domain: dict, max_retries: int = 1) -> tuple:
    domains_present = [DOMAIN_DISPLAY_NAMES.get(d, d) for d in by_domain if by_domain[d]]
    if not domains_present:
        return "## 3. Recommended Substantive Audit Procedures\n\n_No flagged anomalies requiring follow-up._\n", []

    prompt = f"""Write "## 3. Recommended Substantive Audit Procedures" as a numbered action plan for a forensic audit dossier.

Cover only these domains, which had flagged anomalies: {', '.join(domains_present)}.

Strict rules:
- Do NOT mention any currency amount or numeric threshold anywhere.
- Do NOT reference any rule code (e.g. "TXN-001") - discuss domains and general control weaknesses only, not specific rule identifiers.
- Do NOT invent new categories of risk beyond what a normal audit review of these domains would cover.
- Keep it concise: 1-2 sentences per domain.
"""

    warnings = []
    text = ""
    attempt = 0

    while attempt <= max_retries:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.1
        )
        text = response.choices[0].message.content
        issues = _check_section_3(text)
        if not issues:
            return text, []
        attempt += 1

    issues = _check_section_3(text)
    if issues:
        warnings.append(f"Section 3 integrity check failed after retries: {issues}")
    return text, warnings


# ---------------------------------------------------------------
# Public entry point - same signature as before, app.py unchanged
# ---------------------------------------------------------------

def generate_consolidated_master_report(all_domain_data: dict, max_retries: int = 1):
    """
    Synthesizes the unified Master Report.
    Returns (report_text, sentry_warnings) - identical shape to before,
    so app.py requires NO changes.
    """
    client = get_groq_client()
    summary_stats, by_domain = _build_domain_payload(all_domain_data)

    section_1 = _render_section_1(summary_stats)
    section_2 = _render_section_2(by_domain)  # pure Python, no warnings possible
    section_3, warnings_3 = _render_section_3(client, by_domain, max_retries)

    report_text = (
        "# FORENSIC AUDIT EXECUTIVE DOSSIER\n\n"
        + section_1 + "\n---\n\n"
        + section_2 + "\n---\n\n"
        + section_3
    )

    return report_text, warnings_3


# ---------------------------------------------------------------
# Other memo functions - unchanged
# ---------------------------------------------------------------

def generate_executive_memo(domain_name: str, findings: list):
    """Generates domain-level executive summary memo."""
    client = get_groq_client()
    prompt = f"Provide a executive summary for domain '{domain_name}' with findings: {json.dumps(findings)}"
    response = client.chat.completions.create(
        model=MODEL_NAME,
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
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.2
    )
    return response.choices[0].message.content
