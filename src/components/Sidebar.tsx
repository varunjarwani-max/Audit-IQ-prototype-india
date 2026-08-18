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
  Layers 
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
    <aside id="sidebar-container" className="w-full lg:w-72 bg-white border-r border-slate-200 flex flex-col p-6 overflow-y-auto shrink-0 text-slate-900">
      {/* Brand Header */}
      <div className="flex items-center gap-2 mb-8">
        <div className="w-8 h-8 bg-slate-900 rounded flex items-center justify-center">
          <span className="text-white font-bold text-xs">IQ</span>
        </div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900">AuditIQ</h1>
      </div>

      {/* System Configuration (Groq API Key) */}
      <div className="mb-6">
        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
          System Configuration
        </label>
        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-medium text-slate-700">Groq API Key</label>
              {keyStatus.checked && (
                <span className={`text-[10px] font-medium flex items-center gap-1 ${keyStatus.valid ? 'text-green-600' : 'text-amber-600'}`}>
                  {keyStatus.valid ? 'Active' : 'Invalid'}
                </span>
              )}
            </div>
            <div className="relative">
              <input
                id="groq-api-key-input"
                type={showKey ? 'text' : 'password'}
                value={groqApiKey}
                onChange={(e) => {
                  onApiKeyChange(e.target.value);
                  setKeyStatus({ checked: false, valid: false, message: '' });
                }}
                placeholder="gsk_..."
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded focus:ring-1 focus:ring-slate-900 outline-none text-slate-900 placeholder:text-slate-400 pr-8"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Key stored in session_state</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Model Architecture</label>
            <select
              id="groq-model-select"
              value={selectedModel}
              onChange={(e) => onModelChange(e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded focus:ring-1 focus:ring-slate-900 outline-none text-slate-800"
            >
              {GROQ_MODELS.map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>

          <button
            id="test-groq-connection-btn"
            type="button"
            onClick={handleTestKey}
            disabled={testingKey || !groqApiKey}
            className="w-full py-1.5 px-3 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-800 text-xs font-medium rounded transition-colors flex items-center justify-center gap-1.5"
          >
            {testingKey ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3 text-slate-600" />}
            <span>{testingKey ? 'Verifying...' : 'Test Connection'}</span>
          </button>
          {keyStatus.message && (
            <p className={`text-[10px] leading-tight ${keyStatus.valid ? 'text-green-600' : 'text-amber-600'}`}>
              {keyStatus.message}
            </p>
          )}
        </div>
      </div>

      {/* Detection Modules Status */}
      <nav className="mb-6">
        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-2">
          Detection Modules
        </label>
        <ul className="space-y-1">
          {MODULES.map((mod) => {
            const isActive = activeCategory === mod.id;
            return (
              <li
                key={mod.id}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-blue-500' : 'bg-slate-300'}`} />
                {mod.name}
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 5-Record Test Batches */}
      <div className="mb-6 space-y-2">
        <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider">
          5-Record Test Batches
        </label>
        <div className="space-y-1.5">
          {SAMPLE_DATASETS.map((dataset) => {
            const isSelected = activeDatasetId === dataset.id;
            return (
              <button
                key={dataset.id}
                id={`sample-batch-btn-${dataset.id}`}
                onClick={() => onSelectSampleDataset(dataset)}
                className={`w-full text-left p-2.5 rounded-lg border text-xs transition-all flex flex-col gap-0.5 ${
                  isSelected
                    ? 'bg-slate-900 border-slate-900 text-white shadow-xs'
                    : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{dataset.name}</span>
                  <span className={`text-[9px] font-mono uppercase px-1 py-0.5 rounded ${
                    isSelected ? 'bg-slate-800 text-slate-300' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {dataset.category.replace(/_/g, ' ')}
                  </span>
                </div>
                <p className={`text-[10px] line-clamp-1 ${isSelected ? 'text-slate-300' : 'text-slate-400'}`}>
                  {dataset.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Rule Engine Thresholds Customizer */}
      <div className="mb-6 space-y-2">
        <button
          type="button"
          onClick={() => setShowThresholds(!showThresholds)}
          className="w-full flex items-center justify-between p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Sliders className="w-3.5 h-3.5 text-slate-500" />
            Detection Rule Limits
          </span>
          {showThresholds ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>

        {showThresholds && (
          <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-3 text-xs">
            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-1">
                <span>Approval Limit ($)</span>
                <span className="font-mono text-slate-900 font-semibold">${thresholds.transactions.approvalLimit.toLocaleString()}</span>
              </div>
              <input
                type="range"
                min={2000}
                max={25000}
                step={1000}
                value={thresholds.transactions.approvalLimit}
                onChange={(e) => onUpdateThresholds({
                  ...thresholds,
                  transactions: { ...thresholds.transactions, approvalLimit: Number(e.target.value) }
                })}
                className="w-full accent-slate-900"
              />
            </div>
            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-1">
                <span>Structuring Lower ($)</span>
                <span className="font-mono text-slate-900 font-semibold">${thresholds.transactions.structuringLowerBound.toLocaleString()}</span>
              </div>
              <input
                type="range"
                min={5000}
                max={9800}
                step={100}
                value={thresholds.transactions.structuringLowerBound}
                onChange={(e) => onUpdateThresholds({
                  ...thresholds,
                  transactions: { ...thresholds.transactions, structuringLowerBound: Number(e.target.value) }
                })}
                className="w-full accent-slate-900"
              />
            </div>
            <div>
              <div className="flex justify-between text-[11px] text-slate-600 mb-1">
                <span>Severe Overdue (Days)</span>
                <span className="font-mono text-slate-900 font-semibold">{thresholds.aging.severeOverdueDays}d</span>
              </div>
              <input
                type="range"
                min={30}
                max={120}
                step={5}
                value={thresholds.aging.severeOverdueDays}
                onChange={(e) => onUpdateThresholds({
                  ...thresholds,
                  aging: { ...thresholds.aging, severeOverdueDays: Number(e.target.value) }
                })}
                className="w-full accent-slate-900"
              />
            </div>
            <button
              type="button"
              onClick={onResetThresholds}
              className="w-full text-center text-[10px] text-slate-500 hover:text-slate-800 underline pt-1"
            >
              Reset to Defaults
            </button>
          </div>
        )}
      </div>

      {/* Clean Bottom Profile Badge */}
      <div className="pt-6 mt-auto border-t border-slate-100">
        <div className="bg-slate-900 text-white p-4 rounded-lg text-center">
          <p className="text-xs opacity-70 mb-1">Current Profile</p>
          <p className="text-sm font-semibold">Internal Audit v2.5</p>
        </div>
      </div>
    </aside>
  );
};
