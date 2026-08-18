import React, { useState } from 'react';
import { 
  Check, 
  Sparkles, 
  AlertCircle, 
  RefreshCw,
  SlidersHorizontal
} from 'lucide-react';
import { DetectionClassification, FinancialDataType } from '../types';
import { SIGNATURES } from '../utils/detector';
import { groqClassifyAmbiguousColumns } from '../utils/groqClient';

interface ManualConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  classification: DetectionClassification;
  headers: string[];
  sampleRows: Record<string, any>[];
  groqApiKey: string;
  selectedModel: string;
  onConfirmCategory: (category: FinancialDataType, customColumnMap?: Record<string, string>) => void;
}

export const ManualConfirmationModal: React.FC<ManualConfirmationModalProps> = ({
  isOpen,
  onClose,
  classification,
  headers,
  sampleRows,
  groqApiKey,
  selectedModel,
  onConfirmCategory
}) => {
  const [selectedCategory, setSelectedCategory] = useState<FinancialDataType>(
    classification.detectedType !== 'ambiguous' ? classification.detectedType : 'transactions'
  );
  const [columnMap, setColumnMap] = useState<Record<string, string>>({ ...classification.matchedColumns });
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [aiReasoning, setAiReasoning] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  if (!isOpen) return null;

  const currentSignature = SIGNATURES.find(s => s.category === selectedCategory);

  const handleGroqClassification = async () => {
    if (!groqApiKey) {
      setAiError('Please configure your Groq API key in the sidebar to use AI classification.');
      return;
    }
    setIsAiLoading(true);
    setAiError(null);
    try {
      const res = await groqClassifyAmbiguousColumns(groqApiKey, selectedModel, headers, sampleRows);
      if (res.recommendedCategory && ['transactions', 'ar_ap_aging', 'general_ledger', 'fixed_assets'].includes(res.recommendedCategory)) {
        setSelectedCategory(res.recommendedCategory as FinancialDataType);
      }
      if (res.suggestedColumnMapping) {
        setColumnMap(res.suggestedColumnMapping);
      }
      setAiReasoning(res.reasoning);
    } catch (err: any) {
      setAiError(err?.message || 'Failed to classify with Groq AI.');
    } finally {
      setIsAiLoading(false);
    }
  };

  const handleSave = () => {
    onConfirmCategory(selectedCategory, columnMap);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in">
      <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 shadow-xl space-y-5 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded bg-slate-100 text-slate-700 flex items-center justify-center font-bold">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">
                Confirm Financial Data Schema
              </h3>
              <p className="text-xs text-slate-500">
                Select the target category to route to the appropriate anomaly detection engine.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
          >
            ✕
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="space-y-5 overflow-y-auto flex-1 pr-1 text-xs">
          {/* Groq AI Assistant Assist Box */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-1.5 font-bold text-slate-900">
                <Sparkles className="w-3.5 h-3.5 text-slate-700" />
                <span>AI Automated Signature Matching</span>
              </div>
              <p className="text-slate-500 text-[11px] mt-0.5">
                Use Groq LLM to inspect messy/unstandardized column names and infer the optimal financial domain.
              </p>
            </div>
            <button
              id="groq-auto-classify-btn"
              type="button"
              onClick={handleGroqClassification}
              disabled={isAiLoading}
              className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white font-medium rounded transition-colors flex items-center gap-1.5 shrink-0"
            >
              {isAiLoading ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              <span>{isAiLoading ? 'Analyzing...' : 'Auto-Map with AI'}</span>
            </button>
          </div>

          {aiError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{aiError}</span>
            </div>
          )}

          {aiReasoning && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-900">
              <span className="font-bold text-[10px] uppercase block mb-1">AI Reasoning</span>
              <p className="text-slate-700 leading-snug">{aiReasoning}</p>
            </div>
          )}

          {/* 1. Category Selection */}
          <div className="space-y-2">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              1. Select Domain Category
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { id: 'transactions', name: 'Transactions', desc: 'Vendor, Account, Approval & Amount' },
                { id: 'ar_ap_aging', name: 'AR / AP Aging', desc: 'Invoices, Due Dates, Overdue Aging' },
                { id: 'general_ledger', name: 'General Ledger', desc: 'Double-Entry, Debit/Credit, Period-End' },
                { id: 'fixed_assets', name: 'Fixed Assets', desc: 'Depreciation, Useful Life & Carrying Value' }
              ].map((cat) => {
                const isSelected = selectedCategory === cat.id;
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => setSelectedCategory(cat.id as FinancialDataType)}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      isSelected
                        ? 'border-slate-900 bg-slate-50 ring-1 ring-slate-900 text-slate-900'
                        : 'border-slate-200 hover:border-slate-300 text-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold">{cat.name}</span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-slate-900" />}
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">{cat.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 2. Column Mapping Field Editor */}
          {currentSignature && (
            <div className="space-y-2">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                2. Map File Headers to Standard Audit Fields
              </label>
              <div className="border border-slate-200 rounded-lg divide-y divide-slate-100 overflow-hidden">
                {currentSignature.primaryHeaders.map((field) => {
                  const currentMapped = columnMap[field] || '';
                  return (
                    <div key={field} className="p-2.5 flex items-center justify-between gap-4 bg-white">
                      <div className="w-1/3">
                        <span className="font-mono font-bold text-slate-800 uppercase text-[11px]">
                          {field}
                        </span>
                      </div>
                      <div className="w-2/3">
                        <select
                          value={currentMapped}
                          onChange={(e) => setColumnMap({ ...columnMap, [field]: e.target.value })}
                          className="w-full px-2 py-1 bg-slate-50 border border-slate-200 rounded text-xs text-slate-900 focus:outline-none focus:border-slate-900"
                        >
                          <option value="">-- Select Header --</option>
                          {headers.map((h) => (
                            <option key={h} value={h}>
                              {h}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 border border-slate-200 rounded hover:bg-slate-50 text-slate-700 text-xs font-semibold"
          >
            Cancel
          </button>
          <button
            id="save-manual-confirmation-btn"
            type="button"
            onClick={handleSave}
            className="px-4 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded text-xs font-semibold"
          >
            Confirm & Run Engine
          </button>
        </div>
      </div>
    </div>
  );
};
