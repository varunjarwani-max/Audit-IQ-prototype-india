# AuditIQ — Financial Data Classification & Anomaly Routing Engine

**A modular anomaly-detection pipeline that classifies uploaded financial data, routes it to the correct detection engine, and generates AI-assisted audit workpapers — built for Indian CA firms.**

---

## Why this exists

Internal audit teams at Indian Chartered Accountancy firms still review transactions, ledgers, and aging reports largely by hand. That's slow, inconsistent between reviewers, and hard to scale across clients. AuditIQ automates the first, most repetitive layer of that work: **taking in raw financial exports, figuring out what kind of data they are, and flagging the anomalies a human auditor would look for anyway** — before a reviewer ever opens the file.

Because audit data is client-confidential, AuditIQ keeps all deterministic detection local — no financial data or rule logic ever leaves the machine running the app. AI narratives currently use Groq's hosted API to draft the plain-language write-up; a fully offline/local-model deployment is on the roadmap.

**[Live demo →](https://audit-iq-prototype-india.streamlit.app)**

---

## What it does

1. **Ingest** — user uploads a financial export (CSV/Excel) via the Streamlit UI
2. **Classify** — `detector.py` normalizes column headers and uses alias-based schema matching to identify which of 4 financial data types the file is
3. **Route** — the classified data is passed to the matching detection engine
4. **Detect** — vectorized Pandas rules flag specific anomaly patterns (see below)
5. **Report** — flagged findings are passed to the configured Groq model for narrative drafting. The deterministic rules — not the LLM — make the audit classification and anomaly decisions

---

## Supported data types & detection rules

| Category | Rule ID | What it catches |
|---|---|---|
| **Transactions** | `TXN-001` | Missing management approval sign-off |
| | `TXN-002` | Exact round-number disbursements ≥ ₹50,000 |
| | `TXN-003` | Near-threshold "structuring" evasion (₹45,000–₹49,999.99) |
| | `TXN-004` | Rolling 7-day multi-payment vendor split invoicing |
| **AR / AP Aging** | `AGE-001` | Invoices overdue beyond 90 days |
| | `AGE-002` | Inverted chronology (payment date before invoice date) |
| | `AGE-003` | Chronic counterparty delinquency across ledger cycles |
| **General Ledger** | `GL-001` | Double-entry voucher imbalance (debits ≠ credits) |
| | `GL-002` | Weekend / off-hour manual journal entries |
| | `GL-003` | High-risk month-end adjustments into suspense accounts |
| | `GL-004` | Suspense/clearing account parking |
| **Fixed Assets** | `AST-001` | Missing or undefined depreciation policy |
| | `AST-002` | Carrying value exceeding historical acquisition cost |
| | `AST-003` | Deviation from straight-line depreciation curve |

Most row-level rules run as vectorized Pandas operations rather than row-by-row loops; grouped and rolling-window rules (like the vendor-split check) use Pandas `groupby`/rolling operations where sequence context across rows is required. Files with ambiguous schemas or missing required evidence fields are rejected for safe manual classification, rather than being silently routed to the closest-guess domain.

---

## How it works (technical detail)

### 1. Classification — schema fingerprinting, not hardcoded matching

Rather than requiring an exact, pre-agreed column layout (which breaks the moment a client exports data with slightly different headers), `detector.py` builds a **schema fingerprint** for each uploaded file:

- Column headers are normalized (lowercased, whitespace/punctuation stripped)
- Each of the 4 known data types (transactions, AR/AP aging, general ledger, fixed assets) has a small set of **alias groups** — e.g., an aging file might be recognized whether its due-date column is named `due_date`, `Due Date`, or `payment_due`
- The uploaded file's normalized headers are scored against each schema's alias groups; the highest-overlap schema wins the classification
- This makes the system tolerant to real-world messiness in exported spreadsheets, which is the actual failure mode of naive "check for exact column names" approaches

### 2. Detection — vectorized masks where possible, groupby/rolling where sequence matters

Most single-row rules in `rules_engine.py` are expressed as a **Pandas boolean mask** applied across the whole column at once, rather than looping through rows in Python:

```python
# vectorized — O(n), runs in compiled C under the hood
flagged = df[(df['amount'] % 50000 == 0) & (df['amount'] >= 50000)]

# NOT this — row-wise Python loop, orders of magnitude slower on large ledgers
for i, row in df.iterrows():
    if row['amount'] % 50000 == 0 and row['amount'] >= 50000:
        flagged.append(row)
```

Rules that need context *across* rows — like the rolling 7-day vendor-split check — can't be expressed as a simple per-row mask, since they depend on a vendor's payment history within a window, not a single row's values. Those use Pandas `groupby`/rolling operations instead, which still avoid explicit Python loops but express a genuinely different kind of computation than a flat boolean mask.

### 3. Routing — category branching today, with a dispatch table as a clear next step

The classified data is routed to the corresponding detection function; the current Streamlit flow does this via explicit category branching rather than a dictionary dispatch. This is a known, deliberate simplification for a 4-category prototype — the natural refactor as more domains are added is to extract the branching into a `{schema_name: rule_function}` dispatch table, so adding a 5th data type is a one-line registration instead of a new branch.

### 4. AI layer — constrained generation, not open-ended prompting

The flagged anomalies (structured data: rule ID, row reference, values involved) are passed to the Groq-hosted LLM with a **constrained prompt template** — the model is given the specific anomaly facts and asked to write the audit-workpaper narrative around them, rather than being asked to "find problems" itself. This keeps the LLM's role to *language generation*, not *detection* — the actual anomaly-finding is deterministic and auditable (a real requirement for audit tooling, where a human reviewer needs to trust *why* something was flagged, not just that an LLM said so).

---

## Architecture

```
├── app.py              # Streamlit UI, session state, batch view orchestration
├── detector.py          # Column normalization & alias-based schema classifier
├── rules_engine.py      # Vectorized Pandas anomaly detection rules (all 4 domains)
├── groq_advisor.py       # Groq API client — generates audit workpaper narratives
├── sample_data.py       # Synthetic test datasets (5 records/domain + edge cases)
└── requirements.txt     # Python dependencies
```

**Design note:** classification (`detector.py`) and detection (`rules_engine.py`) are deliberately separate. A new financial data type can be added by extending the alias schema and adding one rule module.

---

## Tech stack

- **Frontend:** Streamlit
- **Data processing:** Pandas (vectorized rule evaluation)
- **AI layer:** Groq API:
  - `openai/gpt-oss-safeguard-20b`
  - `openai/gpt-oss-20b`
  - `openai/gpt-oss-120b` (fallback)
- **Language:** Python

---

## Try it

The **[live demo](https://audit-iq-prototype-india.streamlit.app)** is deployed on Streamlit Community Cloud — just open the link, no setup or API key needed.

### Running it locally

```bash
git clone https://github.com/varunjarwani-max/Audit-IQ-prototype-india.git
cd Audit-IQ-prototype-india
pip install -r requirements.txt
streamlit run app.py
```

The classification and rule-detection engine works with no configuration. For AI-generated workpaper narratives locally, you'll need your own [Groq API key](https://console.groq.com): copy `.env.example` to `.env` and set `GROQ_API_KEY` there (this file is git-ignored and should never be committed).

---

## Roadmap

- [ ] Fully offline mode (swap Groq for a locally-hosted model, e.g., via Ollama)
- [ ] Configurable rule thresholds per client engagement
- [ ] Export flagged anomalies + workpaper as PDF
- [ ] Additional financial categories (payroll, inventory)

---

## About

Built as a prototype exploring how much of first-pass audit review can be automated safely — i.e., without requiring client financial data to leave the firm's own infrastructure.
