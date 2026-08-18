import React, { useState } from 'react';
import { 
  CheckCircle2, 
  AlertTriangle, 
  ChevronDown, 
  ChevronUp, 
  SlidersHorizontal,
  Table,
  Check
} from 'lucide-react';
import { DetectionClassification, FinancialDataType } from '../types';

interface SegregationHeaderProps {
  classification: DetectionClassification;
  filename: string;
  totalRows: number;
  flaggedCount?: number;
  onOpenManualOverride: () => void;
  onReset: () => void;
}

export const SegregationHeader: React.FC<SegregationHeaderProps> = ({
  classification,
  filename,
  totalRows,
  flaggedCount = 0,
  onOpenManualOverride,
  onReset
}) => {
  const [showMappingDetails, setShowMappingDetails] = useState(false);

  const getCategoryTitle = (type: FinancialDataType) => {
    switch (type) {
      case 'transactions': return 'Transaction Ledger';
      case 'ar_ap_aging': return 'AR/AP Aging Ledger';
      case 'general_ledger': return 'General Ledger (GL)';
      case 'fixed_assets': return 'Fixed Asset Register';
      default: return 'Ambiguous / Unclassified';
    }
  };

  const getModuleFilename = (type: FinancialDataType) => {
    switch (type) {
      case 'transactions': return 'txn_detection.ts';
      case 'ar_ap_aging': return 'aging_detection.ts';
      case 'general_ledger': return 'gl_detection.ts';
      case 'fixed_assets': return 'fixed_asset_detection.ts';
      default: return 'awaiting_routing.ts';
    }
  };

  const matchedCount = Object.keys(classification.matchedColumns).length;

  return (
    <div id="segregation-header-section" className="space-y-4">
      {/* Ambiguity Alert Banner if unclassified */}
      {classification.isAmbiguous && (
        <div id="ambiguity-alert-banner" className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-amber-900">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
            <div>
              <p className="text-xs font-semibold">
                Low Classification Confidence ({classification.confidence}%)
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                Column headers require confirmation to ensure accurate anomaly rule execution.
              </p>
            </div>
          </div>
          <button
            id="manual-confirm-trigger-btn"
            type="button"
            onClick={onOpenManualOverride}
            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs rounded transition-colors shrink-0"
          >
            Confirm Schema
          </button>
        </div>
      )}

      {/* 3 Metrics Cards (Clean Minimalism) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6">
        {/* Card 1: Detected Schema */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase mb-1 tracking-wider">
              Detected Schema
            </p>
            <h3 className="text-lg font-bold text-blue-600 truncate">
              {getCategoryTitle(classification.detectedType)}
            </h3>
          </div>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Confidence: <span className="font-semibold text-slate-700">{classification.confidence}%</span>
            </p>
            <button
              type="button"
              onClick={() => setShowMappingDetails(!showMappingDetails)}
              className="text-[11px] font-semibold text-slate-500 hover:text-slate-900 flex items-center gap-0.5"
            >
              <span>{matchedCount} fields</span>
              {showMappingDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Card 2: Routing Status */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase mb-1 tracking-wider">
              Routing Status
            </p>
            <h3 className="text-lg font-bold text-slate-900 font-mono">
              {getModuleFilename(classification.detectedType)}
            </h3>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
            <p className="text-xs text-slate-500 truncate">
              Rule-based + LLM validation
            </p>
            <span className="w-2 h-2 rounded-full bg-green-500" title="Active engine" />
          </div>
        </div>

        {/* Card 3: Risk Profile */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase mb-1 tracking-wider">
              Risk Profile
            </p>
            <h3 className={`text-lg font-bold ${flaggedCount > 0 ? 'text-red-500' : 'text-green-600'}`}>
              {flaggedCount} {flaggedCount === 1 ? 'Flag Raised' : 'Flags Raised'}
            </h3>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Out of <span className="font-semibold text-slate-700">{totalRows}</span> records processed
            </p>
          </div>
        </div>
      </div>

      {/* Expandable Column Mapping Details */}
      {showMappingDetails && (
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-3 animate-in fade-in">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Ingested Column Bindings
            </span>
            <button
              type="button"
              onClick={onOpenManualOverride}
              className="text-xs font-semibold text-slate-600 hover:text-slate-900 underline"
            >
              Modify Mappings
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {Object.entries(classification.matchedColumns).map(([stdKey, rawCol]) => (
              <div key={stdKey} className="p-2 bg-slate-50 border border-slate-200 rounded text-xs">
                <span className="text-[10px] text-slate-400 block uppercase font-mono">{stdKey}</span>
                <span className="font-semibold text-slate-800 font-mono truncate block">{rawCol}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
