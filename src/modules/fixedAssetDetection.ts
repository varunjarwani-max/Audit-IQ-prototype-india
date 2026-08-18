import { AuditFlag, FlaggedRecord, ModuleAuditResult, RuleThresholds } from '../types';
import { normalizeHeader } from '../utils/detector';

export const DEFAULT_FIXED_ASSET_THRESHOLDS: RuleThresholds['fixedAssets'] = {
  costDiscrepancyTolerance: 500, // $500 discrepancy threshold
  minUsefulLifeYears: 1,
  maxUsefulLifeYears: 40
};

export function runFixedAssetDetection(
  records: Record<string, any>[],
  columnMap: Record<string, string>,
  customThresholds?: Partial<RuleThresholds['fixedAssets']>
): ModuleAuditResult {
  const startTime = performance.now();
  const thresholds = { ...DEFAULT_FIXED_ASSET_THRESHOLDS, ...customThresholds };

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

  const REFERENCE_TODAY = new Date('2024-10-25T00:00:00Z');

  const flaggedRecords: FlaggedRecord[] = [];
  let criticalCount = 0;
  let highCount = 0;

  records.forEach((row, index) => {
    const flags: AuditFlag[] = [];
    const assetName = String(getVal(row, 'asset_name') || `ASSET-${index + 1}`).trim();
    const purchaseDate = parseDate(getVal(row, 'purchase_date'));
    const purchaseCost = parseNum(getVal(row, 'purchase_cost'));
    const deprMethod = String(getVal(row, 'depreciation_method') || '').trim();
    const usefulLife = parseNum(getVal(row, 'useful_life'));
    const currentValue = parseNum(getVal(row, 'current_value'));

    // 1. Missing Depreciation Method or Schedule
    if (!deprMethod || deprMethod.toLowerCase() === 'none' || deprMethod.toLowerCase() === 'null') {
      flags.push({
        id: `FA-METH-${index}`,
        ruleCode: 'FA-01',
        ruleName: 'Undefined Depreciation Policy',
        severity: 'HIGH',
        description: `Asset "${assetName}" lacks an assigned depreciation method or recognized accounting amortization schedule.`,
        affectedField: 'depreciation_method',
        actualValue: deprMethod || 'MISSING / EMPTY',
        expectedCondition: 'Recognized GAAP/IFRS method (e.g. Straight Line, MACRS, DDB)',
        remediation: 'Assign authorized asset classification and depreciation convention in fixed asset register.'
      });
    }

    // 2. Unreasonable or Missing Useful Life
    if (!usefulLife || usefulLife < thresholds.minUsefulLifeYears || usefulLife > thresholds.maxUsefulLifeYears) {
      flags.push({
        id: `FA-LIFE-${index}`,
        ruleCode: 'FA-02',
        ruleName: 'Irregular Useful Life Period',
        severity: usefulLife > 50 ? 'CRITICAL' : 'HIGH',
        description: `Useful life of ${usefulLife || 'UNDEFINED'} years is outside standard industry norms (${thresholds.minUsefulLifeYears} - ${thresholds.maxUsefulLifeYears} years). Artificially extended useful lives understate periodic depreciation expense.`,
        affectedField: 'useful_life',
        actualValue: usefulLife ? `${usefulLife} years` : 'NULL',
        expectedCondition: `${thresholds.minUsefulLifeYears} to ${thresholds.maxUsefulLifeYears} years based on asset class guidelines`,
        remediation: 'Recalibrate useful life in accordance with corporate fixed asset capitalization policy.'
      });
    }

    // 3. Current Book Value Exceeds Initial Purchase Cost
    if (currentValue > purchaseCost && purchaseCost > 0) {
      const overstatement = currentValue - purchaseCost;
      flags.push({
        id: `FA-OVER-COST-${index}`,
        ruleCode: 'FA-03',
        ruleName: 'Carrying Value Exceeds Acquisition Cost',
        severity: 'CRITICAL',
        description: `Reported current book value ($${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}) exceeds the original historical acquisition cost ($${purchaseCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}) by $${overstatement.toLocaleString(undefined, { minimumFractionDigits: 2 })}. Unauthorized asset revaluation anomaly.`,
        affectedField: 'current_value',
        actualValue: `$${currentValue.toLocaleString()} > $${purchaseCost.toLocaleString()}`,
        expectedCondition: 'Current Book Value <= Initial Purchase Cost',
        remediation: 'Audit fixed asset addition adjustments and correct inflated asset ledger balances.'
      });
    }

    // 4. Mathematical Depreciation Reconciliation Check (Straight Line)
    if (
      purchaseDate &&
      purchaseCost > 0 &&
      usefulLife >= 1 &&
      usefulLife <= 40 &&
      deprMethod.toLowerCase().includes('straight')
    ) {
      const elapsedYears = Math.max(0, (REFERENCE_TODAY.getTime() - purchaseDate.getTime()) / (1000 * 60 * 60 * 24 * 365.25));
      const annualDepreciation = purchaseCost / usefulLife;
      const expectedDepreciation = Math.min(purchaseCost, annualDepreciation * elapsedYears);
      const expectedBookValue = Math.max(0, purchaseCost - expectedDepreciation);

      const variance = Math.abs(currentValue - expectedBookValue);
      if (variance > thresholds.costDiscrepancyTolerance) {
        flags.push({
          id: `FA-RECON-${index}`,
          ruleCode: 'FA-04',
          ruleName: 'Carrying Value Reconciliation Discrepancy',
          severity: variance > 5000 ? 'CRITICAL' : 'HIGH',
          description: `Book value calculation discrepancy of $${variance.toLocaleString(undefined, { minimumFractionDigits: 2 })}. After ${elapsedYears.toFixed(1)} years, expected book value is ~$${expectedBookValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}, but register reports $${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}.`,
          affectedField: 'current_value',
          actualValue: `$${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })} (Expected: ~$${expectedBookValue.toLocaleString(undefined, { minimumFractionDigits: 2 })})`,
          expectedCondition: `Cost ($${purchaseCost.toLocaleString()}) - Accumulated Depreciation (~$${expectedDepreciation.toLocaleString()})`,
          remediation: 'Recalculate cumulative depreciation schedule and post correcting catch-up entry.'
        });
      }
    }

    // 5. Negative Book Value
    if (currentValue < 0) {
      flags.push({
        id: `FA-NEG-${index}`,
        ruleCode: 'FA-05',
        ruleName: 'Negative Net Book Value',
        severity: 'CRITICAL',
        description: `Current book value is negative ($${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}). Fixed assets cannot be depreciated below zero or salvage value.`,
        affectedField: 'current_value',
        actualValue: `$${currentValue.toLocaleString()}`,
        expectedCondition: 'Net Book Value >= $0.00',
        remediation: 'Cap accumulated depreciation at historical cost basis and retire/dispose asset if obsolete.'
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
      recordId: getVal(row, 'asset_id') || `ASSET-ROW-${index + 1}`,
      rawRecord: row,
      flags,
      riskScore,
      status: flags.length > 0 ? 'FLAGGED' : 'CLEAN'
    });
  });

  const flaggedCount = flaggedRecords.filter(r => r.status === 'FLAGGED').length;
  const cleanCount = flaggedRecords.length - flaggedCount;

  return {
    moduleName: 'Fixed Asset Reconciliation Engine',
    category: 'fixed_assets',
    totalRecords: records.length,
    flaggedCount,
    cleanCount,
    criticalCount,
    highCount,
    records: flaggedRecords,
    summaryInsights: [
      `Reconciled ${records.length} fixed capital assets against straight-line and GAAP capitalization parameters.`,
      `Flagged ${flaggedCount} assets with schedule or mathematical valuation discrepancies (${criticalCount} Critical, ${highCount} High priority).`,
      `Checked useful life boundaries and cumulative depreciation wear models.`
    ],
    executionTimeMs: Math.round(performance.now() - startTime)
  };
}
