"""
rules_engine.py
High-Performance Vectorized Anomaly Detection Engines for AuditIQ.
Optimized for zero-latency execution on 10,000+ row files using boolean vector masks and itertuples.
Includes parameterized and dynamic reference dates for aging and fixed asset schedules.
"""

import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Set


def audit_transactions(
    df: pd.DataFrame, 
    col_map: Dict[str, str], 
    threshold_limit: float = 50000.0
) -> List[Dict[str, Any]]:
    """
    High-Performance Vectorized Transaction Audit Rules:
    1. TXN-001: Missing Approval Sign-off
    2. TXN-002: Exact Round-Number Amount over Threshold (₹50,000+)
    3. TXN-003: Near-Threshold Structuring Zone (₹45,000 - ₹49,999.99)
    4. TXN-004: Multi-Payment Vendor Structuring (7-day window)
    """
    findings = []
    if df is None or df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    n_rows = len(working_df)
    
    col_amount = col_map.get("amount", "amount")
    col_approved = col_map.get("approved_by", "approved_by")
    col_vendor = col_map.get("vendor", "vendor")
    col_date = col_map.get("date", "date")

    # Fast Vectorized Pre-processing
    amt_series = pd.to_numeric(working_df.get(col_amount, 0), errors="coerce").fillna(0)
    date_series = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    vendor_series = working_df.get(col_vendor, "").astype(str).fillna("").str.strip()
    approver_series = working_df.get(col_approved, "").astype(str).fillna("").str.strip()

    working_df["_amt"] = amt_series
    working_df["_date"] = date_series
    working_df["_vendor"] = vendor_series
    working_df["_approver"] = approver_series

    # Vectorized Rule Masks
    # Rule 1: Missing Approvals
    missing_approval_mask = (
        approver_series.isna() | 
        (approver_series == "") | 
        approver_series.str.lower().isin(["none", "null", "nan", "unassigned", "-", "n/a", "undefined"])
    ).to_numpy()

    # Rule 2: Round Numbers over threshold (₹50,000+)
    amt_arr = amt_series.to_numpy()
    round_number_mask = (
        (amt_arr >= threshold_limit) & 
        ((amt_arr % 1000 == 0) | (amt_arr % 5000 == 0))
    )

    # Rule 3: Near-Threshold Structuring (90% to < 100% of threshold)
    structuring_mask = (
        (amt_arr >= (threshold_limit * 0.90)) & 
        (amt_arr < threshold_limit)
    )

    # Rule 4: Multi-Payment Vendor Structuring within 7-Day Window (O(n) monotonic sliding window)
    structuring_7d_indices = set()
    valid_dates_mask = date_series.notna().to_numpy()
    if valid_dates_mask.any():
        for vendor_name, group in working_df.groupby("_vendor"):
            if vendor_name and len(group) > 1:
                valid_group = group.dropna(subset=["_date"]).sort_values("_date")
                n_grp = len(valid_group)
                if n_grp > 1:
                    dates = valid_group["_date"].to_numpy()
                    amounts = valid_group["_amt"].to_numpy()
                    idxs = valid_group.index.to_numpy()
                    cum_amt = np.cumsum(np.insert(amounts, 0, 0.0))
                    
                    right = 0
                    for left in range(n_grp):
                        while right < n_grp and (dates[right] - dates[left]) <= np.timedelta64(7, 'D'):
                            right += 1
                        # Window is [left, right)
                        if (right - left) > 1:
                            window_amt = cum_amt[right] - cum_amt[left]
                            if window_amt >= threshold_limit:
                                structuring_7d_indices.update(idxs[left:right])

    # Fast Row Compilation using pre-computed arrays & itertuples
    for idx, row in enumerate(working_df.itertuples(index=False)):
        row_flags = []
        amt_val = float(amt_arr[idx])
        approver_val = str(approver_series.iloc[idx])
        vendor_val = str(vendor_series.iloc[idx])

        if missing_approval_mask[idx]:
            row_flags.append({
                "rule_code": "TXN-001",
                "rule_name": "Missing Approval Sign-off",
                "severity": "CRITICAL" if amt_val >= threshold_limit else "HIGH",
                "description": f"Transaction of ₹{amt_val:,.2f} has no documented authorizing sign-off.",
                "detected_value": f"Approver: '{approver_val}'",
                "expected": f"Mandatory authorized manager sign-off for expenses.",
                "remediation": "Request physical or digital approval voucher before disbursement clearance."
            })

        if round_number_mask[idx]:
            row_flags.append({
                "rule_code": "TXN-002",
                "rule_name": "Exact Round-Number Disbursement",
                "severity": "HIGH",
                "description": f"Exact round figure of ₹{amt_val:,.2f} exceeds ₹{threshold_limit:,.0f} audit threshold.",
                "detected_value": f"₹{amt_val:,.2f}",
                "expected": "Itemized vendor billings with tax/fee fractions.",
                "remediation": "Obtain itemized vendor invoice and inspect line-item cost components."
            })

        if structuring_mask[idx]:
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


def audit_aging(
    df: pd.DataFrame, 
    col_map: Dict[str, str], 
    severe_overdue_days: int = 90,
    as_of_date: Optional[Union[datetime, str]] = None
) -> List[Dict[str, Any]]:
    """
    Vectorized AR/AP Aging Audit Rules:
    1. AGE-001: Severe Overdue Exposure (> 90 Days Past Maturity)
    2. AGE-002: Inverted Settlement Chronology (Payment Date < Invoice Date)
    3. AGE-003: Chronic Counterparty Delinquency

    Parameters:
    - as_of_date: Reference audit benchmark date. If None, dynamically resolves to max date in data or datetime.now().
    """
    findings = []
    if df is None or df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_inv_date = col_map.get("invoice_date", "invoice_date")
    col_due_date = col_map.get("due_date", "due_date")
    col_pay_date = col_map.get("payment_date", "payment_date")
    col_amt = col_map.get("amount", "amount")
    col_party = col_map.get("customer_vendor", "customer_vendor")
    col_status = col_map.get("invoice_status", "invoice_status")

    inv_date_series = pd.to_datetime(working_df.get(col_inv_date, ""), errors="coerce")
    due_date_series = pd.to_datetime(working_df.get(col_due_date, ""), errors="coerce")
    pay_date_series = pd.to_datetime(working_df.get(col_pay_date, ""), errors="coerce")
    amt_series = pd.to_numeric(working_df.get(col_amt, 0), errors="coerce").fillna(0)
    party_series = working_df.get(col_party, "").astype(str).fillna("").str.strip()
    status_series = working_df.get(col_status, "").astype(str).fillna("").str.upper()

    working_df["_inv_date"] = inv_date_series
    working_df["_due_date"] = due_date_series
    working_df["_pay_date"] = pay_date_series
    working_df["_amt"] = amt_series
    working_df["_party"] = party_series
    working_df["_status"] = status_series

    # Dynamic Benchmark Date Resolution
    if as_of_date is not None:
        ref_date = pd.to_datetime(as_of_date)
    else:
        # Resolve to the maximum observed date in the workpaper or current date
        all_valid_dates = pd.concat([inv_date_series.dropna(), due_date_series.dropna(), pay_date_series.dropna()])
        if not all_valid_dates.empty:
            ref_date = all_valid_dates.max()
        else:
            ref_date = pd.to_datetime(datetime.now())

    # Overdue Days calculation (safe from negative overflow)
    days_past_due = (ref_date - due_date_series).dt.days.fillna(0)
    days_past_due = np.maximum(0, days_past_due)

    # Overdue Mask
    unpaid_mask = pay_date_series.isna() | (pay_date_series == "")
    overdue_mask = (
        (due_date_series.notna() & unpaid_mask & (days_past_due > severe_overdue_days)) |
        (status_series.str.contains("OVERDUE|DELINQUENT", regex=True))
    ).to_numpy()

    # Inverted Timeline Mask
    inverted_mask = (
        inv_date_series.notna() & 
        pay_date_series.notna() & 
        (pay_date_series < inv_date_series)
    ).to_numpy()

    # Chronic Delinquency
    party_overdue_counts = working_df[overdue_mask]["_party"].value_counts().to_dict()

    for idx, row in enumerate(working_df.itertuples(index=False)):
        row_flags = []
        amt_val = float(amt_series.iloc[idx])
        party_val = str(party_series.iloc[idx])
        due_d = due_date_series.iloc[idx]
        inv_d = inv_date_series.iloc[idx]
        pay_d = pay_date_series.iloc[idx]

        if overdue_mask[idx]:
            dp = int(days_past_due.iloc[idx])
            row_flags.append({
                "rule_code": "AGE-001",
                "rule_name": f"Severe Overdue Aging (> {severe_overdue_days} Days)",
                "severity": "CRITICAL" if amt_val >= 100000 else "HIGH",
                "description": f"Invoice of ₹{amt_val:,.2f} is {max(dp, severe_overdue_days + 1)} days past due date.",
                "detected_value": f"Due: {str(due_d)[:10]} | Open Balance: ₹{amt_val:,.2f}",
                "expected": f"Settlement within contractual credit terms (< {severe_overdue_days} days).",
                "remediation": "Initiate legal notice and provision allowance for doubtful accounts (ECL model)."
            })

        if inverted_mask[idx]:
            row_flags.append({
                "rule_code": "AGE-002",
                "rule_name": "Inverted Chronology (Payment Before Invoice)",
                "severity": "CRITICAL",
                "description": f"Remittance date ({str(pay_d)[:10]}) predates invoice origination ({str(inv_d)[:10]}).",
                "detected_value": f"Paid: {str(pay_d)[:10]} < Invoiced: {str(inv_d)[:10]}",
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


def audit_general_ledger(
    df: pd.DataFrame, 
    col_map: Dict[str, str], 
    period_end_days: int = 4
) -> List[Dict[str, Any]]:
    """
    Vectorized General Ledger Audit Rules:
    1. GL-001:  Double-Entry Voucher Imbalance (Debits != Credits), for rows
                carrying a real journal/voucher reference.
    2. GL-001B: Missing Journal Reference (Balance Unverifiable) -- rows with
                no reference are never pooled together to "check" a balance
                across unrelated transactions.
    3. GL-002:  Non-Business Hours & Weekend Postings
    4. GL-003:  High-Risk Period-End Month-Close Adjustments
    5. GL-004:  Suspense / Unallocated Clearing Account Usage

    BUGFIX NOTES (see inline comments for detail):
    - Previously, `groupby("_ref")` silently lumped every row with a blank
      journal_reference into one bucket, summing debits/credits across
      unrelated transactions and stamping a false CRITICAL "unbalanced
      voucher" flag on every blank-ref row. This is fixed by excluding
      blank/placeholder references from the balance check entirely.
    - References are now case/whitespace-normalized so "JV-001" and
      "jv-001" aren't treated as two different (and spuriously
      "unbalanced") vouchers.
    - A consistency assertion at the end cross-checks the per-row register
      against the aggregate unbalanced-voucher set, so a register/summary
      mismatch fails loudly here instead of silently reaching the UI.
    """
    findings = []
    if df is None or df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_date = col_map.get("entry_date", "entry_date")
    col_acc = col_map.get("account_name", "account_name")
    col_dr = col_map.get("debit", "debit")
    col_cr = col_map.get("credit", "credit")
    col_ref = col_map.get("journal_reference", "journal_reference")

    date_series = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    acc_series = working_df.get(col_acc, "").astype(str).fillna("").str.strip()
    dr_series = pd.to_numeric(working_df.get(col_dr, 0), errors="coerce").fillna(0)
    cr_series = pd.to_numeric(working_df.get(col_cr, 0), errors="coerce").fillna(0)

    # Keep the original (display) reference separately from the normalized
    # one used for grouping, so messages still show what was actually in the file.
    raw_ref_series = working_df.get(col_ref, "").astype(str).fillna("").str.strip()
    ref_series = raw_ref_series.str.upper()

    working_df["_date"] = date_series
    working_df["_acc"] = acc_series
    working_df["_dr"] = dr_series
    working_df["_cr"] = cr_series
    working_df["_ref"] = ref_series

    # --- BUGFIX (GL-001) ---
    # Rows with a missing/blank/placeholder journal reference must NEVER be
    # grouped together as if they were one voucher -- doing so sums debits and
    # credits across unrelated transactions and produces a bogus "imbalance"
    # that then gets stamped onto every blank-ref row. This is very likely
    # the exact source of the register/summary contradiction: a downstream
    # summary that (correctly) counts only *named* unbalanced voucher IDs
    # reports 0, while the per-row register still carried GL-001 on every
    # blank-ref row because "" itself qualified as "unbalanced".
    MISSING_REF_TOKENS = {"", "NONE", "NULL", "NAN", "-", "N/A", "UNDEFINED"}
    has_ref_mask = ~ref_series.isin(MISSING_REF_TOKENS)

    ref_totals = (
        working_df[has_ref_mask]
        .groupby("_ref")
        .agg({"_dr": "sum", "_cr": "sum"})
    )
    BALANCE_TOLERANCE = 0.01  # absorbs float rounding noise only, not real mismatches
    unbalanced_refs = set(
        ref_totals[abs(ref_totals["_dr"] - ref_totals["_cr"]) > BALANCE_TOLERANCE].index
    )

    # Rule 2: Weekend Postings (Saturday = 5, Sunday = 6)
    weekend_mask = date_series.dt.dayofweek.isin([5, 6]).to_numpy()

    # Rule 3: Month-end Close Entries (last N days of month)
    is_period_end_mask = (
        date_series.notna() & 
        (date_series.dt.day >= (date_series.dt.days_in_month - period_end_days))
    ).to_numpy()

    # Rule 4: Suspense / Clearing Account Usage
    suspense_mask = acc_series.str.contains(r"suspense|clearing|unallocated|wash|temp|dummy", case=False, regex=True).to_numpy()

    for idx, row in enumerate(working_df.itertuples(index=False)):
        row_flags = []
        ref_val = str(ref_series.iloc[idx])
        raw_ref_val = str(raw_ref_series.iloc[idx])
        acc_val = str(acc_series.iloc[idx])
        dr_val = float(dr_series.iloc[idx])
        cr_val = float(cr_series.iloc[idx])
        date_val = date_series.iloc[idx]

        if ref_val in MISSING_REF_TOKENS:
            # Never pooled with other blank-ref rows -- flagged honestly as
            # "can't verify", not as a false CRITICAL imbalance.
            row_flags.append({
                "rule_code": "GL-001B",
                "rule_name": "Missing Journal Reference (Balance Unverifiable)",
                "severity": "MEDIUM",
                "description": "Entry has no journal/voucher reference, so its debit/credit balance cannot be matched against a counter-leg.",
                "detected_value": f"Reference: '{raw_ref_val}' | Debit: ₹{dr_val:,.2f} | Credit: ₹{cr_val:,.2f}",
                "expected": "Every posting carries a unique journal reference linking it to its offsetting leg(s).",
                "remediation": "Assign a valid journal/voucher reference and re-run the balance check."
            })
        elif ref_val in unbalanced_refs:
            tot_dr = ref_totals.loc[ref_val, "_dr"]
            tot_cr = ref_totals.loc[ref_val, "_cr"]
            row_flags.append({
                "rule_code": "GL-001",
                "rule_name": "Unbalanced Journal Voucher (Dr ≠ Cr)",
                "severity": "CRITICAL",
                "description": f"Voucher '{raw_ref_val}' is out of balance: Total Dr = ₹{tot_dr:,.2f}, Total Cr = ₹{tot_cr:,.2f} (Diff: ₹{abs(tot_dr - tot_cr):,.2f}).",
                "detected_value": f"Debit: ₹{dr_val:,.2f} | Credit: ₹{cr_val:,.2f}",
                "expected": "Total Debits must equal Total Credits per accounting standard.",
                "remediation": "Reconcile offsetting credit/debit leg before posting to master ledger."
            })

        if weekend_mask[idx]:
            day_name = date_val.strftime("%A") if pd.notna(date_val) else "Weekend"
            row_flags.append({
                "rule_code": "GL-002",
                "rule_name": "Weekend / Off-Hours Journal Entry",
                "severity": "HIGH",
                "description": f"Manual journal adjustment posted on {day_name} outside business authorization hours.",
                "detected_value": f"Posting Date: {str(date_val)[:10]} ({day_name})",
                "expected": "Standard business weekday postings under active supervisory oversight.",
                "remediation": "Verify management sign-off and server authentication logs for emergency weekend entry."
            })

        if is_period_end_mask[idx] and suspense_mask[idx]:
            day_num = date_val.day if pd.notna(date_val) else "Month-End"
            row_flags.append({
                "rule_code": "GL-003",
                "rule_name": "High-Risk Period-End Suspense Adjustment",
                "severity": "CRITICAL",
                "description": f"Month-end adjustment booked directly to clearing account '{acc_val}' on day {day_num}.",
                "detected_value": f"Account: {acc_val} | Amount: ₹{max(dr_val, cr_val):,.2f}",
                "expected": "Full clear-down of temporary accounts prior to month-end close.",
                "remediation": "Require substantiating supporting schedules for temporary clearing accounts."
            })
        elif suspense_mask[idx]:
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

    # --- Sentry-style consistency guard ---
    # Recompute, from the finished per-row register itself, which reference
    # IDs actually carry a GL-001 flag, and compare that to the aggregate
    # `unbalanced_refs` set any downstream summary/dashboard would use.
    # If a future edit reintroduces a divergence between "what the register
    # shows" and "what the summary counts", this raises immediately instead
    # of shipping a silently contradictory result to the UI.
    distinct_flagged_refs = {
        str(ref_series.iloc[i])
        for i, f in enumerate(findings)
        if any(fl["rule_code"] == "GL-001" for fl in f["flags"])
    }
    if distinct_flagged_refs != unbalanced_refs:
        raise AssertionError(
            "GL-001 consistency check failed: per-row register flags "
            f"{distinct_flagged_refs} but the aggregate unbalanced-voucher "
            f"set computed {unbalanced_refs}. Register and summary would "
            "disagree downstream -- investigate before returning findings."
        )

    return findings


def audit_fixed_assets(
    df: pd.DataFrame, 
    col_map: Dict[str, str],
    as_of_date: Optional[Union[datetime, str]] = None
) -> List[Dict[str, Any]]:
    """
    Vectorized Fixed Asset Audit Rules:
    1. AST-001: Missing / Undefined Depreciation Schedule
    2. AST-002: Valuation Discrepancy (Carrying Value > Purchase Cost)
    3. AST-003: Straight-Line Mathematical Curve Discrepancy

    Parameters:
    - as_of_date: Reference audit benchmark date. If None, dynamically resolves to max date in data or datetime.now().
    """
    findings = []
    if df is None or df.empty:
        return findings

    working_df = df.copy().reset_index(drop=True)
    col_name = col_map.get("asset_name", "asset_name")
    col_date = col_map.get("purchase_date", "purchase_date")
    col_cost = col_map.get("purchase_cost", "purchase_cost")
    col_method = col_map.get("depreciation_method", "depreciation_method")
    col_life = col_map.get("useful_life", "useful_life")
    col_val = col_map.get("current_value", "current_value")

    name_series = working_df.get(col_name, "").astype(str).fillna("")
    date_series = pd.to_datetime(working_df.get(col_date, ""), errors="coerce")
    cost_series = pd.to_numeric(working_df.get(col_cost, 0), errors="coerce").fillna(0)
    method_series = working_df.get(col_method, "").astype(str).fillna("").str.strip()
    life_series = pd.to_numeric(working_df.get(col_life, 0), errors="coerce").fillna(0)
    curr_val_series = pd.to_numeric(working_df.get(col_val, 0), errors="coerce").fillna(0)

    working_df["_name"] = name_series
    working_df["_date"] = date_series
    working_df["_cost"] = cost_series
    working_df["_method"] = method_series
    working_df["_life"] = life_series
    working_df["_curr_val"] = curr_val_series

    # Dynamic Benchmark Date Resolution
    if as_of_date is not None:
        ref_date = pd.to_datetime(as_of_date)
    else:
        valid_dates = date_series.dropna()
        if not valid_dates.empty:
            ref_date = valid_dates.max()
        else:
            ref_date = pd.to_datetime(datetime.now())

    for idx, row in enumerate(working_df.itertuples(index=False)):
        row_flags = []
        name_val = str(name_series.iloc[idx])
        cost_val = float(cost_series.iloc[idx])
        curr_val = float(curr_val_series.iloc[idx])
        method_val = str(method_series.iloc[idx])
        life_val = float(life_series.iloc[idx])
        purch_date = date_series.iloc[idx]

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

        # Rule 3: Straight line math discrepancy check (handles future/current dates cleanly without negative elapsed years)
        if method_val.lower() in ["straight line", "slm", "straight-line"] and life_val > 0 and pd.notna(purch_date) and cost_val > 0:
            diff_days = (ref_date - purch_date).days
            elapsed_years = max(0.0, diff_days / 365.25)
            if elapsed_years > 0.5:
                expected_annual_dep = cost_val / life_val
                expected_curr_val = max(0.0, cost_val - (expected_annual_dep * min(elapsed_years, life_val)))
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


def verify_report_amounts(findings: List[Dict[str, Any]], report_text: str) -> None:
    """
    Boundary Verification Guard:
    Extracts every ₹ figure quoted in the rendered report and confirms it
    appears verbatim somewhere in the source findings. Any amount in the
    report that isn't traceable to a finding is a fabrication/corruption
    and must fail loudly, regardless of which file or module produced it.
    """
    source_amounts = set()
    amount_pattern = re.compile(r"₹[\d,]+\.\d{2}")
    
    for f in findings:
        for fl in f.get("flags", []):
            for field in ("description", "detected_value", "expected"):
                source_amounts.update(amount_pattern.findall(fl.get(field, "")))

    report_amounts = set(amount_pattern.findall(report_text))
    unverified = report_amounts - source_amounts
    
    if unverified:
        raise AssertionError(
            f"Report contains {len(unverified)} rupee amount(s) with no "
            f"matching source finding — possible fabrication/corruption: {unverified}"
        )
