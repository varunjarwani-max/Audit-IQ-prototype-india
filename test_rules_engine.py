import pandas as pd

from detector import classify_columns
from rules_engine import audit_aging, audit_fixed_assets, audit_transactions


def rule_codes(result):
    return {flag["rule_code"] for flag in result["flags"]}


def test_paid_invoices_are_not_overdue_or_chronic():
    df = pd.DataFrame([
        {
            "invoice_date": "2023-01-01",
            "due_date": "2023-02-01",
            "payment_date": "2023-02-05",
            "amount": "₹125,000",
            "customer_vendor": "Acme Ltd",
            "invoice_status": "PAID",
        },
        {
            "invoice_date": "2023-03-01",
            "due_date": "2023-04-01",
            "payment_date": "2023-04-03",
            "amount": "25,000",
            "customer_vendor": "Acme Ltd",
            "invoice_status": "Cleared",
        },
    ])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_aging(df, mapping, as_of_date="2026-01-01")

    assert all("AGE-001" not in rule_codes(item) for item in findings)
    assert all("AGE-003" not in rule_codes(item) for item in findings)


def test_only_open_overdue_invoices_drive_chronic_delinquency():
    df = pd.DataFrame([
        {"due_date": "2024-01-01", "payment_date": "", "amount": 1000, "customer": "ACME", "status": "OPEN"},
        {"due_date": "2024-02-01", "payment_date": "", "amount": 2000, "customer": " acme ", "status": "Overdue"},
        {"due_date": "2024-03-01", "payment_date": "2024-03-02", "amount": 3000, "customer": "Acme", "status": "PAID"},
    ])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_aging(df, mapping, as_of_date="2024-12-31")

    assert "AGE-003" in rule_codes(findings[0])
    assert "AGE-003" in rule_codes(findings[1])
    assert "AGE-003" not in rule_codes(findings[2])


def test_missing_optional_aging_fields_do_not_crash():
    df = pd.DataFrame([{"due_date": "2024-01-01", "amount_due": "10,000", "party_name": "Buyer A"}])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_aging(df, mapping, as_of_date="2025-01-01")

    assert "AGE-001" in rule_codes(findings[0])


def test_fixed_asset_rules_are_method_aware_and_non_contradictory():
    df = pd.DataFrame([
        {
            "asset_name": "Land parcel",
            "purchase_date": "2020-01-01",
            "purchase_cost": 500000,
            "depreciation_method": "Land",
            "useful_life": 20,
            "current_value": 500000,
        },
        {
            "asset_name": "Machine",
            "purchase_date": "2020-01-01",
            "purchase_cost": 100000,
            "depreciation_method": "WDV",
            "useful_life": 5,
            "current_value": 33000,
        },
        {
            "asset_name": "Server",
            "purchase_date": "2020-01-01",
            "purchase_cost": 100000,
            "depreciation_method": "None",
            "useful_life": 5,
            "current_value": 100000,
        },
    ])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_fixed_assets(df, mapping, as_of_date="2025-01-01")

    assert not rule_codes(findings[0])
    assert "AST-003" not in rule_codes(findings[1])
    assert rule_codes(findings[2]) == {"AST-001"}


def test_duplicate_dates_and_indices_are_supported():
    df = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "amount": [30000, 30000],
            "vendor": ["Vendor A", "Vendor A"],
            "approved_by": ["Manager", "Manager"],
        },
        index=[7, 7],
    )
    findings = audit_transactions(df)
    assert len(findings) == 2
    assert "TXN-004" in rule_codes(findings[1])
