"""
Groq LLM Client & 5C Audit Workpaper Generator for AuditIQ.

Architecture Note (Privacy & Deployment):
- The core detection engine runs 100% locally and deterministically on-premise without external network calls.
- This advisor module provides LLM-assisted drafting of formal 5C Internal Audit Workpapers.
- Fixed to use openai/gpt-oss-20b with internal fallback to llama-3.1-8b-instant.
- Includes automated key rotation across 5 predefined keys to survive rate limits.
"""

import json
import time
import random
import streamlit as st
from typing import Dict, List, Any

try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False
    import urllib.request
    import urllib.error


def _get_groq_api_keys() -> List[str]:
    """Safely retrieves API keys from st.secrets at runtime to prevent top-level import crashes."""
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
    temperature: float = 0.2,
    max_backoff_rounds: int = 3,
    allow_fallback: bool = True
) -> str:
    """
    Executes a chat completion call with automatic key rotation and exponential backoff.
    Tries the next key immediately on 429 rate limit. If all 5 keys fail, it backs off 
    exponentially before retrying the pool. Falls back to 8B model if 20B fails completely.
    """
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
                
                if "429" in err_str or "rate limit" in err_str or "tpm" in err_str or "rpm" in err_str:
                    continue
                elif "timeout" in err_str or "connection" in err_str:
                    continue
                else:
                    continue

        if round_num < max_backoff_rounds - 1:
            sleep_time = (2 ** (round_num + 1)) + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)

    if allow_fallback and model == "openai/gpt-oss-20b":
        return _call_groq_with_retry(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=max_tokens,
            temperature=temperature,
            max_backoff_rounds=1,
            allow_fallback=False
        )

    raise RuntimeError(f"Groq generation failed with model '{model}' after exhausting all keys: {str(last_exception)}")


def generate_executive_memo(
    category: str,
    findings: List[Dict[str, Any]],
    batch_df_records: List[Dict[str, Any]],
    confidence: float
) -> str:
    """Generates a formal 5C Internal Audit Workpaper Memo across the batch findings."""
    flagged_records = [f for f in findings if f.get("status") == "FLAGGED"]

    concise_findings = []
    for f in findings[:10]:
        concise_findings.append({
            "row_index": f.get("row_index"),
            "status": f.get("status"),
            "risk_score": f.get("risk_score"),
            "flags": [
                {
                    "rule_code": flg.get("rule_code"),
                    "rule_name": flg.get("rule_name"),
                    "severity": flg.get("severity"),
                    "detected_value": flg.get("detected_value")
                }
                for flg in f.get("flags", [])
            ]
        })

    prompt = f"""
You are an expert Senior Forensic Internal Auditor and Chartered Accountant.
Evaluate this financial audit batch and draft a formal 5C Audit Workpaper Memo.

METADATA:
- Category: {category} (Signature Confidence: {confidence}%)
- Batch Evaluated: {len(findings)} records | Flagged Anomalies: {len(flagged_records)}

DETERMINISTIC FINDINGS SUMMARY:
{json.dumps(concise_findings, indent=2)}

SAMPLE DATA ROWS:
{json.dumps(batch_df_records[:5], indent=2)}

FORMAT INSTRUCTIONS:
Structure your response strictly following the 5C Internal Audit Framework:

# FORENSIC AUDIT WORKPAPER MEMO
**Engagement:** Internal Control & Data Segregation Review
**Audit Scope:** {category.upper()} Ledger Slice
**AI Draft Engine:** openai/gpt-oss-20b (Deterministic Rule-Grounded)

## 1. CONDITION (What Was Found)
State the exact factual deviations detected (cite Row #, amounts in INR with ₹ formatting, vendor/account names, and triggered rule codes).

## 2. CRITERIA (Governing Standards)
State the applicable internal authorization thresholds (e.g. ₹50,000 dual-signoff limit), ICAI accounting standards, or SOX-404 segregation of duties requirements.

## 3. CAUSE (Root Failure Mode)
Explain the operational breakdown (e.g. circumvented approval workflow, lack of maker-checker controls, ERP timestamp override, or split purchase orders).

## 4. CONSEQUENCE (Financial & Compliance Risk)
Detail the exposure (potential fraudulent diversion, structuring penalty, unrecorded liability, or statutory audit qualification).

## 5. CORRECTIVE ACTION & REMEDIATION
Provide actionable, itemized recommendations for management and workpaper sign-off steps for the Lead Engagement Partner.
"""

    messages = [
        {"role": "system", "content": "You are a licensed Chartered Accountant and Forensic Auditor. Write strictly in objective, evidence-based professional audit terminology."},
        {"role": "user", "content": prompt}
    ]

    return _call_groq_with_retry(messages, max_tokens=1500, temperature=0.15)


def generate_5c_finding_memo(
    record: Dict[str, Any],
    category: str
) -> str:
    """Generates a dedicated, single-record 5C workpaper memo for an individual flagged transaction."""
    prompt = f"""
Draft a concise 5C Workpaper Note for this individual flagged record in the {category} module:

RECORD DATA:
{json.dumps(record, indent=2)}

STRUCTURE:
- **Condition:** Exact factual violation detected.
- **Criteria:** Governing internal control or accounting rule.
- **Cause:** Process failure or control gap.
- **Consequence:** Quantified exposure in ₹ INR.
- **Corrective Action:** Immediate action required prior to audit clearance.
"""

    messages = [
        {"role": "system", "content": "You are a CA Forensic Auditor drafting a precise 5C workpaper note."},
        {"role": "user", "content": prompt}
    ]

    return _call_groq_with_retry(messages, max_tokens=600, temperature=0.1)


def generate_consolidated_master_report(
    all_domain_data: Dict[str, Any]
) -> str:
    """Synthesizes findings across multiple datasets into a single partner-level executive dossier."""
    master_summary = []
    
    for filename, data in all_domain_data.items():
        flagged_items = [f for f in data.get("findings", []) if f.get("status") == "FLAGGED"]
        
        domain_block = {
            "file": filename,
            "domain": data.get("category", "Unknown"),
            "total_rows_evaluated": len(data.get("df", [])),
            "flagged_count": len(flagged_items),
            "critical_flags": []
        }
        
        for item in flagged_items[:10]:
            domain_block["critical_flags"].append({
                "row": item.get("row_index"),
                "flags": item.get("flags")
            })
            
        master_summary.append(domain_block)
        
    prompt = f"""
You are an elite Senior Audit Partner at a Big 4 accounting firm.
Review the following cross-domain anomaly telemetry extracted by the AuditIQ deterministic engine.

DATA INGESTED:
{json.dumps(master_summary, indent=2)}

Draft a formal, partner-level 'Executive Roll-Up Memo'.
Structure the response exactly as follows:
1. Executive Summary & Exposure Overview
2. Multi-Domain Anomaly Register (Summarize the worst findings across domains)
3. Control Environment Assessment
4. Recommended Substantive Audit Procedures

Maintain a strictly professional, objective, and authoritative forensic accounting tone.
"""

    messages = [
        {"role": "system", "content": "You are a licensed Chartered Accountant and Forensic Auditor."},
        {"role": "user", "content": prompt}
    ]

    return _call_groq_with_retry(messages, max_tokens=2000, temperature=0.2)
