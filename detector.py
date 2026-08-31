"""
detector.py
Data Segregation & Column Alias Signature Classifier for AuditIQ.
Enforces strict word-boundary token matching to prevent false positives (e.g. 'dr' in 'address').
Synchronized scoring logic with TypeScript (85/15 primary/secondary weighted ratios + category penalty floors).
"""

import re
from typing import Dict, List, Tuple, Any, Optional

ALIAS_DEFINITIONS = {
    "transactions": {
        "display_name": "Transactions Data",
        "module_file": "txn_detection.py",
        "primary_fields": ["date", "amount", "vendor", "account_code", "approved_by", "department"],
        "secondary_fields": ["transaction_id", "description", "payment_method", "currency", "receipt_attached"],
        "aliases": {
            "date": ["date", "txn_date", "transaction_date", "trans_date", "spend_date", "posting_date", "timestamp"],
            "amount": ["amount", "txn_amount", "total_amount", "cost", "spend", "amount_inr", "amount_usd", "subtotal", "val_num", "charge"],
            "vendor": ["vendor", "supplier", "payee", "merchant", "vendor_name", "counterparty", "contractor", "seller"],
            "account_code": ["account_code", "account_no", "gl_code", "expense_code", "cost_code", "code_ref", "chart_of_accounts"],
            "approved_by": ["approved_by", "approver", "authorized_by", "signer", "approved", "approval_user", "manager", "auth_user"],
            "department": ["department", "dept", "cost_center", "division", "business_unit", "team", "branch"],
            "account_code": ["account_code", "account_no", "gl_code", "expense_code", "cost_code", "code_ref"],
            "currency": ["currency", "currency_code", "curr", "iso_currency"],
            "transaction_id": ["transaction_id", "txn_id", "payment_id", "reference_id", "id"],
            "three_way_match_status": ["three_way_match_status", "three_way_match", "match_status", "po_match_status"],
            "duplicate_payment_candidate": ["duplicate_payment_candidate", "duplicate_candidate", "duplicate_payment", "is_duplicate"]
        }
    },
    "ar_ap_aging": {
        "display_name": "AR / AP Aging Ledger",
        "module_file": "aging_detection.py",
        "primary_fields": ["invoice_date", "due_date", "payment_date", "amount", "counterparty", "invoice_status"],
        "secondary_fields": ["invoice_number", "terms", "aging_bucket", "days_overdue", "currency", "discount"],
        "aliases": {
            "invoice_date": ["invoice_date", "inv_date", "bill_date", "doc_date", "issue_date", "origination_date"],
            "due_date": ["due_date", "maturity_date", "payment_due", "due", "expiry_date", "expected_date"],
            "payment_date": ["payment_date", "paid_date", "settlement_date", "cleared_date", "remittance_date", "paid_on", "date_paid", "date_settled", "receipt_date"],
            "amount": ["amount", "invoice_amount", "balance", "outstanding_amount", "open_amount", "total_billed", "net_due", "amount_due", "invoice_total", "gross_amount"],
            "counterparty": ["customer_vendor", "customer", "vendor", "client", "customer_name", "vendor_name", "debtor", "creditor", "counterparty", "payer", "party_name", "account_name"],
            "invoice_status": ["invoice_status", "status", "payment_status", "aging_status", "state", "inv_status", "settlement_status", "paid_status", "document_status"]
        }
    },
    "general_ledger": {
        "display_name": "General Ledger (GL) Entries",
        "module_file": "gl_detection.py",
        "primary_fields": ["posting_date", "account_name", "debit", "credit", "voucher_id", "prepared_by"],
        "secondary_fields": ["line_number", "description", "entity_id", "currency", "is_manual", "posted_time"],
        "aliases": {
            "posting_date": ["entry_date", "posting_date", "je_date", "effective_date", "txn_timestamp", "journal_date"],
            "account_name": ["account_name", "account_description", "gl_account", "account_title", "account", "ledger_account"],
            "debit": ["debit", "dr", "debit_amount", "dr_amount", "debits"],
            "credit": ["credit", "cr", "credit_amount", "cr_amount", "credits"],
            "voucher_id": ["journal_reference", "je_number", "ref_number", "journal_id", "batch_id", "voucher_no", "reference", "journal_ref"],
            "prepared_by": ["prepared_by", "created_by", "entered_by", "posted_by", "user_id", "author", "originator"],
            "is_manual": ["is_manual", "manual_entry", "manual", "entry_type", "journal_type"]
        }
    },
    "fixed_assets": {
        "display_name": "Fixed Asset Register",
        "module_file": "fixed_asset_detection.py",
        "primary_fields": ["asset_name", "purchase_date", "cost", "method", "useful_life", "book_value"],
        "secondary_fields": ["asset_id", "asset_tag", "serial_number", "accumulated_depreciation", "salvage_value", "location"],
        "aliases": {
            "asset_name": ["asset_name", "asset_description", "equipment_name", "asset_title", "item_name", "asset"],
            "purchase_date": ["purchase_date", "acquisition_date", "capitalization_date", "placed_in_service", "buy_date", "in_service_date"],
            "cost": ["purchase_cost", "original_cost", "historical_cost", "acquisition_cost", "asset_cost", "gross_book_value", "cost"],
            "method": ["depreciation_method", "depr_method", "depr_type", "method", "depreciation_type", "depreciation_basis", "depreciation_policy"],
            "useful_life": ["useful_life", "lifespan", "useful_life_years", "life_years", "est_life", "asset_life", "estimated_useful_life", "life_in_years"],
            "book_value": ["current_value", "book_value", "net_book_value", "nbv", "carrying_value", "present_value", "closing_book_value", "written_down_value"]
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
    
    if alias == norm_col:
        return True
    
    tokens = norm_col.split('_')
    if len(alias) <= 3:
        return alias in tokens

    if alias in tokens:
        return True
    
    pattern = rf"(^|_){re.escape(alias)}(_|$)"
    if re.search(pattern, norm_col):
        return True
    
    return False


def classify_columns(columns: List[str]) -> Dict[str, Any]:
    """
    Analyzes list of columns against alias dictionaries using token-boundary matching.
    Applies weighted scoring (85% primary + 15% secondary) with penalty floors.
    """
    if not columns:
        return {
            "category": "ambiguous",
            "raw_best_category": "transactions",
            "confidence": 0,
            "is_ambiguous": True,
            "matched_columns": {},
            "all_scores": {cat: 0 for cat in ALIAS_DEFINITIONS},
            "schema_details": ALIAS_DEFINITIONS["transactions"]
        }

    normalized_cols = {col: normalize_string(col) for col in columns}
    scores = {}
    mappings = {}

    for cat, schema in ALIAS_DEFINITIONS.items():
        matched_fields = {}
        primary_fields = schema["primary_fields"]
        secondary_fields = schema.get("secondary_fields", [])
        aliases = schema["aliases"]

        matched_primary_count = 0
        for std_field in primary_fields:
            field_aliases = [normalize_string(a) for a in aliases.get(std_field, [std_field])]
            for orig_col, norm_col in normalized_cols.items():
                if any(alias_matches_column(alias, norm_col) for alias in field_aliases):
                    matched_fields[std_field] = orig_col
                    matched_primary_count += 1
                    break
        
        matched_sec_count = 0
        for sec_field in secondary_fields:
            norm_sec = normalize_string(sec_field)
            for orig_col, norm_col in normalized_cols.items():
                if alias_matches_column(norm_sec, norm_col) and orig_col not in matched_fields.values():
                    matched_sec_count += 1
                    break

        primary_ratio = matched_primary_count / len(primary_fields)
        secondary_ratio = min(1.0, matched_sec_count / 2.0) if secondary_fields else 0.0
        score = int(round((primary_ratio * 85.0) + (secondary_ratio * 15.0)))

        if cat == "general_ledger":
            has_dr_cr = ("debit" in matched_fields) or ("credit" in matched_fields)
            if not has_dr_cr:
                score = min(score, 30)
        elif cat == "fixed_assets":
            has_asset_cost = ("asset_name" in matched_fields) or ("cost" in matched_fields)
            if not has_asset_cost:
                score = min(score, 30)
        elif cat == "ar_ap_aging":
            has_due_status = ("due_date" in matched_fields) or ("invoice_status" in matched_fields)
            if not has_due_status:
                score = min(score, 30)

        scores[cat] = score
        mappings[cat] = matched_fields

    ranked_categories = sorted(scores, key=scores.get, reverse=True)
    best_category = ranked_categories[0]
    runner_up_confidence = scores[ranked_categories[1]] if len(ranked_categories) > 1 else 0
    best_confidence = scores[best_category]
    score_margin = best_confidence - runner_up_confidence
    matched_primary = set(mappings.get(best_category, {}))
    required_evidence = {
        "transactions": {"date", "amount"},
        "ar_ap_aging": {"due_date", "amount"},
        "general_ledger": {"posting_date", "debit", "credit"},
        "fixed_assets": {"asset_name", "cost"},
    }
    minimum_evidence_met = required_evidence[best_category].issubset(matched_primary)
    is_ambiguous = best_confidence < 50.0 or score_margin < 10 or not minimum_evidence_met
    warnings = []
    if not minimum_evidence_met:
        missing = sorted(required_evidence[best_category] - matched_primary)
        warnings.append(f"Missing required field evidence for {best_category}: {', '.join(missing)}.")
    if score_margin < 10:
        warnings.append("The top schema scores are too close for safe automatic routing.")

    return {
        "category": "ambiguous" if is_ambiguous else best_category,
        "raw_best_category": best_category,
        "confidence": best_confidence,
        "is_ambiguous": is_ambiguous,
        "matched_columns": mappings.get(best_category, {}),
        "all_scores": scores,
        "score_margin": score_margin,
        "classification_warnings": warnings,
        "schema_details": ALIAS_DEFINITIONS.get(best_category, {})
    }
