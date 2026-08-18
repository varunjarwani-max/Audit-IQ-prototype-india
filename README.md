# AuditIQ - Data Segregation & Anomaly Routing Layer

Pure Python & Streamlit application for automated financial data classification, schema alias binding, vectorized pandas anomaly rule detection, and LLM-assisted forensic internal audit workpaper generation using Groq.

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
├── app.py              # Main Streamlit user interface, state orchestration & batch view
├── detector.py         # Column normalization & alias-based schema classifier
├── rules_engine.py     # Pure vectorized Pandas anomaly detection engines
├── groq_advisor.py     # Groq API client & executive internal audit workpaper generator
├── sample_data.py      # Synthetic 5-record test datasets for all 4 domains + edge cases
└── requirements.txt    # Python package dependencies
```

---

## 🎯 Supported Financial Categories & Vectorized Rules

1. **Transactions (`txn_detection.py`)**:
   - `TXN-001`: Missing management approval sign-off.
   - `TXN-002`: Exact round-number disbursements over threshold (≥ ₹50,000).
   - `TXN-003`: Near-threshold structuring evasion zone (₹45,000 – ₹49,999.99).
   - `TXN-004`: Rolling 7-day multi-payment vendor split invoicing.

2. **AR / AP Aging (`aging_detection.py`)**:
   - `AGE-001`: Invoices overdue beyond 90 days.
   - `AGE-002`: Inverted chronology (payment date earlier than invoice date).
   - `AGE-003`: Chronic counterparty delinquency across multiple ledger cycles.

3. **General Ledger (`gl_detection.py`)**:
   - `GL-001`: Double-entry voucher imbalance (Debits ≠ Credits).
   - `GL-002`: Weekend and off-hour manual journal entries.
   - `GL-003`: High-risk month-end close adjustments into clearing/suspense accounts.
   - `GL-004`: Suspense / clearing account parking.

4. **Fixed Assets (`fixed_asset_detection.py`)**:
   - `AST-001`: Missing or undefined depreciation amortization policy.
   - `AST-002`: Carrying value exceeding historical acquisition cost.
   - `AST-003`: Straight-line mathematical depreciation schedule curve deviation.

---

## 🔑 Groq Integration & Models
- **API Key Handling**: Configured via sidebar password field and stored in `st.session_state["groq_api_key"]`.
- **Target Supported Models (16GB Hardware / Local On-Premise Path)**:
  - `openai/gpt-oss-20b` (OpenAI GPT-OSS 20B)
  - `llama-3.1-8b-instant` (Meta Llama 3.1 8B Instant)
- **Connection Test**: Integrated `Test Connection` button validates key connectivity before invoking workpaper generators.
