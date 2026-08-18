import React from 'react';
import { 
  UploadCloud, 
  FileCheck2, 
  Cpu, 
  TableProperties, 
  CheckCircle2, 
  AlertTriangle,
  ArrowRight
} from 'lucide-react';
import { FinancialDataType } from '../types';

export type WorkflowStage = 'upload' | 'classify' | 'route' | 'review';

interface WorkflowStepperProps {
  activeStage: WorkflowStage;
  onSelectStage: (stage: WorkflowStage) => void;
  isAmbiguous: boolean;
  confidence: number;
  detectedType: FinancialDataType;
  flaggedCount: number;
  totalRecords: number;
}

export const WorkflowStepper: React.FC<WorkflowStepperProps> = ({
  activeStage,
  onSelectStage,
  isAmbiguous,
  confidence,
  detectedType,
  flaggedCount,
  totalRecords
}) => {
  const stages = [
    {
      id: 'upload' as WorkflowStage,
      number: '01',
      title: 'Upload',
      subtitle: `${totalRecords} records ready`,
      icon: UploadCloud,
      status: 'complete'
    },
    {
      id: 'classify' as WorkflowStage,
      number: '02',
      title: 'Classification',
      subtitle: isAmbiguous ? 'Manual binding required' : `${confidence}% signature match`,
      icon: FileCheck2,
      status: isAmbiguous ? 'warning' : 'complete'
    },
    {
      id: 'route' as WorkflowStage,
      number: '03',
      title: 'Routing & Engine',
      subtitle: detectedType !== 'ambiguous' ? `${detectedType} (deterministic)` : 'Pending classification',
      icon: Cpu,
      status: detectedType !== 'ambiguous' ? 'complete' : 'pending'
    },
    {
      id: 'review' as WorkflowStage,
      number: '04',
      title: 'Batch Review',
      subtitle: `${flaggedCount} flags in active slice`,
      icon: TableProperties,
      status: flaggedCount > 0 ? 'alert' : 'complete'
    }
  ];

  return (
    <div id="audit-workflow-stepper" className="bg-slate-900 border border-slate-800 rounded-xl p-3 sm:p-4 text-white shadow-xs">
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-2 md:gap-4">
        {stages.map((stage, idx) => {
          const Icon = stage.icon;
          const isActive = activeStage === stage.id;
          
          return (
            <React.Fragment key={stage.id}>
              <button
                type="button"
                onClick={() => onSelectStage(stage.id)}
                className={`flex-1 flex items-center gap-3 p-2.5 sm:p-3 rounded-lg text-left transition-all border ${
                  isActive
                    ? 'bg-slate-800 border-slate-600 shadow-xs'
                    : 'bg-slate-900/60 border-transparent hover:bg-slate-800/40 text-slate-300'
                }`}
              >
                <div className={`w-8 h-8 rounded flex items-center justify-center shrink-0 font-mono text-xs font-bold border ${
                  isActive
                    ? 'bg-blue-600 border-blue-400 text-white'
                    : stage.status === 'warning'
                    ? 'bg-amber-950/80 border-amber-600 text-amber-300'
                    : 'bg-slate-800 border-slate-700 text-slate-400'
                }`}>
                  {stage.number}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold tracking-tight text-slate-100">
                      {stage.title}
                    </span>
                    {stage.status === 'warning' && (
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                    )}
                  </div>
                  <p className="text-[11px] font-mono text-slate-400 truncate">
                    {stage.subtitle}
                  </p>
                </div>
              </button>

              {idx < stages.length - 1 && (
                <div className="hidden md:flex items-center justify-center text-slate-700 shrink-0">
                  <ArrowRight className="w-4 h-4" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
