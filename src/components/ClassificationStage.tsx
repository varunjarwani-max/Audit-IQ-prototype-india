import React, { useState } from 'react';
import { 
  CheckCircle2, 
  AlertTriangle, 
  SlidersHorizontal, 
  Table, 
  ArrowRight, 
  RotateCcw,
  Sparkles,
  HelpCircle,
  Check,
  Columns
} from 'lucide-react';
import { DetectionClassification, FinancialDataType } from '../types';
import { getCategoryFields } from '../utils/detector';
import { suggestColumnMappingWithGroq } from '../utils/groqClient';

interface ClassificationStageProps {
  classification: DetectionClassification;
  headers: string[];
  sampleRows: Record<string, any>[];
  customColumnMap: Record<string, string>;
  onConfirmManualMapping: (category: FinancialDataType, columnMap: Record<string, string>) => void;
  onAdvanceToRoute: () => void;
  groqApiKey: string;
  selectedModel: string;
}

export const ClassificationStage: React.FC<ClassificationStageProps> = ({
  classification,
  headers,
  sampleRows,
  customColumnMap,
  onConfirmManualMapping,
  onAdvanceToRoute,
  groqApiKey,
  selectedModel
}) => {
  const [forceManualMode, setForceManualMode] = useState<boolean>(classification.isAmbiguous || classification.confidence < 50);
  const [selectedCategory, setSelectedCategory] = useState<FinancialDataType>(
    classification.detectedType === 'ambiguous' ? 'transactions' : classification.detectedType
  );
  const [mapping, setMapping] = useState<Record<string, string>>({
    ...classification.matchedColumns,
    ...customColumnMap
  });
  const [isSuggestingWithAI, setIsSuggestingWithAI] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState(false);

  const availableFields = getCategoryFields(selectedCategory);

  const handleFieldChange = (header: string, standardField: string) => {
    setMapping(prev => ({
      ...prev,
      [header]: standardField
    }));
  };

  const handleSaveMapping = () => {
    onConfirmManualMapping(selectedCategory, mapping);
    setSaveFeedback(true);
    setTimeout(() => setSaveFeedback(false), 2000);
  };

  const handleAutoSuggestAI = async () => {
    if (!groqApiKey.trim()) {
      alert('Please enter your Groq API key in the sidebar to use AI column mapping suggestions.');
      return;
    }
    setIsSuggestingWithAI(true);
    try {
      const suggested = await suggestColumnMappingWithGroq(
        groqApiKey,
        selectedModel,
        headers,
        sampleRows,
        selectedCategory
      );
      if (suggested && Object.keys(suggested).length > 0) {
        setMapping(prev => ({ ...prev, ...suggested }));
      }
    } catch (e: any) {
      alert(e?.message || 'Error running Groq AI suggestion.');
    } finally {
      setIsSuggestingWithAI(false);
    }
  };

  const getCategoryTitle = (type: FinancialDataType) => {
    switch (type) {
      case 'transactions': return 'Transaction Ledger';
      case 'ar_ap_aging': return 'AR/AP Aging Ledger';
      case 'general_ledger': return 'General Ledger (GL)';
      case 'fixed_assets': return 'Fixed Asset Register';
      default: return 'Ambiguous / Unclassified';
    }
  };

  const isManualView = forceManualMode || classification.isAmbiguous || classification.confidence < 50;

  return (
    <div id="stage-2-classify-workspace" className="space-y-6">
      {/* Stage Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-900 text-white">
              STAGE 02
            </span>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
              Schema Classification & Alias Matching Engine
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Evaluates uploaded column headers against canonical alias vectors with automated confidence scoring.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setForceManualMode(!isManualView)}
            className={`px-3 py-1.5 text-xs font-semibold rounded border transition-colors flex items-center gap-1.5 ${
              isManualView
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>{isManualView ? 'Show Automated Analysis' : 'Manual Mapping Override'}</span>
          </button>
        </div>
      </div>

      {/* If Ambiguous / Low Confidence Alert */}
      {classification.isAmbiguous && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 flex items-start gap-3 text-amber-900">
          <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900">
              Ambiguous Schema Signature Detected (Confidence: {classification.confidence}%)
            </h4>
            <p className="text-xs text-amber-800 mt-0.5">
              The uploaded column headers do not uniquely match a pre-defined canonical template with high confidence. Please use the two-column manual mapping interface below to bind columns to the expected audit schema.
            </p>
          </div>
        </div>
      )}

      {/* Main View: Either Detected Category Summary Card OR Manual Mapping Interface */}
      {!isManualView ? (
        <div className="space-y-6">
          {/* Card 1: Detected Category Card */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-2xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <span className="text-[10px] font-bold font-mono text-slate-400 uppercase tracking-wider">
                  Automated Signature Classifier Result
                </span>
                <div className="flex items-center gap-3 mt-1">
                  <h3 className="text-xl font-bold text-slate-900">
                    {getCategoryTitle(classification.detectedType)}
                  </h3>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border ${
                    classification.confidence >= 80
                      ? 'bg-emerald-50 border-emerald-300 text-emerald-700'
                      : classification.confidence >= 50
                      ? 'bg-blue-50 border-blue-300 text-blue-700'
                      : 'bg-amber-50 border-amber-300 text-amber-700'
                  }`}>
                    {classification.confidence}% match confidence
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onAdvanceToRoute}
                  className="px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2 shadow-2xs"
                >
                  <span>Proceed to Stage 03: Engine Routing</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Breakdown of which column headers matched which alias set */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Columns className="w-3.5 h-3.5 text-slate-500" />
                  <span>Column Header Alias Matching Breakdown ({headers.length} headers evaluated)</span>
                </h4>
                <span className="text-[11px] font-mono text-slate-500">
                  {Object.keys(classification.matchedColumns).length} of {availableFields.length} expected fields resolved
                </span>
              </div>

              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100/80 text-slate-700 font-semibold font-mono text-[11px] border-b border-slate-200">
                      <th className="py-2.5 px-4">Uploaded File Header</th>
                      <th className="py-2.5 px-4">Mapped Canonical Schema Field</th>
                      <th className="py-2.5 px-4 text-center">Alias Match Status</th>
                      <th className="py-2.5 px-4">Sample Value (Row 1)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {headers.map(header => {
                      const matchedField = classification.matchedColumns[header] || mapping[header];
                      const sampleVal = sampleRows[0] ? String(sampleRows[0][header] ?? '—') : '—';
                      const isMatched = !!matchedField;

                      return (
                        <tr key={header} className="hover:bg-slate-50 transition-colors">
                          <td className="py-2.5 px-4 font-mono font-bold text-slate-900">
                            {header}
                          </td>
                          <td className="py-2.5 px-4">
                            {isMatched ? (
                              <span className="font-mono text-[11px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
                                {matchedField}
                              </span>
                            ) : (
                              <span className="text-slate-400 italic text-[11px]">
                                unmapped / extra attribute
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-center">
                            {isMatched ? (
                              <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                                Mapped OK
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
                                Pass-Through
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 font-mono text-[11px] text-slate-600 truncate max-w-[200px]">
                            {sampleVal}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Two-Column Manual Mapping Interface */
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-2xs space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <h3 className="text-base font-bold text-slate-900">
                Two-Column Manual Schema Binding Interface
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Map raw uploaded column headers on the left directly into the expected audit schema fields on the right.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleAutoSuggestAI}
                disabled={isSuggestingWithAI}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded flex items-center gap-1.5"
              >
                <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                <span>{isSuggestingWithAI ? 'Suggesting...' : 'AI Auto-Suggest Mapping'}</span>
              </button>

              <button
                type="button"
                onClick={handleSaveMapping}
                className="px-4 py-1.5 text-xs font-bold bg-slate-900 hover:bg-slate-800 text-white rounded flex items-center gap-1.5 shadow-2xs"
              >
                {saveFeedback ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : null}
                <span>{saveFeedback ? 'Bindings Saved!' : 'Apply Column Bindings'}</span>
              </button>
            </div>
          </div>

          {/* Domain Selection Tabs */}
          <div className="space-y-2">
            <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              Target Financial Audit Domain:
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {(['transactions', 'ar_ap_aging', 'general_ledger', 'fixed_assets'] as FinancialDataType[]).map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`p-2.5 rounded-lg border text-left text-xs font-bold transition-all ${
                    selectedCategory === cat
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  <span className="font-mono block text-[10px] text-slate-400">
                    {cat.toUpperCase()}
                  </span>
                  {getCategoryTitle(cat)}
                </button>
              ))}
            </div>
          </div>

          {/* Two-Column Mapping Grid */}
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-100 text-slate-700 font-semibold font-mono text-[11px] border-b border-slate-200">
                  <th className="py-2.5 px-4 w-1/2">
                    Raw Uploaded Column Header (Left)
                  </th>
                  <th className="py-2.5 px-4 w-1/2">
                    Target Canonical Schema Field (Right)
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {headers.map(header => {
                  const currentMapped = mapping[header] || '';
                  const sampleVal = sampleRows[0] ? String(sampleRows[0][header] ?? '') : '';
                  const isUnmatched = !currentMapped;

                  return (
                    <tr 
                      key={header} 
                      className={`transition-colors ${
                        isUnmatched ? 'bg-amber-50/40 hover:bg-amber-50/70' : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="py-3 px-4 align-top">
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-slate-900 text-xs">
                            {header}
                          </span>
                          {isUnmatched && (
                            <span className="text-[10px] font-bold font-mono text-amber-700 bg-amber-100 border border-amber-300 px-2 py-0.5 rounded">
                              Unmapped
                            </span>
                          )}
                        </div>
                        {sampleVal && (
                          <div className="mt-1 font-mono text-[11px] text-slate-500 truncate">
                            Preview: <span className="text-slate-700">{sampleVal}</span>
                          </div>
                        )}
                      </td>

                      <td className="py-3 px-4 align-top">
                        <select
                          value={currentMapped}
                          onChange={(e) => handleFieldChange(header, e.target.value)}
                          className="w-full font-mono text-xs p-2 rounded-lg border border-slate-300 bg-white focus:outline-hidden focus:ring-1 focus:ring-slate-900"
                        >
                          <option value="">-- Ignore / Unmapped Pass-Through --</option>
                          {availableFields.map(f => (
                            <option key={f} value={f}>
                              {f}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => {
                handleSaveMapping();
                onAdvanceToRoute();
              }}
              className="px-5 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2 shadow-2xs"
            >
              <span>Confirm Bindings & Proceed to Route (Stage 03)</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
