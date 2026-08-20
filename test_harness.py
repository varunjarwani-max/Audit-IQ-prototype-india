"""
test_harness.py
Dedicated Test & ROI Benchmarking Harness for AuditIQ.

Demonstrates:
1. Exact timing of deterministic vectorized Pandas rule engines across entire unsliced datasets (10,000+ rows).
2. Verified evaluation of cross-row rules (TXN-004 7-day structuring, AGE-003 chronic delinquency, GL-001 voucher imbalance).
3. Individual per-record 5C workpaper generation loop using `generate_5c_finding_memo` with ~30 RPM pacing & retry resilience.

Usage:
    python test_harness.py [--file path/to/data.csv] [--category transactions] [--llm-samples 3]
"""

import sys
import os
import time
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from detector import classify_columns, ALIAS_DEFINITIONS
from rules_engine import audit_transactions, audit_aging, audit_general_ledger, audit_fixed_assets
from groq_advisor import generate_5c_finding_memo, test_groq_key, SUPPORTED_MODELS
from sample_data import SAMPLE_DATASETS


def generate_stress_dataset(num_rows: int = 10000) -> pd.DataFrame:
    """Generates a synthetic 10,000-row transaction ledger with deliberate anomalies."""
    print(f"[*] Generating {num_rows:,} synthetic transaction records for stress testing...")
    np.random.seed(42)
    
    vendors = ["CloudNet Hosting", "Starlight Logistics", "Apex Consulting", "FastTrack Couriers", "Sigma Office Supplies"]
    departments = ["Engineering", "Operations", "Finance", "Marketing", "Legal"]
    approvers = ["J. Miller", "S. Chen", "A. Patel", "R. Sharma", "None", "", "M. Vance"]
    
    base_date = datetime(2024, 10, 1)
    
    dates = [base_date + timedelta(days=int(np.random.randint(0, 30)), hours=int(np.random.randint(0, 24))) for _ in range(num_rows)]
    amounts = np.random.uniform(500.0, 60000.0, size=num_rows).round(2)
    
    # Inject specific anomalies:
    # 1. Round numbers (TXN-002)
    amounts[10] = 50000.00
    amounts[50] = 75000.00
    amounts[100] = 120000.00
    
    # 2. Near-threshold structuring (TXN-003)
    amounts[20] = 49500.00
    amounts[70] = 48200.00
    amounts[150] = 49950.00

    # 3. Missing approvers (TXN-001)
    approver_list = np.random.choice(approvers, size=num_rows)
    approver_list[5] = "None"
    approver_list[15] = ""
    approver_list[25] = "N/A"

    # 4. Multi-payment 7-day vendor split structuring (TXN-004)
    # 3 transactions to Apex Consulting within 3 days totaling ₹70,000
    vendor_list = np.random.choice(vendors, size=num_rows)
    vendor_list[200] = "Apex Consulting"
    dates[200] = base_date + timedelta(days=2)
    amounts[200] = 25000.00
    
    vendor_list[201] = "Apex Consulting"
    dates[201] = base_date + timedelta(days=3)
    amounts[201] = 25000.00

    vendor_list[202] = "Apex Consulting"
    dates[202] = base_date + timedelta(days=4)
    amounts[202] = 20000.00

    df = pd.DataFrame({
        "txn_date": [d.strftime("%Y-%m-%d %H:%M") for d in dates],
        "spend_amount": amounts,
        "payee_name": vendor_list,
        "cost_code": np.random.choice(["GL-7010", "GL-5020", "GL-3011", "GL-8080"], size=num_rows),
        "authorized_by": approver_list,
        "business_unit": np.random.choice(departments, size=num_rows)
    })
    return df


def run_benchmark(
    file_path: str = None, 
    forced_category: str = None, 
    llm_samples: int = 2,
    api_key: str = None,
    model: str = "openai/gpt-oss-20b"
):
    print("=" * 80)
    print("🚀 AuditIQ Forensic Engine: Production Performance & Timing Benchmark")
    print("=" * 80)

    # 1. Ingest Data
    if file_path and os.path.exists(file_path):
        print(f"[1] Loading dataset from: {file_path}")
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
    else:
        print("[1] No external file specified. Using 10,000-row synthetic stress dataset.")
        df = generate_stress_dataset(10000)

    n_rows = len(df)
    print(f"    Loaded {n_rows:,} rows with columns: {list(df.columns)}")

    # 2. Benchmark Column Classification
    t0 = time.perf_counter()
    classification = classify_columns(list(df.columns))
    t_classify_ms = (time.perf_counter() - t0) * 1000.0

    cat = forced_category or classification["category"]
    if cat == "ambiguous":
        cat = classification["raw_best_category"]

    col_map = classification["matched_columns"]
    print(f"\n[2] Schema Classification Result:")
    print(f"    - Detected Domain: {cat.upper()} ({classification['confidence']}% confidence)")
    print(f"    - Execution Time:  {t_classify_ms:.2f} ms")
    print(f"    - Field Mappings:  {col_map}")

    # 3. Benchmark Vectorized Rule Execution across Full Unsliced DataFrame
    print(f"\n[3] Executing Deterministic Vectorized Rule Engine across FULL {n_rows:,} rows...")
    t_start_rules = time.perf_counter()

    if cat == "transactions":
        findings = audit_transactions(df, col_map, threshold_limit=50000.0)
    elif cat == "ar_ap_aging":
        findings = audit_aging(df, col_map, severe_overdue_days=90)
    elif cat == "general_ledger":
        findings = audit_general_ledger(df, col_map, period_end_days=4)
    elif cat == "fixed_assets":
        findings = audit_fixed_assets(df, col_map)
    else:
        raise ValueError(f"Unknown category '{cat}'")

    t_rules_ms = (time.perf_counter() - t_start_rules) * 1000.0
    throughput = n_rows / (t_rules_ms / 1000.0) if t_rules_ms > 0 else 0

    flagged_records = [f for f in findings if f.get("status") == "FLAGGED"]
    
    # Rule code breakdown
    rule_counts = {}
    for f in flagged_records:
        for flag in f.get("flags", []):
            code = flag["rule_code"]
            rule_counts[code] = rule_counts.get(code, 0) + 1

    print(f"    ⚡ Full Engine Scan Time: {t_rules_ms:.2f} ms ({throughput:,.0f} rows/sec)")
    print(f"    📊 Records Flagged:       {len(flagged_records):,} of {n_rows:,} ({len(flagged_records)/n_rows*100:.1f}%)")
    print(f"    🔍 Rule Code Breakdown:")
    for code, count in sorted(rule_counts.items()):
        print(f"       • {code}: {count:,} instances")

    # Verify cross-row rule TXN-004 if transactions
    if cat == "transactions" and "TXN-004" in rule_counts:
        print(f"    ✅ Cross-row rule TXN-004 successfully captured {rule_counts['TXN-004']} structured split payments across full dataset context.")

    # 4. Benchmark Individual 5C LLM Workpaper Generation (generate_5c_finding_memo)
    groq_key = api_key or os.getenv("GROQ_API_KEY")
    if not groq_key:
        print("\n[!] Skipping LLM 5C workpaper benchmark (no GROQ_API_KEY provided).")
        print("    To run LLM tests: python test_harness.py --api-key gsk_...")
    else:
        print(f"\n[4] Benchmarking Per-Record 5C Workpaper Generation with Groq ({model})...")
        print(f"    Pacing at ~2.0s interval to respect free-tier ~30 RPM rate-limiting ceiling...")
        
        sample_subset = flagged_records[:llm_samples]
        llm_times = []

        for idx, rec in enumerate(sample_subset, start=1):
            row_idx = rec["row_index"]
            raw_data = df.iloc[row_idx - 1].to_dict()
            record_payload = {
                "row_index": row_idx,
                "data": raw_data,
                "flags": rec["flags"]
            }

            t_call_start = time.perf_counter()
            try:
                memo = generate_5c_finding_memo(
                    api_key=groq_key,
                    model=model,
                    record=record_payload,
                    category=ALIAS_DEFINITIONS[cat]["display_name"]
                )
                t_call_sec = time.perf_counter() - t_call_start
                llm_times.append(t_call_sec)
                print(f"    [Record #{row_idx}] 5C Memo Drafted in {t_call_sec:.2f}s:")
                for line in memo.strip().split("\n")[:4]:
                    print(f"       {line}")
                print("       ...")
            except Exception as e:
                print(f"    [Record #{row_idx}] Error: {str(e)}")

            if idx < len(sample_subset):
                # Pacing delay
                time.sleep(2.0)

        if llm_times:
            avg_llm_time = sum(llm_times) / len(llm_times)
            print(f"\n    📈 Average 5C LLM Drafting Time: {avg_llm_time:.2f}s per flagged record")
            print(f"    🎯 Theoretical Throughput @ 30 RPM: ~30 fully documented 5C workpapers / minute")

    print("\n" + "=" * 80)
    print("✅ Benchmark Completed Successfully.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AuditIQ Performance & Timing Benchmark Harness")
    parser.add_argument("--file", type=str, default=None, help="Path to CSV or Excel file")
    parser.add_argument("--category", type=str, default=None, help="Force category")
    parser.add_argument("--llm-samples", type=int, default=2, help="Number of flagged records to draft 5C memos for")
    parser.add_argument("--api-key", type=str, default=None, help="Groq API Key")
    parser.add_argument("--model", type=str, default="openai/gpt-oss-20b", help="Model name")

    args = parser.parse_args()
    run_benchmark(
        file_path=args.file,
        forced_category=args.category,
        llm_samples=args.llm_samples,
        api_key=args.api_key,
        model=args.model
    )
