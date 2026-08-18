import React, { useState } from 'react';
import { 
  ShieldAlert, 
  Copy, 
  Check, 
  FileCheck 
} from 'lucide-react';
import { FlaggedRecord, SeverityLevel } from '../types';

interface AuditFindingsProps {
  records: FlaggedRecord[];
  selectedRowIndex: number | null;
  onClearRowSelection: () => void;
}

export const AuditFindings: React.FC<AuditFindingsProps> = ({
  records,
  selectedRowIndex,
  onClearRowSelection
}) => {
  const [severityFilter, setSeverityFilter] = useState<SeverityLevel | 'ALL'>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Filter records based on selected row & severity
  const activeRecords = records.filter(r => {
    if (selectedRowIndex !== null && r.rowIndex !== selectedRowIndex) return false;
    if (r.status !== 'FLAGGED') return false;
    if (severityFilter === 'ALL') return true;
    return r.flags.some(f => f.severity === severityFilter);
  });

  const allFlags = activeRecords.flatMap(r => r.flags.map(f => ({ ...f, record: r })));

  const handleCopyFinding = (flag: any) => {
    const text = `[AuditIQ Finding] Rule: ${flag.ruleCode} (${flag.ruleName})\nSeverity: ${flag.severity}\nRow #${flag.record.rowIndex} (${flag.record.recordId})\nDetails: ${flag.description}\nActual: ${flag.actualValue} | Expected: ${flag.expectedCondition}\nRemediation: ${flag.remediation}`;
    navigator.clipboard.writeText(text);
    setCopiedId(flag.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getSeverityBadge = (sev: SeverityLevel) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-700 border border-red-200';
      case 'HIGH':
        return 'bg-amber-100 text-amber-800 border border-amber-200';
      case 'MEDIUM':
        return 'bg-blue-100 text-blue-800 border border-blue-200';
      case 'LOW':
      default:
        return 'bg-slate-100 text-slate-700 border border-slate-200';
    }
  };

  return (
    <div id="audit-findings-panel" className="bg-white rounded-xl border border-slate-200 shadow-xs p-5 space-y-4">
      {/* Header with Title and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-slate-900">
              Audit Findings & Rule Explainability
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold">
              {allFlags.length} {allFlags.length === 1 ? 'Violation' : 'Violations'}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Root-cause breakdown and SOX internal audit remediation guidelines.
          </p>
        </div>

        {/* Severity Filter Controls */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {selectedRowIndex !== null && (
            <button
              id="clear-row-filter-btn"
              type="button"
              onClick={onClearRowSelection}
              className="text-[10px] font-semibold px-2 py-1 rounded bg-slate-900 text-white mr-1"
            >
              Row #{selectedRowIndex} (✕)
            </button>
          )}

          {(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((sev) => {
            const isActive = severityFilter === sev;
            return (
              <button
                key={sev}
                id={`filter-severity-${sev.toLowerCase()}`}
                type="button"
                onClick={() => setSeverityFilter(sev)}
                className={`text-[10px] font-bold px-2 py-1 rounded transition-colors uppercase ${
                  isActive
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-50 hover:bg-slate-100 text-slate-600 border border-slate-200'
                }`}
              >
                {sev}
              </button>
            );
          })}
        </div>
      </div>

      {/* Findings List */}
      {allFlags.length === 0 ? (
        <div className="p-8 text-center bg-slate-50/50 rounded-xl border border-slate-100 space-y-2">
          <FileCheck className="w-8 h-8 text-green-600 mx-auto" />
          <h4 className="text-xs font-bold text-slate-800">
            No Violations in Selected View
          </h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {selectedRowIndex !== null
              ? `Record #${selectedRowIndex} complies with active audit rule parameters.`
              : 'All evaluated rows in this batch pass the active threshold validations.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {allFlags.map((flag) => {
            const isCopied = copiedId === flag.id;
            return (
              <div
                key={flag.id}
                id={`finding-card-${flag.id}`}
                className="p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-3 transition-all hover:border-slate-300"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200/80 pb-2">
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded ${getSeverityBadge(flag.severity)}`}>
                      {flag.severity}
                    </span>
                    <span className="font-mono text-xs font-bold text-slate-900">
                      {flag.ruleCode}
                    </span>
                    <span className="text-xs font-semibold text-slate-700">
                      {flag.ruleName}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <span className="text-[10px] font-mono text-slate-500 bg-white px-2 py-0.5 rounded border border-slate-200">
                      Row #{flag.record.rowIndex}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopyFinding(flag)}
                      className="text-xs text-slate-400 hover:text-slate-700 p-1 rounded"
                      title="Copy finding workpaper snippet"
                    >
                      {isCopied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-800 leading-relaxed">
                  {flag.description}
                </p>

                {/* Evidence Comparison Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 bg-white border border-slate-200 rounded">
                    <span className="text-[10px] font-bold text-red-600 block uppercase tracking-wider">
                      Detected Condition
                    </span>
                    <span className="font-mono text-slate-800 text-xs mt-0.5 block">
                      {String(flag.actualValue)}
                    </span>
                  </div>
                  <div className="p-2.5 bg-white border border-slate-200 rounded">
                    <span className="text-[10px] font-bold text-slate-500 block uppercase tracking-wider">
                      Audit Standard Requirement
                    </span>
                    <span className="font-mono text-slate-700 text-xs mt-0.5 block">
                      {flag.expectedCondition}
                    </span>
                  </div>
                </div>

                {/* Remediation */}
                <div className="p-2.5 bg-blue-50/60 border border-blue-100 rounded text-xs text-blue-900">
                  <span className="font-bold text-[10px] uppercase tracking-wider block text-blue-800 mb-0.5">
                    Recommended Remediation Protocol
                  </span>
                  <p className="leading-snug text-slate-700">{flag.remediation}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
