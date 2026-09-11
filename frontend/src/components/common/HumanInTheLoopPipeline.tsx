import React from 'react';
import {
  Users,
  AlertTriangle,
  Radio,
  Cpu,
  UserCheck,
  Truck,
  ShieldCheck,
  RefreshCw,
  CheckCircle2,
  Sliders,
  XCircle,
} from 'lucide-react';

interface HumanInTheLoopPipelineProps {
  interactive?: boolean;
  variant?: 'workflow' | 'decision-card';
  className?: string;
}

export const HumanInTheLoopPipeline: React.FC<HumanInTheLoopPipelineProps> = ({
  variant = 'workflow',
  className = '',
}) => {
  const steps = [
    { label: 'COMMUNITY', icon: Users, desc: 'Field & Citizen Ingestion', phase: 'Ingestion' },
    { label: 'EMERGENCY', icon: AlertTriangle, desc: 'Triage & Verification', phase: 'Triage' },
    { label: 'SITUATION', icon: Radio, desc: 'Live GIS & Hazards', phase: 'Spatial Awareness' },
    { label: 'AI INTELLIGENCE', icon: Cpu, desc: 'Multi-Agent Analysis', phase: 'AI Synthesis', highlight: true },
    { label: 'HUMAN DECISION', icon: UserCheck, desc: 'Operator Authority', phase: 'Human Authority', highlight: true },
    { label: 'RESOURCES', icon: Truck, desc: 'Logistics Allocation', phase: 'Resource Mesh' },
    { label: 'RESPONSE', icon: ShieldCheck, desc: 'Field Execution', phase: 'Ground Action' },
    { label: 'RE-PLANNING', icon: RefreshCw, desc: 'Dynamic Feedback Loop', phase: 'Dynamic Loop' },
  ];

  if (variant === 'decision-card') {
    return (
      <div className={`p-5 rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-teal-500" />
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-900">
              Human-in-the-Loop Decision Engine
            </span>
          </div>
          <span className="font-mono text-[10px] text-slate-500 uppercase tracking-widest px-2 py-0.5 rounded bg-slate-100 border border-slate-200">
            Authority Active
          </span>
        </div>

        {/* Workflow Diagram */}
        <div className="grid grid-cols-3 gap-2.5 my-4 text-center">
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <Cpu className="w-4 h-4 mx-auto mb-1 text-teal-600" />
            <div className="font-mono text-[11px] font-bold text-slate-800">AI RECOMMENDS</div>
            <div className="text-[10px] text-slate-500">Explainable options</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <UserCheck className="w-4 h-4 mx-auto mb-1 text-amber-600" />
            <div className="font-mono text-[11px] font-bold text-slate-800">HUMAN DECIDES</div>
            <div className="text-[10px] text-slate-500">Officer verification</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <ShieldCheck className="w-4 h-4 mx-auto mb-1 text-emerald-600" />
            <div className="font-mono text-[11px] font-bold text-slate-800">SYSTEM EXECUTES</div>
            <div className="text-[10px] text-slate-500">Dispatch & audit</div>
          </div>
        </div>

        {/* Standby Decision Controls */}
        <div className="flex items-center justify-between gap-2 pt-2">
          <button
            disabled
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-100 text-slate-400 border border-slate-200 font-mono text-xs cursor-not-allowed"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            APPROVE
          </button>
          <button
            disabled
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-100 text-slate-400 border border-slate-200 font-mono text-xs cursor-not-allowed"
          >
            <Sliders className="w-3.5 h-3.5" />
            MODIFY
          </button>
          <button
            disabled
            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-100 text-slate-400 border border-slate-200 font-mono text-xs cursor-not-allowed"
          >
            <XCircle className="w-3.5 h-3.5" />
            REJECT
          </button>
        </div>
        <p className="text-[11px] text-center text-slate-500 font-mono mt-2.5">
          Awaiting verified incident triggers to generate response recommendations.
        </p>
      </div>
    );
  }

  return (
    <div className={`w-full overflow-x-auto py-2 ${className}`}>
      <div className="flex items-center justify-between min-w-[760px] gap-2">
        {steps.map((step, idx) => {
          const StepIcon = step.icon;
          return (
            <React.Fragment key={step.label}>
              <div
                className={`flex-1 flex flex-col items-center p-3 rounded-xl border transition-all ${
                  step.highlight
                    ? 'bg-slate-50 border-slate-300 shadow-sm'
                    : 'bg-white border-slate-200 hover:border-slate-300'
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center mb-1.5 ${
                    step.highlight
                      ? 'bg-teal-50 text-teal-700 border border-teal-200'
                      : 'bg-slate-100 text-slate-600 border border-slate-200'
                  }`}
                >
                  <StepIcon className="w-4 h-4" />
                </div>
                <div
                  className={`font-mono text-[10px] font-bold tracking-wider text-center ${
                    step.highlight ? 'text-slate-900' : 'text-slate-700'
                  }`}
                >
                  {step.label}
                </div>
                <div className="text-[9px] text-slate-500 text-center line-clamp-1 mt-0.5">
                  {step.desc}
                </div>
                <div className="mt-1 font-mono text-[8px] text-slate-400 uppercase">
                  {step.phase}
                </div>
              </div>

              {idx < steps.length - 1 && (
                <div className="text-slate-400 font-mono text-xs flex-shrink-0">
                  →
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

