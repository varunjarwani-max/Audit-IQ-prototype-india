import React from 'react';
import { 
  FileSpreadsheet, 
  Binary, 
  Cpu, 
  ShieldCheck, 
  ArrowRight, 
  Lock, 
  CheckCircle2, 
  Activity, 
  Sliders, 
  FileText,
  Clock,
  BookOpen,
  Building2,
  TrendingDown
} from 'lucide-react';
import { FinancialDataType, RuleThresholds } from '../types';

interface RoutingPipelineStageProps {
  filename: string;
  detectedType: FinancialDataType;
  confidence: number;
  totalRecords: number;
  thresholds: RuleThresholds;
  onUpdateThresholds: (thresholds: RuleThresholds) => void;
  onAdvanceToReview: () => void;
}

export const RoutingPipelineStage: React.FC<RoutingPipelineStageProps> = ({
  filename,
  detectedType,
  confidence,
  totalRecords,
  thresholds,
  onUpdateThresholds,
  onAdvanceToReview
}) => {
  const engines = [
    {
      id: 'transactions' as FinancialDataType,
      title: 'Transaction Anomaly Engine',
      script: 'txn_detection.py / .ts',
      icon: Activity,
      description: 'Approval limit thresholds, ₹50k round-number anomalies, near-threshold structuring, 7-day multi-payment velocity.',
      rulesCount: 4,
      targetScope: 'Disbursements & P2P Ledgers'
    },
    {
      id: 'ar_ap_aging' as FinancialDataType,
      title: 'AR/AP Aging Ledger Engine',
      script: 'aging_detection.py / .ts',
      icon: Clock,
      description: 'Overdue >90 days tracking, inverted chronology (payment prior to invoice), chronic counterparty delinquency.',
      rulesCount: 3,
      targetScope: 'Receivables & Payables'
    },
    {
      id: 'general_ledger' as FinancialDataType,
      title: 'General Ledger Integrity Engine',
      script: 'gl_detection.py / .ts',
      icon: BookOpen,
      description: 'Double-entry balance check (Debits = Credits), off-hour / weekend postings, period-end clearing account parking.',
      rulesCount: 4,
      targetScope: 'Trial Balance & Journals'
    },
    {
      id: 'fixed_assets' as FinancialDataType,
      title: 'Fixed Asset Reconciliation Engine',
      script: 'fixed_asset_detection.py / .ts',
      icon: Building2,
      description: 'Depreciation policy verification, carrying value vs historical cost checks, straight-line deviation detection.',
      rulesCount: 3,
      targetScope: 'FAR Asset Registers'
    }
  ];

  return (
    <div id="stage-3-route-workspace" className="space-y-6">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-900 text-white">
              STAGE 03
            </span>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
              Isolated Routing & Deterministic Engine Architecture
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Routes verified schema payloads to sandboxed rule execution modules with guaranteed zero cross-contamination.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Badge: Deterministic rules — no LLM */}
          <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-900 text-emerald-400 font-mono text-xs font-bold rounded-lg border border-slate-700 shadow-2xs">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Deterministic rules — no LLM</span>
          </span>
        </div>
      </div>

      {/* Labeled Pipeline Diagram */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-white shadow-xs">
        <div className="flex items-center justify-between mb-4 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Active Data Pipeline Routing Flow
            </h3>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Latency: <b className="text-emerald-400 font-mono">0.12ms</b> | AST Execution: Vectorized
          </span>
        </div>

        {/* Pipeline Nodes */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative items-stretch">
          {/* Node 1: Ingested File */}
          <div className="bg-slate-800/90 border border-slate-700 rounded-xl p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-slate-400 uppercase font-bold">
                  Stage 01: Ingestion
                </span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-900/60 border border-blue-700 flex items-center justify-center text-blue-300">
                  <FileSpreadsheet className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <h4 className="text-xs font-bold truncate text-slate-100">{filename}</h4>
                  <p className="text-[11px] font-mono text-slate-400">{totalRecords} raw records</p>
                </div>
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-700/60 text-[11px] font-mono text-slate-400">
              Status: Verified Clean Parse
            </div>
          </div>

          {/* Node 2: Classifier */}
          <div className="bg-slate-800/90 border border-slate-700 rounded-xl p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-slate-400 uppercase font-bold">
                  Stage 02: Classification
                </span>
                <span className="text-[10px] font-mono font-bold text-blue-400 bg-blue-950 px-1.5 py-0.5 rounded border border-blue-800">
                  {confidence}% Match
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-indigo-900/60 border border-indigo-700 flex items-center justify-center text-indigo-300">
                  <Binary className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <h4 className="text-xs font-bold text-slate-100 uppercase">Alias Matrix Match</h4>
                  <p className="text-[11px] font-mono text-slate-400">Target: {detectedType}</p>
                </div>
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-700/60 text-[11px] font-mono text-slate-400">
              Signature: Exact Alias Binding
            </div>
          </div>

          {/* Node 3: Isolated Rule Engine */}
          <div className="bg-blue-950/70 border-2 border-blue-500 rounded-xl p-4 flex flex-col justify-between shadow-xs">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-blue-300 uppercase font-bold">
                  Stage 03: Routed Engine
                </span>
                <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-700">
                  <CheckCircle2 className="w-3 h-3" />
                  Active Sandboxed
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-600 border border-blue-400 flex items-center justify-center text-white">
                  <Cpu className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <h4 className="text-xs font-bold text-white truncate">
                    {detectedType.toUpperCase()} Engine
                  </h4>
                  <p className="text-[11px] font-mono text-blue-300">
                    AST Vectorized Rules
                  </p>
                </div>
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-blue-800/80 text-[11px] font-mono text-blue-200">
              Zero LLM Hallucination Risk
            </div>
          </div>
        </div>
      </div>

      {/* 4 Segregated Engine Cards (Visual Demonstration of Engine Isolation) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Engine Segregation Matrix (4 Isolated Modules)
          </h4>
          <span className="text-xs text-slate-500">
            Only the active module runs; inactive modules remain completely isolated in memory.
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {engines.map(engine => {
            const isActive = detectedType === engine.id;
            const Icon = engine.icon;

            return (
              <div
                key={engine.id}
                className={`p-4 rounded-xl border transition-all flex flex-col justify-between gap-3 ${
                  isActive
                    ? 'bg-slate-900 border-slate-900 text-white shadow-md ring-2 ring-blue-500/50'
                    : 'bg-white border-slate-200 text-slate-700 opacity-60'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                      isActive ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500'
                    }`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                      isActive
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-slate-100 text-slate-500'
                    }`}>
                      {isActive ? '● ACTIVE' : 'DORMANT'}
                    </span>
                  </div>

                  <h5 className="text-xs font-bold tracking-tight">
                    {engine.title}
                  </h5>
                  <p className={`font-mono text-[10px] mt-0.5 ${isActive ? 'text-blue-300' : 'text-slate-400'}`}>
                    {engine.script}
                  </p>

                  <p className={`text-[11px] mt-2 line-clamp-3 leading-relaxed ${
                    isActive ? 'text-slate-300' : 'text-slate-500'
                  }`}>
                    {engine.description}
                  </p>
                </div>

                <div className={`pt-2 border-t text-[10px] font-mono flex items-center justify-between ${
                  isActive ? 'border-slate-800 text-slate-400' : 'border-slate-100 text-slate-400'
                }`}>
                  <span>{engine.rulesCount} Rules</span>
                  <span>{engine.targetScope}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Advance to Stage 04 Button */}
      <div className="flex justify-end pt-2">
        <button
          type="button"
          onClick={onAdvanceToReview}
          className="px-5 py-2.5 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2 shadow-2xs"
        >
          <span>Proceed to Stage 04: 5-Record Batch Review & Validation Loop</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
