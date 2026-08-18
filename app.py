"""
AuditIQ - Data Segregation & Routing Layer
Pure Python & Streamlit Application

Run locally with:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Local helper modules
from detector import classify_columns, ALIAS_DEFINITIONS
from rules_engine import audit_transactions, audit_aging, audit_general_ledger, audit_fixed_assets
from groq_advisor import SUPPORTED_MODELS, test_groq_key, generate_executive_memo
from sample_data import SAMPLE_DATASETS

# ---------------------------------------------------------
# Page Configuration & Clean Minimalism Custom CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="AuditIQ - Data Segregation & Routing",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject Clean Minimalist styling & enforce dark text across native Streamlit widgets
st.markdown("""
<style>
    /* Global & Native Streamlit Typography / Elements */
    .stApp, .stApp p, .stApp span, .stApp label, 
    .stMarkdown, h1, h2, h3, h4, h5, h6,
    [data-testid="stCaptionContainer"],
    [data-testid="stSidebar"] *,
    [data-testid="stWidgetLabel"] label,
    .stRadio label, .stSelectbox label, .stTextInput label,
    .stDataFrame, .stTable {
        color: #0F172A !important;
    }

    /* Background & Clean Container */
    .stApp {
        background-color: #F8FAFC !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #0F172A !important;
    }
    
    /* Metrics / Summary Cards */
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
    .metric-subtext {
        font-size: 12px;
        color: #64748B !important;
        margin-top: 4px;
    }
    
    /* Findings Card */
    .finding-box {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-critical {
        background-color: #FEE2E2;
        color: #991B1B !important;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        border: 1px solid #FECACA;
    }
    .badge-high {
        background-color: #FEF3C7;
        color: #92400E !important;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        border: 1px solid #FDE68A;
    }
    .badge-cleared {
        background-color: #DCFCE7;
        color: #166534 !important;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        border: 1px solid #BBF7D0;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "groq_api_key" not in st.session_state:
    st.session_state["groq_api_key"] = ""
if "connection_tested" not in st.session_state:
    st.session_state["connection_tested"] = False
if "selected_model" not in st.session_state or st.session_state["selected_model"] not in [m["id"] for m in SUPPORTED_MODELS]:
    st.session_state["selected_model"] = "openai/gpt-oss-20b"
if "batch_index" not in st.session_state:
    st.session_state["batch_index"] = 0
if "current_dataset_key" not in st.session_state:
    st.session_state["current_dataset_key"] = "transactions"
if "working_df" not in st.session_state:
    st.session_state["working_df"] = SAMPLE_DATASETS["transactions"]["df"].copy()
if "override_category" not in st.session_state:
    st.session_state["override_category"] = None
if "custom_col_map" not in st.session_state:
    st.session_state["custom_col_map"] = {}
if "txn_threshold" not in st.session_state:
    st.session_state["txn_threshold"] = 50000.0


# ---------------------------------------------------------
# Sidebar: Brand, API Key, Model & Sample Datasets
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛡️ **AuditIQ**")
    st.caption("Data Segregation & Anomaly Routing Engine")
    st.divider()

    # Groq API Key Configuration
    st.markdown("#### 🔑 **Groq API Configuration**")
    api_key_input = st.text_input(
        "Groq API Key",
        value=st.session_state["groq_api_key"],
        type="password",
        placeholder="gsk_...",
        help="Session stored. Used for connection tests and AI workpaper memos."
    )
    if api_key_input != st.session_state["groq_api_key"]:
        st.session_state["groq_api_key"] = api_key_input
        st.session_state["connection_tested"] = False

    # Model Dropdown
    model_options = [m["id"] for m in SUPPORTED_MODELS]
    model_labels = {m["id"]: m["name"] for m in SUPPORTED_MODELS}
    
    selected_model = st.selectbox(
        "Inference Model",
        options=model_options,
        format_func=lambda x: model_labels.get(x, x),
        index=0
    )
    st.session_state["selected_model"] = selected_model

    # Connection Test Button
    if st.button("⚡ Test Connection", use_container_width=True):
        if not st.session_state["groq_api_key"]:
            st.error("Please enter a Groq API key first.")
        else:
            with st.spinner("Testing Groq API connection..."):
                res = test_groq_key(st.session_state["groq_api_key"], model=selected_model)
                if res["success"]:
                    st.success(res["message"])
                    st.session_state["connection_tested"] = True
                else:
                    st.error(res["message"])
                    st.session_state["connection_tested"] = False

    st.divider()

    # Pre-Loaded Synthetic Test Batches
    st.markdown("#### 📂 **Pre-loaded Test Batches**")
    st.caption("Select a 5-record slice to evaluate segregation & anomaly rules:")
    
    sample_choice = st.radio(
        "Select Domain Batch:",
        options=list(SAMPLE_DATASETS.keys()),
        format_func=lambda k: SAMPLE_DATASETS[k]["name"],
        index=list(SAMPLE_DATASETS.keys()).index(st.session_state["current_dataset_key"])
    )

    if sample_choice != st.session_state["current_dataset_key"]:
        st.session_state["current_dataset_key"] = sample_choice
        st.session_state["working_df"] = SAMPLE_DATASETS[sample_choice]["df"].copy()
        st.session_state["batch_index"] = 0
        st.session_state["override_category"] = None
        st.session_state["custom_col_map"] = {}
        st.rerun()

    st.divider()

    # Rule Parameters Slider
    st.markdown("#### ⚙️ **Audit Rule Thresholds**")
    st.session_state["txn_threshold"] = st.slider(
        "Transaction Approval Ceiling (₹)",
        min_value=10000.0,
        max_value=100000.0,
        value=50000.0,
        step=5000.0
    )


# ---------------------------------------------------------
# Main App Header & File Ingestion
# ---------------------------------------------------------
st.title("AuditIQ Data Segregation Layer")
st.markdown("Ingest any financial data file to automatically classify schemas, bind column aliases, and route records to specialized vectorized anomaly detection engines.")

# File Uploader
uploaded_file = st.file_uploader(
    "Upload Financial Data File (CSV or Excel)",
    type=["csv", "xlsx", "xls"],
    help="Upload your transaction register, aging ledger, general ledger, or fixed asset schedule."
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            uploaded_df = pd.read_csv(uploaded_file)
        else:
            uploaded_df = pd.read_excel(uploaded_file)
        
        if not uploaded_df.empty and not uploaded_df.equals(st.session_state["working_df"]):
            st.session_state["working_df"] = uploaded_df
            st.session_state["batch_index"] = 0
            st.session_state["override_category"] = None
            st.session_state["custom_col_map"] = {}
            st.success(f"Successfully loaded {uploaded_file.name} ({len(uploaded_df)} rows)")
    except Exception as e:
        st.error(f"Error parsing uploaded file: {str(e)}")

current_df = st.session_state["working_df"]


# ---------------------------------------------------------
# Data Type Detection & Column Classification
# ---------------------------------------------------------
classification = classify_columns(list(current_df.columns))

# Allow manual override if requested or if confidence is low (< 50%)
active_category = st.session_state["override_category"] or classification["category"]
if active_category == "ambiguous":
    active_category = classification["raw_best_category"]

confidence = classification["confidence"]
is_ambiguous = classification["is_ambiguous"] and (st.session_state["override_category"] is None)

# Effective Column Mapping
effective_col_map = {**classification["matched_columns"], **st.session_state["custom_col_map"]}


# ---------------------------------------------------------
# Low Confidence / Manual Mapping Interface
# ---------------------------------------------------------
if is_ambiguous:
    st.warning("⚠️ **Low Header Confidence**: The uploaded column headers did not match standard signatures with high confidence (> 50%). Please confirm the schema mapping below.")
    with st.expander("🛠️ Manual Column Mapping & Domain Configuration", expanded=True):
        col_cat, col_map_ui = st.columns([1, 2])
        
        with col_cat:
            chosen_category = st.selectbox(
                "Target Financial Domain:",
                options=["transactions", "ar_ap_aging", "general_ledger", "fixed_assets"],
                format_func=lambda x: ALIAS_DEFINITIONS[x]["display_name"],
                index=["transactions", "ar_ap_aging", "general_ledger", "fixed_assets"].index(active_category)
            )
            if chosen_category != st.session_state["override_category"]:
                st.session_state["override_category"] = chosen_category

        with col_map_ui:
            st.markdown("**Map Standard Fields to Uploaded Headers:**")
            req_fields = ALIAS_DEFINITIONS[chosen_category]["primary_fields"]
            new_map = {}
            map_cols = st.columns(2)
            
            for i, f in enumerate(req_fields):
                target_col = map_cols[i % 2]
                matched_val = effective_col_map.get(f, "")
                opts = [""] + list(current_df.columns)
                default_idx = opts.index(matched_val) if matched_val in opts else 0
                
                selected_header = target_col.selectbox(
                    f"Field: `{f}`",
                    options=opts,
                    index=default_idx,
                    key=f"map_select_{f}"
                )
                if selected_header:
                    new_map[f] = selected_header
            
            if st.button("Confirm Mapping & Route Engine", type="primary"):
                st.session_state["custom_col_map"] = new_map
                st.session_state["override_category"] = chosen_category
                st.rerun()


# ---------------------------------------------------------
# 3-Card Minimalist Summary Grid
# ---------------------------------------------------------
module_script_name = ALIAS_DEFINITIONS[active_category]["module_file"]
category_title = ALIAS_DEFINITIONS[active_category]["display_name"]

# 5-Record Batching Slice
BATCH_SIZE = 5
total_records = len(current_df)
total_batches = max(1, (total_records + BATCH_SIZE - 1) // BATCH_SIZE)
current_batch_idx = min(st.session_state["batch_index"], total_batches - 1)

batch_df = current_df.iloc[current_batch_idx * BATCH_SIZE : (current_batch_idx + 1) * BATCH_SIZE].copy()

# Execute Vectorized Anomaly Detection for Current Batch
if active_category == "transactions":
    findings = audit_transactions(batch_df, effective_col_map, threshold_limit=st.session_state["txn_threshold"])
elif active_category == "ar_ap_aging":
    findings = audit_aging(batch_df, effective_col_map, severe_overdue_days=90)
elif active_category == "general_ledger":
    findings = audit_general_ledger(batch_df, effective_col_map, period_end_days=4)
elif active_category == "fixed_assets":
    findings = audit_fixed_assets(batch_df, effective_col_map)
else:
    findings = []

flagged_count = sum(1 for f in findings if f["status"] == "FLAGGED")

# Render 3 Summary Metric Cards
m_col1, m_col2, m_col3 = st.columns(3)

with m_col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Detected Schema</div>
        <div class="metric-value" style="color: #2563EB;">{category_title}</div>
        <div class="metric-subtext">Confidence Score: <b>{confidence}%</b></div>
    </div>
    """, unsafe_allow_html=True)

with m_col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Routing Status</div>
        <div class="metric-value" style="font-family: monospace;">{module_script_name}</div>
        <div class="metric-subtext">Vectorized Pandas Rule Engine</div>
    </div>
    """, unsafe_allow_html=True)

with m_col3:
    risk_color = "#EF4444" if flagged_count > 0 else "#10B981"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Risk Profile</div>
        <div class="metric-value" style="color: {risk_color};">{flagged_count} Flags Raised</div>
        <div class="metric-subtext">Out of <b>{len(batch_df)}</b> records in current batch</div>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# Interactive 5-Record Batch Editor (st.data_editor)
# ---------------------------------------------------------
st.markdown("### 📊 Live Batch Preview & Interactive Test Editor")
st.caption(f"Showing slice records `{current_batch_idx * BATCH_SIZE + 1}` to `{min((current_batch_idx + 1) * BATCH_SIZE, total_records)}` of `{total_records}` total. You can edit cells inline below to immediately test rule sensitivities:")

# Render editable table
edited_batch_df = st.data_editor(
    batch_df,
    use_container_width=True,
    num_rows="dynamic",
    key=f"editor_batch_{current_batch_idx}"
)

# Update session working_df if modified
if not edited_batch_df.equals(batch_df):
    st.session_state["working_df"].iloc[current_batch_idx * BATCH_SIZE : (current_batch_idx + 1) * BATCH_SIZE] = edited_batch_df
    st.rerun()

# Batch Pagination Controls
nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])

with nav_col1:
    if st.button("⬅️ Previous 5 Records", disabled=(current_batch_idx == 0), use_container_width=True):
        st.session_state["batch_index"] = max(0, current_batch_idx - 1)
        st.rerun()

with nav_col2:
    st.markdown(f"<div style='text-align: center; padding-top: 6px; font-size: 13px; font-weight: 600;'>Batch {current_batch_idx + 1} of {total_batches}</div>", unsafe_allow_html=True)

with nav_col3:
    if st.button("Next 5 Records ➡️", disabled=(current_batch_idx >= total_batches - 1), use_container_width=True):
        st.session_state["batch_index"] = min(total_batches - 1, current_batch_idx + 1)
        st.rerun()


# ---------------------------------------------------------
# Itemized Audit Findings & Rule Explainability
# ---------------------------------------------------------
st.divider()
st.markdown("### 🔍 Itemized Audit Findings")
st.caption("Root-cause breakdown and SOX internal audit remediation guidelines for the active batch slice:")

if flagged_count == 0:
    st.success("✅ **Batch Cleared**: No compliance violations or transaction anomalies detected across active parameters.")
else:
    for item in findings:
        row_num = item["row_index"]
        status = item["status"]
        flags = item["flags"]
        
        if status == "FLAGGED":
            with st.container():
                st.markdown(f"#### 🚩 Record #{row_num} (Row Index: {current_batch_idx * BATCH_SIZE + row_num})")
                for f in flags:
                    sev = f["severity"]
                    badge_class = "badge-critical" if sev == "CRITICAL" else "badge-high"
                    
                    st.markdown(f"""
                    <div class="finding-box">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div>
                                <span class="{badge_class}">{sev}</span>
                                <span style="font-family: monospace; font-weight: 700; margin-left: 8px;">{f['rule_code']}</span>
                                <span style="font-weight: 600; margin-left: 4px;">{f['rule_name']}</span>
                            </div>
                        </div>
                        <p style="font-size: 13px; color: #1E293B; margin-bottom: 8px;">{f['description']}</p>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; font-size: 12px;">
                            <div style="background: #F8FAFC; padding: 8px; border-radius: 6px; border: 1px solid #E2E8F0;">
                                <b style="color: #DC2626;">Detected Value:</b> {f['detected_value']}
                            </div>
                            <div style="background: #F8FAFC; padding: 8px; border-radius: 6px; border: 1px solid #E2E8F0;">
                                <b style="color: #64748B;">Audit Requirement:</b> {f['expected']}
                            </div>
                        </div>
                        <div style="background: #EFF6FF; padding: 8px; border-radius: 6px; font-size: 12px; color: #1E40AF; border: 1px solid #DBEAFE;">
                            <b>Remediation Protocol:</b> {f['remediation']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)


# ---------------------------------------------------------
# Groq AI Audit Advisor Memo Generator
# ---------------------------------------------------------
st.divider()
st.markdown("### 🤖 Groq AI Forensic Audit Advisor")
st.caption("Generate an executive workpaper memo summarizing risk exposures and internal control actions:")

ai_col1, ai_col2 = st.columns([3, 1])
with ai_col1:
    st.info(f"Active Model: **{selected_model}** | Key Status: {'✅ Configured' if st.session_state['groq_api_key'] else '❌ Missing API Key'}")

with ai_col2:
    generate_btn = st.button("✨ Generate Audit Memo", type="primary", use_container_width=True)

if generate_btn:
    if not st.session_state["groq_api_key"]:
        st.error("Please provide a Groq API Key in the sidebar to generate AI memos.")
    else:
        with st.spinner(f"Analyzing batch with Groq ({selected_model})..."):
            try:
                memo = generate_executive_memo(
                    api_key=st.session_state["groq_api_key"],
                    model=selected_model,
                    category=category_title,
                    findings=findings,
                    batch_df_records=batch_df.to_dict(orient="records"),
                    confidence=confidence
                )
                st.markdown("#### 📄 Executive Workpaper Memo")
                st.markdown(memo)
                st.download_button(
                    "📥 Download Workpaper (.md)",
                    data=memo,
                    file_name=f"auditiq_workpaper_batch_{current_batch_idx + 1}.md",
                    mime="text/markdown"
                )
            except Exception as e:
                st.error(f"Failed to generate memo: {str(e)}")
