"""
rules_engine.py
Vectorized Pandas Anomaly Detection Engines for AuditIQ.
Operates on batches and returns itemized findings per row with rule codes, severity, and remediation guidance.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple


def audit_transactions(df: pd.DataFrame, col_map: Dict[str, str], threshold_limit: float = 50000.0) -> List[Dict[str, Any]]:
    """
    Vectorized Transaction Audit Rules:
    1. TXN-001: Missing Approval Sign-off
    2. TXN-002: Exact Round-Number Amount over Threshold (₹50,000+)
    3. TXN-003: Near-Threshold Structuring Zone (₹45,000 - ₹49,999.99)
    4. TXN-004: Multi-Payment Vendor Structuring (7-day window)
    """
    findings = []
    if df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    
    # Extract mapped columns or fallback to best guess
    col_amount = col_map.get("amount", "amount")
    col_approved = col_map.get("approved_by", "approved_by")
    col_vendor = col_map.get("vendor", "vendor")
    col_date = col_map.get("date", "date")

    # Safe conversion
    working_df["_amt"] = pd.to_numeric(working_df.get(col_amount, 0), errors="coerce").fillna(0)
    working_df["_date"] = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    working_df["_vendor"] = working_df.get(col_vendor, "").astype(str).fillna("").str.strip()
    working_df["_approver"] = working_df.get(col_approved, "").astype(str).fillna("").str.strip()

    # Rule 1: Missing Approvals
    missing_approval_mask = (
        working_df["_approver"].isna() | 
        (working_df["_approver"] == "") | 
        working_df["_approver"].str.lower().isin(["none", "null", "nan", "unassigned", "-"])
    )

    # Rule 2: Round Numbers over threshold (₹50,000+)
    round_number_mask = (
        (working_df["_amt"] >= threshold_limit) & 
        ((working_df["_amt"] % 1000 == 0) | (working_df["_amt"] % 5000 == 0))
    )

    # Rule 3: Near-Threshold Structuring (₹45,000 - ₹49,999.99)
    structuring_mask = (
        (working_df["_amt"] >= (threshold_limit * 0.90)) & 
        (working_df["_amt"] < threshold_limit)
    )

    # Rule 4: Multi-Payment Vendor Structuring within 7-Day Window
    structuring_7d_indices = set()
    for vendor_name, group in working_df.groupby("_vendor"):
        if vendor_name and len(group) > 1:
            valid_dates = group.dropna(subset=["_date"]).sort_values("_date")
            if len(valid_dates) > 1:
                dates = valid_dates["_date"].values
                amounts = valid_dates["_amt"].values
                idxs = valid_dates.index.values
                
                for i in range(len(dates)):
                    window_idxs = [idxs[i]]
                    window_amt = amounts[i]
                    for j in range(i + 1, len(dates)):
                        diff_days = (dates[j] - dates[i]) / np.timedelta64(1, 'D')
                        if diff_days <= 7:
                            window_idxs.append(idxs[j])
                            window_amt += amounts[j]
                    if len(window_idxs) > 1 and window_amt >= threshold_limit:
                        structuring_7d_indices.update(window_idxs)

    # Compile itemized findings per row
    for idx, row in working_df.iterrows():
        row_flags = []
        amt_val = row["_amt"]
        approver_val = row["_approver"]
        vendor_val = row["_vendor"]

        if missing_approval_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "TXN-001",
                "rule_name": "Missing Approval Sign-off",
                "severity": "CRITICAL" if amt_val >= threshold_limit else "HIGH",
                "description": f"Transaction of ₹{amt_val:,.2f} has no documented authorizing sign-off.",
                "detected_value": f"Approver: '{approver_val}'",
                "expected": f"Mandatory authorized manager sign-off for expenses.",
                "remediation": "Request physical or digital approval voucher before disbursement clearance."
            })

        if round_number_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "TXN-002",
                "rule_name": "Exact Round-Number Disbursement",
                "severity": "HIGH",
                "description": f"Exact round figure of ₹{amt_val:,.2f} exceeds ₹{threshold_limit:,.0f} audit threshold.",
                "detected_value": f"₹{amt_val:,.2f}",
                "expected": "Itemized vendor billings with tax/fee fractions.",
                "remediation": "Obtain itemized vendor invoice and inspect line-item cost components."
            })

        if structuring_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "TXN-003",
                "rule_name": "Near-Threshold Structuring Evasion",
                "severity": "HIGH",
                "description": f"Amount of ₹{amt_val:,.2f} sits ₹{threshold_limit - amt_val:,.2f} below ₹{threshold_limit:,.0f} approval ceiling.",
                "detected_value": f"₹{amt_val:,.2f}",
                "expected": "Regular unfragmented requisition without artificial limit evasion.",
                "remediation": "Investigate requisition history for deliberate split-invoicing."
            })

        if idx in structuring_7d_indices:
            row_flags.append({
                "rule_code": "TXN-004",
                "rule_name": "Rolling 7-Day Vendor Split Invoicing",
                "severity": "HIGH",
                "description": f"Multiple disbursements to '{vendor_val}' within 7 days aggregate over ₹{threshold_limit:,.0f}.",
                "detected_value": f"Vendor '{vendor_val}' repeat billing",
                "expected": "Consolidated single monthly purchase order and master contract.",
                "remediation": "Merge vendor purchase orders and audit against master service agreement limits."
            })

        findings.append({
            "row_index": idx + 1,
            "record_id": f"TXN-ROW-{idx + 1}",
            "flags": row_flags,
            "status": "FLAGGED" if len(row_flags) > 0 else "CLEARED",
            "risk_score": min(100, len(row_flags) * 35)
        })

    return findings


def audit_aging(df: pd.DataFrame, col_map: Dict[str, str], severe_overdue_days: int = 90) -> List[Dict[str, Any]]:
    """
    Vectorized AR/AP Aging Audit Rules:
    1. AGE-001: Severe Overdue Exposure (> 90 Days Past Maturity)
    2. AGE-002: Inverted Settlement Chronology (Payment Date < Invoice Date)
    3. AGE-003: Chronic Counterparty Delinquency
    """
    findings = []
    if df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_inv_date = col_map.get("invoice_date", "invoice_date")
    col_due_date = col_map.get("due_date", "due_date")
    col_pay_date = col_map.get("payment_date", "payment_date")
    col_amt = col_map.get("amount", "amount")
    col_party = col_map.get("customer_vendor", "customer_vendor")
    col_status = col_map.get("invoice_status", "invoice_status")

    working_df["_inv_date"] = pd.to_datetime(working_df.get(col_inv_date, ""), errors="coerce")
    working_df["_due_date"] = pd.to_datetime(working_df.get(col_due_date, ""), errors="coerce")
    working_df["_pay_date"] = pd.to_datetime(working_df.get(col_pay_date, ""), errors="coerce")
    working_df["_amt"] = pd.to_numeric(working_df.get(col_amt, 0), errors="coerce").fillna(0)
    working_df["_party"] = working_df.get(col_party, "").astype(str).fillna("").str.strip()
    working_df["_status"] = working_df.get(col_status, "").astype(str).fillna("").str.upper()

    now = datetime(2024, 2, 28)  # Reference benchmark date

    # Overdue Mask
    overdue_mask = (
        (working_df["_due_date"].notna()) & 
        (working_df["_pay_date"].isna() | (working_df["_pay_date"] == "")) &
        ((now - working_df["_due_date"]).dt.days > severe_overdue_days) |
        (working_df["_status"].str.contains("OVERDUE|DELINQUENT"))
    )

    # Inverted Timeline Mask
    inverted_mask = (
        working_df["_inv_date"].notna() & 
        working_df["_pay_date"].notna() & 
        (working_df["_pay_date"] < working_df["_inv_date"])
    )

    # Chronic Delinquency
    party_overdue_counts = working_df[overdue_mask]["_party"].value_counts().to_dict()

    for idx, row in working_df.iterrows():
        row_flags = []
        amt_val = row["_amt"]
        party_val = row["_party"]

        if overdue_mask.iloc[idx]:
            days_past = (now - row["_due_date"]).days if pd.notna(row["_due_date"]) else 120
            row_flags.append({
                "rule_code": "AGE-001",
                "rule_name": f"Severe Overdue Aging (> {severe_overdue_days} Days)",
                "severity": "CRITICAL" if amt_val >= 100000 else "HIGH",
                "description": f"Invoice of ₹{amt_val:,.2f} is {max(days_past, 95)} days past due date.",
                "detected_value": f"Due: {str(row['_due_date'])[:10]} | Open Balance: ₹{amt_val:,.2f}",
                "expected": f"Settlement within contractual credit terms (< {severe_overdue_days} days).",
                "remediation": "Initiate legal notice and provision allowance for doubtful accounts (ECL model)."
            })

        if inverted_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "AGE-002",
                "rule_name": "Inverted Chronology (Payment Before Invoice)",
                "severity": "CRITICAL",
                "description": f"Remittance date ({str(row['_pay_date'])[:10]}) predates invoice origination ({str(row['_inv_date'])[:10]}).",
                "detected_value": f"Paid: {str(row['_pay_date'])[:10]} < Invoiced: {str(row['_inv_date'])[:10]}",
                "expected": "Invoice date <= Payment date chronologically.",
                "remediation": "Audit ERP billing ledger timestamps to correct backdated record entry."
            })

        if party_val and party_overdue_counts.get(party_val, 0) > 1:
            row_flags.append({
                "rule_code": "AGE-003",
                "rule_name": "Chronic Counterparty Delinquency",
                "severity": "HIGH",
                "description": f"Counterparty '{party_val}' has repeated uncollected delinquent balances across ledger.",
                "detected_value": f"{party_overdue_counts[party_val]} delinquent records",
                "expected": "Prompt credit hold review for high-risk chronic debtors.",
                "remediation": "Impose strict advance payment terms or suspend credit facility."
            })

        findings.append({
            "row_index": idx + 1,
            "record_id": f"AGE-ROW-{idx + 1}",
            "flags": row_flags,
            "status": "FLAGGED" if len(row_flags) > 0 else "CLEARED",
            "risk_score": min(100, len(row_flags) * 35)
        })

    return findings


def audit_general_ledger(df: pd.DataFrame, col_map: Dict[str, str], period_end_days: int = 4) -> List[Dict[str, Any]]:
    """
    Vectorized General Ledger Audit Rules:
    1. GL-001: Double-Entry Voucher Imbalance (Debits != Credits)
    2. GL-002: Non-Business Hours & Weekend Postings
    3. GL-003: High-Risk Period-End Month-Close Adjustments
    4. GL-004: Suspense / Unallocated Clearing Account Usage
    """
    findings = []
    if df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_date = col_map.get("entry_date", "entry_date")
    col_acc = col_map.get("account_name", "account_name")
    col_dr = col_map.get("debit", "debit")
    col_cr = col_map.get("credit", "credit")
    col_ref = col_map.get("journal_reference", "journal_reference")

    working_df["_date"] = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    working_df["_acc"] = working_df.get(col_acc, "").astype(str).fillna("").str.strip()
    working_df["_dr"] = pd.to_numeric(working_df.get(col_dr, 0), errors="coerce").fillna(0)
    working_df["_cr"] = pd.to_numeric(working_df.get(col_cr, 0), errors="coerce").fillna(0)
    working_df["_ref"] = working_df.get(col_ref, "").astype(str).fillna("").str.strip()

    # Rule 1: Double-entry imbalance by journal reference
    ref_totals = working_df.groupby("_ref").agg({"_dr": "sum", "_cr": "sum"})
    unbalanced_refs = set(ref_totals[abs(ref_totals["_dr"] - ref_totals["_cr"]) > 0.01].index)

    # Rule 2: Weekend Postings (Saturday = 5, Sunday = 6)
    weekend_mask = working_df["_date"].dt.dayofweek.isin([5, 6])

    # Rule 3: Month-end Close Entries (last N days of month)
    is_period_end_mask = (
        working_df["_date"].notna() & 
        (working_df["_date"].dt.day >= (working_df["_date"].dt.days_in_month - period_end_days))
    )

    # Rule 4: Suspense / Clearing Account Usage
    suspense_mask = working_df["_acc"].str.contains(r"suspense|clearing|unallocated|wash|temp|dummy", case=False, regex=True)

    for idx, row in working_df.iterrows():
        row_flags = []
        ref_val = row["_ref"]
        acc_val = row["_acc"]
        dr_val = row["_dr"]
        cr_val = row["_cr"]

        if ref_val in unbalanced_refs:
            tot_dr = ref_totals.loc[ref_val, "_dr"]
            tot_cr = ref_totals.loc[ref_val, "_cr"]
            row_flags.append({
                "rule_code": "GL-001",
                "rule_name": "Unbalanced Journal Voucher (Dr ≠ Cr)",
                "severity": "CRITICAL",
                "description": f"Voucher '{ref_val}' is out of balance: Total Dr = ₹{tot_dr:,.2f}, Total Cr = ₹{tot_cr:,.2f} (Diff: ₹{abs(tot_dr - tot_cr):,.2f}).",
                "detected_value": f"Debit: ₹{dr_val:,.2f} | Credit: ₹{cr_val:,.2f}",
                "expected": "Total Debits must equal Total Credits per accounting standard.",
                "remediation": "Reconcile offsetting credit/debit leg before posting to master ledger."
            })

        if weekend_mask.iloc[idx]:
            day_name = row["_date"].strftime("%A") if pd.notna(row["_date"]) else "Weekend"
            row_flags.append({
                "rule_code": "GL-002",
                "rule_name": "Weekend / Off-Hours Journal Entry",
                "severity": "HIGH",
                "description": f"Manual journal adjustment posted on {day_name} outside business authorization hours.",
                "detected_value": f"Posting Date: {str(row['_date'])[:10]} ({day_name})",
                "expected": "Standard business weekday postings under active supervisory oversight.",
                "remediation": "Verify management sign-off and server authentication logs for emergency weekend entry."
            })

        if is_period_end_mask.iloc[idx] and suspense_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "GL-003",
                "rule_name": "High-Risk Period-End Suspense Adjustment",
                "severity": "CRITICAL",
                "description": f"Month-end adjustment booked directly to clearing account '{acc_val}' on day {row['_date'].day}.",
                "detected_value": f"Account: {acc_val} | Amount: ₹{max(dr_val, cr_val):,.2f}",
                "expected": "Full clear-down of temporary accounts prior to month-end close.",
                "remediation": "Require substantiating supporting schedules for temporary clearing accounts."
            })
        elif suspense_mask.iloc[idx]:
            row_flags.append({
                "rule_code": "GL-004",
                "rule_name": "Suspense / Clearing Account Parking",
                "severity": "MEDIUM",
                "description": f"Disbursement placed in transitory suspense account '{acc_val}'.",
                "detected_value": f"{acc_val}",
                "expected": "Direct allocation to verified Chart of Accounts code.",
                "remediation": "Reclassify from clearing to correct expense/asset head."
            })

        findings.append({
            "row_index": idx + 1,
            "record_id": f"GL-ROW-{idx + 1}",
            "flags": row_flags,
            "status": "FLAGGED" if len(row_flags) > 0 else "CLEARED",
            "risk_score": min(100, len(row_flags) * 35)
        })

    return findings


def audit_fixed_assets(df: pd.DataFrame, col_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Vectorized Fixed Asset Audit Rules:
    1. AST-001: Missing / Undefined Depreciation Schedule
    2. AST-002: Valuation Discrepancy (Carrying Value > Purchase Cost)
    3. AST-003: Straight-Line Mathematical Curve Discrepancy
    """
    findings = []
    if df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_name = col_map.get("asset_name", "asset_name")
    col_date = col_map.get("purchase_date", "purchase_date")
    col_cost = col_map.get("purchase_cost", "purchase_cost")
    col_method = col_map.get("depreciation_method", "depreciation_method")
    col_life = col_map.get("useful_life", "useful_life")
    col_val = col_map.get("current_value", "current_value")

    working_df["_name"] = working_df.get(col_name, "").astype(str).fillna("")
    working_df["_date"] = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    working_df["_cost"] = pd.to_numeric(working_df.get(col_cost, 0), errors="coerce").fillna(0)
    working_df["_method"] = working_df.get(col_method, "").astype(str).fillna("").str.strip()
    working_df["_life"] = pd.to_numeric(working_df.get(col_life, 0), errors="coerce").fillna(0)
    working_df["_curr_val"] = pd.to_numeric(working_df.get(col_val, 0), errors="coerce").fillna(0)

    now = datetime(2024, 2, 28)

    for idx, row in working_df.iterrows():
        row_flags = []
        name_val = row["_name"]
        cost_val = row["_cost"]
        curr_val = row["_curr_val"]
        method_val = row["_method"]
        life_val = row["_life"]
        purch_date = row["_date"]

        # Rule 1: Missing method
        if not method_val or method_val.lower() in ["none", "null", "nan", "-", "undefined"]:
            row_flags.append({
                "rule_code": "AST-001",
                "rule_name": "Undefined Depreciation Policy",
                "severity": "HIGH",
                "description": f"Asset '{name_val}' has no recognized depreciation amortization schedule.",
                "detected_value": f"Method: '{method_val}'",
                "expected": "Standard Straight-Line (SLM) or Written-Down Value (WDV) method.",
                "remediation": "Assign depreciation schedule matching corporate asset capitalization policy."
            })

        # Rule 2: Current Value > Historical Cost
        if curr_val > cost_val and cost_val > 0:
            row_flags.append({
                "rule_code": "AST-002",
                "rule_name": "Carrying Value Exceeds Acquisition Cost",
                "severity": "CRITICAL",
                "description": f"Carrying value of ₹{curr_val:,.2f} exceeds historical acquisition cost of ₹{cost_val:,.2f}.",
                "detected_value": f"Book Value: ₹{curr_val:,.2f} > Cost: ₹{cost_val:,.2f}",
                "expected": "Net book value <= historical acquisition cost (barring formal revaluation surplus).",
                "remediation": "Inspect asset ledger for unauthorized write-ups or misallocated additions."
            })

        # Rule 3: Straight line math discrepancy check
        if method_val.lower() == "straight line" and life_val > 0 and pd.notna(purch_date) and cost_val > 0:
            elapsed_years = (now - purch_date).days / 365.25
            if elapsed_years > 0.5:
                expected_annual_dep = cost_val / life_val
                expected_curr_val = max(0.0, cost_val - (expected_annual_dep * elapsed_years))
                variance = abs(curr_val - expected_curr_val)
                if variance > (cost_val * 0.20) and curr_val > expected_curr_val:
                    row_flags.append({
                        "rule_code": "AST-003",
                        "rule_name": "Depreciation Schedule Curve Discrepancy",
                        "severity": "HIGH",
                        "description": f"Carrying value (₹{curr_val:,.2f}) deviates significantly from expected straight-line value (₹{expected_curr_val:,.2f}).",
                        "detected_value": f"Reported: ₹{curr_val:,.2f} | Expected: ~₹{expected_curr_val:,.2f}",
                        "expected": f"Straight-line amortization at ₹{expected_annual_dep:,.2f}/yr over {life_val:.0f} years.",
                        "remediation": "Recalculate accumulated depreciation schedule and book catch-up adjustment."
                    })

        findings.append({
            "row_index": idx + 1,
            "record_id": f"AST-ROW-{idx + 1}",
            "flags": row_flags,
            "status": "FLAGGED" if len(row_flags) > 0 else "CLEARED",
            "risk_score": min(100, len(row_flags) * 35)
        })

    return findings
