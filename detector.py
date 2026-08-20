"""
detector.py
Data Segregation & Column Alias Signature Classifier for AuditIQ.
Enforces strict word-boundary token matching to prevent false positives (e.g. 'dr' in 'address').
"""

import re
from typing import Dict, List, Tuple, Any, Optional

ALIAS_DEFINITIONS = {
    "transactions": {
        "display_name": "Transactions Data",
        "module_file": "txn_detection.py",
        "primary_fields": ["date", "amount", "vendor", "account_code", "approved_by", "department"],
        "aliases": {
            "date": ["date", "txn_date", "transaction_date", "trans_date", "spend_date", "posting_date", "timestamp"],
            "amount": ["amount", "txn_amount", "total_amount", "cost", "spend", "amount_inr", "amount_usd", "subtotal", "val_num", "charge"],
            "vendor": ["vendor", "supplier", "payee", "merchant", "vendor_name", "counterparty", "contractor", "seller"],
            "account_code": ["account_code", "account_no", "gl_code", "expense_code", "cost_code", "code_ref", "chart_of_accounts"],
            "approved_by": ["approved_by", "approver", "authorized_by", "signer", "approved", "approval_user", "manager", "auth_user"],
            "department": ["department", "dept", "cost_center", "division", "business_unit", "team", "branch"]
        }
    },
    "ar_ap_aging": {
        "display_name": "AR / AP Aging Ledger",
        "module_file": "aging_detection.py",
        "primary_fields": ["invoice_date", "due_date", "payment_date", "amount", "customer_vendor", "invoice_status"],
        "aliases": {
            "invoice_date": ["invoice_date", "inv_date", "bill_date", "doc_date", "issue_date", "origination_date"],
            "due_date": ["due_date", "maturity_date", "payment_due", "due", "expiry_date", "expected_date"],
            "payment_date": ["payment_date", "paid_date", "settlement_date", "cleared_date", "remittance_date", "paid_on"],
            "amount": ["amount", "invoice_amount", "balance", "outstanding_amount", "open_amount", "total_billed", "net_due"],
            "customer_vendor": ["customer_vendor", "customer", "vendor", "client", "customer_name", "vendor_name", "debtor", "creditor", "counterparty", "payer"],
            "invoice_status": ["invoice_status", "status", "payment_status", "aging_status", "state", "inv_status"]
        }
    },
    "general_ledger": {
        "display_name": "General Ledger (GL) Entries",
        "module_file": "gl_detection.py",
        "primary_fields": ["entry_date", "account_name", "debit", "credit", "journal_reference", "prepared_by"],
        "aliases": {
            "entry_date": ["entry_date", "posting_date", "je_date", "effective_date", "txn_timestamp", "journal_date"],
            "account_name": ["account_name", "account_description", "gl_account", "account_title", "account", "ledger_account"],
            "debit": ["debit", "dr", "debit_amount", "dr_amount", "debits"],
            "credit": ["credit", "cr", "credit_amount", "cr_amount", "credits"],
            "journal_reference": ["journal_reference", "je_number", "ref_number", "journal_id", "batch_id", "voucher_no", "reference", "journal_ref"],
            "prepared_by": ["prepared_by", "created_by", "entered_by", "posted_by", "user_id", "author", "originator"]
        }
    },
    "fixed_assets": {
        "display_name": "Fixed Asset Register",
        "module_file": "fixed_asset_detection.py",
        "primary_fields": ["asset_name", "purchase_date", "purchase_cost", "depreciation_method", "useful_life", "current_value"],
        "aliases": {
            "asset_name": ["asset_name", "asset_description", "equipment_name", "asset_title", "item_name", "asset"],
            "purchase_date": ["purchase_date", "acquisition_date", "capitalization_date", "placed_in_service", "buy_date", "in_service_date"],
            "purchase_cost": ["purchase_cost", "original_cost", "historical_cost", "acquisition_cost", "asset_cost", "gross_book_value", "cost"],
            "depreciation_method": ["depreciation_method", "depr_method", "depr_type", "method", "depreciation_type"],
            "useful_life": ["useful_life", "lifespan", "useful_life_years", "life_years", "est_life", "asset_life"],
            "current_value": ["current_value", "book_value", "net_book_value", "nbv", "carrying_value", "present_value"]
        }
    }
}


def normalize_string(val: str) -> str:
    """Strip special characters, spaces, and lowercase."""
    if not val:
        return ""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', str(val).strip().lower())
    return re.sub(r'_+', '_', clean).strip('_')


def alias_matches_column(alias: str, norm_col: str) -> bool:
    """
    Robust token-aware column matcher.
    Prevents false positives where short aliases (e.g. 'dr' matching 'address' or 'cr' matching 'credit_card')
    corrupt classification without exact token boundaries.
    """
    if not alias or not norm_col:
        return False
    
    # Direct exact match
    if alias == norm_col:
        return True
    
    tokens = norm_col.split('_')
    
    # For short aliases (<= 3 characters, e.g. 'dr', 'cr', 'je', 'id', 'nbv', 'inv'), require exact token match
    if len(alias) <= 3:
        return alias in tokens

    # For longer aliases, match whole token or anchored compound match
    if alias in tokens:
        return True
    
    # Word-boundary check: alias must appear surrounded by underscores or string boundaries
    pattern = rf"(^|_){re.escape(alias)}(_|$)"
    if re.search(pattern, norm_col):
        return True
    
    return False


def classify_columns(columns: List[str]) -> Dict[str, Any]:
    """
    Analyzes list of columns against alias dictionaries using token-boundary matching.
    Returns detected category, confidence percentage, matched field mappings, and routing metadata.
    """
    normalized_cols = {col: normalize_string(col) for col in columns}
    scores = {}
    mappings = {}

    for cat, schema in ALIAS_DEFINITIONS.items():
        matched_fields = {}
        primary_fields = schema["primary_fields"]
        aliases = schema["aliases"]

        matched_count = 0
        for std_field in primary_fields:
            field_aliases = [normalize_string(a) for a in aliases.get(std_field, [std_field])]
            
            # Find best match in uploaded columns using token matching
            for orig_col, norm_col in normalized_cols.items():
                if any(alias_matches_column(alias, norm_col) for alias in field_aliases):
                    matched_fields[std_field] = orig_col
                    matched_count += 1
                    break
        
        confidence = round((matched_count / len(primary_fields)) * 100, 1)
        scores[cat] = confidence
        mappings[cat] = matched_fields

    best_category = max(scores, key=scores.get)
    best_confidence = scores[best_category]
    is_ambiguous = best_confidence < 50.0

    return {
        "category": "ambiguous" if is_ambiguous else best_category,
        "raw_best_category": best_category,
        "confidence": best_confidence,
        "is_ambiguous": is_ambiguous,
        "matched_columns": mappings.get(best_category, {}),
        "all_scores": scores,
        "schema_details": ALIAS_DEFINITIONS.get(best_category, {})
    }
