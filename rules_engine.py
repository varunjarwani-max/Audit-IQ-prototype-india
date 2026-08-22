"""
rules_engine.py - Audit Rule Detection Engine for AuditIQ
"""
import pandas as pd
import numpy as np
from datetime import datetime

def format_currency(val: float) -> str:
    """Utility helper to guarantee strict 2-decimal currency formatting."""
    return f"₹{float(val):,.2f}"


def audit_transactions(df: pd.DataFrame, col_map: dict = None, threshold_limit: float = 50000.0) -> list:
    """
    Audits transactions dataset for:
    - TXN-001: Missing approval sign-off
    - TXN-002: Exact round figure disbursement (above threshold)
    - TXN-003: Near-Threshold Structuring
    - TXN-004: 7-day rolling split-invoicing aggregate
    """
    results = []
    
    date_col = col_map.get("date", "date") if col_map else "date"
    amt_col = col_map.get("amount", "amount") if col_map else "amount"
    vendor_col = col_map.get("vendor", "vendor") if col_map else "vendor"
    appr_col = col_map.get("approved_by", "approved_by") if col_map else "approved_by"

    # Use a unique positional index for internal calculations so uploaded files
    # with duplicate labels cannot break rolling-window assignment.
    df_clean = df.copy().reset_index(drop=True)
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")

    # Vectorized calculation for TXN-004 (7-Day Split Invoicing).
    # Assign each vendor's rolling results by its original row positions instead
    # of by the date index returned by pandas. This avoids duplicate-label
    # reindexing errors when transactions share a date or source index.
    df_clean['rolling_sum'] = 0.0
    df_clean['rolling_count'] = 0
    if date_col in df_clean.columns and amt_col in df_clean.columns and vendor_col in df_clean.columns:
        df_clean[amt_col] = pd.to_numeric(df_clean[amt_col], errors="coerce")
        df_sorted = df_clean.dropna(subset=[date_col]).sort_values(by=[vendor_col, date_col])
        for _, vendor_rows in df_sorted.groupby(vendor_col, sort=False, dropna=False):
            rolling = vendor_rows.rolling('7D', on=date_col)[amt_col]
            df_clean.loc[vendor_rows.index, 'rolling_sum'] = rolling.sum().to_numpy()
            df_clean.loc[vendor_rows.index, 'rolling_count'] = rolling.count().to_numpy()

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        amt = float(row[amt_col]) if pd.notnull(row.get(amt_col)) else 0.0
        vendor = str(row.get(vendor_col, "Unknown Vendor"))
        appr = str(row.get(appr_col, "")).strip()

        # TXN-001: Missing approval
        if not appr or appr.lower() in ["nan", "none", "null", "''", ""]:
            flags.append({
                "rule_code": "TXN-001",
                "rule_name": "Missing Sign-off Approval",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Transaction of {format_currency(amt)} lacks documented authorizing approval sign-off.",
                "remediation": "Obtain signed physical or digital approval voucher before clearance."
            })

        # TXN-002: Exact round-number disbursement (Threshold enforced)
        if amt >= threshold_limit and amt % 1000 == 0:
            flags.append({
                "rule_code": "TXN-002",
                "rule_name": "Exact Round-Number Disbursement",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Exact round figure disbursement of {format_currency(amt)} exceeds policy threshold.",
                "remediation": "Obtain itemized vendor invoice; inspect line-item cost breakdown."
            })

        # TXN-003: Near-Threshold Structuring
        if (threshold_limit * 0.95) <= amt < threshold_limit:
            flags.append({
                "rule_code": "TXN-003",
                "rule_name": "Near-Threshold Structuring Risk",
                "severity": "CRITICAL",
                "amount": amt,
                "description": f"Amount {format_currency(amt)} sits suspiciously just below the {format_currency(threshold_limit)} limit.",
                "remediation": "Verify if multiple similar invoices exist to bypass manager approval limits."
            })

        # TXN-004: Split Invoicing Detection
        rolling_count = row.get('rolling_count', 0)
        rolling_sum = row.get('rolling_sum', 0.0)
        
        if rolling_count > 1 and rolling_sum >= threshold_limit:
            flags.append({
                "rule_code": "TXN-004",
                "rule_name": "7-Day Split Invoicing Breach",
                "severity": "HIGH",
                "amount": rolling_sum,
                "description": f"Multiple disbursements to '{vendor}' within 7 days aggregate to {format_currency(rolling_sum)}.",
                "remediation": "Merge purchase orders & audit against master service agreement limits."
            })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results


def audit_aging(df: pd.DataFrame, col_map: dict = None, severe_overdue_days: int = 90, as_of_date: str = None) -> list:
    """
    Audits AR/AP Aging dataset for:
    - AGE-001: Severe overdue invoice
    - AGE-002: Inverted chronology (Payment before Invoice)
    - AGE-003: Chronic counterparty delinquency
    """
    results = []
    amt_col = col_map.get("amount", "amount") if col_map else "amount"
    due_col = col_map.get("due_date", "due_date") if col_map else "due_date"
    inv_col = col_map.get("invoice_date", "invoice_date") if col_map else "invoice_date"
    pay_col = col_map.get("payment_date", "payment_date") if col_map else "payment_date"
    cp_col = col_map.get("counterparty", "counterparty") if col_map else "counterparty"

    df_clean = df.copy()
    for col in [due_col, inv_col, pay_col]:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")

    # Dynamic as_of_date resolution
    if as_of_date:
        ref_date = pd.to_datetime(as_of_date)
    else:
        max_date = df_clean[due_col].max() if due_col in df_clean.columns else pd.NaT
        ref_date = max_date if pd.notna(max_date) else pd.to_datetime(datetime.today())

    # Pre-calculate AGE-003: Only count OVERDUE invoices for delinquency
    cp_overdue_counts = {}
    if due_col in df_clean.columns and cp_col in df_clean.columns:
        overdue_mask = (ref_date - df_clean[due_col]).dt.days > 0
        cp_overdue_counts = df_clean.loc[overdue_mask, cp_col].value_counts().to_dict()

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        amt = float(row[amt_col]) if pd.notnull(row.get(amt_col)) else 0.0
        cp = str(row.get(cp_col, "Unknown Counterparty"))
        due = row.get(due_col)
        inv = row.get(inv_col)
        pay = row.get(pay_col)

        # AGE-001: Severe Overdue
        overdue_days = (ref_date - due).days if pd.notnull(due) else 0
        if overdue_days > severe_overdue_days:
            sev = "CRITICAL" if overdue_days > 300 or amt > 100000 else "HIGH"
            flags.append({
                "rule_code": "AGE-001",
                "rule_name": "Severe Overdue Invoice",
                "severity": sev,
                "amount": amt,
                "description": f"Invoice of {format_currency(amt)} for '{cp}' is {overdue_days} days overdue past benchmark date.",
                "remediation": "Initiate formal legal notice and set up ECL doubtful account provisioning."
            })

        # AGE-002: Inverted Chronology
        if pd.notnull(inv) and pd.notnull(pay) and pay < inv:
            flags.append({
                "rule_code": "AGE-002",
                "rule_name": "Inverted Document Chronology",
                "severity": "CRITICAL",
                "amount": amt,
                "description": f"Payment logged on {pay.strftime('%Y-%m-%d')} before invoice generation on {inv.strftime('%Y-%m-%d')}.",
                "remediation": "Investigate potential ghost invoice or premature fund disbursement."
            })

        # AGE-003: Chronic Delinquency
        if cp_overdue_counts.get(cp, 0) >= 2 and overdue_days > 0:
            flags.append({
                "rule_code": "AGE-003",
                "rule_name": "Chronic Counterparty Delinquency",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Counterparty '{cp}' has {cp_overdue_counts[cp]} active delinquent records across ledger.",
                "remediation": "Impose strict advance payment terms or suspend credit facility."
            })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results


def audit_general_ledger(df: pd.DataFrame, col_map: dict = None, period_end_days: int = 4) -> list:
    """
    Audits General Ledger dataset for:
    - GL-001: Unbalanced journal voucher (Debit != Credit)
    - GL-002: Off-hours / Weekend manual posting
    """
    results = []
    dr_col = col_map.get("debit", "debit") if col_map else "debit"
    cr_col = col_map.get("credit", "credit") if col_map else "credit"
    date_col = col_map.get("posting_date", "posting_date") if col_map else "posting_date"
    vouch_col = col_map.get("voucher_id", "voucher_id") if col_map else "voucher_id"

    df_clean = df.copy()
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")

    voucher_balances = {}
    if vouch_col in df_clean.columns:
        grouped = df_clean.groupby(vouch_col)
        for v_id, group in grouped:
            total_dr = group[dr_col].sum() if dr_col in group.columns else 0.0
            total_cr = group[cr_col].sum() if cr_col in group.columns else 0.0
            voucher_balances[v_id] = (total_dr, total_cr)

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        dr = float(row[dr_col]) if dr_col in row and pd.notnull(row[dr_col]) else 0.0
        cr = float(row[cr_col]) if cr_col in row and pd.notnull(row[cr_col]) else 0.0
        v_id = str(row.get(vouch_col, f"VOUCH-{row_index}"))
        p_date = row.get(date_col)

        if v_id in voucher_balances:
            tot_dr, tot_cr = voucher_balances[v_id]
            diff = abs(tot_dr - tot_cr)
            if diff > 0.01:
                flags.append({
                    "rule_code": "GL-001",
                    "rule_name": "Unbalanced Journal Voucher",
                    "severity": "CRITICAL",
                    "amount": diff,
                    "debit": tot_dr,
                    "credit": tot_cr,
                    "description": f"Voucher '{v_id}' is out of balance: Total Dr = {format_currency(tot_dr)}, Total Cr = {format_currency(tot_cr)} (Diff: {format_currency(diff)}).",
                    "remediation": "Reconcile offsetting credit/debit leg before posting to master ledger."
                })

        if pd.notnull(p_date) and p_date.weekday() in [5, 6]:
            day_name = p_date.strftime("%A")
            date_str = p_date.strftime("%Y-%m-%d")
            flags.append({
                "rule_code": "GL-002",
                "rule_name": "Weekend Manual Journal Entry",
                "severity": "HIGH",
                "amount": max(dr, cr),
                "description": f"Manual journal adjustment posted on {day_name} ({date_str}) outside business authorization hours.",
                "remediation": "Verify management sign-off and server authentication logs for emergency weekend entry."
            })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results


def audit_fixed_assets(df: pd.DataFrame, col_map: dict = None, as_of_date: str = None) -> list:
    """
    Audits Fixed Assets dataset for:
    - AST-001: Undefined depreciation method
    - AST-002: Book value exceeds historical acquisition cost
    - AST-003: Depreciation curve / WDV deviation anomaly
    """
    results = []
    cost_col = col_map.get("cost", "cost") if col_map else "cost"
    bv_col = col_map.get("book_value", "book_value") if col_map else "book_value"
    method_col = col_map.get("method", "method") if col_map else "method"
    asset_col = col_map.get("asset_name", "asset_name") if col_map else "asset_name"
    date_col = col_map.get("purchase_date", "purchase_date") if col_map else "purchase_date"
    life_col = col_map.get("useful_life", "useful_life") if col_map else "useful_life"
    
    df_clean = df.copy()
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")
        
    ref_date = pd.to_datetime(as_of_date) if as_of_date else pd.to_datetime(datetime.today())

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        cost = float(row[cost_col]) if cost_col in row and pd.notnull(row[cost_col]) else 0.0
        bv = float(row[bv_col]) if bv_col in row and pd.notnull(row[bv_col]) else 0.0
        method = str(row.get(method_col, "")).strip()
        asset_name = str(row.get(asset_col, f"Asset #{row_index}"))
        p_date = row.get(date_col)
        life = float(row[life_col]) if life_col in row and pd.notnull(row[life_col]) else 0.0

        # AST-001: Undefined depreciation
        if not method or method.lower() in ["nan", "none", "null", "''", ""]:
            flags.append({
                "rule_code": "AST-001",
                "rule_name": "Undefined Depreciation Policy",
                "severity": "HIGH",
                "amount": cost,
                "description": f"Asset '{asset_name}' has no recognized depreciation amortization schedule.",
                "remediation": "Assign depreciation schedule matching corporate asset capitalization policy."
            })

        # AST-002: BV > Cost
        if bv > cost:
            flags.append({
                "rule_code": "AST-002",
                "rule_name": "Carrying Value Exceeds Cost",
                "severity": "CRITICAL",
                "amount": bv - cost,
                "book_value": bv,
                "cost": cost,
                "description": f"Carrying value of {format_currency(bv)} exceeds historical acquisition cost of {format_currency(cost)}.",
                "remediation": "Inspect asset ledger for unauthorized write-ups or misallocated additions."
            })

        # AST-003: Depreciation Curve Deviation
        if pd.notnull(p_date) and cost > 0 and life > 0:
            age_years = (ref_date - p_date).days / 365.25
            if age_years >= 1.0:
                expected_bv = max(0.0, cost - (cost / life * age_years))
                if (bv - expected_bv) > (cost * 0.15):
                    flags.append({
                        "rule_code": "AST-003",
                        "rule_name": "Depreciation Curve Anomaly",
                        "severity": "HIGH",
                        "amount": bv - expected_bv,
                        "description": f"Asset '{asset_name}' book value ({format_currency(bv)}) is highly inflated vs. expected straight-line depreciation ({format_currency(expected_bv)}).",
                        "remediation": "Verify accumulated depreciation ledger and ensure consistent write-down procedures."
                    })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results
