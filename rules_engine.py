"""
rules_engine.py - Audit Rule Detection Engine for AuditIQ
"""
import pandas as pd
import numpy as np
from datetime import datetime


def format_currency(val: float) -> str:
    """Utility helper to guarantee strict 2-decimal currency formatting."""
    return f"₹{float(val):,.2f}"


def audit_transactions(df: pd.DataFrame, col_map: dict = None) -> list:
    """
    Audits transactions dataset without threshold limits for:
    - TXN-001: Missing approval sign-off
    - TXN-002: Exact round figure disbursement
    - TXN-004: 7-day rolling split-invoicing aggregate
    """
    results = []
    
    date_col = col_map.get("date", "date") if col_map else "date"
    amt_col = col_map.get("amount", "amount") if col_map else "amount"
    vendor_col = col_map.get("vendor", "vendor") if col_map else "vendor"
    appr_col = col_map.get("approved_by", "approved_by") if col_map else "approved_by"

    df_clean = df.copy()
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")

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

        # TXN-002: Exact round-number disbursement
        if amt > 0 and amt % 1000 == 0:
            flags.append({
                "rule_code": "TXN-002",
                "rule_name": "Exact Round-Number Disbursement",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Exact round figure disbursement of {format_currency(amt)} detected.",
                "remediation": "Obtain itemized vendor invoice; inspect line-item cost breakdown."
            })

        # TXN-004: Split Invoicing Detection (Rolling 7 days for same vendor)
        if date_col in df_clean.columns and pd.notnull(row[date_col]):
            row_date = row[date_col]
            vendor_txns = df_clean[
                (df_clean[vendor_col] == vendor) &
                (df_clean[date_col] >= row_date - pd.Timedelta(days=7)) &
                (df_clean[date_col] <= row_date)
            ]
            rolling_sum = vendor_txns[amt_col].sum()
            if len(vendor_txns) > 1:
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
    - AGE-003: Chronic counterparty delinquency
    """
    results = []
    amt_col = col_map.get("amount", "amount") if col_map else "amount"
    due_col = col_map.get("due_date", "due_date") if col_map else "due_date"
    cp_col = col_map.get("counterparty", "counterparty") if col_map else "counterparty"

    ref_date = pd.to_datetime(as_of_date) if as_of_date else pd.to_datetime("2026-05-01")
    df_clean = df.copy()
    if due_col in df_clean.columns:
        df_clean[due_col] = pd.to_datetime(df_clean[due_col], errors="coerce")

    cp_counts = df_clean[cp_col].value_counts().to_dict() if cp_col in df_clean.columns else {}

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        amt = float(row[amt_col]) if pd.notnull(row.get(amt_col)) else 0.0
        cp = str(row.get(cp_col, "Unknown Counterparty"))
        due = row.get(due_col)

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

        if cp_counts.get(cp, 0) >= 2:
            flags.append({
                "rule_code": "AGE-003",
                "rule_name": "Chronic Counterparty Delinquency",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Counterparty '{cp}' has {cp_counts[cp]} repeated uncollected delinquent records across ledger.",
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
    """
    results = []
    cost_col = col_map.get("cost", "cost") if col_map else "cost"
    bv_col = col_map.get("book_value", "book_value") if col_map else "book_value"
    method_col = col_map.get("method", "depreciation_method") if col_map else "depreciation_method"
    asset_col = col_map.get("asset_name", "asset_description") if col_map else "asset_description"

    for idx, row in df.iterrows():
        row_index = idx + 1
        flags = []
        cost = float(row[cost_col]) if cost_col in row and pd.notnull(row[cost_col]) else 0.0
        bv = float(row[bv_col]) if bv_col in row and pd.notnull(row[bv_col]) else 0.0
        method = str(row.get(method_col, "")).strip()
        asset_name = str(row.get(asset_col, f"Asset #{row_index}"))

        if not method or method.lower() in ["nan", "none", "null", "''", ""]:
            flags.append({
                "rule_code": "AST-001",
                "rule_name": "Undefined Depreciation Policy",
                "severity": "HIGH",
                "amount": cost,
                "description": f"Asset '{asset_name}' has no recognized depreciation amortization schedule.",
                "remediation": "Assign depreciation schedule matching corporate asset capitalization policy."
            })

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

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results
