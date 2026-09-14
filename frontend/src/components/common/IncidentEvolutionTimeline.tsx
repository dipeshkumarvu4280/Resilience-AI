import React, { useState, useEffect } from 'react';
import {
  Clock,
  Filter,
  ArrowUpDown,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Camera,
  Layers,
  ShieldCheck,
  Activity,
  MapPin,
  RefreshCw,
  User,
  Shield,
  HelpCircle,
} from 'lucide-react';
import type {
  IncidentEvolutionEvent,
  IncidentEvolutionTimelineResponse,
  IncidentEvolutionCategory,
} from '../../types';
import {
  getSituationEvolutionTimeline,
  getReportEvolutionTimeline,
} from '../../services/fieldOperationsApi';

interface IncidentEvolutionTimelineProps {
  targetId: string;
  targetType: 'CITIZEN_REPORT' | 'SITUATION';
  initialData?: IncidentEvolutionTimelineResponse;
  className?: string;
}

const CATEGORY_COLORS: Record<IncidentEvolutionCategory, { bg: string; text: string; border: string; badgeBg: string }> = {
  REPORT: { bg: 'bg-blue-50/70', text: 'text-blue-700', border: 'border-blue-200', badgeBg: 'bg-blue-100/80 text-blue-800' },
  EVIDENCE: { bg: 'bg-purple-50/70', text: 'text-purple-700', border: 'border-purple-200', badgeBg: 'bg-purple-100/80 text-purple-800' },
  SENSOR: { bg: 'bg-sky-50/70', text: 'text-sky-700', border: 'border-sky-200', badgeBg: 'bg-sky-100/80 text-sky-800' },
  CORROBORATION: { bg: 'bg-indigo-50/70', text: 'text-indigo-700', border: 'border-indigo-200', badgeBg: 'bg-indigo-100/80 text-indigo-800' },
  CONFLICT: { bg: 'bg-rose-50/80', text: 'text-rose-700', border: 'border-rose-200', badgeBg: 'bg-rose-100 text-rose-800' },
  FIELD_VERIFICATION: { bg: 'bg-emerald-50/70', text: 'text-emerald-700', border: 'border-emerald-200', badgeBg: 'bg-emerald-100/80 text-emerald-800' },
  OFFICER_ACTION: { bg: 'bg-amber-50/70', text: 'text-amber-800', border: 'border-amber-200', badgeBg: 'bg-amber-100 text-amber-900' },
  RESPONSE_PLAN: { bg: 'bg-teal-50/70', text: 'text-teal-700', border: 'border-teal-200', badgeBg: 'bg-teal-100/80 text-teal-800' },
  FIELD_TASK: { bg: 'bg-cyan-50/70', text: 'text-cyan-700', border: 'border-cyan-200', badgeBg: 'bg-cyan-100/80 text-cyan-800' },
  REPLANNING: { bg: 'bg-yellow-50/70', text: 'text-yellow-800', border: 'border-yellow-200', badgeBg: 'bg-yellow-100 text-yellow-900' },
  RESOLUTION: { bg: 'bg-emerald-50/70', text: 'text-emerald-800', border: 'border-emerald-200', badgeBg: 'bg-emerald-100 text-emerald-900' },
};

export const IncidentEvolutionTimeline: React.FC<IncidentEvolutionTimelineProps> = ({
  targetId,
  targetType,
  initialData,
  className = '',
}) => {
  const [timelineData, setTimelineData] = useState<IncidentEvolutionTimelineResponse | null>(
    initialData || null
  );
  const [isLoading, setIsLoading] = useState<boolean>(!initialData);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const fetchTimeline = async () => {
    setIsLoading(true);
    setError(null);
    try {
      let data: IncidentEvolutionTimelineResponse;
      if (targetType === 'SITUATION') {
        data = await getSituationEvolutionTimeline(targetId, {
          order: sortOrder,
          category: selectedCategory !== 'ALL' ? selectedCategory : undefined,
        });
      } else {
        data = await getReportEvolutionTimeline(targetId, {
          order: sortOrder,
          category: selectedCategory !== 'ALL' ? selectedCategory : undefined,
        });
      }
      setTimelineData(data);
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 404) {
        setError(detail || (targetType === 'SITUATION' ? 'Situation not found' : 'Report not found'));
      } else {
        setError(detail || 'Unable to load timeline');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (targetId) {
      fetchTimeline();
    }
  }, [targetId, targetType, sortOrder, selectedCategory]);

  const getCategoryIcon = (category: IncidentEvolutionCategory) => {
    switch (category) {
      case 'REPORT':
        return <FileText className="w-3.5 h-3.5 text-blue-600" />;
      case 'EVIDENCE':
        return <Camera className="w-3.5 h-3.5 text-purple-600" />;
      case 'SENSOR':
        return <Activity className="w-3.5 h-3.5 text-sky-600" />;
      case 'CORROBORATION':
        return <Layers className="w-3.5 h-3.5 text-indigo-600" />;
      case 'CONFLICT':
        return <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />;
      case 'FIELD_VERIFICATION':
        return <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />;
      case 'OFFICER_ACTION':
        return <User className="w-3.5 h-3.5 text-amber-700" />;
      case 'RESPONSE_PLAN':
      case 'FIELD_TASK':
        return <CheckCircle2 className="w-3.5 h-3.5 text-cyan-600" />;
      case 'REPLANNING':
        return <RefreshCw className="w-3.5 h-3.5 text-yellow-700" />;
      case 'RESOLUTION':
        return <Shield className="w-3.5 h-3.5 text-emerald-700" />;
      default:
        return <HelpCircle className="w-3.5 h-3.5 text-slate-500" />;
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      const d = new Date(ts);
      return {
        date: d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        time: d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
    } catch {
      return { date: '', time: ts };
    }
  };

  const categories: { label: string; value: string }[] = [
    { label: 'All Events', value: 'ALL' },
    { label: 'Citizen Reports', value: 'REPORT' },
    { label: 'Live Evidence', value: 'EVIDENCE' },
    { label: 'Sensors', value: 'SENSOR' },
    { label: 'Corroborations', value: 'CORROBORATION' },
    { label: 'Conflicts', value: 'CONFLICT' },
    { label: 'Field Verifications', value: 'FIELD_VERIFICATION' },
    { label: 'Officer Actions', value: 'OFFICER_ACTION' },
    { label: 'Response Plans', value: 'RESPONSE_PLAN' },
    { label: 'Field Tasks', value: 'FIELD_TASK' },
    { label: 'Replanning', value: 'REPLANNING' },
    { label: 'Resolution', value: 'RESOLUTION' },
  ];

  return (
    <div className={`flex flex-col bg-white border border-slate-200 rounded-2xl p-5 shadow-xs ${className}`}>
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-blue-50 border border-blue-100 text-blue-600">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Incident Evolution Timeline
            </h3>
            <p className="text-xs text-slate-500">
              Auditable ground truth & decision evolution for <span className="font-mono font-semibold text-blue-700">{targetId}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Sort order toggle */}
          <button
            type="button"
            onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-xl transition-all cursor-pointer"
            title="Toggle Sort Order"
          >
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-600" />
            <span>{sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}</span>
          </button>

          {/* Refresh Button */}
          <button
            type="button"
            onClick={fetchTimeline}
            disabled={isLoading}
            className="p-1.5 text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded-xl transition-all disabled:opacity-50 cursor-pointer"
            title="Refresh Timeline"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-blue-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-3 no-scrollbar">
        <Filter className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 ml-1 mr-1" />
        {categories.map((c) => {
          const isSelected = selectedCategory === c.value;
          return (
            <button
              type="button"
              key={c.value}
              onClick={() => setSelectedCategory(c.value)}
              className={`flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-xl whitespace-nowrap transition-all cursor-pointer ${
                isSelected
                  ? 'bg-blue-600 text-white border border-blue-600 shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900 border border-slate-200'
              }`}
            >
              <span>{c.label}</span>
            </button>
          );
        })}
      </div>

      {/* Events List */}
      <div className="mt-2 min-h-[220px] max-h-[480px] overflow-y-auto pr-2 space-y-4">
        {isLoading && !timelineData ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-400">
            <RefreshCw className="w-7 h-7 animate-spin text-blue-600 mb-2" />
            <p className="text-xs font-medium">Aggregating incident evolution trail...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-10 text-center p-4 bg-rose-50/60 border border-rose-200 rounded-xl text-rose-700">
            <AlertTriangle className="w-7 h-7 mb-2 text-rose-600" />
            <p className="text-xs font-bold">{error}</p>
            <button
              type="button"
              onClick={fetchTimeline}
              className="mt-3 px-3 py-1 text-xs font-semibold bg-white border border-rose-300 text-rose-800 rounded-lg hover:bg-rose-50 cursor-pointer"
            >
              Retry Loading
            </button>
          </div>
        ) : !timelineData || timelineData.events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center bg-slate-50 border border-dashed border-slate-200 rounded-xl">
            <Activity className="w-7 h-7 text-slate-400 mb-2" />
            <p className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              No Timeline Events Available
            </p>
            <p className="text-[11px] text-slate-500 max-w-xs mt-1">
              Zero telemetry, field verification, or dispatch actions recorded for this target.
            </p>
          </div>
        ) : (
          <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-[2px] before:bg-slate-200">
            {timelineData.events.map((event: IncidentEvolutionEvent, idx: number) => {
              const formatting = CATEGORY_COLORS[event.category] || {
                bg: 'bg-slate-50',
                text: 'text-slate-700',
                border: 'border-slate-200',
                badgeBg: 'bg-slate-100 text-slate-800',
              };
              const { date, time } = formatTimestamp(event.timestamp);
              const isConflictOrRejection = event.is_conflict || event.event_type === 'REPORT_REJECTED' || event.category === 'CONFLICT';

              return (
                <div key={event.event_id || idx} className="relative group">
                  {/* Timeline Node Point */}
                  <div
                    className={`absolute -left-6 top-2 w-5 h-5 rounded-full border-2 bg-white ${
                      isConflictOrRejection
                        ? 'border-rose-500 ring-4 ring-rose-100'
                        : 'border-blue-500 group-hover:border-blue-600'
                    } flex items-center justify-center transition-all`}
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        isConflictOrRejection ? 'bg-rose-600' : 'bg-blue-600'
                      }`}
                    />
                  </div>

                  {/* Event Card */}
                  <div
                    className={`p-3.5 rounded-xl border ${formatting.border} ${formatting.bg} transition-all duration-200 hover:shadow-xs hover:border-slate-300`}
                  >
                    {/* Top Row: Category badge, Title, and Timestamp */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center flex-wrap gap-2">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-semibold border ${formatting.border} ${formatting.badgeBg}`}
                        >
                          {getCategoryIcon(event.category)}
                          <span>{event.category.replace('_', ' ')}</span>
                        </span>

                        <h4 className="text-xs font-bold text-slate-900">
                          {event.title || event.event_type.replace(/_/g, ' ')}
                        </h4>

                        {event.is_conflict && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 border border-rose-300 text-rose-800 uppercase tracking-wide">
                            <AlertTriangle className="w-2.5 h-2.5 text-rose-600" />
                            Conflict
                          </span>
                        )}
                      </div>

                      <div className="text-right flex-shrink-0">
                        <div className="text-[11px] font-mono font-bold text-slate-800">
                          {time}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {date}
                        </div>
                      </div>
                    </div>

                    {/* Summary / Details Body */}
                    <p className="mt-1.5 text-xs text-slate-700 leading-relaxed font-normal">
                      {event.summary}
                    </p>

                    {/* Bottom Badges: Actor, Spatial distance, Source */}
                    <div className="mt-2.5 pt-2 border-t border-slate-200/70 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <div className="flex items-center gap-2">
                        {event.actor_name && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white text-slate-700 border border-slate-200 shadow-2xs font-medium">
                            <User className="w-3 h-3 text-slate-500" />
                            <span>{event.actor_name}</span>
                            {event.actor_role && (
                              <span className="text-[10px] text-blue-600 font-semibold">
                                ({event.actor_role})
                              </span>
                            )}
                          </span>
                        )}

                        {event.badge_number && (
                          <span className="text-[10px] text-slate-500 font-mono">
                            Badge #{event.badge_number}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {event.distance_meters !== null && event.distance_meters !== undefined && (
                          <span className="inline-flex items-center gap-1 text-[10px] text-slate-600 font-medium">
                            <MapPin className="w-2.5 h-2.5 text-blue-600" />
                            <span>{event.distance_meters.toFixed(0)}m from target</span>
                            {event.spatial_relation && (
                              <span className="text-slate-400 font-mono">
                                [{event.spatial_relation}]
                              </span>
                            )}
                          </span>
                        )}

                        {event.source_id && (
                          <span className="text-[10px] font-mono text-slate-500">
                            ID: {event.source_id}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
