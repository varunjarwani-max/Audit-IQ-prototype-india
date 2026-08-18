import React, { useState, useMemo } from 'react';
import { 
  ShieldCheck, 
  RotateCcw, 
  Sparkles, 
  Eye, 
  SlidersHorizontal,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  FolderOpen
} from 'lucide-react';
import { 
  FinancialDataType, 
  DetectionClassification, 
  ModuleAuditResult, 
  RuleThresholds, 
  SampleDataset 
} from './types';
import { SAMPLE_DATASETS } from './data/sampleDatasets';
import { classifyFinancialData } from './utils/detector';
import { runTransactionDetection, DEFAULT_TRANSACTION_THRESHOLDS } from './modules/transactionDetection';
import { runAgingDetection, DEFAULT_AGING_THRESHOLDS } from './modules/agingDetection';
import { runGlDetection, DEFAULT_GL_THRESHOLDS } from './modules/glDetection';
import { runFixedAssetDetection, DEFAULT_FIXED_ASSET_THRESHOLDS } from './modules/fixedAssetDetection';
import { ParsedFileData } from './utils/parser';

import { Sidebar } from './components/Sidebar';
import { WorkflowStepper, WorkflowStage } from './components/WorkflowStepper';
import { UploadStage } from './components/UploadStage';
import { ClassificationStage } from './components/ClassificationStage';
import { RoutingPipelineStage } from './components/RoutingPipelineStage';
import { BatchReviewStage } from './components/BatchReviewStage';

const INITIAL_THRESHOLDS: RuleThresholds = {
  transactions: DEFAULT_TRANSACTION_THRESHOLDS,
  aging: DEFAULT_AGING_THRESHOLDS,
  generalLedger: DEFAULT_GL_THRESHOLDS,
  fixedAssets: DEFAULT_FIXED_ASSET_THRESHOLDS
};

export default function App() {
  // 1. Groq API Key Handling (Stored in session state as requested)
  const [groqApiKey, setGroqApiKey] = useState<string>(() => {
    return sessionStorage.getItem('auditiq_groq_api_key') || '';
  });
  const [selectedModel, setSelectedModel] = useState<string>('openai/gpt-oss-20b');

  const handleApiKeyChange = (key: string) => {
    setGroqApiKey(key);
    sessionStorage.setItem('auditiq_groq_api_key', key);
  };

  // 2. 4-Stage Workflow State: 'upload' | 'classify' | 'route' | 'review'
  const [currentStage, setCurrentStage] = useState<WorkflowStage>('review');
  const [showAllStagesView, setShowAllStagesView] = useState<boolean>(false);

  // 3. Active Dataset / Workpaper State (Defaults to 5-record Transaction test batch)
  const defaultDataset = SAMPLE_DATASETS[0];
  const [activeDatasetId, setActiveDatasetId] = useState<string>(defaultDataset.id);
  const [filename, setFilename] = useState<string>('synthetic_transactions_batch_5.csv');
  const [headers, setHeaders] = useState<string[]>(Object.keys(defaultDataset.data[0]));
  const [records, setRecords] = useState<Record<string, any>[]>(defaultDataset.data);

  // 4. Classification & Routing State
  const [customColumnMap, setCustomColumnMap] = useState<Record<string, string>>({});
  const [manualCategoryOverride, setManualCategoryOverride] = useState<FinancialDataType | null>(null);

  // 5. Rule Thresholds
  const [thresholds, setThresholds] = useState<RuleThresholds>(INITIAL_THRESHOLDS);

  // 6. 5-Record Batch Testing Slice State
  const [activeBatchIndex, setActiveBatchIndex] = useState<number>(0);
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null);

  // Compute Classification based on headers
  const classification: DetectionClassification = useMemo(() => {
    const rawClass = classifyFinancialData(headers);
    if (manualCategoryOverride) {
      return {
        ...rawClass,
        detectedType: manualCategoryOverride,
        confidence: 100,
        isAmbiguous: false,
        reasons: ['Auditor manually confirmed and bound schema category.'],
        routedModule: manualCategoryOverride === 'transactions'
          ? 'Transaction Anomaly Detection Engine (Approval & Structuring)'
          : manualCategoryOverride === 'ar_ap_aging'
          ? 'AR/AP Aging Anomaly Engine (Overdue & Payment Velocity)'
          : manualCategoryOverride === 'general_ledger'
          ? 'GL / Journal Entry Engine (Balance, Off-Hours & Period-End)'
          : 'Fixed Asset Reconciliation Engine (Valuation & Schedule Discrepancy)'
      };
    }
    return rawClass;
  }, [headers, manualCategoryOverride]);

  // Combined column map
  const activeColumnMap = useMemo(() => {
    return { ...classification.matchedColumns, ...customColumnMap };
  }, [classification.matchedColumns, customColumnMap]);

  // Execute the appropriate isolated module based on detected/routed category
  const auditResult: ModuleAuditResult = useMemo(() => {
    const targetCategory = classification.detectedType;

    switch (targetCategory) {
      case 'transactions':
        return runTransactionDetection(records, activeColumnMap, thresholds.transactions);
      case 'ar_ap_aging':
        return runAgingDetection(records, activeColumnMap, thresholds.aging);
      case 'general_ledger':
        return runGlDetection(records, activeColumnMap, thresholds.generalLedger);
      case 'fixed_assets':
        return runFixedAssetDetection(records, activeColumnMap, thresholds.fixedAssets);
      case 'ambiguous':
      default:
        return {
          moduleName: 'Awaiting User Category Confirmation',
          category: 'ambiguous',
          totalRecords: records.length,
          flaggedCount: 0,
          cleanCount: records.length,
          criticalCount: 0,
          highCount: 0,
          records: records.map((r, i) => ({
            rowIndex: i + 1,
            recordId: `ROW-${i + 1}`,
            rawRecord: r,
            flags: [],
            riskScore: 0,
            status: 'CLEAN'
          })),
          summaryInsights: ['Classification ambiguous. Please confirm data type to trigger automated rule detection.'],
          executionTimeMs: 0
        };
    }
  }, [classification.detectedType, records, activeColumnMap, thresholds]);

  // Handle sample dataset selection
  const handleSelectSample = (sample: SampleDataset) => {
    setActiveDatasetId(sample.id);
    setFilename(`${sample.id}.csv`);
    const sampleHeaders = Object.keys(sample.data[0] || {});
    setHeaders(sampleHeaders);
    setRecords(sample.data);
    setManualCategoryOverride(sample.category === 'ambiguous' ? null : null);
    setCustomColumnMap({});
    setActiveBatchIndex(0);
    setSelectedRowIndex(null);
  };

  // Handle uploaded file
  const handleFileParsed = (parsed: ParsedFileData) => {
    setActiveDatasetId('');
    setFilename(parsed.filename);
    setHeaders(parsed.headers);
    setRecords(parsed.rows);
    setManualCategoryOverride(null);
    setCustomColumnMap({});
    setActiveBatchIndex(0);
    setSelectedRowIndex(null);
  };

  // Inline Record Update during validation loop
  const handleUpdateRecord = (rowIndex: number, updatedFields: Record<string, any>) => {
    setRecords(prev => {
      const copy = [...prev];
      copy[rowIndex] = { ...copy[rowIndex], ...updatedFields };
      return copy;
    });
  };

  const handleManualMappingConfirm = (cat: FinancialDataType, columnMap: Record<string, string>) => {
    setManualCategoryOverride(cat);
    setCustomColumnMap(columnMap);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex flex-col lg:flex-row antialiased font-sans">
      {/* Sidebar Navigation & Configurations */}
      <Sidebar
        groqApiKey={groqApiKey}
        onApiKeyChange={handleApiKeyChange}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        onSelectSampleDataset={handleSelectSample}
        activeDatasetId={activeDatasetId}
        thresholds={thresholds}
        onUpdateThresholds={setThresholds}
        onResetThresholds={() => setThresholds(INITIAL_THRESHOLDS)}
        activeCategory={classification.detectedType}
      />

      {/* Main Forensic Workstation Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Minimalist Audit Header */}
        <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0 shadow-2xs">
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-300 rounded">
              ● Active Workpaper Session
            </span>
            <span className="text-slate-500 text-xs font-mono truncate max-w-xs font-semibold">
              {filename}
            </span>
            <span className="text-slate-300 text-xs hidden sm:inline">•</span>
            <span className="text-slate-600 text-xs font-mono hidden sm:inline">
              {records.length} records
            </span>
            <span className="text-slate-300 text-xs hidden sm:inline">•</span>
            <span className="text-xs font-mono text-slate-500 hidden md:inline">
              Flags: <b className="text-red-600">{auditResult.flaggedCount}</b>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              id="toggle-all-stages-btn"
              type="button"
              onClick={() => setShowAllStagesView(!showAllStagesView)}
              className={`px-3 py-1.5 text-xs font-semibold border rounded transition-colors flex items-center gap-1.5 ${
                showAllStagesView
                  ? 'bg-slate-900 text-white border-slate-900'
                  : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>{showAllStagesView ? 'Single Focused Stage' : 'All Stages View'}</span>
            </button>

            <button
              id="reset-batch-btn"
              type="button"
              onClick={() => handleSelectSample(SAMPLE_DATASETS[0])}
              className="px-3 py-1.5 text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 rounded transition-colors flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Reset Batch</span>
            </button>
          </div>
        </header>

        {/* Scrollable Audit Workstation */}
        <main className="flex-1 p-5 sm:p-7 space-y-6 overflow-y-auto">
          {/* Horizontal Stepper (Upload → Classify → Route → Review Findings) */}
          <WorkflowStepper
            activeStage={currentStage}
            onSelectStage={setCurrentStage}
            isAmbiguous={classification.isAmbiguous}
            confidence={classification.confidence}
            detectedType={classification.detectedType}
            flaggedCount={auditResult.flaggedCount}
            totalRecords={records.length}
          />

          {/* Workflow Stage Content Rendering */}
          {showAllStagesView ? (
            /* All Stages Rendered in Sequence */
            <div className="space-y-10">
              <UploadStage
                onFileParsed={handleFileParsed}
                onSelectSampleDataset={handleSelectSample}
                currentFilename={filename}
                totalRecords={records.length}
                onAdvanceToClassify={() => setCurrentStage('classify')}
              />

              <ClassificationStage
                classification={classification}
                headers={headers}
                sampleRows={records.slice(0, 5)}
                customColumnMap={customColumnMap}
                onConfirmManualMapping={handleManualMappingConfirm}
                onAdvanceToRoute={() => setCurrentStage('route')}
                groqApiKey={groqApiKey}
                selectedModel={selectedModel}
              />

              <RoutingPipelineStage
                filename={filename}
                detectedType={classification.detectedType}
                confidence={classification.confidence}
                totalRecords={records.length}
                thresholds={thresholds}
                onUpdateThresholds={setThresholds}
                onAdvanceToReview={() => setCurrentStage('review')}
              />

              <BatchReviewStage
                records={auditResult.records}
                activeBatchIndex={activeBatchIndex}
                onBatchChange={setActiveBatchIndex}
                selectedRowIndex={selectedRowIndex}
                onSelectRow={setSelectedRowIndex}
                onUpdateRecord={handleUpdateRecord}
                category={classification.detectedType}
                classification={classification}
                auditResult={auditResult}
                groqApiKey={groqApiKey}
                selectedModel={selectedModel}
                onOpenApiKeyPrompt={() => {
                  const input = document.getElementById('groq-api-key-input');
                  input?.focus();
                }}
              />
            </div>
          ) : (
            /* Single Focused Stage View based on activeStage */
            <div>
              {currentStage === 'upload' && (
                <UploadStage
                  onFileParsed={handleFileParsed}
                  onSelectSampleDataset={handleSelectSample}
                  currentFilename={filename}
                  totalRecords={records.length}
                  onAdvanceToClassify={() => setCurrentStage('classify')}
                />
              )}

              {currentStage === 'classify' && (
                <ClassificationStage
                  classification={classification}
                  headers={headers}
                  sampleRows={records.slice(0, 5)}
                  customColumnMap={customColumnMap}
                  onConfirmManualMapping={handleManualMappingConfirm}
                  onAdvanceToRoute={() => setCurrentStage('route')}
                  groqApiKey={groqApiKey}
                  selectedModel={selectedModel}
                />
              )}

              {currentStage === 'route' && (
                <RoutingPipelineStage
                  filename={filename}
                  detectedType={classification.detectedType}
                  confidence={classification.confidence}
                  totalRecords={records.length}
                  thresholds={thresholds}
                  onUpdateThresholds={setThresholds}
                  onAdvanceToReview={() => setCurrentStage('review')}
                />
              )}

              {currentStage === 'review' && (
                <BatchReviewStage
                  records={auditResult.records}
                  activeBatchIndex={activeBatchIndex}
                  onBatchChange={setActiveBatchIndex}
                  selectedRowIndex={selectedRowIndex}
                  onSelectRow={setSelectedRowIndex}
                  onUpdateRecord={handleUpdateRecord}
                  category={classification.detectedType}
                  classification={classification}
                  auditResult={auditResult}
                  groqApiKey={groqApiKey}
                  selectedModel={selectedModel}
                  onOpenApiKeyPrompt={() => {
                    const input = document.getElementById('groq-api-key-input');
                    input?.focus();
                  }}
                />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
