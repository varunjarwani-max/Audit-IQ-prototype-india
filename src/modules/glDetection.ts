import { AuditFlag, FlaggedRecord, ModuleAuditResult, RuleThresholds } from '../types';
import { normalizeHeader } from '../utils/detector';

export const DEFAULT_GL_THRESHOLDS: RuleThresholds['generalLedger'] = {
  periodEndDaysThreshold: 4, // last 4 days of month
  businessHoursStart: 8, // 8:00 AM
  businessHoursEnd: 18, // 6:00 PM
  allowWeekendEntries: false
};

export function runGlDetection(
  records: Record<string, any>[],
  columnMap: Record<string, string>,
  customThresholds?: Partial<RuleThresholds['generalLedger']>
): ModuleAuditResult {
  const startTime = performance.now();
  const thresholds = { ...DEFAULT_GL_THRESHOLDS, ...customThresholds };

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

  // Group by journal_reference to calculate debit/credit balance
  const jeGroups: Record<string, { totalDebit: number; totalCredit: number; rowIndices: number[] }> = {};

  records.forEach((row, index) => {
    const jeRef = String(getVal(row, 'journal_reference') || `UNASSIGNED_${index}`).trim();
    const debit = parseNum(getVal(row, 'debit'));
    const credit = parseNum(getVal(row, 'credit'));

    if (!jeGroups[jeRef]) {
      jeGroups[jeRef] = { totalDebit: 0, totalCredit: 0, rowIndices: [] };
    }
    jeGroups[jeRef].totalDebit += debit;
    jeGroups[jeRef].totalCredit += credit;
    jeGroups[jeRef].rowIndices.push(index);
  });

  const flaggedRecords: FlaggedRecord[] = [];
  let criticalCount = 0;
  let highCount = 0;

  records.forEach((row, index) => {
    const flags: AuditFlag[] = [];
    const dateVal = parseDate(getVal(row, 'entry_date'));
    const jeRef = String(getVal(row, 'journal_reference') || `UNASSIGNED_${index}`).trim();
    const accountName = String(getVal(row, 'account_name') || '').trim();
    const debit = parseNum(getVal(row, 'debit'));
    const credit = parseNum(getVal(row, 'credit'));
    const preparedBy = String(getVal(row, 'prepared_by') || '').trim();

    // 1. Unbalanced Journal Entry Check (Debits ≠ Credits in voucher/batch)
    if (jeRef && jeGroups[jeRef]) {
      const group = jeGroups[jeRef];
      const diff = Math.abs(group.totalDebit - group.totalCredit);
      if (diff > 0.01) {
        flags.push({
          id: `GL-BAL-${index}`,
          ruleCode: 'GL-01',
          ruleName: 'Unbalanced Journal Voucher (Debits ≠ Credits)',
          severity: 'CRITICAL',
          description: `Journal entry "${jeRef}" is unbalanced by $${diff.toLocaleString(undefined, { minimumFractionDigits: 2 })} (Total Dr: $${group.totalDebit.toLocaleString(undefined, { minimumFractionDigits: 2 })} vs Total Cr: $${group.totalCredit.toLocaleString(undefined, { minimumFractionDigits: 2 })}). Violates fundamental double-entry accounting rule.`,
          affectedField: 'debit / credit',
          actualValue: `Dr $${group.totalDebit.toFixed(2)} ≠ Cr $${group.totalCredit.toFixed(2)} (Diff: $${diff.toFixed(2)})`,
          expectedCondition: 'Total Debits == Total Credits (Variance = 0.00)',
          remediation: 'Post balancing entry to correcting suspense clearing ledger before trial balance aggregation.'
        });
      }
    }

    // 2. Off-Hours / Weekend Entry Creation Check
    if (dateVal) {
      const dayOfWeek = dateVal.getDay(); // 0 = Sunday, 6 = Saturday
      const hours = dateVal.getHours();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isOffHours = hours < thresholds.businessHoursStart || hours >= thresholds.businessHoursEnd;

      if (isWeekend) {
        flags.push({
          id: `GL-WKND-${index}`,
          ruleCode: 'GL-02',
          ruleName: 'Weekend Manual Journal Creation',
          severity: 'HIGH',
          description: `Journal posted on ${dateVal.toLocaleDateString('en-US', { weekday: 'long' })} at ${dateVal.toTimeString().split(' ')[0]}. Weekend manual adjustments are a primary indicator of unauthorized executive overrides or concealment.`,
          affectedField: 'entry_date',
          actualValue: `${dateVal.toLocaleDateString('en-US', { weekday: 'long' })} ${dateVal.toLocaleTimeString()}`,
          expectedCondition: 'Standard business weekday operational shift (Mon-Fri)',
          remediation: 'Require dual-custody audit confirmation for weekend posting authority.'
        });
      } else if (isOffHours) {
        flags.push({
          id: `GL-OFFHOURS-${index}`,
          ruleCode: 'GL-03',
          ruleName: 'Outside Normal Business Hours',
          severity: 'MEDIUM',
          description: `Journal entered at ${dateVal.toLocaleTimeString()} (outside normal window ${thresholds.businessHoursStart}:00 - ${thresholds.businessHoursEnd}:00).`,
          affectedField: 'entry_date',
          actualValue: `${hours}:${String(dateVal.getMinutes()).padStart(2, '0')}`,
          expectedCondition: `Between ${thresholds.businessHoursStart}:00 AM and ${thresholds.businessHoursEnd}:00 PM`,
          remediation: 'Review system audit logs for scheduled batch script justification or user login IP.'
        });
      }
    }

    // 3. Period-End Journal Adjustments (Last 3-5 days of the month)
    if (dateVal) {
      const year = dateVal.getFullYear();
      const month = dateVal.getMonth();
      const lastDayOfMonth = new Date(year, month + 1, 0).getDate();
      const currentDay = dateVal.getDate();
      const daysUntilMonthEnd = lastDayOfMonth - currentDay;

      if (daysUntilMonthEnd <= thresholds.periodEndDaysThreshold && daysUntilMonthEnd >= 0) {
        flags.push({
          id: `GL-PERIOD-END-${index}`,
          ruleCode: 'GL-04',
          ruleName: 'Period-End Manual Journal Adjustment',
          severity: 'HIGH',
          description: `Posted on Day ${currentDay} of ${lastDayOfMonth} (${daysUntilMonthEnd} day(s) before monthly financial close). High risk for earnings management, channel stuffing, or revenue manipulation.`,
          affectedField: 'entry_date',
          actualValue: `${dateVal.toISOString().split('T')[0]} (${daysUntilMonthEnd} days to close)`,
          expectedCondition: 'Routine subledger integration or documented closing checklist justification',
          remediation: 'Verify closing workpapers, supporting contract evidence, and controller approval memo.'
        });
      }
    }

    // 4. Unusual Suspense / Miscellaneous Account Names
    const suspiciousKeywords = ['suspense', 'misc', 'miscellaneous', 'adjustment', 'unallocated', 'clearing', 'reconcil'];
    if (suspiciousKeywords.some(kw => accountName.toLowerCase().includes(kw))) {
      flags.push({
        id: `GL-SUSPENSE-${index}`,
        ruleCode: 'GL-05',
        ruleName: 'High-Risk Clearing / Suspense Account Routing',
        severity: 'MEDIUM',
        description: `Account "${accountName}" represents a temporary clearing/suspense bucket. Unresolved balances in suspense accounts often mask unrecorded liabilities.`,
        affectedField: 'account_name',
        actualValue: accountName,
        expectedCondition: 'Permanent balance sheet or P&L account line item',
        remediation: 'Clear suspense balances to permanent accounts before closing reporting period.'
      });
    }

    // 5. Missing Prepared_By
    if (!preparedBy) {
      flags.push({
        id: `GL-NO-AUTHOR-${index}`,
        ruleCode: 'GL-06',
        ruleName: 'Unattributed Journal Originator',
        severity: 'MEDIUM',
        description: 'Journal record contains no preparer ID or user attribution credential.',
        affectedField: 'prepared_by',
        actualValue: 'NULL / UNKNOWN',
        expectedCondition: 'Verified accounting staff SSO username',
        remediation: 'Enforce non-repudiation audit trail in ERP journal entry sub-system.'
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
      recordId: jeRef || `GL-ROW-${index + 1}`,
      rawRecord: row,
      flags,
      riskScore,
      status: flags.length > 0 ? 'FLAGGED' : 'CLEAN'
    });
  });

  const flaggedCount = flaggedRecords.filter(r => r.status === 'FLAGGED').length;
  const cleanCount = flaggedRecords.length - flaggedCount;

  return {
    moduleName: 'GL / Journal Entry Anomaly Engine',
    category: 'general_ledger',
    totalRecords: records.length,
    flaggedCount,
    cleanCount,
    criticalCount,
    highCount,
    records: flaggedRecords,
    summaryInsights: [
      `Audited ${records.length} journal lines across ${Object.keys(jeGroups).length} unique journal reference batches.`,
      `Found ${flaggedCount} lines violating accounting controls (${criticalCount} Critical, ${highCount} High priority).`,
      `Verified double-entry balance: ${Object.values(jeGroups).filter(g => Math.abs(g.totalDebit - g.totalCredit) > 0.01).length} unbalanced vouchers detected.`
    ],
    executionTimeMs: Math.round(performance.now() - startTime)
  };
}
