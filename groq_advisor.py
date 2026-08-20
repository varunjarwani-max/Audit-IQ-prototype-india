"""
groq_advisor.py
Groq LLM Client & 5C Audit Workpaper Generator for AuditIQ.

Architecture Note (Privacy & Deployment):
- The core detection engine runs 100% locally and deterministically on-premise without external network calls.
- This advisor module provides LLM-assisted drafting of formal 5C Internal Audit Workpapers.
- In this environment, it routes to Groq Cloud API for ultra-low latency validation; in air-gapped CA production,
  the endpoint can be seamlessly toggled to an on-premise inference server (e.g. Ollama or vLLM at localhost:11434).
- Includes exponential backoff retry logic to handle free-tier TPM / RPM 429 throttling gracefully.
"""

import json
import time
import random
from typing import Dict, List, Any, Optional

try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False
    import urllib.request
    import urllib.error


SUPPORTED_MODELS = [
    {"id": "openai/gpt-oss-20b", "name": "OpenAI GPT-OSS 20B (16GB On-Premise Target)"},
    {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant (Edge/Local Low-Footprint)"}
]


def _call_groq_with_retry(
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 1500,
    temperature: float = 0.2,
    max_retries: int = 4
) -> str:
    """
    Executes a chat completion call with exponential backoff and jitter to survive HTTP 429 rate-limiting.
    """
    cleaned_key = api_key.strip()
    last_exception = None

    for attempt in range(max_retries):
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
            
            # Check for HTTP 429 / Rate Limit
            is_rate_limit = "429" in err_str or "rate limit" in err_str or "tpm" in err_str or "rpm" in err_str
            
            if is_rate_limit and attempt < max_retries - 1:
                # Exponential backoff with random jitter: 2s, 4s, 8s + jitter
                sleep_time = (2 ** (attempt + 1)) + random.uniform(0.5, 1.5)
                time.sleep(sleep_time)
                continue
            elif attempt < max_retries - 1 and ("timeout" in err_str or "connection" in err_str):
                time.sleep(1.5)
                continue
            else:
                break

    raise RuntimeError(f"Groq generation failed with model '{model}' after {max_retries} attempts: {str(last_exception)}")


def test_groq_key(api_key: str, model: str = "llama-3.1-8b-instant") -> Dict[str, Any]:
    """Tests the Groq API key with a fast ping call."""
    if not api_key or not api_key.strip():
        return {"success": False, "message": "No API key provided."}

    try:
        messages = [
            {"role": "system", "content": "You are a ping test assistant. Respond strictly with 'OK'."},
            {"role": "user", "content": "Ping"}
        ]
        _call_groq_with_retry(api_key, model, messages, max_tokens=10, max_retries=2)
        return {"success": True, "message": f"Connection verified successfully using {model}!"}
    except Exception as e:
        return {"success": False, "message": f"Groq verification failed: {str(e)}"}


def generate_executive_memo(
    api_key: str,
    model: str,
    category: str,
    findings: List[Dict[str, Any]],
    batch_df_records: List[Dict[str, Any]],
    confidence: float
) -> str:
    """
    Generates a formal 5C Internal Audit Workpaper Memo across the batch findings.
    Adheres strictly to the professional 5C Audit Standard:
    1. Condition (What was found)
    2. Criteria (What policy / accounting rule applies)
    3. Cause (Why the deviation happened)
    4. Consequence / Risk (Financial & regulatory exposure)
    5. Corrective Action (Immediate remediation)
    """
    if not api_key or not api_key.strip():
        raise ValueError("Groq API key is missing. Please enter your key in the sidebar.")

    flagged_records = [f for f in findings if f.get("status") == "FLAGGED"]

    # Keep payload concise to protect Groq TPM budget on free-tier
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
**AI Draft Engine:** {model} (Deterministic Rule-Grounded)

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

    return _call_groq_with_retry(api_key, model, messages, max_tokens=1500, temperature=0.15)


def generate_5c_finding_memo(
    api_key: str,
    model: str,
    record: Dict[str, Any],
    category: str
) -> str:
    """
    Generates a dedicated, single-record 5C workpaper memo for an individual flagged transaction.
    """
    if not api_key or not api_key.strip():
        raise ValueError("Groq API key is missing.")

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

    return _call_groq_with_retry(api_key, model, messages, max_tokens=600, temperature=0.1)
