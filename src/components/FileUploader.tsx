import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, Code2, AlertCircle } from 'lucide-react';
import { parseFinancialFile, parseRawCsvText, ParsedFileData } from '../utils/parser';

interface FileUploaderProps {
  onFileParsed: (data: ParsedFileData) => void;
  isLoading: boolean;
}

export const FileUploader: React.FC<FileUploaderProps> = ({ onFileParsed, isLoading }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pastedText, setPastedText] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setErrorMessage(null);
    try {
      const parsed = await parseFinancialFile(file);
      if (!parsed.headers || parsed.headers.length === 0) {
        setErrorMessage('Uploaded file appears empty or missing readable column headers.');
        return;
      }
      onFileParsed(parsed);
    } catch (err: any) {
      setErrorMessage(err?.message || 'Error processing file.');
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
      const parsed = parseRawCsvText(pastedText, 'pasted_table.csv');
      if (!parsed.headers || parsed.headers.length === 0) {
        setErrorMessage('Unable to extract headers from pasted content.');
        return;
      }
      onFileParsed(parsed);
      setShowPasteModal(false);
      setPastedText('');
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to parse pasted data.');
    }
  };

  return (
    <div id="file-uploader-section" className="w-full">
      <div
        id="drop-zone-container"
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`bg-white border-2 border-dashed rounded-xl p-5 transition-all cursor-pointer flex flex-col items-center justify-center text-center shadow-xs ${
          isDragging
            ? 'border-slate-900 bg-slate-50'
            : 'border-slate-200 hover:border-slate-400'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv, .xlsx, .xls, .txt"
          onChange={handleFileChange}
          className="hidden"
          id="file-input-hidden"
        />

        <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-slate-700 mb-2">
          <UploadCloud className="w-5 h-5" />
        </div>

        <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
          Upload Financial Data File
        </h3>
        <p className="text-xs text-slate-500 mt-0.5 max-w-md">
          Drag & drop CSV or Excel (.xlsx) file. Columns are automatically classified and routed.
        </p>

        <div className="flex items-center gap-2 mt-3">
          <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
            CSV / XLSX
          </span>
          <span className="text-xs text-slate-400">or</span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowPasteModal(true);
            }}
            className="text-xs font-semibold text-slate-700 hover:text-slate-900 underline"
          >
            Paste Raw CSV
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Paste Modal */}
      {showPasteModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-white border border-slate-200 rounded-xl max-w-lg w-full p-5 shadow-lg space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-sm font-bold text-slate-900">Paste CSV Text</h4>
              <button
                type="button"
                onClick={() => setShowPasteModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕
              </button>
            </div>

            <textarea
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder="date,vendor,amount,account_code,approved_by&#10;2024-01-15,Acme Corp,5000,6100-OFF,J.Smith"
              className="w-full h-40 p-3 bg-slate-50 border border-slate-200 rounded text-xs font-mono text-slate-900 focus:outline-none focus:border-slate-900"
            />

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowPasteModal(false)}
                className="px-3 py-1.5 text-xs font-semibold border border-slate-200 rounded hover:bg-slate-50 text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePasteSubmit}
                className="px-4 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded hover:bg-slate-800"
              >
                Ingest Data
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
