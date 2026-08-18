import Papa from 'papaparse';
import * as XLSX from 'xlsx';

export interface ParsedFileData {
  filename: string;
  headers: string[];
  rows: Record<string, any>[];
  totalRowCount: number;
}

export async function parseFinancialFile(file: File): Promise<ParsedFileData> {
  const filename = file.name;
  const extension = filename.split('.').pop()?.toLowerCase() || '';

  if (extension === 'csv' || extension === 'txt') {
    return parseCsvFile(file);
  } else if (['xlsx', 'xls', 'xlsm', 'ods'].includes(extension)) {
    return parseExcelFile(file);
  } else {
    // Attempt CSV parse fallback
    return parseCsvFile(file);
  }
}

function parseCsvFile(file: File): Promise<ParsedFileData> {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: 'greedy',
      dynamicTyping: true,
      complete: (results) => {
        const headers = (results.meta.fields || []).map(h => String(h).trim()).filter(Boolean);
        const rows = (results.data as Record<string, any>[]).filter(row => {
          return Object.values(row).some(v => v !== null && v !== undefined && String(v).trim() !== '');
        });

        resolve({
          filename: file.name,
          headers,
          rows,
          totalRowCount: rows.length
        });
      },
      error: (error) => {
        reject(new Error(`CSV Parsing failed: ${error.message}`));
      }
    });
  });
}

function parseExcelFile(file: File): Promise<ParsedFileData> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: 'array', cellDates: true });
        
        const firstSheetName = workbook.SheetNames[0];
        if (!firstSheetName) {
          throw new Error('Workbook contains no sheets.');
        }

        const worksheet = workbook.Sheets[firstSheetName];
        const jsonData = XLSX.utils.sheet_to_json<Record<string, any>>(worksheet, {
          raw: false,
          dateNF: 'yyyy-mm-dd'
        });

        if (jsonData.length === 0) {
          resolve({
            filename: file.name,
            headers: [],
            rows: [],
            totalRowCount: 0
          });
          return;
        }

        // Extract headers
        const headers = Object.keys(jsonData[0] || {}).map(h => String(h).trim()).filter(Boolean);
        
        resolve({
          filename: file.name,
          headers,
          rows: jsonData,
          totalRowCount: jsonData.length
        });
      } catch (err: any) {
        reject(new Error(`Excel Parsing failed: ${err?.message || 'Unknown error'}`));
      }
    };

    reader.onerror = () => {
      reject(new Error('Failed to read file from disk.'));
    };

    reader.readAsArrayBuffer(file);
  });
}

export function parseRawCsvText(csvText: string, filename = 'pasted_data.csv'): ParsedFileData {
  const results = Papa.parse(csvText, {
    header: true,
    skipEmptyLines: 'greedy',
    dynamicTyping: true
  });

  const headers = (results.meta.fields || []).map(h => String(h).trim()).filter(Boolean);
  const rows = (results.data as Record<string, any>[]).filter(row => {
    return Object.values(row).some(v => v !== null && v !== undefined && String(v).trim() !== '');
  });

  return {
    filename,
    headers,
    rows,
    totalRowCount: rows.length
  };
}
