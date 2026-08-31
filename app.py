"""
AuditIQ - Data Segregation & Routing Layer
Pure Python & Streamlit Application

Run locally with:
    streamlit run app.py
"""

import streamlit as st

# Must strictly be the very first Streamlit command executed
st.set_page_config(
    page_title="AuditIQ - Data Segregation & Routing",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

import hashlib
import io
import pandas as pd
import numpy as np
import time
from datetime import datetime

# Local helper modules imported AFTER set_page_config
from detector import classify_columns, ALIAS_DEFINITIONS
from rules_engine import (
    DEFAULT_PERIOD_END_DAYS,
    DEFAULT_SEVERE_OVERDUE_DAYS,
    DEFAULT_TRANSACTION_THRESHOLD,
    audit_aging,
    audit_fixed_assets,
    audit_general_ledger,
    audit_transactions,
)
from groq_advisor import generate_executive_memo, generate_5c_finding_memo, generate_consolidated_master_report
from sample_data import SAMPLE_DATASETS

# ---------------------------------------------------------
# Clean Minimalism Custom CSS
# ---------------------------------------------------------
st.markdown("""
<style>
    .stApp, .stApp p, .stApp span, .stApp label, 
    .stMarkdown, h1, h2, h3, h4, h5, h6,
    [data-testid="stSidebar"] *,
    .stDataFrame, .stTable {
        color: #0F172A !important;
    }
    .stApp {
        background-color: #F8FAFC !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    .metric-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        margin-bottom: 12px;
    }
    .metric-label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        color: #64748B !important;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 20px;
        font-weight: 800;
        color: #0F172A !important;
    }
    .finding-box {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-critical { background-color: #FEE2E2; color: #991B1B !important; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; }
    .badge-high { background-color: #FEF3C7; color: #92400E !important; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; }
    .sentry-alert { background-color: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px; margin-bottom: 16px; border-radius: 4px; color: #991B1B !important; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _uploaded_file_signature(uploaded_file) -> tuple[str, int, str]:
    payload = uploaded_file.getvalue()
    return uploaded_file.name, len(payload), hashlib.sha256(payload).hexdigest()


def _parse_uploaded_file(uploaded_file) -> pd.DataFrame:
    payload = uploaded_file.getvalue()
    if not payload:
        raise ValueError("The uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("The uploaded file exceeds the 15 MB safety limit.")
    stream = io.BytesIO(payload)
    if uploaded_file.name.lower().endswith(".csv"):
        return pd.read_csv(stream)
    return pd.read_excel(stream)


# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "batch_index" not in st.session_state: st.session_state["batch_index"] = 0
if "working_df" not in st.session_state: st.session_state["working_df"] = SAMPLE_DATASETS["transactions"]["df"].copy()
if "override_category" not in st.session_state: st.session_state["override_category"] = None
if "custom_col_map" not in st.session_state: st.session_state["custom_col_map"] = {}
if "individual_memos" not in st.session_state: st.session_state["individual_memos"] = {}
if "multi_file_data" not in st.session_state: st.session_state["multi_file_data"] = {}
if "active_file_name" not in st.session_state: st.session_state["active_file_name"] = None
if "audit_config" not in st.session_state: st.session_state["audit_config"] = None

# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛡️ **AuditIQ**")
    st.caption("Data Segregation & Anomaly Routing Engine")
    
    st.markdown("---")
    st.markdown("### Global Settings")
    txn_threshold = DEFAULT_TRANSACTION_THRESHOLD
    st.caption(f"Transaction approval benchmark: ₹{txn_threshold:,.0f}")
    as_of_date = st.date_input("Audit As-Of Date", value=datetime.today())

# ---------------------------------------------------------
# Main App Header & Multi-File Ingestion
# ---------------------------------------------------------
st.title("AuditIQ Data Segregation Layer")
st.markdown("Ingest multiple financial files simultaneously. AuditIQ will auto-route each to its respective engine and generate a unified Master Report.")

uploaded_files = st.file_uploader(
    "Upload Financial Data Files (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if uploaded_files:
    signatures = tuple(sorted(_uploaded_file_signature(file) for file in uploaded_files))
    current_audit_config = (signatures, as_of_date.isoformat(), txn_threshold)

    if current_audit_config != st.session_state["audit_config"]:
        processed_files = {}
        rejected_files = []
        for file in uploaded_files:
            try:
                df = _parse_uploaded_file(file)
            except Exception as exc:
                rejected_files.append(file.name)
                st.error(f"`{file.name}` could not be parsed: {exc}")
                continue

            classification = classify_columns(list(df.columns))
            for warning in classification.get("classification_warnings", []):
                st.warning(f"`{file.name}`: {warning}")

            category = classification["category"]
            if category == "ambiguous":
                rejected_files.append(file.name)
                st.error(f"`{file.name}` was not audited because its schema could not be classified safely.")
                continue

            col_map = classification["matched_columns"]
            if category == "transactions":
                findings = audit_transactions(df, col_map, threshold_limit=txn_threshold)
            elif category == "ar_ap_aging":
                findings = audit_aging(df, col_map, severe_overdue_days=DEFAULT_SEVERE_OVERDUE_DAYS, as_of_date=as_of_date)
            elif category == "general_ledger":
                findings = audit_general_ledger(df, col_map, period_end_days=DEFAULT_PERIOD_END_DAYS)
            else:
                findings = audit_fixed_assets(df, col_map, as_of_date=as_of_date)

            processed_files[file.name] = {
                "df": df,
                "category": category,
                "findings": findings,
                "classification": classification,
                "audit_as_of_date": as_of_date.isoformat(),
                "content_signature": _uploaded_file_signature(file)[2],
            }

        st.session_state["multi_file_data"] = processed_files
        st.session_state["audit_config"] = current_audit_config
        st.session_state["individual_memos"] = {}
        if processed_files:
            first_name = next(iter(processed_files))
            st.session_state["active_file_name"] = first_name
            st.session_state["working_df"] = processed_files[first_name]["df"].copy()
        else:
            st.session_state["active_file_name"] = None
        st.session_state["override_category"] = None
        st.session_state["custom_col_map"] = {}
        st.rerun()

# ---------------------------------------------------------
# Consolidated Dashboard & Master Report Generation
# ---------------------------------------------------------
if st.session_state["multi_file_data"]:
    st.markdown("---")
    st.markdown("### 🌐 Consolidated Multi-Domain Dashboard")
    
    total_files = len(st.session_state["multi_file_data"])
    total_flagged_rows = sum(
        sum(1 for item in data["findings"] if item["status"] == "FLAGGED")
        for data in st.session_state["multi_file_data"].values()
    )
    total_findings = sum(
        sum(len(item.get("flags", [])) for item in data["findings"])
        for data in st.session_state["multi_file_data"].values()
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Domains Analyzed", total_files)
    c2.metric("Total Rows Processed", sum(len(data["df"]) for data in st.session_state["multi_file_data"].values()))
    c3.metric("Flagged Rows", total_flagged_rows)
    c4.metric("Individual Findings", total_findings)

    if st.button("✨ Generate Unified Master Report", type="primary", use_container_width=True):
        with st.spinner("Calculating exact metrics and synthesizing dossier..."):
            master_memo, sentry_warnings = generate_consolidated_master_report(
                all_domain_data=st.session_state["multi_file_data"]
            )
            
            if sentry_warnings:
                st.markdown("### ⚠️ Sentry Verification Alerts")
                for warning in sentry_warnings:
                    st.markdown(f"<div class='sentry-alert'><b>{warning}</b></div>", unsafe_allow_html=True)
            
            st.markdown("#### 📑 Master Executive Dossier")
            st.markdown(master_memo)
            st.download_button("📥 Download Master Report", data=master_memo, file_name="AuditIQ_Master_Report.md", mime="text/markdown")

    st.markdown("---")
    
    selected_file = st.selectbox("Select File for Interactive Deep Dive:", options=list(st.session_state["multi_file_data"].keys()))
    if selected_file != st.session_state["active_file_name"]:
        st.session_state["active_file_name"] = selected_file
        st.session_state["working_df"] = st.session_state["multi_file_data"][selected_file]["df"]
        st.session_state["batch_index"] = 0
        st.rerun()

    current_df = st.session_state["working_df"]
    active_data = st.session_state["multi_file_data"][st.session_state["active_file_name"]]
    active_category = active_data["category"]
    confidence = active_data["classification"]["confidence"]
    effective_col_map = {**active_data["classification"]["matched_columns"], **st.session_state["custom_col_map"]}
    all_findings = active_data["findings"]

    total_records = len(current_df)
    total_flagged_all = sum(1 for f in all_findings if f["status"] == "FLAGGED")
    
    BATCH_SIZE = 5
    total_batches = max(1, (total_records + BATCH_SIZE - 1) // BATCH_SIZE)
    current_batch_idx = min(st.session_state["batch_index"], total_batches - 1)
    batch_start_idx = current_batch_idx * BATCH_SIZE
    batch_end_idx = min((current_batch_idx + 1) * BATCH_SIZE, total_records)
    batch_df = current_df.iloc[batch_start_idx:batch_end_idx].copy()
    batch_findings = all_findings[batch_start_idx:batch_end_idx]
    batch_flagged_count = sum(1 for f in batch_findings if f["status"] == "FLAGGED")

    st.markdown(f"### 🔍 Deep Dive: `{st.session_state['active_file_name']}` ({ALIAS_DEFINITIONS[active_category]['display_name']})")
    
    edited_batch_df = st.data_editor(batch_df, use_container_width=True, num_rows="dynamic", key=f"editor_batch_{current_batch_idx}")
    if not edited_batch_df.equals(batch_df):
        st.session_state["working_df"].iloc[batch_start_idx:batch_end_idx] = edited_batch_df
        updated_df = st.session_state["working_df"]
        
        new_findings = []
        if active_category == "transactions": new_findings = audit_transactions(updated_df, effective_col_map, threshold_limit=txn_threshold)
        elif active_category == "ar_ap_aging": new_findings = audit_aging(updated_df, effective_col_map, severe_overdue_days=90, as_of_date=as_of_date)
        elif active_category == "general_ledger": new_findings = audit_general_ledger(updated_df, effective_col_map, period_end_days=4)
        elif active_category == "fixed_assets": new_findings = audit_fixed_assets(updated_df, effective_col_map, as_of_date=as_of_date)
        
        st.session_state["multi_file_data"][st.session_state["active_file_name"]]["df"] = updated_df
        st.session_state["multi_file_data"][st.session_state["active_file_name"]]["findings"] = new_findings
        st.rerun()

    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
    with nav_col1:
        if st.button("⬅️ Previous 5", disabled=(current_batch_idx == 0), use_container_width=True):
            st.session_state["batch_index"] = max(0, current_batch_idx - 1); st.rerun()
    with nav_col2:
        st.markdown(f"<div style='text-align: center; padding-top: 6px; font-size: 13px; font-weight: 600;'>Batch {current_batch_idx + 1} of {total_batches}</div>", unsafe_allow_html=True)
    with nav_col3:
        if st.button("Next 5 ➡️", disabled=(current_batch_idx >= total_batches - 1), use_container_width=True):
            st.session_state["batch_index"] = min(total_batches - 1, current_batch_idx + 1); st.rerun()

    st.divider()
    if batch_flagged_count == 0:
        st.success("✅ **Batch Slice Cleared**: No compliance violations detected in this 5-record window.")
    else:
        for item in batch_findings:
            if item["status"] == "FLAGGED":
                global_row_num = item["row_index"]
                st.markdown(f"#### 🚩 Record #{global_row_num}")
                for f in item["flags"]:
                    sev = f["severity"]
                    badge = "badge-critical" if sev == "CRITICAL" else "badge-high"
                    st.markdown(f"""
                    <div class="finding-box">
                        <span class="{badge}">{sev}</span> <b>{f['rule_code']}</b>: {f['rule_name']}<br>
                        <span style="font-size: 13px; color: #64748B;">{f['description']}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                active_signature = active_data.get("content_signature", "unspecified")
                memo_key = f"{st.session_state['active_file_name']}:{active_signature}:row:{global_row_num}"
                if memo_key in st.session_state["individual_memos"]:
                    st.markdown(st.session_state["individual_memos"][memo_key])
                else:
                    if st.button(f"Generate 5C Note for Row #{global_row_num}", key=f"btn_5c_{global_row_num}"):
                        note = generate_5c_finding_memo({"row_index": global_row_num, "data": current_df.iloc[global_row_num - 1].to_dict(), "flags": item["flags"]}, ALIAS_DEFINITIONS[active_category]['display_name'])
                        st.session_state["individual_memos"][memo_key] = note
                        st.rerun()
