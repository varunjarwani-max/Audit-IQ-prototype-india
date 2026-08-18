import React, { useState, useEffect, useMemo } from 'react';
import { 
  ShieldCheck, 
  Layers, 
  FileSpreadsheet, 
  AlertTriangle, 
  Info, 
  CheckCircle2, 
  RotateCcw,
  Sparkles,
  SlidersHorizontal
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
import { FileUploader } from './components/FileUploader';
import { SegregationHeader } from './components/SegregationHeader';
import { ManualConfirmationModal } from './components/ManualConfirmationModal';
import { BatchViewer } from './components/BatchViewer';
import { AuditFindings } from './components/AuditFindings';
import { GroqAuditAdvisor } from './components/GroqAuditAdvisor';

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

  // 2. Active File / Dataset State (Defaults to 5-record Transaction synthetic test batch)
  const defaultDataset = SAMPLE_DATASETS[0];
  const [activeDatasetId, setActiveDatasetId] = useState<string>(defaultDataset.id);
  const [filename, setFilename] = useState<string>('synthetic_transactions_batch_5.csv');
  const [headers, setHeaders] = useState<string[]>(Object.keys(defaultDataset.data[0]));
  const [records, setRecords] = useState<Record<string, any>[]>(defaultDataset.data);

  // 3. Classification & Routing State
  const [customColumnMap, setCustomColumnMap] = useState<Record<string, string>>({});
  const [manualCategoryOverride, setManualCategoryOverride] = useState<FinancialDataType | null>(null);
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);

  // 4. Rule Thresholds
  const [thresholds, setThresholds] = useState<RuleThresholds>(INITIAL_THRESHOLDS);

  // 5. 5-Record Batch Testing Slice State
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
        reasons: ['User manually confirmed and assigned data category.'],
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

  // Combined column map (auto detected + manual overrides)
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
        // When ambiguous, produce empty or baseline result
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

    // If ambiguous, automatically trigger confirmation modal
    const check = classifyFinancialData(parsed.headers);
    if (check.isAmbiguous) {
      setIsManualModalOpen(true);
    }
  };

  // Update a record inline during iterative testing
  const handleUpdateRecord = (rowIndex: number, updatedFields: Record<string, any>) => {
    setRecords(prev => {
      const copy = [...prev];
      copy[rowIndex] = { ...copy[rowIndex], ...updatedFields };
      return copy;
    });
  };

  // Reset to clean state
  const handleReset = () => {
    handleSelectSample(SAMPLE_DATASETS[0]);
  };

  return (
    <div className="min-h-screen bg-[#F3F4F6] text-slate-900 flex flex-col lg:flex-row antialiased font-sans">
      {/* Streamlit-Style Sidebar */}
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

      {/* Main App Workspace */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Minimalist Header */}
        <header className="h-16 bg-white border-b border-slate-200 px-6 sm:px-8 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold px-2 py-1 bg-green-100 text-green-700 rounded">
              Active Session
            </span>
            <span className="text-slate-400 text-xs font-mono truncate max-w-xs">
              {filename}
            </span>
            <span className="text-slate-300 text-xs hidden sm:inline">•</span>
            <span className="text-slate-500 text-xs hidden sm:inline">
              {records.length} records loaded
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              id="header-clear-btn"
              type="button"
              onClick={handleReset}
              className="px-3.5 py-1.5 text-xs font-semibold border border-slate-200 rounded hover:bg-slate-50 text-slate-700 transition-colors"
            >
              Reset Batch
            </button>
            <button
              id="header-override-btn"
              type="button"
              onClick={() => setIsManualModalOpen(true)}
              className="px-3.5 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded hover:bg-slate-800 transition-colors"
            >
              Configure Schema
            </button>
          </div>
        </header>

        {/* Scrollable Main Area */}
        <main className="flex-1 p-6 sm:p-8 space-y-6 overflow-y-auto">
          {/* File Upload Section */}
          <FileUploader
            onFileParsed={handleFileParsed}
            isLoading={false}
          />

          {/* 3-Card Segregation Status: (a) Detected Schema, (b) Routing Status, (c) Risk Profile */}
          <SegregationHeader
            classification={classification}
            filename={filename}
            totalRows={records.length}
            flaggedCount={auditResult.flaggedCount}
            onOpenManualOverride={() => setIsManualModalOpen(true)}
            onReset={handleReset}
          />

          {/* Testing Workflow: 5-Record Batch Table */}
          <BatchViewer
            records={auditResult.records}
            activeBatchIndex={activeBatchIndex}
            onBatchChange={setActiveBatchIndex}
            selectedRowIndex={selectedRowIndex}
            onSelectRow={setSelectedRowIndex}
            onUpdateRecord={handleUpdateRecord}
            category={classification.detectedType}
          />

          {/* Audit Findings: Detailed rule explainability matrix */}
          <AuditFindings
            records={auditResult.records}
            selectedRowIndex={selectedRowIndex}
            onClearRowSelection={() => setSelectedRowIndex(null)}
          />

          {/* Groq AI Forensic Audit Memo & Advisor */}
          <GroqAuditAdvisor
            groqApiKey={groqApiKey}
            selectedModel={selectedModel}
            classification={classification}
            auditResult={auditResult}
            batchData={records.slice(activeBatchIndex * 5, (activeBatchIndex + 1) * 5)}
            onOpenApiKeyPrompt={() => {
              const input = document.getElementById('groq-api-key-input');
              input?.focus();
            }}
          />
        </main>
      </div>

      {/* Manual Classification & Ambiguity Resolution Modal */}
      <ManualConfirmationModal
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
        classification={classification}
        headers={headers}
        sampleRows={records.slice(0, 5)}
        groqApiKey={groqApiKey}
        selectedModel={selectedModel}
        onConfirmCategory={(cat, customMap) => {
          setManualCategoryOverride(cat);
          if (customMap) setCustomColumnMap(customMap);
        }}
      />
    </div>
  );
}
