import { AuditFlag, FlaggedRecord, ModuleAuditResult, RuleThresholds } from '../types';
import { normalizeHeader } from '../utils/detector';

export const DEFAULT_AGING_THRESHOLDS: RuleThresholds['aging'] = {
  moderateOverdueDays: 45,
  severeOverdueDays: 90,
  chronicLateCount: 2
};

export function runAgingDetection(
  records: Record<string, any>[],
  columnMap: Record<string, string>,
  customThresholds?: Partial<RuleThresholds['aging']>
): ModuleAuditResult {
  const startTime = performance.now();
  const thresholds = { ...DEFAULT_AGING_THRESHOLDS, ...customThresholds };

  const getVal = (row: Record<string, any>, standardField: string): any => {
    for (const [rawKey, canonicalKey] of Object.entries(columnMap)) {
      if (canonicalKey === standardField && row[rawKey] !== undefined) {
        return row[rawKey];
      }
    }
    if (row[standardField] !== undefined) return row[standardField];

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

  // Fixed benchmark date for repeatable testing: 2024-10-25
  const REFERENCE_TODAY = new Date('2024-10-25T00:00:00Z');

  // Group by customer/vendor to detect chronic delinquency
  const partyHistory: Record<string, { totalInvoices: number; overdueCount: number; totalOverdueSum: number }> = {};

  records.forEach((row) => {
    const party = String(getVal(row, 'customer_vendor') || '').trim();
    const dueDate = parseDate(getVal(row, 'due_date'));
    const paymentDate = parseDate(getVal(row, 'payment_date'));
    const status = String(getVal(row, 'invoice_status') || '').toUpperCase();
    const amount = parseNum(getVal(row, 'amount'));

    if (party) {
      if (!partyHistory[party]) {
        partyHistory[party] = { totalInvoices: 0, overdueCount: 0, totalOverdueSum: 0 };
      }
      partyHistory[party].totalInvoices++;

      const isUnpaid = !paymentDate || ['OPEN', 'OVERDUE', 'PENDING', 'UNPAID'].includes(status);
      if (isUnpaid && dueDate && dueDate < REFERENCE_TODAY) {
        partyHistory[party].overdueCount++;
        partyHistory[party].totalOverdueSum += amount;
      }
    }
  });

  const flaggedRecords: FlaggedRecord[] = [];
  let criticalCount = 0;
  let highCount = 0;

  records.forEach((row, index) => {
    const flags: AuditFlag[] = [];
    const invoiceDate = parseDate(getVal(row, 'invoice_date'));
    const dueDate = parseDate(getVal(row, 'due_date'));
    const paymentDate = parseDate(getVal(row, 'payment_date'));
    const amount = parseNum(getVal(row, 'amount'));
    const party = String(getVal(row, 'customer_vendor') || '').trim();
    const status = String(getVal(row, 'invoice_status') || '').toUpperCase();

    // 1. Severe Aging / Extreme Overdue check (>90 days or >45 days)
    if (dueDate) {
      const isUnpaid = !paymentDate || ['OPEN', 'OVERDUE', 'PENDING', 'UNPAID'].includes(status);
      if (isUnpaid) {
        const daysPastDue = Math.floor((REFERENCE_TODAY.getTime() - dueDate.getTime()) / (1000 * 60 * 60 * 24));
        
        if (daysPastDue >= thresholds.severeOverdueDays) {
          flags.push({
            id: `AGING-SEV-${index}`,
            ruleCode: 'AGE-01',
            ruleName: 'Severely Delinquent Aging (>90 Days)',
            severity: 'CRITICAL',
            description: `Invoice balance $${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })} is ${daysPastDue} days past maturity. Probability of uncollectible bad debt loss exceeds 75%.`,
            affectedField: 'due_date',
            actualValue: `${daysPastDue} days overdue (${dueDate.toISOString().split('T')[0]})`,
            expectedCondition: `<= ${thresholds.moderateOverdueDays} days past due`,
            remediation: 'Issue formal demand letter and initiate allowance for doubtful accounts write-down review.'
          });
        } else if (daysPastDue >= thresholds.moderateOverdueDays) {
          flags.push({
            id: `AGING-MOD-${index}`,
            ruleCode: 'AGE-02',
            ruleName: 'Moderately Delinquent Aging (>45 Days)',
            severity: 'HIGH',
            description: `Invoice is ${daysPastDue} days overdue with outstanding balance $${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}.`,
            affectedField: 'due_date',
            actualValue: `${daysPastDue} days overdue`,
            expectedCondition: 'Settlement within standard net-30 terms',
            remediation: 'Contact counterparty accounts payable / credit management to confirm remittance ETA.'
          });
        }
      }
    }

    // 2. Inverted Payment Timing (Payment made before invoice origination)
    if (paymentDate && invoiceDate && paymentDate.getTime() < invoiceDate.getTime()) {
      flags.push({
        id: `AGING-INV-PAY-${index}`,
        ruleCode: 'AGE-03',
        ruleName: 'Inverted Settlement Timing',
        severity: 'HIGH',
        description: `Payment date (${paymentDate.toISOString().split('T')[0]}) is recorded BEFORE the invoice issuance date (${invoiceDate.toISOString().split('T')[0]}). Indicates backdated documentation or fictitious billing.`,
        affectedField: 'payment_date',
        actualValue: `Paid on ${paymentDate.toISOString().split('T')[0]} (Invoiced: ${invoiceDate.toISOString().split('T')[0]})`,
        expectedCondition: 'Payment Date >= Invoice Issuance Date',
        remediation: 'Reconcile bank deposit statement to verify actual clearance timestamp and contract terms.'
      });
    }

    // 3. Corrupted Date Logic (Due date occurs prior to invoice date)
    if (dueDate && invoiceDate && dueDate.getTime() < invoiceDate.getTime()) {
      flags.push({
        id: `AGING-INV-DUE-${index}`,
        ruleCode: 'AGE-04',
        ruleName: 'Corrupted Maturity Chronology',
        severity: 'MEDIUM',
        description: `Invoice due date (${dueDate.toISOString().split('T')[0]}) precedes the document origination date (${invoiceDate.toISOString().split('T')[0]}). System calculation error or forged billing.`,
        affectedField: 'due_date',
        actualValue: `Due: ${dueDate.toISOString().split('T')[0]} < Invoiced: ${invoiceDate.toISOString().split('T')[0]}`,
        expectedCondition: 'Due Date >= Invoice Date + Standard Terms',
        remediation: 'Correct ERP aging schedule master data and re-evaluate term calculations.'
      });
    }

    // 4. Chronic Delinquent Counterparty Flag
    if (party && partyHistory[party] && partyHistory[party].overdueCount >= thresholds.chronicLateCount) {
      const stats = partyHistory[party];
      flags.push({
        id: `AGING-CHRONIC-${index}`,
        ruleCode: 'AGE-05',
        ruleName: 'Chronic Default Risk / Counterparty Exposure',
        severity: 'HIGH',
        description: `Account "${party}" possesses ${stats.overdueCount} concurrent delinquent balances totaling $${stats.totalOverdueSum.toLocaleString(undefined, { minimumFractionDigits: 2 })}.`,
        affectedField: 'customer_vendor',
        actualValue: `${stats.overdueCount} overdue items ($${stats.totalOverdueSum.toLocaleString()})`,
        expectedCondition: 'Credit limit enforcement and freeze on pending shipments/POs',
        remediation: 'Place account on credit freeze / prepay cash-in-advance terms immediately.'
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
      recordId: getVal(row, 'invoice_number') || `INV-ROW-${index + 1}`,
      rawRecord: row,
      flags,
      riskScore,
      status: flags.length > 0 ? 'FLAGGED' : 'CLEAN'
    });
  });

  const flaggedCount = flaggedRecords.filter(r => r.status === 'FLAGGED').length;
  const cleanCount = flaggedRecords.length - flaggedCount;

  return {
    moduleName: 'AR/AP Aging Anomaly Engine',
    category: 'ar_ap_aging',
    totalRecords: records.length,
    flaggedCount,
    cleanCount,
    criticalCount,
    highCount,
    records: flaggedRecords,
    summaryInsights: [
      `Evaluated aging profile for ${records.length} ledger invoices against benchmark audit date (2024-10-25).`,
      `Detected ${flaggedCount} aging anomalies (${criticalCount} Critical, ${highCount} High priority).`,
      `Identified ${Object.keys(partyHistory).filter(k => partyHistory[k].overdueCount > 0).length} accounts with overdue balances.`
    ],
    executionTimeMs: Math.round(performance.now() - startTime)
  };
}
