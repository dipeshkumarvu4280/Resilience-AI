import React, { useState, useEffect } from 'react';
import {
  X,
  FileCheck,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { analyticsApi } from '../../services/analyticsApi';
import type { PostIncidentIntelligence } from '../../types/analytics';

interface PostIncidentIntelligenceModalProps {
  situationId: string;
  isOpen: boolean;
  onClose: () => void;
}

export const PostIncidentIntelligenceModal: React.FC<PostIncidentIntelligenceModalProps> = ({
  situationId,
  isOpen,
  onClose,
}) => {
  const [data, setData] = useState<PostIncidentIntelligence | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && situationId) {
      loadIntelligence();
    }
  }, [isOpen, situationId]);

  const loadIntelligence = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await analyticsApi.getPostIncidentIntelligence(situationId);
      setData(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load post-incident intelligence debrief.');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-4xl w-full overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-red-500/20 border border-red-400/30 flex items-center justify-center text-red-400">
              <FileCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-xs font-bold rounded-md bg-red-600 text-white">
                  INTELLIGENCE AUDIT
                </span>
                <span className="text-xs text-slate-400 font-mono">{situationId}</span>
              </div>
              <h2 className="text-lg font-bold text-white">Post-Incident Intelligence Debrief</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 max-h-[80vh] overflow-y-auto space-y-6">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <div className="w-8 h-8 border-3 border-red-600 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm font-medium text-slate-600">Generating 12-factor post-incident summary...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 flex items-center gap-3 text-sm">
              <AlertCircle className="w-5 h-5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : data ? (
            <>
              {/* Situation Header Banner */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="font-bold text-slate-900 text-base">{data.title}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Type: <span className="font-semibold text-slate-700">{data.emergency_type}</span> • Severity:{' '}
                    <span className="font-semibold text-red-600">{data.severity_level}</span> • Status:{' '}
                    <span className="font-semibold text-emerald-600">{data.status}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-right">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Total Duration</span>
                    <span className="text-sm font-bold text-slate-800 font-mono">
                      {data.total_duration_hours !== null ? `${data.total_duration_hours} hrs` : 'Active'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 12-Factor Response Metrics Grid */}
              <div>
                <h4 className="text-xs uppercase font-bold text-slate-500 tracking-wider mb-3">
                  12-Factor Operational Debrief
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Citizen Reports</span>
                    <span className="text-xl font-bold text-slate-900">{data.total_citizen_reports}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Plan Versions (Replans)</span>
                    <span className="text-xl font-bold text-slate-900">
                      v{data.plan_versions_count} <span className="text-xs font-normal text-slate-500">({data.total_replans} revs)</span>
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Tasks Generated / Done</span>
                    <span className="text-xl font-bold text-slate-900">
                      {data.tasks_completed}/{data.total_tasks_generated}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Task Completion Rate</span>
                    <span className="text-xl font-bold text-emerald-600">{data.task_completion_rate}%</span>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Responders Engaged</span>
                    <span className="text-xl font-bold text-blue-600">{data.volunteers_engaged_count}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Vehicles Deployed</span>
                    <span className="text-xl font-bold text-purple-600">{data.vehicles_deployed_count}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Route Obstacles Reported</span>
                    <span className="text-xl font-bold text-amber-600">{data.route_disruptions_count}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Monitoring Events</span>
                    <span className="text-xl font-bold text-slate-900">{data.monitoring_events_count}</span>
                  </div>
                </div>
              </div>

              {/* Participating Domain Agents */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-slate-500" />
                  Participating Multi-Agent Systems
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {data.participating_agents.length > 0 ? (
                    data.participating_agents.map((ag) => (
                      <span
                        key={ag}
                        className="px-2.5 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-800"
                      >
                        {ag}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-slate-400 italic">No agent runs recorded</span>
                  )}
                </div>
              </div>

              {/* Operational Improvements & Learnings */}
              <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-200">
                <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4 text-amber-600" />
                  Operational Improvements & Recommendations
                </h4>
                <ul className="space-y-1.5">
                  {data.operational_improvements.map((imp, idx) => (
                    <li key={idx} className="text-xs text-amber-950 flex items-start gap-2">
                      <CheckCircle2 className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <span>{imp}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Executive Summary Explanation */}
              {data.ai_summary_explanation && (
                <div className="p-4 rounded-xl bg-slate-900 text-white text-xs leading-relaxed">
                  <span className="font-bold text-red-400 block mb-1">Executive Summary</span>
                  {data.ai_summary_explanation}
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold transition-colors"
          >
            Close Debrief
          </button>
        </div>
      </div>
    </div>
  );
};
