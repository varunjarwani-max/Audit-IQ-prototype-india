import React, { useState, useRef } from 'react';
import { 
  UploadCloud, 
  FileSpreadsheet, 
  FileText, 
  Code2, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  FolderOpen,
  ArrowRight
} from 'lucide-react';
import { parseFinancialFile, parseRawCsvText, ParsedFileData } from '../utils/parser';
import { SampleDataset } from '../types';
import { SAMPLE_DATASETS } from '../data/sampleDatasets';

interface UploadHistoryItem {
  id: string;
  filename: string;
  rowCount: number;
  format: 'CSV' | 'XLSX' | 'PASTE';
  timestamp: string;
  status: 'Parsed 100% OK' | 'Header Warning';
}

interface UploadStageProps {
  onFileParsed: (data: ParsedFileData) => void;
  onSelectSampleDataset: (sample: SampleDataset) => void;
  currentFilename: string;
  totalRecords: number;
  onAdvanceToClassify: () => void;
}

export const UploadStage: React.FC<UploadStageProps> = ({
  onFileParsed,
  onSelectSampleDataset,
  currentFilename,
  totalRecords,
  onAdvanceToClassify
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pastedText, setPastedText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadHistory, setUploadHistory] = useState<UploadHistoryItem[]>([
    {
      id: 'log-01',
      filename: 'synthetic_transactions_batch_5.csv',
      rowCount: 5,
      format: 'CSV',
      timestamp: 'Today, 10:42:15 AM',
      status: 'Parsed 100% OK'
    },
    {
      id: 'log-02',
      filename: 'q3_vendor_aging_ledger.xlsx',
      rowCount: 5,
      format: 'XLSX',
      timestamp: 'Yesterday, 04:15:20 PM',
      status: 'Parsed 100% OK'
    }
  ]);

  const handleFile = async (file: File) => {
    setErrorMessage(null);
    try {
      const parsed = await parseFinancialFile(file);
      if (!parsed.headers || parsed.headers.length === 0) {
        setErrorMessage('Uploaded file appears empty or missing readable column headers.');
        return;
      }
      
      const newLogItem: UploadHistoryItem = {
        id: `log-${Date.now()}`,
        filename: file.name,
        rowCount: parsed.rows.length,
        format: file.name.endsWith('.xlsx') || file.name.endsWith('.xls') ? 'XLSX' : 'CSV',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        status: 'Parsed 100% OK'
      };
      
      setUploadHistory(prev => [newLogItem, ...prev.slice(0, 4)]);
      onFileParsed(parsed);
      onAdvanceToClassify();
    } catch (err: any) {
      setErrorMessage(err?.message || 'Error processing financial data file.');
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handlePasteSubmit = () => {
    if (!pastedText.trim()) return;
    setErrorMessage(null);
    try {
      const parsed = parseRawCsvText(pastedText, 'pasted_ledger_table.csv');
      if (!parsed.headers || parsed.headers.length === 0) {
        setErrorMessage('Unable to extract headers from pasted table content.');
        return;
      }

      const newLogItem: UploadHistoryItem = {
        id: `log-${Date.now()}`,
        filename: 'pasted_ledger_table.csv',
        rowCount: parsed.rows.length,
        format: 'PASTE',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        status: 'Parsed 100% OK'
      };
      setUploadHistory(prev => [newLogItem, ...prev.slice(0, 4)]);

      onFileParsed(parsed);
      setShowPasteModal(false);
      setPastedText('');
      onAdvanceToClassify();
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to parse pasted data.');
    }
  };

  return (
    <div id="stage-1-upload-workspace" className="space-y-6">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded bg-slate-900 text-white">
              STAGE 01
            </span>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
              Financial Data Ingestion & Drag-and-Drop
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Accepts CSV, XLSX workpapers, or raw ERP clipboard dumps for schema classification.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowPasteModal(true)}
            className="px-3 py-1.5 text-xs font-semibold bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded transition-colors flex items-center gap-1.5 shadow-2xs"
          >
            <Code2 className="w-3.5 h-3.5 text-slate-500" />
            <span>Paste Table Text</span>
          </button>
        </div>
      </div>

      {/* Drag & Drop Area */}
      <div
        id="drop-zone-main"
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`bg-white border-2 border-dashed rounded-xl p-8 transition-all cursor-pointer flex flex-col items-center justify-center text-center shadow-2xs ${
          isDragging
            ? 'border-blue-600 bg-blue-50/50'
            : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50/50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv, .xlsx, .xls, .txt"
          onChange={handleFileChange}
          className="hidden"
          id="file-upload-input"
        />

        <div className="w-12 h-12 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 mb-3 shadow-2xs">
          <UploadCloud className="w-6 h-6 text-slate-700" />
        </div>

        <h3 className="text-sm font-bold text-slate-900">
          Drag and drop audit workpaper file here
        </h3>
        <p className="text-xs text-slate-500 mt-1 max-w-md">
          Supports <span className="font-mono font-medium text-slate-700">.csv</span> and <span className="font-mono font-medium text-slate-700">.xlsx</span> formats. Files are processed entirely locally on-premise.
        </p>

        <div className="flex items-center gap-3 mt-4">
          <span className="text-[11px] font-mono font-semibold px-2.5 py-1 rounded bg-slate-100 text-slate-700 border border-slate-200">
            CSV / XLSX
          </span>
          <span className="text-xs text-slate-400">or</span>
          <span className="text-xs font-semibold text-blue-700 hover:underline">
            Browse Local File Explorer
          </span>
        </div>
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div className="p-3.5 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2.5 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Pre-Loaded CA Test Workpapers */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-slate-500" />
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              Pre-loaded Test Batches (5-Record Validation Slices)
            </h4>
          </div>
          <span className="text-[11px] font-mono text-slate-500">
            Current: <b className="text-slate-800">{currentFilename}</b> ({totalRecords} records)
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {SAMPLE_DATASETS.map((sample) => {
            const isSelected = currentFilename.includes(sample.id) || currentFilename.includes(sample.category);
            return (
              <button
                key={sample.id}
                type="button"
                onClick={() => {
                  onSelectSampleDataset(sample);
                  onAdvanceToClassify();
                }}
                className={`p-3 rounded-lg border text-left transition-all flex flex-col justify-between gap-1.5 ${
                  isSelected
                    ? 'bg-slate-900 border-slate-900 text-white shadow-2xs'
                    : 'bg-slate-50 hover:bg-white border-slate-200 text-slate-800 hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                    isSelected ? 'bg-slate-800 text-blue-300' : 'bg-white border border-slate-200 text-slate-600'
                  }`}>
                    {sample.category.toUpperCase()}
                  </span>
                  {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />}
                </div>

                <div>
                  <h5 className="text-xs font-bold truncate">
                    {sample.name}
                  </h5>
                  <p className={`text-[11px] line-clamp-1 mt-0.5 ${
                    isSelected ? 'text-slate-300' : 'text-slate-500'
                  }`}>
                    {sample.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Upload Ingestion Log Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-500" />
            <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              Recent File Ingestion Log
            </h4>
          </div>
          <span className="text-[11px] font-mono text-slate-500">
            {uploadHistory.length} audit sessions logged
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-100/70 text-slate-600 font-semibold font-mono text-[11px]">
                <th className="py-2.5 px-4">Audit File ID</th>
                <th className="py-2.5 px-4">Filename</th>
                <th className="py-2.5 px-4 text-center">Format</th>
                <th className="py-2.5 px-4 text-right">Row Count</th>
                <th className="py-2.5 px-4">Ingestion Timestamp</th>
                <th className="py-2.5 px-4">Parser Verification</th>
                <th className="py-2.5 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {uploadHistory.map((item, idx) => (
                <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-4 font-mono font-medium text-slate-600">
                    AUD-LOG-{idx + 1}
                  </td>
                  <td className="py-2.5 px-4 font-semibold text-slate-900 flex items-center gap-2">
                    <FileSpreadsheet className="w-3.5 h-3.5 text-blue-600" />
                    <span className="truncate max-w-[220px]">{item.filename}</span>
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 font-medium">
                      {item.format}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono font-semibold text-slate-900">
                    {item.rowCount} rows
                  </td>
                  <td className="py-2.5 px-4 text-slate-500 font-mono text-[11px]">
                    {item.timestamp}
                  </td>
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-medium bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                      <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                      {item.status}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-right">
                    <button
                      type="button"
                      onClick={onAdvanceToClassify}
                      className="text-[11px] font-semibold text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
                    >
                      <span>Inspect Schema</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Paste Table Modal */}
      {showPasteModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-xl w-full p-6 space-y-4 shadow-xl border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-slate-700" />
                <h4 className="text-sm font-bold text-slate-900">
                  Paste Financial Table Text (CSV or TSV)
                </h4>
              </div>
              <button
                type="button"
                onClick={() => setShowPasteModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xs font-bold"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Paste comma-separated or tab-separated text copied from Excel or Tally/SAP ERP exports:
            </p>

            <textarea
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder="date,amount,vendor,account_code,approved_by,department&#10;2024-01-15,48500,Apex Cloud Systems,6100-IT,V.Sharma,Engineering"
              rows={8}
              className="w-full font-mono text-xs p-3 rounded-lg border border-slate-300 focus:outline-hidden focus:ring-1 focus:ring-slate-900 bg-slate-50"
            />

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowPasteModal(false)}
                className="px-3.5 py-1.5 text-xs font-semibold border border-slate-200 rounded hover:bg-slate-50 text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePasteSubmit}
                className="px-3.5 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded hover:bg-slate-800"
              >
                Parse & Ingest
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
