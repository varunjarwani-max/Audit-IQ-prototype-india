def _unpack_nested_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unpacks rules_engine.py flags while preserving entity context (vendors, assets, counterparties)."""
    flat_list = []
    for rec in findings:
        if not isinstance(rec, dict):
            continue

        row_idx = rec.get("row_index")
        record_id = rec.get("record_id")
        flags = rec.get("flags", [])
        
        # Extract entity metadata if present
        entity = (
            rec.get("vendor") or 
            rec.get("customer_vendor") or 
            rec.get("asset_name") or 
            rec.get("account_name") or 
            "N/A"
        )
        approver = rec.get("approved_by") or rec.get("prepared_by") or "N/A"

        if isinstance(flags, list) and len(flags) > 0:
            for flag in flags:
                if isinstance(flag, dict):
                    flat_list.append({
                        "row": row_idx,
                        "record_id": record_id,
                        "entity": entity,
                        "approver": approver,
                        "rule": flag.get("rule_code") or flag.get("rule_name") or "ANOMALY",
                        "severity": flag.get("severity", "MEDIUM"),
                        "finding": flag.get("description") or flag.get("detected_value") or "Flagged anomaly detected.",
                        "detected_value": flag.get("detected_value", ""),
                        "remediation": flag.get("remediation", "")
                    })
        elif str(rec.get("status")).upper() == "FLAGGED":
            flat_list.append({
                "row": row_idx,
                "record_id": record_id,
                "entity": entity,
                "approver": approver,
                "rule": rec.get("rule_code") or rec.get("rule") or "ANOMALY",
                "finding": str(rec.get("description") or rec.get("finding") or "Flagged anomaly")[:200]
            })
    return flat_list


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
        unpacked = _unpack_nested_findings(data.get("findings", []))[:10]
        tokenized_subset = _tokenize_currency(unpacked, token_registry, value_to_token)
        tokenized_domain_findings.append((filename, tokenized_subset))

    known_currency_values = set(token_registry.values())
    token_glossary = "\n".join(f"{tok} = {val}" for tok, val in token_registry.items())

    prompt = f"""
Synthesize this cross-domain audit telemetry into a complete Master Executive Dossier.

STRICT NUMERIC CONSTRAINTS:
- Exact Files Processed: {total_files}
- Combined Row Count: {exact_total_rows}
- Total Flagged Anomalies: {exact_flagged_count}
- Domain Breakdown Data: {json.dumps(domain_breakdown)}

GROUND-TRUTH RUPEE TOKEN GLOSSARY:
{token_glossary if token_glossary else "(no rupee figures)"}

ITEMIZED DOMAIN FINDINGS TELEMETRY:
"""
    for filename, tokenized_subset in tokenized_domain_findings:
        prompt += f"\nFile: {filename}\n{json.dumps(tokenized_subset, default=str)}\n"

    prompt += f"""
CRITICAL INSTRUCTIONS:
1. You MUST use exact token codes (e.g. [[GT_1]], [[GT_2]]) in the Key Finding section instead of raw rupee amounts.
2. Ensure every section, including Section 3, is fully written out and NOT cut off.
3. Use standard ASCII hyphens (-) for rule codes (e.g., TXN-004, GL-001).

STRUCTURE REQUIREMENT:
# FORENSIC AUDIT EXECUTIVE DOSSIER

## 1. Executive Summary & Verified Exposure
- **Exact Files Processed:** {total_files}
- **Exact Combined Row Count Across All Files:** {exact_total_rows}
- **Exact Total Flagged Anomalies:** {exact_flagged_count}

## 2. Multi-Domain Anomaly Register
(Detail key findings including rule code, severity, [[GT_n]] token, entity name, and remediation.)

## 3. Recommended Substantive Audit Procedures
(Provide 3-5 complete, actionable audit recommendations.)
"""

    messages = [
        {"role": "system", "content": "You are a CA Forensic Auditor drafting a complete executive dossier. Never leave responses truncated."},
        {"role": "user", "content": prompt}
    ]

    try:
        # Raised max_tokens to 2500 to prevent response truncation
        raw_report = _call_groq_with_retry(messages, max_tokens=2500, temperature=0.0)
    except Exception as err:
        return f"# Error Generating Dossier\n\nFailed to connect to LLM provider: {str(err)}", [str(err)]

    # Clean non-breaking hyphens and replace tokens with ground-truth values
    sanitized_report = raw_report.replace('\u2011', '-')
    final_report = GT_TOKEN_PATTERN.sub(lambda m: token_registry.get(m.group(0), m.group(0)), sanitized_report)
    
    sentry_warnings = _verify_no_unverified_currency(final_report, known_currency_values)

    return final_report, sentry_warnings
