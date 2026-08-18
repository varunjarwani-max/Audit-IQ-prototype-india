import { SampleDataset } from '../types';

export const SAMPLE_DATASETS: SampleDataset[] = [
  {
    id: 'sample_txns_5',
    name: 'Transactions (5 Test Records)',
    category: 'transactions',
    description: '5-record batch with missing approvers, round $5K/$25K figures, and $9,950 structuring evasion.',
    expectedAnomalies: [
      'Row 1: Missing approver & exact round amount ($5,000.00)',
      'Row 2: Structuring threshold evasion ($9,950.00 to Apex Logistics)',
      'Row 4: Consecutive vendor structuring ($9,800.00 to Apex Logistics)',
      'Row 5: High round amount ($25,000.00) without approval sign-off'
    ],
    data: [
      {
        date: '2024-10-12',
        amount: 5000.00,
        vendor: 'OmniCorp Supplies',
        account_code: 'EXP-6010',
        approved_by: '',
        department: 'Operations'
      },
      {
        date: '2024-10-14',
        amount: 9950.00,
        vendor: 'Apex Logistics LLC',
        account_code: 'EXP-5420',
        approved_by: 'M. Jenkins',
        department: 'Logistics'
      },
      {
        date: '2024-10-15',
        amount: 1420.75,
        vendor: 'CloudStack SaaS',
        account_code: 'EXP-7100',
        approved_by: 'S. Connor',
        department: 'Engineering'
      },
      {
        date: '2024-10-15',
        amount: 9800.00,
        vendor: 'Apex Logistics LLC',
        account_code: 'EXP-5420',
        approved_by: 'M. Jenkins',
        department: 'Logistics'
      },
      {
        date: '2024-10-18',
        amount: 25000.00,
        vendor: 'Global Advisory Partners',
        account_code: 'EXP-8800',
        approved_by: null,
        department: 'Executive'
      }
    ]
  },
  {
    id: 'sample_aging_5',
    name: 'AR/AP Aging (5 Test Records)',
    category: 'ar_ap_aging',
    description: '5-record batch testing >90 days severe overdue, inverted payment timing, and chronic delinquent accounts.',
    expectedAnomalies: [
      'Row 1: Severe overdue (118 days past due, unpaid $38,400.00)',
      'Row 2: Inverted payment timing (payment date recorded prior to invoice date)',
      'Row 4: Chronic late paying account with repeated overdue balance ($64,250.00)',
      'Row 5: Corrupted date logic (due date occurs before invoice date)'
    ],
    data: [
      {
        invoice_date: '2024-05-10',
        due_date: '2024-06-09',
        payment_date: '',
        amount: 38400.00,
        customer_vendor: 'Vanguard Industrial Corp',
        invoice_status: 'OPEN'
      },
      {
        invoice_date: '2024-09-01',
        due_date: '2024-10-01',
        payment_date: '2024-08-25',
        amount: 12500.00,
        customer_vendor: 'Nexus Retail Holdings',
        invoice_status: 'PAID'
      },
      {
        invoice_date: '2024-09-15',
        due_date: '2024-10-15',
        payment_date: '2024-10-10',
        amount: 8340.50,
        customer_vendor: 'Helios Solar Systems',
        invoice_status: 'PAID'
      },
      {
        invoice_date: '2024-06-20',
        due_date: '2024-07-20',
        payment_date: '',
        amount: 64250.00,
        customer_vendor: 'Vanguard Industrial Corp',
        invoice_status: 'OVERDUE'
      },
      {
        invoice_date: '2024-10-10',
        due_date: '2024-09-20',
        payment_date: '',
        amount: 5120.00,
        customer_vendor: 'Starlight Media Group',
        invoice_status: 'PENDING'
      }
    ]
  },
  {
    id: 'sample_gl_5',
    name: 'General Ledger / Journal Entries (5 Test Records)',
    category: 'general_ledger',
    description: '5-record batch testing unbalanced debits/credits, weekend off-hour entries, and period-end manual entries.',
    expectedAnomalies: [
      'Rows 1-2 (JE-2024-104): Unbalanced journal entry (Debit $15,000 ≠ Credit $13,500; $1,500 gap)',
      'Row 3: Off-hours / Sunday posting (2024-10-27 23:42:10 UTC)',
      'Row 4: Period-end manual journal entry (posted on Oct 31 at month-end closing)'
    ],
    data: [
      {
        entry_date: '2024-10-18 14:20:00',
        journal_reference: 'JE-2024-104',
        account_name: '1010 - Operating Cash',
        debit: 15000.00,
        credit: 0.00,
        prepared_by: 'T. Vance'
      },
      {
        entry_date: '2024-10-18 14:20:00',
        journal_reference: 'JE-2024-104',
        account_name: '4010 - Consulting Revenue',
        debit: 0.00,
        credit: 13500.00,
        prepared_by: 'T. Vance'
      },
      {
        entry_date: '2024-10-27 23:42:10', // Sunday night off-hours
        journal_reference: 'JE-2024-118',
        account_name: '2100 - Accounts Payable',
        debit: 45000.00,
        credit: 0.00,
        prepared_by: 'SYS_ADMIN'
      },
      {
        entry_date: '2024-10-31 17:55:00', // Month-end manual JE
        journal_reference: 'JE-2024-129',
        account_name: '6090 - Miscellaneous Adjustment',
        debit: 8200.00,
        credit: 8200.00,
        prepared_by: 'C. Finch'
      },
      {
        entry_date: '2024-10-15 10:15:00',
        journal_reference: 'JE-2024-099',
        account_name: '1200 - Prepaid Expenses',
        debit: 6000.00,
        credit: 6000.00,
        prepared_by: 'A. Cooper'
      }
    ]
  },
  {
    id: 'sample_fixed_assets_5',
    name: 'Fixed Assets (5 Test Records)',
    category: 'fixed_assets',
    description: '5-record batch testing book value reconciliation errors, missing depreciation methods, and unreasonable useful life.',
    expectedAnomalies: [
      'Row 1: Reconciliation failure (Reported current_value $46,000 vs Expected $28,000 based on 3-yr straight line)',
      'Row 2: Missing depreciation method & null useful life',
      'Row 3: Unreasonable useful life (99 years for office laptops)',
      'Row 4: Current book value exceeds original purchase cost ($14,000 > $12,000)'
    ],
    data: [
      {
        asset_name: 'High-Precision CNC Milling Unit',
        purchase_date: '2021-01-15',
        purchase_cost: 60000.00,
        depreciation_method: 'Straight Line',
        useful_life: 5,
        current_value: 46000.00 // Should be ~24,000 after 3.7 years
      },
      {
        asset_name: 'Executive Boardroom Display Wall',
        purchase_date: '2023-04-10',
        purchase_cost: 18500.00,
        depreciation_method: '',
        useful_life: null,
        current_value: 18500.00
      },
      {
        asset_name: 'Dev Engineering Laptops (10x)',
        purchase_date: '2023-08-01',
        purchase_cost: 24000.00,
        depreciation_method: 'Straight Line',
        useful_life: 99, // Unreasonable useful life
        current_value: 23500.00
      },
      {
        asset_name: 'Warehouse Forklift Electric #2',
        purchase_date: '2022-06-15',
        purchase_cost: 12000.00,
        depreciation_method: 'Straight Line',
        useful_life: 7,
        current_value: 14000.00 // Current value higher than purchase cost
      },
      {
        asset_name: 'HQ Backup Diesel Generator 50kW',
        purchase_date: '2022-01-10',
        purchase_cost: 35000.00,
        depreciation_method: 'Straight Line',
        useful_life: 10,
        current_value: 28000.00 // Clean ~2 yrs depr ($3.5k/yr)
      }
    ]
  },
  {
    id: 'sample_ambiguous_5',
    name: 'Ambiguous / Unclassified File (5 Records)',
    category: 'ambiguous',
    description: 'Generic raw telemetry/metrics file with obscure headers to test low-confidence prompt and manual classification.',
    expectedAnomalies: [
      'Ambiguity Trigger: Columns (metric_id, timestamp_utc, telemetry_val, ping_ms, node_ref) do not match financial categories.',
      'Manual User Selection Required: Demonstrates user confirmation overlay rather than guessing incorrectly.'
    ],
    data: [
      {
        metric_id: 'NODE-US-EAST-01',
        timestamp_utc: '2024-10-18T12:00:00Z',
        telemetry_val: 88.42,
        ping_ms: 14,
        node_ref: 'SYS_GATEWAY'
      },
      {
        metric_id: 'NODE-US-EAST-02',
        timestamp_utc: '2024-10-18T12:01:00Z',
        telemetry_val: 94.10,
        ping_ms: 18,
        node_ref: 'SYS_GATEWAY'
      },
      {
        metric_id: 'NODE-EU-WEST-01',
        timestamp_utc: '2024-10-18T12:02:00Z',
        telemetry_val: 72.80,
        ping_ms: 82,
        node_ref: 'SYS_GATEWAY_EU'
      },
      {
        metric_id: 'NODE-AP-SOUTH-01',
        timestamp_utc: '2024-10-18T12:03:00Z',
        telemetry_val: 61.15,
        ping_ms: 120,
        node_ref: 'SYS_GATEWAY_AP'
      },
      {
        metric_id: 'NODE-US-WEST-01',
        timestamp_utc: '2024-10-18T12:04:00Z',
        telemetry_val: 89.90,
        ping_ms: 22,
        node_ref: 'SYS_GATEWAY'
      }
    ]
  }
];
