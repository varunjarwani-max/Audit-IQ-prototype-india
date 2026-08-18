import React, { useState } from 'react';
import { 
  Key, 
  ShieldCheck, 
  ShieldAlert, 
  RefreshCw, 
  Sliders, 
  FileSpreadsheet, 
  Database, 
  CheckCircle2, 
  Sparkles, 
  ChevronDown, 
  ChevronUp, 
  Eye, 
  EyeOff, 
  Cpu, 
  Layers,
  Server,
  Building
} from 'lucide-react';
import { FinancialDataType, RuleThresholds, SampleDataset } from '../types';
import { SAMPLE_DATASETS } from '../data/sampleDatasets';
import { GROQ_MODELS, testGroqConnection } from '../utils/groqClient';

interface SidebarProps {
  groqApiKey: string;
  onApiKeyChange: (key: string) => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
  onSelectSampleDataset: (dataset: SampleDataset) => void;
  activeDatasetId?: string;
  thresholds: RuleThresholds;
  onUpdateThresholds: (thresholds: RuleThresholds) => void;
  onResetThresholds: () => void;
  activeCategory: FinancialDataType;
}

export const Sidebar: React.FC<SidebarProps> = ({
  groqApiKey,
  onApiKeyChange,
  selectedModel,
  onModelChange,
  onSelectSampleDataset,
  activeDatasetId,
  thresholds,
  onUpdateThresholds,
  onResetThresholds,
  activeCategory
}) => {
  const [showKey, setShowKey] = useState(false);
  const [testingKey, setTestingKey] = useState(false);
  const [keyStatus, setKeyStatus] = useState<{ checked: boolean; valid: boolean; message: string }>({
    checked: false,
    valid: false,
    message: ''
  });
  const [showThresholds, setShowThresholds] = useState(false);

  const handleTestKey = async () => {
    if (!groqApiKey.trim()) {
      setKeyStatus({ checked: true, valid: false, message: 'Please enter a Groq API key first.' });
      return;
    }
    setTestingKey(true);
    setKeyStatus({ checked: false, valid: false, message: '' });
    const result = await testGroqConnection(groqApiKey, selectedModel);
    setTestingKey(false);
    setKeyStatus({
      checked: true,
      valid: result.success,
      message: result.message
    });
  };

  const MODULES: { id: FinancialDataType; name: string }[] = [
    { id: 'transactions', name: 'Transactions' },
    { id: 'ar_ap_aging', name: 'AR/AP Aging' },
    { id: 'general_ledger', name: 'General Ledger' },
    { id: 'fixed_assets', name: 'Fixed Assets' }
  ];

  return (
    <aside id="sidebar-container" className="w-full lg:w-80 bg-white border-r border-slate-200 flex flex-col p-5 overflow-y-auto shrink-0 text-slate-900 shadow-xs">
      {/* Brand Header */}
      <div className="flex items-center gap-3 pb-4 mb-5 border-b border-slate-200">
        <div className="w-9 h-9 bg-slate-900 rounded-lg flex items-center justify-center shadow-2xs">
          <span className="text-white font-extrabold text-sm font-mono">IQ</span>
        </div>
        <div>
          <div className="flex items-center gap-1.5">
            <h1 className="text-base font-bold tracking-tight text-slate-900">AuditIQ</h1>
            <span className="text-[10px] font-mono font-bold bg-slate-100 border border-slate-300 text-slate-700 px-1.5 py-0.2 rounded">
              PROTOTYPE
            </span>
          </div>
          <p className="text-[11px] font-mono text-slate-500">
            CA On-Premise Audit Layer
          </p>
        </div>
      </div>

      {/* Audit Engagement Metadata Box */}
      <div className="mb-5 p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-2">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <span className="text-slate-500 flex items-center gap-1">
            <Building className="w-3 h-3 text-slate-400" />
            Client Node:
          </span>
          <span className="font-bold text-slate-800">Local CA Server</span>
        </div>
        <div className="flex items-center justify-between text-[11px] font-mono">
          <span className="text-slate-500 flex items-center gap-1">
            <Server className="w-3 h-3 text-slate-400" />
            Hardware Profile:
          </span>
          <span className="font-bold text-slate-800">16GB RAM Target</span>
        </div>
        <div className="flex items-center justify-between text-[11px] font-mono pt-1.5 border-t border-slate-200/80">
          <span className="text-slate-500">Engine Type:</span>
          <span className="font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
            Vectorized Deterministic
          </span>
        </div>
      </div>

      {/* System Configuration (Groq API Key) */}
      <div className="mb-5">
        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
          Groq AI Advisor Setup
        </label>
        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">Groq API Key</label>
              {keyStatus.checked && (
                <span className={`text-[10px] font-medium flex items-center gap-1 ${keyStatus.valid ? 'text-emerald-600' : 'text-amber-600'}`}>
                  {keyStatus.valid ? <CheckCircle2 className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
                  {keyStatus.valid ? 'Connected' : 'Failed'}
                </span>
              )}
            </div>
            <div className="relative">
              <input
                id="groq-api-key-input"
                type={showKey ? 'text' : 'password'}
                value={groqApiKey}
                onChange={(e) => onApiKeyChange(e.target.value)}
                placeholder="gsk_..."
                className="w-full text-xs font-mono px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg pr-16 focus:outline-hidden focus:ring-1 focus:ring-slate-900 focus:bg-white transition-all"
              />
              <div className="absolute right-1.5 top-1.5 flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="p-1 text-slate-400 hover:text-slate-600 rounded"
                  title={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Target On-Premise LLM</label>
            <select
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              className="w-full text-xs font-mono p-2 bg-slate-50 border border-slate-300 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-slate-900"
            >
              {GROQ_MODELS.map(m => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={handleTestKey}
            disabled={testingKey || !groqApiKey.trim()}
            className="w-full py-1.5 px-3 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50 shadow-2xs"
          >
            {testingKey ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Key className="w-3.5 h-3.5" />}
            <span>Test Connection</span>
          </button>
        </div>
      </div>

      {/* Segregated Rule Engines Status */}
      <div className="mb-5">
        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
          Engine Routing Modules
        </label>
        <div className="space-y-1.5">
          {MODULES.map(m => {
            const isActive = activeCategory === m.id;
            return (
              <div
                key={m.id}
                className={`p-2.5 rounded-lg border text-xs flex items-center justify-between transition-colors ${
                  isActive
                    ? 'bg-slate-900 border-slate-900 text-white font-bold shadow-2xs'
                    : 'bg-slate-50 border-slate-200 text-slate-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-slate-300'}`} />
                  <span>{m.name}</span>
                </div>
                <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  isActive ? 'bg-slate-800 text-blue-300' : 'bg-white border border-slate-200 text-slate-500'
                }`}>
                  {isActive ? 'Routed' : 'Dormant'}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Thresholds Accordion */}
      <div className="mb-5 pt-3 border-t border-slate-200">
        <button
          type="button"
          onClick={() => setShowThresholds(!showThresholds)}
          className="w-full flex items-center justify-between text-xs font-bold text-slate-700 hover:text-slate-900 py-1"
        >
          <div className="flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-slate-500" />
            <span>Deterministic Thresholds</span>
          </div>
          {showThresholds ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {showThresholds && (
          <div className="mt-3 space-y-3 p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs">
            <div>
              <div className="flex justify-between text-[11px] font-mono mb-1">
                <span className="text-slate-600">Approval Limit:</span>
                <span className="font-bold text-slate-900">₹{thresholds.transactions.approvalThreshold.toLocaleString('en-IN')}</span>
              </div>
              <input
                type="range"
                min={10000}
                max={200000}
                step={5000}
                value={thresholds.transactions.approvalThreshold}
                onChange={(e) => onUpdateThresholds({
                  ...thresholds,
                  transactions: {
                    ...thresholds.transactions,
                    approvalThreshold: Number(e.target.value)
                  }
                })}
                className="w-full accent-slate-900"
              />
            </div>

            <div>
              <div className="flex justify-between text-[11px] font-mono mb-1">
                <span className="text-slate-600">Overdue Days:</span>
                <span className="font-bold text-slate-900">{thresholds.aging.overdueDaysThreshold} days</span>
              </div>
              <input
                type="range"
                min={30}
                max={180}
                step={15}
                value={thresholds.aging.overdueDaysThreshold}
                onChange={(e) => onUpdateThresholds({
                  ...thresholds,
                  aging: {
                    ...thresholds.aging,
                    overdueDaysThreshold: Number(e.target.value)
                  }
                })}
                className="w-full accent-slate-900"
              />
            </div>

            <button
              type="button"
              onClick={onResetThresholds}
              className="w-full text-center text-[10px] font-mono font-bold text-blue-700 hover:underline pt-1"
            >
              Reset to Standard ICAI Defaults
            </button>
          </div>
        )}
      </div>

      {/* Footer System Status */}
      <div className="mt-auto pt-4 border-t border-slate-200 text-[11px] font-mono text-slate-400 space-y-1">
        <div className="flex justify-between">
          <span>Engine Status:</span>
          <span className="text-emerald-700 font-bold">● Active Online</span>
        </div>
        <div className="flex justify-between">
          <span>Vector Mode:</span>
          <span className="text-slate-600">Pure AST / Pandas</span>
        </div>
      </div>
    </aside>
  );
};
