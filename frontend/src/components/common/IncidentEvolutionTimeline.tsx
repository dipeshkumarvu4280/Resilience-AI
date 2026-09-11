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

const CATEGORY_COLORS: Record<IncidentEvolutionCategory, { bg: string; text: string; border: string; iconBg: string }> = {
  REPORT: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', iconBg: 'bg-blue-500/20' },
  EVIDENCE: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', iconBg: 'bg-purple-500/20' },
  SENSOR: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/30', iconBg: 'bg-cyan-500/20' },
  CORROBORATION: { bg: 'bg-indigo-500/10', text: 'text-indigo-400', border: 'border-indigo-500/30', iconBg: 'bg-indigo-500/20' },
  CONFLICT: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30', iconBg: 'bg-rose-500/20' },
  FIELD_VERIFICATION: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', iconBg: 'bg-emerald-500/20' },
  OFFICER_ACTION: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30', iconBg: 'bg-amber-500/20' },
  RESPONSE_PLAN: { bg: 'bg-teal-500/10', text: 'text-teal-400', border: 'border-teal-500/30', iconBg: 'bg-teal-500/20' },
  FIELD_TASK: { bg: 'bg-sky-500/10', text: 'text-sky-400', border: 'border-sky-500/30', iconBg: 'bg-sky-500/20' },
  REPLANNING: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', iconBg: 'bg-yellow-500/20' },
  RESOLUTION: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', iconBg: 'bg-emerald-500/20' },
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
      setError(err?.response?.data?.detail || err.message || 'Failed to load timeline');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTimeline();
  }, [targetId, targetType, sortOrder, selectedCategory]);

  const getCategoryIcon = (category: IncidentEvolutionCategory) => {
    switch (category) {
      case 'REPORT':
        return <FileText className="w-4 h-4 text-blue-400" />;
      case 'EVIDENCE':
        return <Camera className="w-4 h-4 text-purple-400" />;
      case 'SENSOR':
        return <Activity className="w-4 h-4 text-cyan-400" />;
      case 'CORROBORATION':
        return <Layers className="w-4 h-4 text-indigo-400" />;
      case 'CONFLICT':
        return <AlertTriangle className="w-4 h-4 text-rose-400" />;
      case 'FIELD_VERIFICATION':
        return <ShieldCheck className="w-4 h-4 text-emerald-400" />;
      case 'OFFICER_ACTION':
        return <User className="w-4 h-4 text-amber-400" />;
      case 'RESPONSE_PLAN':
      case 'FIELD_TASK':
        return <CheckCircle2 className="w-4 h-4 text-sky-400" />;
      case 'REPLANNING':
        return <RefreshCw className="w-4 h-4 text-yellow-400" />;
      case 'RESOLUTION':
        return <Shield className="w-4 h-4 text-emerald-400" />;
      default:
        return <HelpCircle className="w-4 h-4 text-slate-400" />;
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
    <div className={`flex flex-col bg-slate-900/90 border border-slate-800 rounded-xl p-5 backdrop-blur-md shadow-xl ${className}`}>
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <Clock className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white tracking-wide">
              Incident Evolution Timeline
            </h3>
            <p className="text-xs text-slate-400">
              Auditable ground truth & decision evolution for <span className="font-mono text-emerald-400">{targetId}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Sort order toggle */}
          <button
            onClick={() => setSortOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 rounded-lg transition-colors"
            title="Toggle Sort Order"
          >
            <ArrowUpDown className="w-3.5 h-3.5 text-emerald-400" />
            <span>{sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}</span>
          </button>

          {/* Refresh Button */}
          <button
            onClick={fetchTimeline}
            disabled={isLoading}
            className="p-1.5 text-slate-400 hover:text-white bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh Timeline"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-3 no-scrollbar">
        <Filter className="w-3.5 h-3.5 text-slate-500 flex-shrink-0 ml-1 mr-1" />
        {categories.map((c) => {
          const count = timelineData?.category_counts?.[c.value] ?? (c.value === 'ALL' ? timelineData?.total_events : undefined);
          const isSelected = selectedCategory === c.value;
          return (
            <button
              key={c.value}
              onClick={() => setSelectedCategory(c.value)}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md whitespace-nowrap transition-all ${
                isSelected
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'bg-slate-800/50 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <span>{c.label}</span>
              {count !== undefined && count > 0 && (
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                  isSelected ? 'bg-emerald-500/30 text-emerald-200' : 'bg-slate-700 text-slate-300'
                }`}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Events List */}
      <div className="mt-2 min-h-[220px] max-h-[480px] overflow-y-auto pr-2 space-y-4">
        {isLoading && !timelineData ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500">
            <RefreshCw className="w-8 h-8 animate-spin text-emerald-500/60 mb-2" />
            <p className="text-xs">Aggregating incident evolution trail...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-10 text-rose-400">
            <AlertTriangle className="w-8 h-8 mb-2 opacity-80" />
            <p className="text-xs font-medium">{error}</p>
          </div>
        ) : !timelineData || timelineData.events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center bg-slate-950/40 border border-dashed border-slate-800 rounded-xl">
            <Activity className="w-8 h-8 text-slate-600 mb-2" />
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              NO EVENTS RECORDED
            </p>
            <p className="text-[11px] text-slate-500 max-w-xs mt-1">
              Zero telemetry, field verification, or dispatch actions recorded for this target.
            </p>
          </div>
        ) : (
          <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-[2px] before:bg-slate-800">
            {timelineData.events.map((event: IncidentEvolutionEvent, idx: number) => {
              const formatting = CATEGORY_COLORS[event.category] || {
                bg: 'bg-slate-500/10',
                text: 'text-slate-400',
                border: 'border-slate-500/30',
                iconBg: 'bg-slate-500/20',
              };
              const { date, time } = formatTimestamp(event.timestamp);

              return (
                <div key={event.event_id || idx} className="relative group">
                  {/* Timeline Node Point */}
                  <div
                    className={`absolute -left-6 top-1.5 w-5 h-5 rounded-full border-2 ${
                      event.is_conflict
                        ? 'bg-rose-950 border-rose-500 ring-4 ring-rose-500/20'
                        : 'bg-slate-900 border-slate-700 group-hover:border-emerald-500'
                    } flex items-center justify-center transition-all`}
                  >
                    <div
                      className={`w-2 h-2 rounded-full ${
                        event.is_conflict ? 'bg-rose-500' : 'bg-emerald-400'
                      }`}
                    />
                  </div>

                  {/* Event Card */}
                  <div
                    className={`p-3.5 rounded-lg border ${formatting.border} ${formatting.bg} transition-all duration-200 hover:shadow-md hover:border-opacity-80`}
                  >
                    {/* Top Row: Category badge, Title, and Timestamp */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center flex-wrap gap-2">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border ${formatting.border} ${formatting.text} bg-slate-950/60`}
                        >
                          {getCategoryIcon(event.category)}
                          <span>{event.category.replace('_', ' ')}</span>
                        </span>

                        <h4 className="text-xs font-semibold text-slate-100">
                          {event.title}
                        </h4>

                        {event.is_conflict && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 border border-rose-500/40 text-rose-300 uppercase tracking-wide">
                            <AlertTriangle className="w-2.5 h-2.5 text-rose-400" />
                            Conflict
                          </span>
                        )}
                      </div>

                      <div className="text-right flex-shrink-0">
                        <div className="text-[11px] font-mono font-medium text-slate-300">
                          {time}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {date}
                        </div>
                      </div>
                    </div>

                    {/* Summary / Details Body */}
                    <p className="mt-1.5 text-xs text-slate-300 leading-relaxed">
                      {event.summary}
                    </p>

                    {/* Bottom Badges: Actor, Spatial distance, Source */}
                    <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <div className="flex items-center gap-2">
                        {event.actor_name && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60">
                            <User className="w-3 h-3 text-slate-400" />
                            <span>{event.actor_name}</span>
                            {event.actor_role && (
                              <span className="text-[10px] text-emerald-400 font-medium">
                                ({event.actor_role})
                              </span>
                            )}
                          </span>
                        )}

                        {event.badge_number && (
                          <span className="text-[10px] text-slate-400 font-mono">
                            Badge #{event.badge_number}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {event.distance_meters !== null && event.distance_meters !== undefined && (
                          <span className="inline-flex items-center gap-1 text-[10px] text-slate-400">
                            <MapPin className="w-2.5 h-2.5 text-emerald-400" />
                            <span>{event.distance_meters.toFixed(0)}m from target</span>
                            {event.spatial_relation && (
                              <span className="text-slate-500 font-mono">
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
