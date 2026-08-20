# AuditIQ - Data Segregation & Anomaly Routing Layer

Pure Python & Streamlit application for automated financial data classification, schema alias binding, vectorized pandas anomaly rule detection, and 5C forensic internal audit workpaper generation.

---

## 🔒 Privacy & Architecture Model

AuditIQ is engineered around a strict **air-gapped, zero-data-leakage architecture**:

1. **Deterministic Anomaly Detection (100% Local & On-Premise)**:
   - All classification, schema mapping, and detection rules execute strictly within the local Python runtime using vectorized Pandas & NumPy boolean index masks.
   - Financial ledger records **never leave the client machine** during classification or rule evaluation. Zero telemetry or external API calls are made for detection.

2. **5C Forensic Workpaper Generation (On-Premise Ready)**:
   - For rapid cloud prototype validation, the LLM workpaper generator interfaces with Groq's high-speed inference engine using targeted low-footprint models (`openai/gpt-oss-20b` and `llama-3.1-8b-instant`).
   - The architecture is symbolized for **16GB RAM On-Premise Hardware** — ready for drop-in local inference via Ollama or vLLM (`http://localhost:11434/v1`) for complete air-gapped compliance in institutional CA firm deployments.
   - Includes automatic exponential backoff retry logic with jitter to gracefully handle free-tier TPM / RPM 429 rate limiting.

---

## 🚀 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Streamlit Application
```bash
streamlit run app.py
```

---

## 📁 Python Architecture & File Structure

```
├── app.py              # Main Streamlit user interface, state orchestration & 4-stage batch review
├── detector.py         # Token-boundary column normalization & alias schema classifier
├── rules_engine.py     # High-performance vectorized Pandas anomaly detection engines
├── groq_advisor.py     # Groq API client with 5C Workpaper generator & exponential backoff
├── sample_data.py      # Synthetic test datasets for all 4 domains + unmapped edge cases
└── requirements.txt    # Python package dependencies (streamlit, pandas, numpy, openpyxl, groq)
```

---

## 🎯 Supported Financial Categories & Vectorized Rules

1. **Transactions (`txn_detection.py`)**:
   - `TXN-001`: Missing management approval sign-off.
   - `TXN-002`: Exact round-number disbursements over threshold (≥ ₹50,000).
   - `TXN-003`: Near-threshold structuring evasion zone (₹45,000 – ₹49,999.99).
   - `TXN-004`: Rolling 7-day multi-payment vendor split invoicing.

2. **AR / AP Aging (`aging_detection.py`)**:
   - `AGE-001`: Severe overdue aging (> 90 days past contractual maturity).
   - `AGE-002`: Inverted chronology (remittance date earlier than invoice date).
   - `AGE-003`: Chronic counterparty delinquency across multiple ledger cycles.
   - *Dynamic Benchmark Date*: Parameterized and auto-resolving to max observed ledger date or current date.

3. **General Ledger (`gl_detection.py`)**:
   - `GL-001`: Double-entry voucher imbalance (Debits ≠ Credits).
   - `GL-002`: Weekend and off-hour manual journal entries.
   - `GL-003`: High-risk month-end close adjustments into clearing/suspense accounts.
   - `GL-004`: Suspense / clearing account parking.

4. **Fixed Assets (`fixed_asset_detection.py`)**:
   - `AST-001`: Missing or undefined depreciation amortization policy.
   - `AST-002`: Carrying value exceeding historical acquisition cost.
   - `AST-003`: Straight-line mathematical depreciation schedule curve deviation.
   - *Dynamic Benchmark Date*: Handles historical and 2025/2026 dates without negative elapsed-year distortions.

---

## 📋 The 5C Internal Audit Framework

The workpaper generator structures forensic output strictly according to the professional **5C Audit Standard**:
- **Condition**: What was found (exact factual deviation with Row #, ₹ INR figures, and counterparty).
- **Criteria**: Governing policies (internal authorization limits, ICAI accounting standards, or SOX-404).
- **Cause**: Root operational breakdown (absent maker-checker controls, ERP timestamp override, split POs).
- **Consequence**: Quantified exposure (unrecorded liabilities, unauthorized disbursements, tax penalties).
- **Corrective Action**: Actionable remediation protocol for management and Lead Engagement Partner workpaper sign-off.

---

## 🔑 Groq Integration & Model Selection
- **API Key Handling**: Configured via sidebar password input and persisted in `st.session_state["groq_api_key"]`.
- **Target Supported Models**:
  - `openai/gpt-oss-20b` (OpenAI GPT-OSS 20B)
  - `llama-3.1-8b-instant` (Meta Llama 3.1 8B Instant)
- **Built-in Resilience**: Exponential backoff and token-budget conservation to avoid rate limit crashes during high-volume testing.
