"""
sample_data.py
Synthetic 5-record test datasets for AuditIQ Data Segregation & Anomaly Detection.
"""

import pandas as pd

SAMPLE_DATASETS = {
    "transactions": {
        "name": "Transactions - 5-Record Test Batch",
        "description": "Tests missing approval, round-number amount, and threshold evasion structuring.",
        "category": "transactions",
        "filename": "synthetic_transactions_batch_5.csv",
        "df": pd.DataFrame([
            {
                "date": "2024-01-15",
                "vendor": "Apex Cloud Systems",
                "amount": 48500.00,
                "account_code": "6100-IT",
                "approved_by": "V.Sharma",
                "department": "Engineering"
            },
            {
                "date": "2024-01-16",
                "vendor": "Horizon Consulting",
                "amount": 49950.00,
                "account_code": "6200-PROF",
                "approved_by": "",  # Missing Approval
                "department": "Operations"
            },
            {
                "date": "2024-01-18",
                "vendor": "Swift Office Supplies",
                "amount": 12400.00,
                "account_code": "6300-OPS",
                "approved_by": "A.Mehta",
                "department": "Facilities"
            },
            {
                "date": "2024-01-20",
                "vendor": "Global Logistics Corp",
                "amount": 100000.00,  # Exact round number > ₹50,000
                "approved_by": "R.Patel",
                "account_code": "6400-LOG",
                "department": "Supply Chain"
            },
            {
                "date": "2024-01-22",
                "vendor": "Apex Cloud Systems",  # Same vendor within 7 days
                "amount": 47500.00,  # Structuring split payment
                "account_code": "6100-IT",
                "approved_by": "V.Sharma",
                "department": "Engineering"
            }
        ])
    },
    "ar_ap_aging": {
        "name": "AR/AP Aging - 5-Record Test Batch",
        "description": "Tests 90+ days overdue aging, timeline inversion (payment before invoice), and chronic delinquency.",
        "category": "ar_ap_aging",
        "filename": "synthetic_aging_batch_5.csv",
        "df": pd.DataFrame([
            {
                "invoice_date": "2023-09-01",
                "due_date": "2023-10-01",
                "payment_date": "",
                "amount": 125000.00,
                "customer_vendor": "Zenith Retailers",
                "invoice_status": "OVERDUE"  # > 90 days overdue
            },
            {
                "invoice_date": "2024-01-10",
                "due_date": "2024-02-10",
                "payment_date": "2024-01-05",  # Inverted timeline: payment before invoice
                "amount": 42000.00,
                "customer_vendor": "Nexus Infotech",
                "invoice_status": "PAID"
            },
            {
                "invoice_date": "2024-01-15",
                "due_date": "2024-02-15",
                "payment_date": "2024-02-10",
                "amount": 68000.00,
                "customer_vendor": "Starlight Industries",
                "invoice_status": "CLEARED"
            },
            {
                "invoice_date": "2023-08-15",
                "due_date": "2023-09-15",
                "payment_date": "",
                "amount": 310000.00,
                "customer_vendor": "Zenith Retailers",  # Chronic late payer
                "invoice_status": "DELINQUENT"
            },
            {
                "invoice_date": "2024-01-20",
                "due_date": "2024-02-20",
                "payment_date": "2024-02-18",
                "amount": 15500.00,
                "customer_vendor": "Alpha Trade Links",
                "invoice_status": "PAID"
            }
        ])
    },
    "general_ledger": {
        "name": "General Ledger - 5-Record Test Batch",
        "description": "Tests unbalance vouchers (Debits != Credits), weekend postings, and month-end clearing adjustments.",
        "category": "general_ledger",
        "filename": "synthetic_gl_batch_5.csv",
        "df": pd.DataFrame([
            {
                "entry_date": "2024-01-15",
                "account_name": "Cash at Bank",
                "debit": 50000.00,
                "credit": 0.00,
                "journal_reference": "JV-2024-001",
                "prepared_by": "K.Verma"
            },
            {
                "entry_date": "2024-01-15",
                "account_name": "Accounts Receivable",
                "debit": 0.00,
                "credit": 45000.00,  # Unbalanced: Debit 50,000 != Credit 45,000
                "journal_reference": "JV-2024-001",
                "prepared_by": "K.Verma"
            },
            {
                "entry_date": "2024-01-21",  # Sunday (Weekend posting)
                "account_name": "Miscellaneous Expense",
                "debit": 18000.00,
                "credit": 0.00,
                "journal_reference": "JV-2024-002",
                "prepared_by": "System-Auto"
            },
            {
                "entry_date": "2024-01-21",  # Sunday
                "account_name": "Petty Cash",
                "debit": 0.00,
                "credit": 18000.00,
                "journal_reference": "JV-2024-002",
                "prepared_by": "System-Auto"
            },
            {
                "entry_date": "2024-01-31",  # Month-end last day into Suspense Account
                "account_name": "Unallocated Suspense Clearing",
                "debit": 75000.00,
                "credit": 0.00,
                "journal_reference": "JV-2024-003",
                "prepared_by": "M.Gupta"
            }
        ])
    },
    "fixed_assets": {
        "name": "Fixed Assets - 5-Record Test Batch",
        "description": "Tests missing depreciation schedules, carrying value > purchase cost, and curve discrepancies.",
        "category": "fixed_assets",
        "filename": "synthetic_assets_batch_5.csv",
        "df": pd.DataFrame([
            {
                "asset_name": "Dell Precision Server R750",
                "purchase_date": "2022-01-15",
                "purchase_cost": 450000.00,
                "depreciation_method": "Straight Line",
                "useful_life": 5,
                "current_value": 270000.00
            },
            {
                "asset_name": "Executive Conference Setup",
                "purchase_date": "2023-06-10",
                "purchase_cost": 120000.00,
                "depreciation_method": "None",  # Missing depreciation schedule
                "useful_life": 3,
                "current_value": 120000.00
            },
            {
                "asset_name": "Hydraulic Cargo Lift",
                "purchase_date": "2021-03-20",
                "purchase_cost": 850000.00,
                "depreciation_method": "Straight Line",
                "useful_life": 10,
                "current_value": 920000.00  # Valuation anomaly: Current value > Purchase cost
            },
            {
                "asset_name": "Facility Generator 50kVA",
                "purchase_date": "2020-01-01",
                "purchase_cost": 600000.00,
                "depreciation_method": "Straight Line",
                "useful_life": 5,
                "current_value": 500000.00  # Mathematical deviation from straight line (should be ~120k)
            },
            {
                "asset_name": "MacBook Pro 16 M3",
                "purchase_date": "2023-11-01",
                "purchase_cost": 250000.00,
                "depreciation_method": "Straight Line",
                "useful_life": 3,
                "current_value": 230000.00
            }
        ])
    },
    "ambiguous": {
        "name": "Ambiguous Columns - Test Batch",
        "description": "Tests unstandardized headers triggering the manual column mapping interface.",
        "category": "ambiguous",
        "filename": "unmapped_test_batch_5.csv",
        "df": pd.DataFrame([
            {
                "col_alpha": "2024-01-10",
                "col_beta": "Vendor XYZ",
                "val_num": 52000.00,
                "code_ref": "EXP-99",
                "auth_user": "J.Doe"
            },
            {
                "col_alpha": "2024-01-12",
                "col_beta": "Supplier ABC",
                "val_num": 49000.00,
                "code_ref": "EXP-99",
                "auth_user": ""
            },
            {
                "col_alpha": "2024-01-15",
                "col_beta": "Tech Logistics",
                "val_num": 10000.00,
                "code_ref": "EXP-12",
                "auth_user": "A.Smith"
            },
            {
                "col_alpha": "2024-01-18",
                "col_beta": "Office Supply",
                "val_num": 3000.00,
                "code_ref": "EXP-05",
                "auth_user": "M.Roy"
            },
            {
                "col_alpha": "2024-01-20",
                "col_beta": "Vendor XYZ",
                "val_num": 48000.00,
                "code_ref": "EXP-99",
                "auth_user": "J.Doe"
            }
        ])
    }
}
