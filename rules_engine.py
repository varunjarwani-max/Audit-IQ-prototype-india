"""
rules_engine.py - Audit Rule Detection Engine for AuditIQ
"""
import pandas as pd
import numpy as np
from datetime import datetime

DEFAULT_TRANSACTION_THRESHOLD = 50000.0
DEFAULT_SEVERE_OVERDUE_DAYS = 90
DEFAULT_PERIOD_END_DAYS = 4
DEFAULT_ASSET_VARIANCE_RATIO = 0.10


def format_currency(val: float) -> str:
    """Utility helper to guarantee strict 2-decimal currency formatting."""
    return f"₹{float(val):,.2f}"


def _safe_number(value, default: float = 0.0) -> float:
    """Parse uploaded numeric values without crashing on commas, symbols, or blanks."""
    if pd.isna(value):
        return default
    if isinstance(value, str):
        value = value.replace(",", "").replace("₹", "").replace("$", "").strip()
    parsed = pd.to_numeric(value, errors="coerce")
    return float(parsed) if pd.notna(parsed) else default


def _normalized_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("_", " ").replace("-", " ")


def audit_transactions(df: pd.DataFrame, col_map: dict = None, threshold_limit: float = DEFAULT_TRANSACTION_THRESHOLD) -> list:
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
    account_col = col_map.get("account_code", "account_code") if col_map else "account_code"
    currency_col = col_map.get("currency", "currency") if col_map else "currency"
    match_col = col_map.get("three_way_match_status", "three_way_match_status") if col_map else "three_way_match_status"
    duplicate_col = col_map.get("duplicate_payment_candidate", "duplicate_payment_candidate") if col_map else "duplicate_payment_candidate"

    # Use a unique positional index for internal calculations so uploaded files
    # with duplicate labels cannot break rolling-window assignment.
    df_clean = df.copy().reset_index(drop=True)
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")
    if amt_col in df_clean.columns:
        df_clean[amt_col] = df_clean[amt_col].map(_safe_number)

    # Vectorized calculation for TXN-004 (7-Day Split Invoicing)
    df_clean['rolling_sum'] = 0.0
    df_clean['rolling_count'] = 0
    if date_col in df_clean.columns and amt_col in df_clean.columns and vendor_col in df_clean.columns:
        df_sorted = df_clean.dropna(subset=[date_col]).sort_values(by=[vendor_col, date_col])
        if not df_sorted.empty:
            rolling_sums = df_sorted.groupby(vendor_col).rolling('7D', on=date_col)[amt_col].sum().reset_index(level=0, drop=True)
            rolling_counts = df_sorted.groupby(vendor_col).rolling('7D', on=date_col)[amt_col].count().reset_index(level=0, drop=True)

            # Assign positionally instead of allowing pandas to align the rolling
            # Series by its date index. Repeated transaction dates create duplicate
            # labels in that Series, which makes label-based reindexing fail.
            df_clean.loc[df_sorted.index, 'rolling_sum'] = rolling_sums.to_numpy()
            df_clean.loc[df_sorted.index, 'rolling_count'] = rolling_counts.to_numpy()

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        amt = _safe_number(row.get(amt_col))
        vendor = str(row.get(vendor_col, "Unknown Vendor")).strip()
        appr = "" if pd.isna(row.get(appr_col)) else str(row.get(appr_col)).strip()
        match_status = _normalized_text(row.get(match_col, ""))
        duplicate_status = _normalized_text(row.get(duplicate_col, ""))
        currency = "" if pd.isna(row.get(currency_col)) else str(row.get(currency_col)).strip().upper()

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

        if match_status and match_status not in {"matched", "match", "ok", "pass", "passed", "yes"}:
            flags.append({
                "rule_code": "TXN-005", "rule_name": "Three-Way Match Exception", "severity": "CRITICAL",
                "amount": abs(amt), "description": f"Transaction for {format_currency(abs(amt))} has three-way match status '{row.get(match_col)}'.",
                "remediation": "Reconcile purchase order, receipt, and supplier invoice before payment."
            })

        if duplicate_status in {"yes", "true", "1", "candidate", "duplicate", "flagged"}:
            flags.append({
                "rule_code": "TXN-006", "rule_name": "Duplicate Payment Candidate", "severity": "CRITICAL",
                "amount": abs(amt), "description": f"Transaction for {format_currency(abs(amt))} is marked as a duplicate-payment candidate.",
                "remediation": "Block settlement and compare invoice, vendor, amount, and payment references."
            })

        if amt < 0:
            flags.append({
                "rule_code": "TXN-007", "rule_name": "Negative Transaction Amount", "severity": "HIGH",
                "amount": abs(amt), "description": f"Negative transaction amount of {format_currency(amt)} requires credit-note or reversal support.",
                "remediation": "Verify the original entry, credit note, authorization, and reversal linkage."
            })

        if currency_col in df_clean.columns and not currency:
            flags.append({
                "rule_code": "TXN-008", "rule_name": "Missing Currency Code", "severity": "MEDIUM",
                "amount": abs(amt), "description": "Transaction currency is blank, preventing reliable valuation and aggregation.",
                "remediation": "Populate a valid ISO currency code and validate the applicable exchange rate."
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
        
        # Emit once when a sequence of individually sub-threshold payments first
        # crosses the approval limit. This avoids relabeling every later payment
        # in an otherwise ordinary high-volume vendor window as structuring.
        prior_window_sum = rolling_sum - max(amt, 0.0)
        if (
            0 < amt < threshold_limit
            and rolling_count > 1
            and prior_window_sum < threshold_limit <= rolling_sum
        ):
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


def audit_aging(df: pd.DataFrame, col_map: dict = None, severe_overdue_days: int = DEFAULT_SEVERE_OVERDUE_DAYS, as_of_date: str = None) -> list:
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
    status_col = col_map.get("invoice_status", "invoice_status") if col_map else "invoice_status"

    df_clean = df.copy().reset_index(drop=True)
    for col in [due_col, inv_col, pay_col]:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")

    # A supplied benchmark is authoritative. Otherwise use today's date so aging
    # is meaningful even when the file contains only old or future due dates.
    parsed_ref_date = pd.to_datetime(as_of_date, errors="coerce") if as_of_date else pd.Timestamp.today()
    ref_date = parsed_ref_date.normalize() if pd.notna(parsed_ref_date) else pd.Timestamp.today().normalize()

    closed_statuses = {
        "paid", "cleared", "settled", "closed", "complete", "completed",
        "fully paid", "paid in full", "reconciled", "written off", "write off",
    }

    def is_open_invoice(row) -> bool:
        payment_date = row.get(pay_col) if pay_col in df_clean.columns else pd.NaT
        status = _normalized_text(row.get(status_col, "")) if status_col in df_clean.columns else ""
        return pd.isna(payment_date) and status not in closed_statuses

    # AGE-003 counts only currently open invoices whose due dates have passed.
    cp_overdue_counts = {}
    if due_col in df_clean.columns and cp_col in df_clean.columns:
        open_mask = df_clean.apply(is_open_invoice, axis=1)
        overdue_mask = open_mask & df_clean[due_col].notna() & (df_clean[due_col] < ref_date)
        normalized_counterparties = df_clean[cp_col].map(_normalized_text)
        valid_cp_mask = normalized_counterparties.ne("")
        cp_overdue_counts = normalized_counterparties[overdue_mask & valid_cp_mask].value_counts().to_dict()

    cp_late_counts = {}
    if due_col in df_clean.columns and pay_col in df_clean.columns and cp_col in df_clean.columns:
        payment_lag = (df_clean[pay_col] - df_clean[due_col]).dt.days
        late_mask = df_clean[pay_col].notna() & df_clean[due_col].notna() & (payment_lag >= 60)
        normalized_counterparties = df_clean[cp_col].map(_normalized_text)
        cp_late_counts = normalized_counterparties[late_mask & normalized_counterparties.ne("")].value_counts().to_dict()

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        amt = _safe_number(row.get(amt_col))
        cp_raw = row.get(cp_col, "Unknown Counterparty")
        cp = str(cp_raw).strip() if pd.notna(cp_raw) and str(cp_raw).strip() else "Unknown Counterparty"
        cp_key = _normalized_text(cp_raw)
        due = row.get(due_col) if due_col in df_clean.columns else pd.NaT
        inv = row.get(inv_col) if inv_col in df_clean.columns else pd.NaT
        pay = row.get(pay_col) if pay_col in df_clean.columns else pd.NaT
        invoice_is_open = is_open_invoice(row)

        # AGE-001: Severe Overdue applies only to unpaid/open invoices.
        overdue_days = max(0, (ref_date - due).days) if pd.notnull(due) else 0
        if invoice_is_open and overdue_days > severe_overdue_days:
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

        if pd.notnull(pay) and pd.notnull(due):
            payment_lag_days = (pay - due).days
            if cp_key and cp_late_counts.get(cp_key, 0) >= 3 and payment_lag_days >= 60:
                flags.append({
                    "rule_code": "AGE-004", "rule_name": "Chronic Late-Payment Pattern", "severity": "HIGH",
                    "amount": amt, "description": f"Counterparty '{cp}' paid {cp_late_counts[cp_key]} invoices at least 60 days late; this invoice was {payment_lag_days} days late.",
                    "remediation": "Reassess credit terms, limits, expected-credit-loss assumptions, and collection controls."
                })

        # AGE-003: Chronic Delinquency
        if invoice_is_open and cp_key and cp_overdue_counts.get(cp_key, 0) >= 2 and overdue_days > 0:
            flags.append({
                "rule_code": "AGE-003",
                "rule_name": "Chronic Counterparty Delinquency",
                "severity": "HIGH",
                "amount": amt,
                "description": f"Counterparty '{cp}' has {cp_overdue_counts[cp_key]} active delinquent records across ledger.",
                "remediation": "Impose strict advance payment terms or suspend credit facility."
            })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results


def audit_general_ledger(df: pd.DataFrame, col_map: dict = None, period_end_days: int = DEFAULT_PERIOD_END_DAYS) -> list:
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
    manual_col = col_map.get("is_manual", "is_manual") if col_map else "is_manual"

    df_clean = df.copy().reset_index(drop=True)
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")
    for col in [dr_col, cr_col]:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].map(_safe_number)

    voucher_balances = {}
    voucher_counts = {}
    if vouch_col in df_clean.columns:
        valid_refs = df_clean[vouch_col].map(_normalized_text).ne("")
        grouped = df_clean.loc[valid_refs].groupby(vouch_col, dropna=False)
        for v_id, group in grouped:
            voucher_counts[str(v_id)] = len(group)
            # Balance only multi-leg vouchers. A unique reference on a single-leg
            # export is not evidence that the underlying journal is unbalanced.
            if len(group) >= 2:
                total_dr = group[dr_col].sum() if dr_col in group.columns else 0.0
                total_cr = group[cr_col].sum() if cr_col in group.columns else 0.0
                voucher_balances[str(v_id)] = (total_dr, total_cr)

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        dr = _safe_number(row.get(dr_col))
        cr = _safe_number(row.get(cr_col))
        raw_v_id = row.get(vouch_col, "")
        v_id = "" if pd.isna(raw_v_id) else str(raw_v_id).strip()
        p_date = row.get(date_col) if date_col in df_clean.columns else pd.NaT
        manual_value = _normalized_text(row.get(manual_col, ""))
        is_manual = manual_value in {"yes", "true", "1", "manual", "y"}

        balance = voucher_balances.get(v_id)
        if balance is None and dr != 0 and cr != 0:
            balance = (dr, cr)
        if balance is not None:
            tot_dr, tot_cr = balance
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

        if pd.notnull(p_date) and p_date.weekday() in [5, 6] and is_manual:
            day_name = p_date.strftime("%A")
            date_str = p_date.strftime("%Y-%m-%d")
            flags.append({
                "rule_code": "GL-002",
                "rule_name": "Weekend Manual Journal Entry",
                "severity": "HIGH",
                "amount": max(abs(dr), abs(cr)),
                "description": f"Entry marked manual was posted on {day_name} ({date_str}) outside normal business days.",
                "remediation": "Verify management sign-off and server authentication logs for the weekend entry."
            })

        if vouch_col in df_clean.columns and not v_id:
            flags.append({
                "rule_code": "GL-003", "rule_name": "Missing Journal Reference", "severity": "HIGH",
                "amount": max(abs(dr), abs(cr)), "description": "Ledger entry has no journal reference and cannot be traced to a complete voucher.",
                "remediation": "Assign a unique source reference and reconcile the entry to supporting documentation."
            })

        if is_manual and pd.notnull(p_date) and p_date.day >= 25:
            flags.append({
                "rule_code": "GL-004", "rule_name": "Period-End Manual Posting", "severity": "MEDIUM",
                "amount": max(abs(dr), abs(cr)), "description": f"Manual entry was posted near period end on {p_date.strftime('%Y-%m-%d')}.",
                "remediation": "Inspect period-end support, approval, cutoff, and any subsequent reversal."
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
    
    df_clean = df.copy().reset_index(drop=True)
    if date_col in df_clean.columns:
        df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors="coerce")

    parsed_ref_date = pd.to_datetime(as_of_date, errors="coerce") if as_of_date else pd.Timestamp.today()
    ref_date = parsed_ref_date.normalize() if pd.notna(parsed_ref_date) else pd.Timestamp.today().normalize()
    undefined_methods = {"", "nan", "none", "null", "n/a", "na", "not applicable", "undefined"}
    straight_line_methods = {"straight line", "straightline", "slm", "straight line method"}
    declining_methods = {
        "wdv", "written down value", "diminishing balance", "declining balance",
        "double declining balance", "reducing balance",
    }
    no_depreciation_methods = {"land", "non depreciable", "not depreciated"}

    for idx, row in df_clean.iterrows():
        row_index = idx + 1
        flags = []
        cost = _safe_number(row.get(cost_col))
        bv = _safe_number(row.get(bv_col))
        method_raw = row.get(method_col, "")
        method = _normalized_text(method_raw)
        asset_raw = row.get(asset_col, f"Asset #{row_index}")
        asset_name = str(asset_raw).strip() if pd.notna(asset_raw) and str(asset_raw).strip() else f"Asset #{row_index}"
        p_date = row.get(date_col) if date_col in df_clean.columns else pd.NaT
        life = _safe_number(row.get(life_col))
        method_is_defined = method not in undefined_methods

        # AST-001: Undefined depreciation
        if not method_is_defined:
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

        # AST-003: Compare only recognized methods with their matching curve.
        # Unknown-but-present methods are not silently treated as straight-line.
        if method_is_defined and method not in no_depreciation_methods and pd.notnull(p_date) and cost > 0 and life > 0:
            age_years = max(0.0, (ref_date - p_date).days / 365.25)
            expected_bv = None
            curve_name = None

            if method in straight_line_methods:
                expected_bv = max(0.0, cost - (cost / life * min(age_years, life)))
                curve_name = "straight-line"
            elif method in declining_methods:
                # Without an uploaded depreciation rate, useful life supplies a
                # conservative declining-balance rate rather than assuming SLM.
                annual_rate = min(1.0, max(0.0, 1.0 / life))
                expected_bv = max(0.0, cost * ((1.0 - annual_rate) ** age_years))
                curve_name = "declining-balance"

            if expected_bv is not None and age_years >= 1.0:
                variance = bv - expected_bv
                if variance > (cost * DEFAULT_ASSET_VARIANCE_RATIO):
                    flags.append({
                        "rule_code": "AST-003",
                        "rule_name": "Depreciation Curve Anomaly",
                        "severity": "HIGH",
                        "amount": variance,
                        "description": f"Asset '{asset_name}' book value ({format_currency(bv)}) is materially above the expected {curve_name} value ({format_currency(expected_bv)}).",
                        "remediation": "Verify accumulated depreciation, useful life, residual value, and posting completeness."
                    })

        results.append({
            "row_index": row_index,
            "status": "FLAGGED" if len(flags) > 0 else "CLEARED",
            "flags": flags
        })

    return results
