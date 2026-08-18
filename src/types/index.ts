export type FinancialDataType = 
  | 'transactions'
  | 'ar_ap_aging'
  | 'general_ledger'
  | 'fixed_assets'
  | 'ambiguous';

export interface ColumnSignature {
  category: FinancialDataType;
  displayName: string;
  description: string;
  targetModule: string;
  primaryHeaders: string[];
  secondaryHeaders: string[];
  aliasMap: Record<string, string[]>;
}

export interface MatchScore {
  category: FinancialDataType;
  displayName: string;
  score: number; // 0 to 100
  matchedPrimary: string[];
  matchedSecondary: string[];
  confidenceLevel: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';
  missingCritical: string[];
}

export interface DetectionClassification {
  detectedType: FinancialDataType;
  confidence: number; // 0 - 100
  isAmbiguous: boolean;
  scores: MatchScore[];
  matchedColumns: Record<string, string>; // rawHeader -> canonicalHeader
  unmatchedHeaders: string[];
  reasons: string[];
  routedModule: string;
}

export type SeverityLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export interface AuditFlag {
  id: string;
  ruleCode: string;
  ruleName: string;
  severity: SeverityLevel;
  description: string;
  affectedField?: string;
  actualValue?: any;
  expectedCondition?: string;
  remediation: string;
}

export interface FlaggedRecord {
  rowIndex: number;
  recordId: string | number;
  rawRecord: Record<string, any>;
  flags: AuditFlag[];
  riskScore: number; // 0 - 100
  status: 'FLAGGED' | 'CLEAN';
}

export interface ModuleAuditResult {
  moduleName: string;
  category: FinancialDataType;
  totalRecords: number;
  flaggedCount: number;
  cleanCount: number;
  criticalCount: number;
  highCount: number;
  records: FlaggedRecord[];
  summaryInsights: string[];
  executionTimeMs: number;
}

export interface RuleThresholds {
  transactions: {
    approvalLimit: number;
    structuringWindowDays: number;
    structuringLowerBound: number;
    structuringUpperBound: number;
    roundNumberMultiple: number;
  };
  aging: {
    moderateOverdueDays: number;
    severeOverdueDays: number;
    chronicLateCount: number;
  };
  generalLedger: {
    periodEndDaysThreshold: number; // e.g. last 4 days of month
    businessHoursStart: number; // 8 AM
    businessHoursEnd: number; // 18 PM (6 PM)
    allowWeekendEntries: boolean;
  };
  fixedAssets: {
    costDiscrepancyTolerance: number; // $ difference allowed
    minUsefulLifeYears: number;
    maxUsefulLifeYears: number;
  };
}

export interface SampleDataset {
  id: string;
  name: string;
  category: FinancialDataType;
  description: string;
  expectedAnomalies: string[];
  data: Record<string, any>[];
}
