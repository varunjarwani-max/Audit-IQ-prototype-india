import pandas as pd
import numpy as np
from typing import List, Dict, Any, Set

def evaluate_txn_004_structuring(
    df: pd.DataFrame, 
    threshold: float = 50000.0, 
    window_days: int = 7
) -> List[Dict[str, Any]]:
    """
    Identifies vendor structuring / split invoicing.
    Flags transactions where multiple disbursements to the SAME vendor 
    within a rolling 7-day window aggregate over the threshold (₹50,000).
    """
    if df is None or df.empty or 'vendor' not in df.columns or 'date' not in df.columns or 'amount' not in df.columns:
        return []

    # Work on a copy with datetime parsing
    temp_df = df.copy()
    temp_df['date_dt'] = pd.to_datetime(temp_df['date'], errors='coerce')
    temp_df['amount_num'] = pd.to_numeric(temp_df['amount'], errors='coerce').fillna(0.0)

    flagged_indices: Set[int] = set()
    window_details: Dict[int, Dict[str, Any]] = {}

    # Group strictly by vendor
    for vendor_name, group in temp_df.groupby('vendor'):
        # Ignore empty/missing vendors
        if not str(vendor_name).strip() or str(vendor_name).upper() == 'NAN':
            continue

        # Sort chronologically by date
        group_sorted = group.sort_values('date_dt')
        indices = group_sorted.index.tolist()
        dates = group_sorted['date_dt'].tolist()
        amounts = group_sorted['amount_num'].tolist()
        n = len(group_sorted)

        # Check rolling bidirectional 7-day window for each transaction
        for i in range(n):
            current_date = dates[i]
            if pd.isna(current_date):
                continue

            # Identify all rows for this vendor within 7 days of current_date
            cluster_indices = []
            cluster_sum = 0.0

            for j in range(n):
                if pd.isna(dates[j]):
                    continue
                # Check if transaction falls within [-7 days, +7 days] or [0, +7 days]
                day_diff = abs((dates[j] - current_date).days)
                if day_diff <= window_days:
                    cluster_indices.append(indices[j])
                    cluster_sum += amounts[j]

            # Trigger condition: MULTIPLE txns in window AND total sum exceeds threshold
            if len(cluster_indices) > 1 and cluster_sum > threshold:
                for idx in cluster_indices:
                    # Ensure individual txn is a split piece (under threshold)
                    if temp_df.loc[idx, 'amount_num'] < threshold:
                        flagged_indices.add(idx)
                        window_details[idx] = {
                            "vendor": vendor_name,
                            "window_sum": cluster_sum,
                            "cluster_count": len(cluster_indices)
                        }

    # Format findings list
    findings = []
    for idx in sorted(list(flagged_indices)):
        row = df.loc[idx]
        info = window_details[idx]
        findings.append({
            "row_index": int(idx),
            "record_id": row.get("record_id", f"ROW-{idx}"),
            "vendor": info["vendor"],
            "date": str(row.get("date", "")),
            "amount": float(row.get("amount", 0.0)),
            "approved_by": row.get("approved_by", ""),
            "department": row.get("department", ""),
            "flags": [{
                "rule_code": "TXN-004",
                "rule_name": "Vendor Split Invoicing / Structuring",
                "severity": "HIGH",
                "detected_value": f"₹{row.get('amount', 0):,.2f}",
                "expected": f"Single PO or total < ₹{threshold:,.2f}",
                "description": (
                    f"Multiple disbursements to '{info['vendor']}' within 7 days "
                    f"({info['cluster_count']} txns) aggregate to ₹{info['window_sum']:,.2f}, "
                    f"exceeding the ₹{threshold:,.2f} authorization limit."
                ),
                "remediation": "Merge purchase orders; audit against master service agreement limits."
            }]
        })

    return findings
