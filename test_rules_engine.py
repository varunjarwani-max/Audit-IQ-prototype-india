import pandas as pd

from detector import classify_columns
from groq_advisor import generate_consolidated_master_report
from rules_engine import audit_aging, audit_fixed_assets, audit_general_ledger, audit_transactions


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


def test_split_invoicing_emits_only_when_window_first_crosses_threshold():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=6, freq="D"),
        "amount": [12000, 13000, 14000, 15000, 16000, 17000],
        "vendor": ["Vendor A"] * 6,
        "approved_by": ["Manager"] * 6,
    })
    findings = audit_transactions(df, threshold_limit=50000)
    split_rows = [item["row_index"] for item in findings if "TXN-004" in rule_codes(item)]
    assert split_rows == [4]


def test_transaction_findings_use_source_values_and_extended_controls():
    df = pd.DataFrame([
        {"date": "2026-01-01", "amount": 12000, "vendor": "Normal", "approved_by": "R.Mehta", "currency": "INR", "three_way_match_status": "MATCHED", "duplicate_payment_candidate": "NO"},
        {"date": "2026-01-02", "amount": 75000, "vendor": "Missing", "approved_by": "", "currency": "INR", "three_way_match_status": "MATCHED", "duplicate_payment_candidate": "NO"},
        {"date": "2026-01-03", "amount": 18000, "vendor": "Mismatch", "approved_by": "A", "currency": "", "three_way_match_status": "PRICE_MISMATCH", "duplicate_payment_candidate": "YES"},
        {"date": "2026-01-04", "amount": -50000, "vendor": "Credit", "approved_by": "A", "currency": "INR", "three_way_match_status": "MATCHED", "duplicate_payment_candidate": "NO"},
    ])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_transactions(df, mapping)

    assert "TXN-001" not in rule_codes(findings[0])
    assert "TXN-001" in rule_codes(findings[1])
    assert findings[1]["flags"][0]["amount"] == 75000
    assert {"TXN-005", "TXN-006", "TXN-008"}.issubset(rule_codes(findings[2]))
    assert "TXN-007" in rule_codes(findings[3])


def test_gl_controls_respect_export_structure_and_manual_marker():
    df = pd.DataFrame([
        {"posting_date": "2025-04-05", "debit": 13750, "credit": 0, "journal_reference": "JE-0001", "is_manual": "NO"},
        {"posting_date": "2025-04-06", "debit": 0, "credit": 9000, "journal_reference": "JE-0002", "is_manual": "NO"},
        {"posting_date": "2025-06-07", "debit": 12000, "credit": 0, "journal_reference": "", "is_manual": "NO"},
        {"posting_date": "2025-06-07", "debit": 10000, "credit": 9000, "journal_reference": "BAD-JE", "is_manual": "YES"},
    ])
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_general_ledger(df, mapping)

    assert not rule_codes(findings[0])
    assert not rule_codes(findings[1])
    assert rule_codes(findings[2]) == {"GL-003"}
    assert {"GL-001", "GL-002"}.issubset(rule_codes(findings[3]))


def test_gl002_requires_explicit_manual_evidence_for_every_supported_marker():
    non_manual_markers = ["NO", "No", "false", "0", "system", "automatic", "", None]
    manual_markers = ["YES", "yes", "true", "1", "manual", "Y"]
    rows = [
        {"posting_date": "2025-06-07", "debit": 1000, "credit": 0, "journal_reference": f"AUTO-{index}", "is_manual": marker}
        for index, marker in enumerate(non_manual_markers)
    ] + [
        {"posting_date": "2025-06-07", "debit": 1000, "credit": 0, "journal_reference": f"MAN-{index}", "is_manual": marker}
        for index, marker in enumerate(manual_markers)
    ]
    df = pd.DataFrame(rows)
    mapping = classify_columns(list(df.columns))["matched_columns"]
    findings = audit_general_ledger(df, mapping)

    for item in findings[:len(non_manual_markers)]:
        assert "GL-002" not in rule_codes(item)
        assert all("manual" not in flag["description"].lower() for flag in item["flags"])
    for item in findings[len(non_manual_markers):]:
        assert "GL-002" in rule_codes(item)
        gl002 = next(flag for flag in item["flags"] if flag["rule_code"] == "GL-002")
        assert "marked manual" in gl002["description"].lower()


def test_chronic_paid_lateness_and_asset_variance_are_visible():
    aging = pd.DataFrame([
        {"due_date": "2025-01-01", "payment_date": "2025-04-15", "amount": 1000, "customer": "Late Co", "status": "Paid"},
        {"due_date": "2025-02-01", "payment_date": "2025-05-15", "amount": 1000, "customer": "Late Co", "status": "Paid"},
        {"due_date": "2025-03-01", "payment_date": "2025-06-15", "amount": 1000, "customer": "Late Co", "status": "Paid"},
    ])
    mapping = classify_columns(list(aging.columns))["matched_columns"]
    findings = audit_aging(aging, mapping, as_of_date="2026-01-01")
    assert all("AGE-004" in rule_codes(item) for item in findings)
    assert all("AGE-001" not in rule_codes(item) for item in findings)

    assets = pd.DataFrame([{"asset_name": "FA-051", "purchase_date": "2025-04-01", "purchase_cost": 600000, "depreciation_method": "SLM", "useful_life": 5, "current_value": 510000}])
    asset_map = classify_columns(list(assets.columns))["matched_columns"]
    assert "AST-003" in rule_codes(audit_fixed_assets(assets, asset_map, as_of_date="2026-08-22")[0])


def test_master_report_counts_findings_and_discloses_methodology():
    data = {
        "aging.csv": {
            "category": "ar_ap_aging",
            "df": pd.DataFrame([{"amount": 1000}]),
            "audit_as_of_date": "2026-08-22",
            "findings": [{
                "row_index": 1,
                "status": "FLAGGED",
                "flags": [
                    {"rule_code": "AGE-001", "severity": "HIGH", "amount": 1000, "description": "Open overdue invoice.", "remediation": "Review."},
                    {"rule_code": "AGE-003", "severity": "HIGH", "amount": 1000, "description": "Repeated delinquency.", "remediation": "Review."},
                ],
            }],
        }
    }

    report, warnings = generate_consolidated_master_report(data)

    assert not warnings
    assert "**Flagged Rows:** 1" in report
    assert "**Individual Rule Findings:** 2" in report
    assert "**Audit As-Of / Benchmark Date:** 2026-08-22" in report
    assert "| Accounts Receivable / Accounts Payable Aging | 1 | 1 | 2 |" in report
    assert "## 4. Report Completion Statement" in report
    assert report.rstrip().endswith("used for this run.")
