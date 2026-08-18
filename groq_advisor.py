"""
groq_advisor.py
Groq LLM Client & Executive Workpaper Generator for AuditIQ.
"""

import json
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


def test_groq_key(api_key: str, model: str = "llama-3.1-8b-instant") -> Dict[str, Any]:
    """Tests the Groq API key with a fast ping call."""
    if not api_key or not api_key.strip():
        return {"success": False, "message": "No API key provided."}

    cleaned_key = api_key.strip()

    if GROQ_SDK_AVAILABLE:
        try:
            client = Groq(api_key=cleaned_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a ping test assistant. Respond with 'OK'."},
                    {"role": "user", "content": "Ping"}
                ],
                max_tokens=10,
                temperature=0.1
            )
            return {"success": True, "message": f"Connection verified successfully using {model}!"}
        except Exception as e:
            return {"success": False, "message": f"Groq verification failed: {str(e)}"}
    else:
        # Fallback using standard library urllib
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cleaned_key}"
        }
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Ping"}],
            "max_tokens": 10
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return {"success": True, "message": f"Connection verified successfully using {model}!"}
                return {"success": False, "message": f"HTTP {response.status}: {response.reason}"}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            return {"success": False, "message": f"API Error ({e.code}): {err_body}"}
        except Exception as e:
            return {"success": False, "message": f"Network Error: {str(e)}"}


def generate_executive_memo(
    api_key: str,
    model: str,
    category: str,
    findings: List[Dict[str, Any]],
    batch_df_records: List[Dict[str, Any]],
    confidence: float
) -> str:
    """Generates a professional internal audit workpaper memo."""
    if not api_key or not api_key.strip():
        raise ValueError("Groq API key is missing. Please enter your key in the sidebar.")

    flagged_records = [f for f in findings if f["status"] == "FLAGGED"]

    prompt = f"""
You are AuditIQ Senior Forensic AI Auditor. Analyze this 5-record financial data batch:

DATA SEPARATION & CLASSIFICATION:
- Detected Category: {category} ({confidence}% confidence)
- Total Records Evaluated: {len(findings)}
- Flagged Violations: {len(flagged_records)}

RECORD-BY-RECORD AUDIT ENGINE FINDINGS:
{json.dumps(findings, indent=2)}

RAW BATCH RECORDS:
{json.dumps(batch_df_records, indent=2)}

Please draft a crisp, formal Forensic Internal Audit Workpaper Memo containing:
1. Executive Risk Summary & Control Integrity Score
2. Specific Violations Diagnosed (with Row #, rule codes, exact amounts in INR, and underlying patterns)
3. Forensic Risk Implication (e.g. structuring, unauthorized disbursement, invoice fabrication, unrecorded liability)
4. Recommended Immediate Workpaper & Internal Control Action Steps

Write in clear, authoritative audit terminology suitable for external partners and audit committee presentation.
"""

    cleaned_key = api_key.strip()

    if GROQ_SDK_AVAILABLE:
        try:
            client = Groq(api_key=cleaned_key)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a certified internal auditor and forensic fraud examiner."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            return completion.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"Groq generation failed with model '{model}': {str(e)}")
    else:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cleaned_key}"
        }
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a certified internal auditor and forensic fraud examiner."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1500
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"Groq API Error ({e.code}) with model '{model}': {err_body}")
        except Exception as e:
            raise RuntimeError(f"Groq request failed: {str(e)}")
