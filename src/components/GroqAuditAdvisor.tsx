import React, { useState } from 'react';
import { 
  Sparkles, 
  RefreshCw, 
  FileText, 
  Copy, 
  Check, 
  AlertCircle,
  Key
} from 'lucide-react';
import { DetectionClassification, ModuleAuditResult } from '../types';
import { generateGroqAuditReport } from '../utils/groqClient';

interface GroqAuditAdvisorProps {
  groqApiKey: string;
  selectedModel: string;
  classification: DetectionClassification;
  auditResult: ModuleAuditResult;
  batchData: Record<string, any>[];
  onOpenApiKeyPrompt: () => void;
}

export const GroqAuditAdvisor: React.FC<GroqAuditAdvisorProps> = ({
  groqApiKey,
  selectedModel,
  classification,
  auditResult,
  batchData,
  onOpenApiKeyPrompt
}) => {
  const [memo, setMemo] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerateMemo = async () => {
    if (!groqApiKey.trim()) {
      setError('Please enter your Groq API key in the sidebar to generate AI audit memos.');
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const generated = await generateGroqAuditReport(
        groqApiKey,
        selectedModel,
        classification,
        auditResult,
        batchData
      );
      setMemo(generated);
    } catch (err: any) {
      setError(err?.message || 'Failed to generate memo with Groq.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopyMemo = () => {
    if (memo) {
      navigator.clipboard.writeText(memo);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div id="groq-audit-advisor-card" className="bg-white rounded-xl border border-slate-200 shadow-xs p-5 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">
              Groq AI Audit Advisor & Memo Generator
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-bold border border-slate-200">
              {selectedModel.split('-')[0].toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Generates executive SOX & internal audit workpapers summarizing the current 5-record test batch.
          </p>
        </div>

        <button
          id="generate-groq-memo-btn"
          type="button"
          onClick={handleGenerateMemo}
          disabled={isGenerating}
          className="px-4 py-2 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-semibold rounded flex items-center gap-2 transition-colors self-start sm:self-auto shadow-xs"
        >
          {isGenerating ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>Analyzing with Groq...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              <span>Generate Audit Memo</span>
            </>
          )}
        </button>
      </div>

      {!groqApiKey && !memo && (
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between gap-3 text-xs text-slate-700">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-slate-400 shrink-0" />
            <span>
              Enter your Groq API key in the sidebar configuration to enable instant LLM forensic audit analysis.
            </span>
          </div>
          <button
            type="button"
            onClick={onOpenApiKeyPrompt}
            className="text-xs font-semibold text-slate-900 underline shrink-0"
          >
            Enter Key
          </button>
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {memo && (
        <div className="space-y-2 animate-in fade-in">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-slate-500" />
              Executive Audit Workpaper Memo
            </span>
            <button
              id="copy-groq-memo-btn"
              type="button"
              onClick={handleCopyMemo}
              className="text-xs text-slate-500 hover:text-slate-900 flex items-center gap-1"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied to Clipboard' : 'Copy Memo'}</span>
            </button>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 font-sans text-xs text-slate-800 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
            {memo}
          </div>
        </div>
      )}
    </div>
  );
};
