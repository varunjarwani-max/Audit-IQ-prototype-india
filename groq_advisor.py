"""
Groq LLM Client & Ground-Truth Verified Workpaper Generator for AuditIQ.
Architecture: 
- Arithmetic is strictly pre-calculated in Python (pandas).
- LLM is constrained to narrate around injected ground-truth numbers.
- Post-generation Sentry regex verifies the LLM did not hallucinate metrics.
"""

import json
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


def _get_groq_api_keys() -> List[str]:
    """Safely retrieves API keys from st.secrets at runtime."""
    keys = []
    for i in range(1, 6):
        try:
            key = st.secrets.get(f"GROQ_API_KEY_{i}", f"GROQ_API_KEY_{i}_PLACEHOLDER")
        except Exception:
            key = f"GROQ_API_KEY_{i}_PLACEHOLDER"
        keys.append(key)
    return keys


def _call_groq_with_retry(
    messages: List[Dict[str, str]],
    model: str = "openai/gpt-oss-20b",
    max_tokens: int = 1500,
    temperature: float = 0.0,  # Set to 0.0 for strict deterministic adherence
    max_backoff_rounds: int = 3,
    allow_fallback: bool = True
) -> str:
    """Executes completion with key rotation, backoff, and model fallback."""
    api_keys = _get_groq_api_keys()
    last_exception = None

    for round_num in range(max_backoff_rounds):
        for api_key in api_keys:
            cleaned_key = api_key.strip()
            if not cleaned_key or cleaned_key.endswith("_PLACEHOLDER"):
                continue

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
                err_str = str(e).lower()
                last_exception = e
                if "429" in err_str or "rate limit" in err_str:
                    continue
                continue

        if round_num < max_backoff_rounds - 1:
            time.sleep((2 ** (round_num + 1)) + random.uniform(0.5, 1.5))

    if allow_fallback and model == "openai/gpt-oss-20b":
        return _call_groq_with_retry(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=max_tokens,
            temperature=temperature,
            max_backoff_rounds=1,
            allow_fallback=False
        )

    raise RuntimeError(f"Groq generation failed with model '{model}': {str(last_exception)}")


def _verify_report_numerics(report_text: str, ground_truths: Dict[str, Any]) -> List[str]:
    """
    Sentry Guardrail: Deterministically scans LLM report text to detect 
    hallucinated row counts or wrong mathematical calculations.
    """
    warnings = []
    
    # 1. Verify Total Row Count
    actual_rows = ground_truths.get("total_rows")
    if actual_rows is not None:
        matches = re.findall(r'(\d[\d,]*)\s*(?:total\s*)?rows', report_text, re.IGNORECASE)
        for match in matches:
            claimed_rows = int(match.replace(',', ''))
            if claimed_rows != actual_rows:
                warnings.append(f"Sentry Alert: LLM claimed {claimed_rows:,} total rows, but verified data contains exact {actual_rows:,} rows.")

    # 2. Verify Exact JV Imbalances
    for jv_code, expected_diff in ground_truths.get("jv_imbalances", {}).items():
        if jv_code in report_text:
            numbers_found = re.findall(r'₹?\s*([\d,]+\.?\d*)', report_text)
            parsed_nums = []
            for n in numbers_found:
                clean_n = n.replace(',', '')
                if clean_n.replace('.', '', 1).isdigit():
                    parsed_nums.append(float(clean_n))
            
            # Check if expected difference exists in the parsed numbers
            if expected_diff not in parsed_nums and len(parsed_nums) > 0:
                warnings.append(f"Sentry Alert: JV imbalance for {jv_code} computed in Python as ₹{expected_diff:,.2f}, but narrative cites divergent figures.")

    return warnings


def generate_consolidated_master_report(all_domain_data: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Synthesizes findings across multiple datasets, returning the memo and any Sentry warnings."""
    # --- 1. Python Deterministic Pre-Calculation Layer ---
    total_files = len(all_domain_data)
    exact_total_rows = 0
    exact_flagged_count = 0
    domain_breakdown = []
    jv_imbalances = {}

    for filename, data in all_domain_data.items():
        df = data.get("df")
        rows = len(df) if df is not None else 0
        exact_total_rows += rows
        
        findings = data.get("findings", [])
        flagged = [f for f in findings if f.get("status") == "FLAGGED"]
        exact_flagged_count += len(flagged)

        # Calculate exact GL debit/credit differences in Python
        if data.get("category") == "general_ledger" and df is not None:
            if "voucher_no" in df.columns and "debit" in df.columns and "credit" in df.columns:
                grouped = df.groupby("voucher_no")[["debit", "credit"]].sum()
                grouped["diff"] = (grouped["debit"] - grouped["credit"]).abs()
                imbalanced = grouped[grouped["diff"] > 0.01]
                for v_id, row in imbalanced.iterrows():
                    jv_imbalances[str(v_id)] = round(float(row["diff"]), 2)

        domain_breakdown.append({
            "filename": filename,
            "domain": data.get("category", "Unknown"),
            "exact_rows": rows,
            "exact_flagged_anomalies": len(flagged)
        })

    ground_truths = {
        "total_rows": exact_total_rows,
        "total_flagged": exact_flagged_count,
        "total_files": total_files,
        "jv_imbalances": jv_imbalances
    }

    # --- 2. Injection & Generation Layer ---
    prompt = f"""
You are an elite Senior Forensic Audit Partner. Synthesize this cross-domain audit telemetry into a Master Executive Dossier.

STRICT NUMERIC CONSTRAINTS (Calculated by Python Engine - DO NOT ALTER OR RECALCULATE):
- Exact Files Processed: {total_files}
- Exact Combined Row Count Across All Files: {exact_total_rows}
- Exact Total Flagged Anomalies: {exact_flagged_count}
- Domain Breakdown Data: {json.dumps(domain_breakdown)}
- Verified Voucher Imbalances (Exact Debit/Credit Differences): {json.dumps(jv_imbalances)}

RULE: You MUST state the exact total row count ({exact_total_rows}) and precise calculated imbalances above. Do NOT compute, estimate, or modify any math figures yourself.

DOMAIN FINDINGS SUMMARY (Top 10 flags per domain):
"""
    # Append limited summaries to prevent token explosion
    for filename, data in all_domain_data.items():
        flagged_subset = [f for f in data.get("findings", []) if f.get("status") == "FLAGGED"][:10]
        prompt += f"\nFile: {filename}\n{json.dumps(flagged_subset, default=str)}\n"

    prompt += """
STRUCTURE:
# FORENSIC AUDIT EXECUTIVE DOSSIER
## 1. Executive Summary & Verified Exposure
(Explicitly state the exact total rows and flags provided in the constraints).
## 2. Multi-Domain Anomaly Register
(Detail key findings using the exact computed numbers).
## 3. Recommended Substantive Audit Procedures
"""

    messages = [
        {"role": "system", "content": "You are a Forensic Auditor. You never perform arithmetic; you strictly cite pre-calculated Python metrics provided to you."},
        {"role": "user", "content": prompt}
    ]

    raw_report = _call_groq_with_retry(messages, max_tokens=2000, temperature=0.0)
    
    # --- 3. Post-Generation Sentry Verification Layer ---
    sentry_warnings = _verify_report_numerics(raw_report, ground_truths)

    return raw_report, sentry_warnings


def generate_executive_memo(category: str, findings: List[Dict[str, Any]], batch_df_records: List[Dict[str, Any]], confidence: float) -> str:
    """Generates a formal 5C Internal Audit Workpaper Memo for a batch."""
    flagged_records = [f for f in findings if f.get("status") == "FLAGGED"]
    
    prompt = f"""
Draft a formal 5C Audit Workpaper Memo.
Batch Evaluated: {len(findings)} records | Flagged Anomalies: {len(flagged_records)}
"""
    messages = [{"role": "system", "content": "You are a CA Forensic Auditor."}, {"role": "user", "content": prompt}]
    return _call_groq_with_retry(messages, max_tokens=1500, temperature=0.1)


def generate_5c_finding_memo(record: Dict[str, Any], category: str) -> str:
    """Generates a dedicated 5C workpaper memo for a single flagged record."""
    prompt = f"Draft a concise 5C Workpaper Note for this individual record in {category}:\n{json.dumps(record, indent=2)}"
    messages = [{"role": "system", "content": "You are a CA Forensic Auditor."}, {"role": "user", "content": prompt}]
    return _call_groq_with_retry(messages, max_tokens=600, temperature=0.0)
