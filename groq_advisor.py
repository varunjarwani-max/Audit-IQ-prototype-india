"""
groq_advisor.py - AI Report & Memo Synthesis for AuditIQ

Report generation strategy (rewritten):
- Section 1 (Executive Summary) is built with plain Python, not the LLM.
  These are counts/sums you already computed - there is no reason to let
  an LLM restate them and risk transcription errors.
- Section 2 (Anomaly Register) is generated ONE DOMAIN AT A TIME. Smaller
  payload in, smaller table out, per call - this is what actually fixes
  truncation, rather than just raising max_tokens and hoping.
- Section 3 (Recommended Procedures) is one short LLM call scoped only to
  the domains actually present.
- Every LLM-generated chunk is passed through check_sentry_integrity and
  retried up to max_retries times before being accepted.
"""

import os
import re
import json
from groq import Groq

MODEL_NAME = "llama-3.3-70b-versatile"


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
# Sentry integrity check (formatting + grounding, unified)
# ---------------------------------------------------------------

def check_sentry_integrity(text: str, formatted_findings: list) -> list:
    """
    Extracts every currency figure in `text` and checks:
      (a) formatted with exactly two decimal places
      (b) numeric value matches a real amount from formatted_findings

    Returns a list of {"figure": str, "issue": str} dicts. Empty = clean.
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
    for m in re.finditer(pattern, text):
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


# ---------------------------------------------------------------
# Data prep - shared by all sections
# ---------------------------------------------------------------

def _build_domain_payload(all_domain_data: dict):
    """
    Groups formatted_findings by domain and returns:
      summary_stats: list of per-file row/anomaly counts
      by_domain: {domain_name: [finding_dict, ...]}
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
                    by_domain[domain].append(entry)

    return summary_stats, by_domain


# ---------------------------------------------------------------
# Section 1 - pure Python, no LLM, cannot hallucinate or truncate
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
        lines.append(f"| {s['domain']} | {s['rows']} | {s['flagged_anomalies']} |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Section 2 - one Groq call per domain
# ---------------------------------------------------------------

DOMAIN_DISPLAY_NAMES = {
    "transactions": "Transactions",
    "ar_ap_aging": "Accounts Receivable / Accounts Payable Aging",
    "general_ledger": "General Ledger",
    "fixed_assets": "Fixed Assets",
}

SECTION_2_SYSTEM_PROMPT = """You are an Executive Forensic Auditor writing one section of an Audit Master Dossier.
You will render a single Markdown table for ONE domain only.

CRITICAL SENTRY VERIFICATION CONSTRAINTS:
1. ALWAYS format every currency figure with exactly two decimal places (e.g. '₹60,000.00'). Never write '₹60,000' or '₹60000'.
2. NEVER invent, estimate, or state a rule threshold, limit, or benchmark figure unless that exact number appears verbatim in the supplied JSON. If a finding's description has no numeric threshold in the JSON, describe it qualitatively with no number attached.
3. Do NOT include any internal metadata columns (debug tokens, ground-truth tokens, QA fields, "GT Token", "[[GT_n]]", etc.) - only the columns requested.
4. Render the table completely. Do not truncate or cut off mid-row.
5. Every currency figure you write MUST be copied character-for-character from a "formatted_amount", "formatted_debit", "formatted_credit", "formatted_book_value", or "formatted_cost" value in the JSON. Never compute or restate a number from memory.
"""


def _render_section_2_domain(client, domain: str, findings: list, max_retries: int) -> tuple:
    """Generates the Markdown table for a single domain. Returns (markdown, warnings)."""
    display_name = DOMAIN_DISPLAY_NAMES.get(domain, domain)

    if not findings:
        return f"### {display_name}\n\n_No flagged anomalies in this domain._\n", []

    user_prompt = f"""Render a Markdown table of flagged anomalies for the "{display_name}" domain only.

Columns required, in order: Row, Rule, Severity, Finding, Detected Value, Remediation.

Data:
{json.dumps(findings, indent=2)}

Output ONLY a "### {display_name}" heading followed by the Markdown table. No other text.
"""

    warnings = []
    text = ""
    finish_reason = None
    attempt = 0

    while attempt <= max_retries:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SECTION_2_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=2048,
            temperature=0.1
        )
        text = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason

        issues = check_sentry_integrity(text, findings)
        if not issues and finish_reason != "length":
            return text, []

        attempt += 1

    # Ran out of retries - return best attempt with warnings attached
    if finish_reason == "length":
        warnings.append(f"[{display_name}] generation truncated by max_tokens.")
    issues = check_sentry_integrity(text, findings)
    if issues:
        warnings.append(f"[{display_name}] Sentry integrity check failed: {issues}")

    return text, warnings


def _render_section_2(client, by_domain: dict, max_retries: int) -> tuple:
    parts = ["## 2. Multi-Domain Anomaly Register", ""]
    all_warnings = []

    for domain in DOMAIN_DISPLAY_NAMES:
        if domain not in by_domain:
            continue
        findings = by_domain[domain]
        table_md, warnings = _render_section_2_domain(client, domain, findings, max_retries)
        parts.append(table_md)
        parts.append("")
        all_warnings.extend(warnings)

    # Any domain present in data but not in our known display-name map
    for domain, findings in by_domain.items():
        if domain not in DOMAIN_DISPLAY_NAMES:
            table_md, warnings = _render_section_2_domain(client, domain, findings, max_retries)
            parts.append(table_md)
            parts.append("")
            all_warnings.extend(warnings)

    return "\n".join(parts), all_warnings


# ---------------------------------------------------------------
# Section 3 - one short LLM call, scoped to domains present
# ---------------------------------------------------------------

def _render_section_3(client, by_domain: dict) -> str:
    domains_present = [DOMAIN_DISPLAY_NAMES.get(d, d) for d in by_domain if by_domain[d]]
    if not domains_present:
        return "## 3. Recommended Substantive Audit Procedures\n\n_No flagged anomalies requiring follow-up._\n"

    prompt = f"""Write "## 3. Recommended Substantive Audit Procedures" as a numbered action plan for a forensic audit dossier.
Cover only these domains, which had flagged anomalies: {', '.join(domains_present)}.
Do not mention specific currency amounts or numeric thresholds - this section is procedural guidance only, not a restatement of figures.
Keep it concise: 1-2 sentences per domain.
"""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.2
    )
    return response.choices[0].message.content


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
    section_2, warnings_2 = _render_section_2(client, by_domain, max_retries)
    section_3 = _render_section_3(client, by_domain)

    report_text = (
        "# FORENSIC AUDIT EXECUTIVE DOSSIER\n\n"
        + section_1 + "\n---\n\n"
        + section_2 + "\n---\n\n"
        + section_3
    )

    return report_text, warnings_2


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
