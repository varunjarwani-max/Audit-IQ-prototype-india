import React, { useState } from 'react';
import { 
  AlertCircle, 
  CheckCircle2, 
  ChevronLeft, 
  ChevronRight, 
  Edit3, 
  ShieldAlert, 
  Check, 
  Sparkles, 
  Copy, 
  RefreshCw, 
  FileText, 
  Info,
  X,
  Lock
} from 'lucide-react';
import { FlaggedRecord, FinancialDataType, DetectionClassification, ModuleAuditResult } from '../types';
import { formatINR } from '../utils/formatters';
import { generateGroqAuditReport } from '../utils/groqClient';

interface BatchReviewStageProps {
  records: FlaggedRecord[];
  activeBatchIndex: number;
  onBatchChange: (batchIndex: number) => void;
  selectedRowIndex: number | null;
  onSelectRow: (rowIndex: number | null) => void;
  onUpdateRecord: (recordIndex: number, updatedFields: Record<string, any>) => void;
  category: FinancialDataType;
  classification: DetectionClassification;
  auditResult: ModuleAuditResult;
  groqApiKey: string;
  selectedModel: string;
  onOpenApiKeyPrompt: () => void;
}

export const BatchReviewStage: React.FC<BatchReviewStageProps> = ({
  records,
  activeBatchIndex,
  onBatchChange,
  selectedRowIndex,
  onSelectRow,
  onUpdateRecord,
  category,
  classification,
  auditResult,
  groqApiKey,
  selectedModel,
  onOpenApiKeyPrompt
}) => {
  const BATCH_SIZE = 5;
  const totalBatches = Math.ceil(records.length / BATCH_SIZE) || 1;
  const currentBatchRecords = records.slice(
    activeBatchIndex * BATCH_SIZE,
    (activeBatchIndex + 1) * BATCH_SIZE
  );

  // Inline Row Editor State
  const [editingRow, setEditingRow] = useState<FlaggedRecord | null>(null);
  const [editFormData, setEditFormData] = useState<Record<string, any>>({});
  const [activeCellEdit, setActiveCellEdit] = useState<{ rowIndex: number; column: string } | null>(null);
  const [cellValue, setCellValue] = useState<string>('');

  // AI Workpaper Memo State
  const [memo, setMemo] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [memoError, setMemoError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Selected row for diagnostic
  const activeSelectedRecord = records.find(r => r.rowIndex === selectedRowIndex) || currentBatchRecords[0] || null;

  const startEditRow = (rec: FlaggedRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingRow(rec);
    setEditFormData({ ...rec.rawRecord });
  };

  const saveEditRow = () => {
    if (editingRow) {
      onUpdateRecord(editingRow.rowIndex - 1, editFormData);
      setEditingRow(null);
    }
  };

  const startQuickCellEdit = (rowIndex: number, column: string, val: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveCellEdit({ rowIndex, column });
    setCellValue(val !== null && val !== undefined ? String(val) : '');
  };

  const saveQuickCellEdit = () => {
    if (activeCellEdit) {
      const rec = records.find(r => r.rowIndex === activeCellEdit.rowIndex);
      if (rec) {
        let parsedVal: any = cellValue;
        // Parse numerical values if appropriate
        if (!isNaN(Number(cellValue)) && cellValue.trim() !== '') {
          parsedVal = Number(cellValue);
        }
        onUpdateRecord(activeCellEdit.rowIndex - 1, {
          [activeCellEdit.column]: parsedVal
        });
      }
      setActiveCellEdit(null);
    }
  };

  const handleGenerateAIWorkpaper = async () => {
    if (!groqApiKey.trim()) {
      setMemoError('Please enter your Groq API key in the sidebar to generate AI audit memos.');
      return;
    }

    setIsGenerating(true);
    setMemoError(null);
    try {
      const rawRows = currentBatchRecords.map(r => r.rawRecord);
      const generated = await generateGroqAuditReport(
        groqApiKey,
        selectedModel,
        classification,
        auditResult,
        rawRows
      );
      setMemo(generated);
    } catch (err: any) {
      setMemoError(err?.message || 'Failed to generate audit memo.');
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

  // Get primary category columns to render
  const getCategoryColumns = (): { key: string; label: string; align: 'left' | 'right' | 'center'; isCurrency?: boolean }[] => {
    switch (category) {
      case 'transactions':
        return [
          { key: 'date', label: 'Date', align: 'left' },
          { key: 'vendor', label: 'Vendor / Counterparty', align: 'left' },
          { key: 'account_code', label: 'GL Code', align: 'left' },
          { key: 'amount', label: 'Amount (₹)', align: 'right', isCurrency: true },
          { key: 'approved_by', label: 'Authorization', align: 'left' },
          { key: 'department', label: 'Cost Center', align: 'left' }
        ];
      case 'ar_ap_aging':
        return [
          { key: 'customer_vendor', label: 'Counterparty', align: 'left' },
          { key: 'invoice_date', label: 'Invoice Date', align: 'left' },
          { key: 'due_date', label: 'Due Date', align: 'left' },
          { key: 'payment_date', label: 'Payment Date', align: 'left' },
          { key: 'amount', label: 'Balance (₹)', align: 'right', isCurrency: true },
          { key: 'invoice_status', label: 'Status', align: 'center' }
        ];
      case 'general_ledger':
        return [
          { key: 'entry_date', label: 'Posting Date', align: 'left' },
          { key: 'journal_reference', label: 'Voucher Ref', align: 'left' },
          { key: 'account_name', label: 'Account Name', align: 'left' },
          { key: 'debit', label: 'Debit (₹)', align: 'right', isCurrency: true },
          { key: 'credit', label: 'Credit (₹)', align: 'right', isCurrency: true },
          { key: 'prepared_by', label: 'Prepared By', align: 'left' }
        ];
      case 'fixed_assets':
        return [
          { key: 'asset_name', label: 'Asset Description', align: 'left' },
          { key: 'purchase_date', label: 'Acquired Date', align: 'left' },
          { key: 'purchase_cost', label: 'Cost (₹)', align: 'right', isCurrency: true },
          { key: 'current_value', label: 'Carrying (₹)', align: 'right', isCurrency: true },
          { key: 'depreciation_method', label: 'Method', align: 'left' },
          { key: 'useful_life', label: 'Life (Yrs)', align: 'right' }
        ];
      default:
        return [
          { key: 'col1', label: 'Column 1', align: 'left' },
          { key: 'col2', label: 'Column 2', align: 'left' }
        ];
    }
  };

  const activeColumns = getCategoryColumns();

  return (
    <div id="stage-4-review-workspace" className="space-y-6">
      {/* Section Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-900 text-white">
              STAGE 04
            </span>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
              5-Record Batch Review & Ground Truth Validation Loop
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Iterative validation table with live inline correction affordances and instant deterministic re-evaluation.
          </p>
        </div>

        {/* Batch Navigation Toolbar */}
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-white border border-slate-300 rounded-lg p-0.5 shadow-2xs">
            <button
              type="button"
              disabled={activeBatchIndex === 0}
              onClick={() => onBatchChange(activeBatchIndex - 1)}
              className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 text-slate-700 transition-colors"
              title="Previous 5 records"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <span className="font-mono text-xs font-semibold text-slate-700 px-3">
              Batch {activeBatchIndex + 1} of {totalBatches}
            </span>

            <button
              type="button"
              disabled={activeBatchIndex >= totalBatches - 1}
              onClick={() => onBatchChange(activeBatchIndex + 1)}
              className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 text-slate-700 transition-colors"
              title="Next 5 records"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Main 5-Record Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              Active Audit Slice ({currentBatchRecords.length} Records)
            </span>
            <span className="text-[11px] font-mono text-slate-500">
              Showing rows {activeBatchIndex * BATCH_SIZE + 1} - {Math.min((activeBatchIndex + 1) * BATCH_SIZE, records.length)} of {records.length}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-slate-500">
              <b className="text-red-600 font-bold">{currentBatchRecords.filter(r => r.status === 'FLAGGED').length}</b> Flagged in this batch
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-100 text-slate-700 font-semibold font-mono text-[11px] border-b border-slate-200">
                <th className="py-3 px-3 w-12 text-center">Row</th>
                <th className="py-3 px-4 min-w-[140px]">Audit Status</th>
                {activeColumns.map(col => (
                  <th 
                    key={col.key} 
                    className={`py-3 px-4 ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}`}
                  >
                    {col.label}
                  </th>
                ))}
                <th className="py-3 px-4 min-w-[200px]">Triggered Rule Flag(s)</th>
                <th className="py-3 px-3 text-right w-24">Validate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {currentBatchRecords.map(record => {
                const isSelected = selectedRowIndex === record.rowIndex;
                const isFlagged = record.status === 'FLAGGED';

                return (
                  <tr
                    key={`batch-row-${record.rowIndex}-${record.recordId}`}
                    onClick={() => onSelectRow(record.rowIndex)}
                    className={`transition-colors cursor-pointer ${
                      isSelected
                        ? 'bg-blue-50/80 ring-1 ring-blue-500/50'
                        : isFlagged
                        ? 'bg-red-50/20 hover:bg-red-50/40'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    {/* Row Index */}
                    <td className="py-3 px-3 text-center font-mono font-semibold text-slate-500 text-[11px]">
                      #{record.rowIndex}
                    </td>

                    {/* Audit Status Badge */}
                    <td className="py-3 px-4">
                      {isFlagged ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-red-100 text-red-800 border border-red-200">
                          <AlertCircle className="w-3 h-3 text-red-600" />
                          FLAGGED ({record.flags.length})
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          CLEAN
                        </span>
                      )}
                    </td>

                    {/* Dynamic Fields per Category */}
                    {activeColumns.map(col => {
                      const rawVal = record.rawRecord[col.key];
                      const isEditingThisCell = activeCellEdit?.rowIndex === record.rowIndex && activeCellEdit?.column === col.key;

                      return (
                        <td
                          key={`cell-${record.rowIndex}-${col.key}`}
                          onClick={(e) => startQuickCellEdit(record.rowIndex, col.key, rawVal, e)}
                          className={`py-3 px-4 ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'} ${
                            col.isCurrency ? 'font-mono font-semibold text-slate-900' : 'text-slate-800'
                          } hover:bg-amber-100/50 transition-colors group relative`}
                          title="Click to edit value directly (Ground Truth Loop)"
                        >
                          {isEditingThisCell ? (
                            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                              <input
                                autoFocus
                                type="text"
                                value={cellValue}
                                onChange={(e) => setCellValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') saveQuickCellEdit();
                                  if (e.key === 'Escape') setActiveCellEdit(null);
                                }}
                                className="w-full text-xs font-mono p-1 border border-blue-500 rounded bg-white focus:outline-hidden"
                              />
                              <button
                                type="button"
                                onClick={saveQuickCellEdit}
                                className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center justify-between gap-1">
                              <span className={col.align === 'right' ? 'w-full text-right' : ''}>
                                {rawVal === null || rawVal === undefined || rawVal === '' ? (
                                  <span className="text-amber-500 italic font-mono text-[10px]">null</span>
                                ) : col.isCurrency ? (
                                  formatINR(rawVal)
                                ) : (
                                  String(rawVal)
                                )}
                              </span>
                              <Edit3 className="w-3 h-3 text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                            </div>
                          )}
                        </td>
                      );
                    })}

                    {/* Flag Column: Triggered Rule Tags */}
                    <td className="py-3 px-4 align-middle">
                      {record.flags.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {record.flags.map((f, fIdx) => (
                            <span
                              key={`flag-${record.rowIndex}-${f.id || f.ruleCode || fIdx}`}
                              className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border inline-flex items-center gap-1 ${
                                f.severity === 'CRITICAL'
                                  ? 'bg-red-100 text-red-900 border-red-300'
                                  : f.severity === 'HIGH'
                                  ? 'bg-amber-100 text-amber-900 border-amber-300'
                                  : 'bg-yellow-50 text-yellow-800 border-yellow-200'
                              }`}
                              title={f.description}
                            >
                              <span className="font-extrabold">[{f.ruleCode || f.id}]</span>
                              <span>{f.ruleName}</span>
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[11px] text-slate-400 font-mono italic">
                          No deterministic flags triggered
                        </span>
                      )}
                    </td>

                    {/* Inline "Correct" Affordance */}
                    <td className="py-3 px-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => startEditRow(record, e)}
                        className="px-2.5 py-1 text-[11px] font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded inline-flex items-center gap-1 transition-colors shadow-2xs"
                        title="Edit full row to validate ground truth"
                      >
                        <Edit3 className="w-3 h-3 text-slate-500" />
                        <span>Correct</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer Pagination Details */}
        <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between text-xs text-slate-500 gap-2">
          <span>
            Tip: Click any cell directly to edit its value and watch deterministic rules instantly re-evaluate.
          </span>
          <span className="font-mono">
            Slicing: <code className="bg-slate-200 px-1 py-0.5 rounded text-slate-800">df.iloc[{activeBatchIndex * 5} : {(activeBatchIndex + 1) * 5}]</code>
          </span>
        </div>
      </div>

      {/* Row Edit Modal */}
      {editingRow && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h4 className="text-sm font-bold text-slate-900">
                  Ground Truth Validation — Edit Record #{editingRow.rowIndex}
                </h4>
                <p className="text-xs text-slate-500">
                  Modifying fields will immediately re-run the isolated rule engine.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingRow(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
              {Object.keys(editingRow.rawRecord).map(field => (
                <div key={field} className="space-y-1">
                  <label className="text-[11px] font-bold font-mono text-slate-700 uppercase">
                    {field}
                  </label>
                  <input
                    type="text"
                    value={editFormData[field] !== undefined && editFormData[field] !== null ? editFormData[field] : ''}
                    onChange={(e) => {
                      let val: any = e.target.value;
                      if (!isNaN(Number(val)) && val.trim() !== '') {
                        val = Number(val);
                      }
                      setEditFormData(prev => ({ ...prev, [field]: val }));
                    }}
                    className="w-full text-xs font-mono p-2 border border-slate-300 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-slate-900 bg-slate-50"
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setEditingRow(null)}
                className="px-3.5 py-1.5 text-xs font-semibold border border-slate-300 rounded hover:bg-slate-50 text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveEditRow}
                className="px-4 py-1.5 text-xs font-bold bg-slate-900 text-white rounded hover:bg-slate-800"
              >
                Save & Re-evaluate Rules
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AI-Generated Finding Panel (Secondary to Rule Engine) */}
      <div id="ai-findings-panel" className="bg-slate-900 border border-slate-800 rounded-xl p-5 text-white shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-900/60 border border-blue-700 flex items-center justify-center text-blue-300">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100">
                  AI Forensic Audit Finding Memo
                </h3>
                {/* Visible small technical model tag */}
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-blue-300 border border-slate-700 font-bold">
                  model: {selectedModel}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Technical audit workpaper draft explaining the deterministic anomalies detected in the current slice.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {memo && (
              <button
                type="button"
                onClick={handleCopyMemo}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded flex items-center gap-1.5"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy Workpaper'}</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleGenerateAIWorkpaper}
              disabled={isGenerating}
              className="px-4 py-1.5 text-xs font-bold bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded flex items-center gap-1.5 transition-colors shadow-2xs"
            >
              {isGenerating ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Drafting Memo...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Generate Finding Memo</span>
                </>
              )}
            </button>
          </div>
        </div>

        {memoError && (
          <div className="p-3 bg-red-950/80 border border-red-800 rounded-lg text-xs text-red-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
            <span>{memoError}</span>
          </div>
        )}

        {memo ? (
          <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs text-slate-200 leading-relaxed max-h-72 overflow-y-auto whitespace-pre-wrap">
            {memo}
          </div>
        ) : (
          <div className="bg-slate-950/50 border border-slate-800/80 rounded-lg p-6 text-center text-slate-400 space-y-2">
            <Info className="w-5 h-5 mx-auto text-slate-500" />
            <p className="text-xs">
              Click <b className="text-slate-200">"Generate Finding Memo"</b> above to produce an automated forensic audit explanation for the active 5-record batch.
            </p>
            <p className="text-[11px] font-mono text-slate-500">
              Note: Detection logic was executed 100% deterministically by the isolated Python/TypeScript rule engine. The LLM solely assists in formatting audit workpapers.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
