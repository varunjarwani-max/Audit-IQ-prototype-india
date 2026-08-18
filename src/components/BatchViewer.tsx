import React, { useState } from 'react';
import { 
  AlertCircle, 
  CheckCircle2, 
  ChevronLeft, 
  ChevronRight, 
  Edit3, 
  ShieldAlert, 
  Check
} from 'lucide-react';
import { FlaggedRecord, FinancialDataType } from '../types';

interface BatchViewerProps {
  records: FlaggedRecord[];
  activeBatchIndex: number;
  onBatchChange: (batchIndex: number) => void;
  selectedRowIndex: number | null;
  onSelectRow: (rowIndex: number | null) => void;
  onUpdateRecord: (recordIndex: number, updatedFields: Record<string, any>) => void;
  category: FinancialDataType;
}

export const BatchViewer: React.FC<BatchViewerProps> = ({
  records,
  activeBatchIndex,
  onBatchChange,
  selectedRowIndex,
  onSelectRow,
  onUpdateRecord,
  category
}) => {
  const BATCH_SIZE = 5;
  const totalBatches = Math.ceil(records.length / BATCH_SIZE) || 1;
  const currentBatchRecords = records.slice(
    activeBatchIndex * BATCH_SIZE,
    (activeBatchIndex + 1) * BATCH_SIZE
  );

  const [editingRow, setEditingRow] = useState<FlaggedRecord | null>(null);
  const [editFormData, setEditFormData] = useState<Record<string, any>>({});

  const startEdit = (rec: FlaggedRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingRow(rec);
    setEditFormData({ ...rec.rawRecord });
  };

  const saveEdit = () => {
    if (editingRow) {
      onUpdateRecord(editingRow.rowIndex - 1, editFormData);
      setEditingRow(null);
    }
  };

  // Get all unique columns from raw records in batch
  const columns: string[] = Array.from(
    new Set(currentBatchRecords.flatMap(r => Object.keys(r.rawRecord || {})))
  );

  const formatCellValue = (val: any) => {
    if (val === null || val === undefined || val === '') {
      return <span className="text-amber-500 italic font-mono text-[10px]">null</span>;
    }
    if (typeof val === 'number') {
      return <span className="font-mono">${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>;
    }
    return String(val);
  };

  return (
    <div id="batch-viewer-container" className="bg-white rounded-xl border border-slate-200 shadow-xs flex flex-col overflow-hidden">
      {/* Batch Header Bar */}
      <div className="p-4 border-b border-slate-100 bg-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h4 className="text-sm font-bold text-slate-900">
            Live Batch Preview (Top 5 Records)
          </h4>
          <span className="text-[10px] bg-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono">
            batch {activeBatchIndex + 1} of {totalBatches}
          </span>
        </div>

        {/* Batch Pagination Controls */}
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            id="prev-batch-btn"
            type="button"
            disabled={activeBatchIndex === 0}
            onClick={() => onBatchChange(activeBatchIndex - 1)}
            className="p-1.5 rounded border border-slate-200 bg-white disabled:opacity-40 hover:bg-slate-50 text-slate-700 transition-colors"
            title="Previous 5 records"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <span className="font-mono text-xs text-slate-700 px-1 font-semibold">
            {activeBatchIndex + 1} / {totalBatches}
          </span>
          <button
            id="next-batch-btn"
            type="button"
            disabled={activeBatchIndex >= totalBatches - 1}
            onClick={() => onBatchChange(activeBatchIndex + 1)}
            className="p-1.5 rounded border border-slate-200 bg-white disabled:opacity-40 hover:bg-slate-50 text-slate-700 transition-colors"
            title="Next 5 records"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Table Area */}
      <div className="overflow-x-auto">
        <table id="batch-records-table" className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50 text-[10px] uppercase text-slate-400 font-bold border-b border-slate-200">
              <th className="p-3 w-12 text-center">Row</th>
              <th className="p-3 w-24">Status</th>
              <th className="p-3 w-20">Risk</th>
              {columns.map(col => (
                <th key={col} className="p-3 whitespace-nowrap font-mono">
                  {col}
                </th>
              ))}
              <th className="p-3 w-48">Reasoning / Flag</th>
              <th className="p-3 w-16 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="text-xs font-medium divide-y divide-slate-100">
            {currentBatchRecords.map((record) => {
              const isSelected = selectedRowIndex === record.rowIndex;
              const isFlagged = record.status === 'FLAGGED';
              const flagReason = isFlagged 
                ? record.flags.map(f => `${f.ruleName}: ${f.description}`).join(' | ') 
                : 'Standard operational entry. No anomalies detected.';

              return (
                <tr
                  key={record.rowIndex}
                  id={`batch-row-${record.rowIndex}`}
                  onClick={() => onSelectRow(isSelected ? null : record.rowIndex)}
                  className={`cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-blue-50/60 ring-1 ring-blue-500/20'
                      : isFlagged
                      ? 'bg-red-50/30 hover:bg-red-50/50'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  <td className="p-3 text-center text-slate-400 font-mono text-[11px]">
                    #{record.rowIndex}
                  </td>
                  <td className="p-3">
                    {isFlagged ? (
                      <span className="text-red-600 font-bold uppercase text-[9px] px-1.5 py-0.5 bg-red-100 border border-red-200 rounded">
                        Flagged
                      </span>
                    ) : (
                      <span className="text-green-600 font-bold uppercase text-[9px] px-1.5 py-0.5 bg-green-50 border border-green-200 rounded">
                        Cleared
                      </span>
                    )}
                  </td>
                  <td className="p-3 font-mono font-bold">
                    <span className={record.riskScore >= 70 ? 'text-red-600' : record.riskScore > 0 ? 'text-amber-600' : 'text-slate-400'}>
                      {record.riskScore}
                    </span>
                  </td>
                  {columns.map(col => {
                    const rawVal = record.rawRecord ? record.rawRecord[col] : '';
                    return (
                      <td key={col} className="p-3 text-slate-700 whitespace-nowrap">
                        {formatCellValue(rawVal)}
                      </td>
                    );
                  })}
                  <td className="p-3 max-w-xs truncate">
                    <span className={isFlagged ? 'text-red-800 font-medium' : 'text-slate-400 italic'}>
                      {flagReason}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <button
                      type="button"
                      onClick={(e) => startEdit(record, e)}
                      className="p-1 text-slate-400 hover:text-slate-800 rounded hover:bg-slate-100 transition-colors"
                      title="Edit Row Values to Test Rules"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer Navigation Action */}
      <div className="p-3 bg-slate-50 border-t border-slate-100 text-center">
        <button
          type="button"
          disabled={activeBatchIndex >= totalBatches - 1}
          onClick={() => onBatchChange(activeBatchIndex + 1)}
          className="text-[10px] font-bold text-slate-500 uppercase tracking-widest hover:text-slate-900 disabled:opacity-30 transition-colors"
        >
          {activeBatchIndex >= totalBatches - 1 ? 'End of Dataset Records' : 'Load Next 5 Records →'}
        </button>
      </div>

      {/* Inline Edit Modal */}
      {editingRow && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-white border border-slate-200 rounded-xl max-w-md w-full p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-sm font-bold text-slate-900">
                Edit Record #{editingRow.rowIndex} Values
              </h4>
              <button
                type="button"
                onClick={() => setEditingRow(null)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
              {Object.keys(editFormData).map((key) => (
                <div key={key}>
                  <label className="block text-[10px] font-bold text-slate-500 uppercase font-mono mb-1">
                    {key}
                  </label>
                  <input
                    type="text"
                    value={editFormData[key] ?? ''}
                    onChange={(e) => setEditFormData({ ...editFormData, [key]: e.target.value })}
                    className="w-full px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded focus:ring-1 focus:ring-slate-900 outline-none text-slate-900"
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setEditingRow(null)}
                className="px-3 py-1.5 text-xs font-semibold border border-slate-200 rounded hover:bg-slate-50 text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={saveEdit}
                className="px-4 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded hover:bg-slate-800"
              >
                Apply & Re-Audit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
