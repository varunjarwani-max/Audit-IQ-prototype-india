import { AuditFlag, FlaggedRecord, ModuleAuditResult, RuleThresholds } from '../types';
import { normalizeHeader } from '../utils/detector';

export const DEFAULT_TRANSACTION_THRESHOLDS: RuleThresholds['transactions'] = {
  approvalLimit: 10000,
  structuringWindowDays: 3,
  structuringLowerBound: 9000,
  structuringUpperBound: 9999.99,
  roundNumberMultiple: 1000
};

/**
 * Isolated detection module for Operational Transactions
 */
export function runTransactionDetection(
  records: Record<string, any>[],
  columnMap: Record<string, string>,
  customThresholds?: Partial<RuleThresholds['transactions']>
): ModuleAuditResult {
  const startTime = performance.now();
  const thresholds = { ...DEFAULT_TRANSACTION_THRESHOLDS, ...customThresholds };

  // Helper to extract mapped value safely
  const getVal = (row: Record<string, any>, standardField: string): any => {
    // 1. Check mapped canonical keys
    for (const [rawKey, canonicalKey] of Object.entries(columnMap)) {
      if (canonicalKey === standardField && row[rawKey] !== undefined) {
        return row[rawKey];
      }
    }
    // 2. Direct property name fallback
    if (row[standardField] !== undefined) return row[standardField];

    // 3. Fuzzy search in row keys
    const normStandard = normalizeHeader(standardField);
    for (const [key, val] of Object.entries(row)) {
      if (normalizeHeader(key) === normStandard) return val;
    }
    return undefined;
  };

  const parseNum = (val: any): number => {
    if (typeof val === 'number') return isNaN(val) ? 0 : val;
    if (!val) return 0;
    const clean = String(val).replace(/[^0-9.-]/g, '');
    const parsed = parseFloat(clean);
    return isNaN(parsed) ? 0 : parsed;
  };

  const parseDate = (val: any): Date | null => {
    if (!val) return null;
    const d = new Date(val);
    return isNaN(d.getTime()) ? null : d;
  };

  const flaggedRecords: FlaggedRecord[] = [];
  let criticalCount = 0;
  let highCount = 0;

  // Track vendor groupings for multi-transaction structuring detection
  const vendorTransactions: Record<string, { index: number; date: Date | null; amount: number }[]> = {};

  records.forEach((row, index) => {
    const vendor = String(getVal(row, 'vendor') || '').trim();
    const date = parseDate(getVal(row, 'date'));
    const amount = parseNum(getVal(row, 'amount'));
    if (vendor && amount > 0) {
      if (!vendorTransactions[vendor]) vendorTransactions[vendor] = [];
      vendorTransactions[vendor].push({ index, date, amount });
    }
  });

  records.forEach((row, index) => {
    const flags: AuditFlag[] = [];
    const dateVal = getVal(row, 'date');
    const amount = parseNum(getVal(row, 'amount'));
    const vendor = String(getVal(row, 'vendor') || '').trim();
    const approver = getVal(row, 'approved_by');
    const department = String(getVal(row, 'department') || '').trim();
    const accountCode = String(getVal(row, 'account_code') || '').trim();

    // 1. Missing Approval Check
    const isApproverMissing = approver === null || approver === undefined || String(approver).trim() === '';
    if (isApproverMissing) {
      const isHighDollar = amount >= thresholds.approvalLimit;
      flags.push({
        id: `TXN-APP-${index}`,
        ruleCode: 'TXN-01',
        ruleName: 'Missing Authorization Sign-off',
        severity: isHighDollar ? 'CRITICAL' : 'HIGH',
        description: `Transaction amount $${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })} has no recorded approver or authorization credential.`,
        affectedField: 'approved_by',
        actualValue: 'BLANK / NULL',
        expectedCondition: 'Valid authorized manager username or signature ID',
        remediation: 'Obtain retroactive formal sign-off or hold disbursement pending dual manager approval.'
      });
    }

    // 2. Round Number Multiples Check ($1,000, $5,000, $10,000, $25,000)
    if (amount >= 1000 && amount % thresholds.roundNumberMultiple === 0) {
      flags.push({
        id: `TXN-RND-${index}`,
        ruleCode: 'TXN-02',
        ruleName: 'Suspicious Round-Dollar Value',
        severity: amount >= 10000 ? 'HIGH' : 'MEDIUM',
        description: `Exact round sum of $${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })} detected. Fabricated invoices frequently utilize round figures rather than calculated line items.`,
        affectedField: 'amount',
        actualValue: `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        expectedCondition: 'Itemized breakdown with applicable sales tax and line totals',
        remediation: 'Verify original supplier invoice PDF for line-item itemization and delivery confirmation.'
      });
    }

    // 3. Structuring / Threshold Evasion (Just below single-approval ceiling)
    const isStructuringZone = amount >= thresholds.structuringLowerBound && amount <= thresholds.structuringUpperBound;
    if (isStructuringZone) {
      flags.push({
        id: `TXN-STR-${index}`,
        ruleCode: 'TXN-03',
        ruleName: 'Threshold Evasion / Structuring Velocity',
        severity: 'CRITICAL',
        description: `Transaction of $${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })} falls into the evasive zone ($${thresholds.structuringLowerBound.toLocaleString()} - $${thresholds.structuringUpperBound.toLocaleString()}) immediately beneath the $${thresholds.approvalLimit.toLocaleString()} threshold.`,
        affectedField: 'amount',
        actualValue: `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        expectedCondition: `< $${thresholds.structuringLowerBound} or authorized via secondary executive tier`,
        remediation: 'Audit vendor contract for intentional split-billing across multiple purchase orders.'
      });
    }

    // 4. Consecutive Split-Billing across same vendor within close window
    if (vendor && vendorTransactions[vendor] && vendorTransactions[vendor].length > 1) {
      const peers = vendorTransactions[vendor];
      const thisRowDate = parseDate(dateVal);
      const windowPeers = peers.filter(p => {
        if (p.index === index) return false;
        if (!thisRowDate || !p.date) return true; // if no dates, flag all duplicates
        const diffDays = Math.abs((thisRowDate.getTime() - p.date.getTime()) / (1000 * 60 * 60 * 24));
        return diffDays <= thresholds.structuringWindowDays;
      });

      const totalVendorSpend = windowPeers.reduce((acc, p) => acc + p.amount, amount);
      if (windowPeers.length > 0 && totalVendorSpend >= thresholds.approvalLimit) {
        flags.push({
          id: `TXN-SPLIT-${index}`,
          ruleCode: 'TXN-04',
          ruleName: 'Repeated Vendor Split Invoicing',
          severity: 'HIGH',
          description: `Vendor "${vendor}" received ${windowPeers.length + 1} transactions totaling $${totalVendorSpend.toLocaleString(undefined, { minimumFractionDigits: 2 })} within ${thresholds.structuringWindowDays} days, exceeding the $${thresholds.approvalLimit.toLocaleString()} cap.`,
          affectedField: 'vendor',
          actualValue: `${windowPeers.length + 1} invoices ($${totalVendorSpend.toLocaleString()})`,
          expectedCondition: 'Consolidated PO approval required',
          remediation: 'Consolidate multiple orders to enforce aggregate delegation-of-authority limits.'
        });
      }
    }

    // 5. Incomplete Department / Account Code Allocation
    if (!department && !accountCode) {
      flags.push({
        id: `TXN-ALLOC-${index}`,
        ruleCode: 'TXN-05',
        ruleName: 'Unallocated Cost Center / GL Code',
        severity: 'LOW',
        description: 'Transaction lacks both department and account code allocation, creating unbudgeted clearing risk.',
        affectedField: 'department',
        actualValue: 'MISSING',
        expectedCondition: 'Assigned active chart of accounts segment',
        remediation: 'Assign valid cost center before general ledger posting.'
      });
    }

    const maxSeverity = flags.reduce((max, f) => {
      if (f.severity === 'CRITICAL') return 3;
      if (f.severity === 'HIGH' && max < 2) return 2;
      if (f.severity === 'MEDIUM' && max < 1) return 1;
      return max;
    }, 0);

    const riskScore = flags.length === 0 ? 0 : Math.min(100, (flags.length * 25) + (maxSeverity * 20));
    
    if (flags.some(f => f.severity === 'CRITICAL')) criticalCount++;
    if (flags.some(f => f.severity === 'HIGH')) highCount++;

    flaggedRecords.push({
      rowIndex: index + 1,
      recordId: getVal(row, 'transaction_id') || `TXN-ROW-${index + 1}`,
      rawRecord: row,
      flags,
      riskScore,
      status: flags.length > 0 ? 'FLAGGED' : 'CLEAN'
    });
  });

  const flaggedCount = flaggedRecords.filter(r => r.status === 'FLAGGED').length;
  const cleanCount = flaggedRecords.length - flaggedCount;

  const summaryInsights: string[] = [
    `Processed ${records.length} operational transactions across ${Object.keys(vendorTransactions).length} unique suppliers.`,
    `Identified ${flaggedCount} anomalous items (${criticalCount} Critical, ${highCount} High priority).`,
    criticalCount > 0 ? 'Urgent: High-risk structuring and authorization gaps detected.' : 'No critical compliance breaches identified.'
  ];

  return {
    moduleName: 'Transaction Anomaly Detection Engine',
    category: 'transactions',
    totalRecords: records.length,
    flaggedCount,
    cleanCount,
    criticalCount,
    highCount,
    records: flaggedRecords,
    summaryInsights,
    executionTimeMs: Math.round(performance.now() - startTime)
  };
}
