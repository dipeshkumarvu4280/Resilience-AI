import React, { useState, useEffect, useCallback } from 'react';
import {
  getMonitoringEvents,
  getMonitoringStats,
  getEventImpact,
  acknowledgeMonitoringEvent,
  triggerEventReplanning,
} from '../../services/api';
import type {
  MonitoringEvent,
  ChangeImpactResult,
  MonitoringStatsResponse,
  ImpactLevel,
  EventStatus,
  CoordinationPlan,
} from '../../types';
import { CoordinationPlanDiffModal } from './CoordinationPlanDiffModal';
import { OperationalEmptyState } from '../common/OperationalEmptyState';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Search,
  Filter,
  Clock,
  ArrowRight,
  Layers,
  Truck,
  Home,
  HeartPulse,
  Users,
  Eye,
  Check,
  X,
  AlertOctagon,
  ArrowUpRight,
  Sparkles,
  Radio,
} from 'lucide-react';


interface LiveMonitoringPanelProps {
  onInspectSituation?: (situationId: string) => void;
  onInspectPlan?: (situationId: string) => void;
}

export const LiveMonitoringPanel: React.FC<LiveMonitoringPanelProps> = ({
  onInspectSituation,
  onInspectPlan,
}) => {
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [stats, setStats] = useState<MonitoringStatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  // Filters
  const [domainFilter, setDomainFilter] = useState<string>('ALL');
  const [impactFilter, setImpactFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // View Mode: 'feed' vs 'impacted_operations'
  const [viewMode, setViewMode] = useState<'feed' | 'impacted_operations'>('feed');

  // Selected Event Impact Drawer
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedImpact, setSelectedImpact] = useState<ChangeImpactResult | null>(null);
  const [impactLoading, setImpactLoading] = useState<boolean>(false);

  // Acknowledge Modal State
  const [ackEventId, setAckEventId] = useState<string | null>(null);
  const [ackNotes, setAckNotes] = useState<string>('');
  const [ackSubmitting, setAckSubmitting] = useState<boolean>(false);

  // Dynamic Re-Planning & Diff Modal State
  const [activeDiffPlan, setActiveDiffPlan] = useState<CoordinationPlan | null>(null);
  const [replanningLoading, setReplanningLoading] = useState<boolean>(false);

  const fetchMonitoringData = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const isImpactedView = viewMode === 'impacted_operations';
      const [eventsRes, statsRes] = await Promise.all([
        getMonitoringEvents({
          page,
          limit: 20,
          source_type: domainFilter !== 'ALL' ? domainFilter : undefined,
          impact_level: impactFilter !== 'ALL' ? impactFilter : undefined,
          status: statusFilter !== 'ALL' ? statusFilter : undefined,
          is_impacted: isImpactedView ? true : undefined,
          search: searchQuery.trim() || undefined,
        }),
        getMonitoringStats(),
      ]);
      setEvents(eventsRes.items || []);
      setTotalPages(eventsRes.total_pages || 1);
      setTotalCount(eventsRes.total_count || 0);
      setStats(statsRes);
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || err?.message || 'Live monitoring telemetry unavailable';
      console.warn('Could not fetch monitoring telemetry:', err);
      setFetchError(errMsg);
    } finally {
      setLoading(false);
    }
  }, [page, domainFilter, impactFilter, statusFilter, viewMode, searchQuery]);

  useEffect(() => {
    fetchMonitoringData();
  }, [fetchMonitoringData]);

  // Safe 15s polling for live monitoring feed
  useEffect(() => {
    const timer = setInterval(() => {
      fetchMonitoringData();
    }, 15000);
    return () => clearInterval(timer);
  }, [fetchMonitoringData]);

  // Handle Inspect Event Impact
  const handleInspectImpact = async (event: MonitoringEvent) => {
    setSelectedEventId(event.event_id);
    setImpactLoading(true);
    try {
      const impact = await getEventImpact(event.event_id);
      setSelectedImpact(impact);
    } catch (err) {
      console.warn('Could not fetch impact assessment for event:', err);
      setSelectedImpact(null);
    } finally {
      setImpactLoading(false);
    }
  };

  // Handle Acknowledge Alert
  const handleAcknowledge = async () => {
    if (!ackEventId) return;
    setAckSubmitting(true);
    try {
      await acknowledgeMonitoringEvent(ackEventId, ackNotes);
      setAckEventId(null);
      setAckNotes('');
      fetchMonitoringData();
      if (selectedEventId === ackEventId) {
        const refreshedImpact = await getEventImpact(ackEventId);
        setSelectedImpact(refreshedImpact);
      }
    } catch (err) {
      console.warn('Failed to acknowledge alert:', err);
    } finally {
      setAckSubmitting(false);
    }
  };

  const getImpactBadgeClass = (level: ImpactLevel) => {
    switch (level) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200 font-bold';
      case 'HIGH':
        return 'bg-amber-50 text-amber-700 border-amber-200 font-bold';
      case 'MEDIUM':
        return 'bg-yellow-50 text-yellow-800 border-yellow-200';
      case 'LOW':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      default:
        return 'bg-slate-50 text-slate-600 border-slate-200';
    }
  };

  const getStatusBadgeClass = (status: EventStatus) => {
    switch (status) {
      case 'REQUIRES_REVIEW':
        return 'bg-red-50 text-red-700 border-red-200 animate-pulse font-bold';
      case 'RESOLVED':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200 font-bold';
      case 'ACKNOWLEDGED':
        return 'bg-blue-50 text-blue-700 border-blue-200 font-medium';
      case 'ANALYZED':
        return 'bg-slate-50 text-slate-700 border-slate-200';
      case 'DISMISSED':
        return 'bg-slate-100 text-slate-500 border-slate-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const getDomainIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'RESOURCE_INVENTORY':
        return <Truck className="w-3.5 h-3.5 text-emerald-600" />;
      case 'SHELTER_FACILITY':
        return <Home className="w-3.5 h-3.5 text-blue-600" />;
      case 'HEALTHCARE_FACILITY':
        return <HeartPulse className="w-3.5 h-3.5 text-red-600" />;
      case 'VOLUNTEER_NETWORK':
        return <Users className="w-3.5 h-3.5 text-purple-600" />;
      case 'TRANSPORT_FLEET':
      case 'ROUTE_NETWORK':
        return <Layers className="w-3.5 h-3.5 text-amber-600" />;
      case 'SITUATION_INTELLIGENCE':
        return <Activity className="w-3.5 h-3.5 text-blue-700" />;
      case 'SIMULATED_SENSOR':
        return <Radio className="w-3.5 h-3.5 text-cyan-600" />;
      default:
        return <Activity className="w-3.5 h-3.5 text-slate-600" />;
    }
  };

  // Filtered Events for Search Query
  const filteredEvents = events.filter((evt) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      evt.event_id.toLowerCase().includes(q) ||
      evt.source_id.toLowerCase().includes(q) ||
      evt.event_type.toLowerCase().includes(q) ||
      (evt.situation_id && evt.situation_id.toLowerCase().includes(q)) ||
      (evt.coordination_plan_id && evt.coordination_plan_id.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {fetchError && (
        <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <div>
              <span className="font-bold">Live telemetry notice:</span>{' '}
              <span>{fetchError}</span>
            </div>
          </div>
          <button
            onClick={fetchMonitoringData}
            disabled={loading}
            className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1 shrink-0 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Top Telemetry KPI Bar with Interactive Drill-Downs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div
          onClick={() => {
            setViewMode('feed');
            setImpactFilter('ALL');
            setStatusFilter('ALL');
            setSearchQuery('');
          }}
          className="group p-3.5 rounded-2xl bg-white border border-slate-200/90 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold mb-1 group-hover:text-slate-700 transition-colors">
            TOTAL EVENTS
          </div>
          <div className="text-xl font-extrabold text-slate-900 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.total_events || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500 font-sans mt-0.5">
            <span>Authoritative</span>
            <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => {
            setViewMode('feed');
            setImpactFilter('CRITICAL');
          }}
          className="group p-3.5 rounded-2xl bg-white border border-red-200/90 shadow-xs bg-red-50/20 hover:shadow-md hover:border-red-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-red-600 font-bold mb-1 flex items-center gap-1 group-hover:text-red-700 transition-colors">
            <AlertTriangle className="w-3 h-3" />
            <span>CRITICAL IMPACTS</span>
          </div>
          <div className="text-xl font-extrabold text-red-700 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.critical_impacts || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-red-600/80 font-sans mt-0.5">
            <span>Breaches</span>
            <span className="text-red-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => {
            setViewMode('feed');
            setImpactFilter('HIGH');
          }}
          className="group p-3.5 rounded-2xl bg-white border border-amber-200/90 shadow-xs bg-amber-50/20 hover:shadow-md hover:border-amber-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-amber-700 font-bold mb-1 group-hover:text-amber-800 transition-colors">
            HIGH IMPACTS
          </div>
          <div className="text-xl font-extrabold text-amber-800 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.high_impacts || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-amber-700/80 font-sans mt-0.5">
            <span>Reductions</span>
            <span className="text-amber-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setViewMode('impacted_operations')}
          className="group p-3.5 rounded-2xl bg-white border border-slate-200/90 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 font-bold mb-1 group-hover:text-slate-700 transition-colors">
            PLANS AFFECTED
          </div>
          <div className="text-xl font-extrabold text-slate-900 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.invalidated_plans || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500 font-sans mt-0.5">
            <span>Invalidated</span>
            <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => {
            setViewMode('feed');
            setStatusFilter('REQUIRES_REVIEW');
          }}
          className="group p-3.5 rounded-2xl bg-white border border-purple-200/90 shadow-xs bg-purple-50/20 hover:shadow-md hover:border-purple-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-purple-700 font-bold mb-1 group-hover:text-purple-800 transition-colors">
            REQUIRES REVIEW
          </div>
          <div className="text-xl font-extrabold text-purple-800 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.plans_requiring_review || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-purple-700/80 font-sans mt-0.5">
            <span>Attention</span>
            <span className="text-purple-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => {
            setViewMode('feed');
            setStatusFilter('ACKNOWLEDGED');
          }}
          className="group p-3.5 rounded-2xl bg-white border border-emerald-200/90 shadow-xs bg-emerald-50/20 hover:shadow-md hover:border-emerald-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-700 font-bold mb-1 flex items-center gap-1 group-hover:text-emerald-800 transition-colors">
            <CheckCircle className="w-3 h-3" />
            <span>ACKNOWLEDGED</span>
          </div>
          <div className="text-xl font-extrabold text-emerald-800 font-mono group-hover:scale-105 transition-transform origin-left">
            {stats?.acknowledged_events || 0}
          </div>
          <div className="flex items-center justify-between text-[10px] text-emerald-700/80 font-sans mt-0.5">
            <span>Audited</span>
            <span className="text-emerald-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>
      </div>

      {/* Main Container Card */}
      <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm overflow-hidden flex flex-col">
        {/* Control Toolbar */}
        <div className="p-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 bg-slate-50/60">
          {/* Left: View Mode Toggle */}
          <div className="flex items-center gap-2">
            <div className="flex items-center rounded-xl border border-slate-200 bg-white p-1 text-xs font-semibold shadow-2xs">
              <button
                type="button"
                onClick={() => {
                  setViewMode('feed');
                  setPage(1);
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                  viewMode === 'feed'
                    ? 'bg-slate-900 text-white font-bold shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Live Event Stream</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setViewMode('impacted_operations');
                  setPage(1);
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                  viewMode === 'impacted_operations'
                    ? 'bg-red-600 text-white font-bold shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>
                  Impacted Operations ({stats?.impacted_operations_count ?? (stats?.invalidated_plans || 0)})
                </span>
              </button>
            </div>

            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold hidden sm:inline">
              LIVE MONITORING ACTIVE
            </span>
          </div>

          {/* Right: Search & Refresh */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Search event ID, source, plan..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-red-500 w-56 sm:w-64"
              />
            </div>
            <button
              onClick={fetchMonitoringData}
              disabled={loading}
              title="Refresh Monitoring Data"
              className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="px-4 py-2.5 border-b border-slate-100 bg-white flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400 text-[11px] font-semibold flex items-center gap-1 mr-1">
            <Filter className="w-3 h-3" />
            <span>Filters:</span>
          </span>

          {/* Domain Filter */}
          <select
            value={domainFilter}
            onChange={(e) => {
              setDomainFilter(e.target.value);
              setPage(1);
            }}
            className="px-2 py-1 text-xs rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="ALL">All Domains</option>
            <option value="RESOURCE_INVENTORY">Resource Inventory</option>
            <option value="SHELTER_FACILITY">Shelter Facilities</option>
            <option value="HEALTHCARE_FACILITY">Healthcare Facilities</option>
            <option value="VOLUNTEER_NETWORK">Volunteer Network</option>
            <option value="TRANSPORT_FLEET">Transport & Fleet</option>
            <option value="SITUATION_INTELLIGENCE">Situation Intelligence</option>
            <option value="CITIZEN_REPORT">Citizen Reports</option>
            <option value="SIMULATED_SENSOR">IoT Sensor Streams</option>
          </select>

          {/* Impact Level Filter */}
          <select
            value={impactFilter}
            onChange={(e) => {
              setImpactFilter(e.target.value);
              setPage(1);
            }}
            className="px-2 py-1 text-xs rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="ALL">All Impact Levels</option>
            <option value="CRITICAL">Critical Impact</option>
            <option value="HIGH">High Impact</option>
            <option value="MEDIUM">Medium Impact</option>
            <option value="LOW">Low Impact</option>
            <option value="NONE">No Impact (Informational)</option>
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="px-2 py-1 text-xs rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="ALL">All Statuses</option>
            <option value="REQUIRES_REVIEW">Requires Review</option>
            <option value="DETECTED">Detected</option>
            <option value="ANALYZED">Analyzed</option>
            <option value="ACKNOWLEDGED">Acknowledged</option>
            <option value="RESOLVED">Resolved (Remediated)</option>
          </select>
        </div>

        {/* Content Body */}
        {fetchError ? (
          <div className="p-8 text-center space-y-3 bg-red-50/30">
            <div className="w-12 h-12 rounded-2xl bg-red-100 text-red-700 flex items-center justify-center mx-auto border border-red-200">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">Live Monitoring Data Unavailable</h3>
            <p className="text-xs text-red-600 max-w-md mx-auto">{fetchError}</p>
            <button
              onClick={fetchMonitoringData}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-xs font-bold transition inline-flex items-center gap-1.5 shadow-xs cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Telemetry Connection</span>
            </button>
          </div>
        ) : loading && events.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
            <RefreshCw className="w-6 h-6 animate-spin text-red-600" />
            <span>Loading live monitoring telemetry...</span>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="p-8">
            <OperationalEmptyState
              icon={Activity}
              title="No Operational Changes Detected"
              description="Authoritative monitoring loop is active. Real-time events from resource updates, citizen reports, shelter changes, or situations will appear here automatically."
              phaseBadge="LIVE MONITOR"
              accentColor="red"
            />
          </div>
        ) : viewMode === 'feed' ? (

          /* Feed View */
          <div className="divide-y divide-slate-100">
            {filteredEvents.map((evt) => (
              <div
                key={evt.event_id}
                className={`p-4 hover:bg-slate-50/70 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                  evt.impact_level === 'CRITICAL' ? 'bg-red-50/15' : ''
                }`}
              >
                {/* Event Left Metadata */}
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                      {evt.event_id}
                    </span>

                    <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border bg-white text-slate-700 border-slate-200 shadow-2xs">
                      {getDomainIcon(evt.source_type)}
                      <span>{evt.source_type.replace('_', ' ')}</span>
                    </span>

                    <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${getImpactBadgeClass(evt.impact_level)}`}>
                      {evt.impact_level} IMPACT
                    </span>

                    <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${getStatusBadgeClass(evt.status)}`}>
                      {evt.status.replace('_', ' ')}
                    </span>
                  </div>

                  {/* Event Headline */}
                  <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                    <span>{evt.event_type.replace(/_/g, ' ')}</span>
                    <span className="text-slate-300">•</span>
                    <span className="font-mono text-slate-600 font-semibold">{evt.source_id}</span>
                  </div>

                  {/* Correlated Situations & Plans */}
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    {evt.situation_id && (
                      <span
                        onClick={() => onInspectSituation?.(evt.situation_id!)}
                        className="text-blue-600 hover:underline cursor-pointer font-mono font-semibold flex items-center gap-0.5"
                      >
                        📍 Situation: {evt.situation_id}
                      </span>
                    )}
                    {evt.coordination_plan_id && (
                      <span
                        onClick={() => onInspectPlan?.(evt.situation_id || '')}
                        className="text-purple-600 hover:underline cursor-pointer font-mono font-semibold flex items-center gap-0.5"
                      >
                        🛡️ Plan: {evt.coordination_plan_id}
                      </span>
                    )}
                    <span className="flex items-center gap-1 text-slate-400">
                      <Clock className="w-3 h-3" />
                      <span>{new Date(evt.detected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                    </span>
                  </div>
                </div>

                {/* Event Actions */}
                <div className="flex items-center gap-2 flex-shrink-0 pt-2 sm:pt-0">
                  <button
                    onClick={() => handleInspectImpact(evt)}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-xs font-semibold shadow-2xs flex items-center gap-1.5 transition-all cursor-pointer"
                  >
                    <Eye className="w-3.5 h-3.5 text-blue-600" />
                    <span>Inspect Impact</span>
                  </button>

                  {evt.status === 'RESOLVED' ? (
                    <span className="px-2.5 py-1 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold flex items-center gap-1 shadow-2xs">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Resolved</span>
                    </span>
                  ) : evt.status === 'ACKNOWLEDGED' ? (
                    <span className="px-2.5 py-1 rounded-xl bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold flex items-center gap-1 shadow-2xs">
                      <Check className="w-3.5 h-3.5 text-blue-600" />
                      <span>Acknowledged</span>
                    </span>
                  ) : (
                    <button
                      onClick={() => setAckEventId(evt.event_id)}
                      className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-2xs flex items-center gap-1 transition-all cursor-pointer"
                    >
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Acknowledge</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Impacted Operations View */
          <div className="p-4 space-y-4">
            {events.length === 0 ? (
              <div className="p-6">
                <OperationalEmptyState
                  icon={AlertTriangle}
                  title="No Active Operational Disruptions"
                  description="Authoritative monitoring loop confirms all response plans, resource allocations, and operational constraints are satisfied."
                  phaseBadge="DISRUPTIONS CLEAR"
                  accentColor="amber"
                />
              </div>
            ) : (
              events.map((evt) => (
                <div
                  key={evt.event_id}
                  className="p-4 rounded-2xl border border-red-200 bg-red-50/20 shadow-xs space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-red-100 pb-2.5">
                    <div className="flex items-center gap-2">
                      <AlertOctagon className="w-4 h-4 text-red-600" />
                      <span className="text-xs font-extrabold text-red-900">
                        CONSTRAINT VIOLATION — {evt.event_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border bg-white text-slate-700 border-slate-200 shadow-2xs">
                        {getDomainIcon(evt.source_type)}
                        <span>{evt.source_type.replace(/_/g, ' ')}</span>
                      </span>
                      <span className={`text-[10px] uppercase px-2.5 py-0.5 rounded-full border ${getImpactBadgeClass(evt.impact_level)}`}>
                        {evt.impact_level} IMPACT
                      </span>
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${getStatusBadgeClass(evt.status)}`}>
                        {evt.status.replace(/_/g, ' ')}
                      </span>
                      <span className="font-mono text-xs text-slate-600 font-semibold">{evt.event_id}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                    <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs space-y-1">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">AFFECTED SITUATION</div>
                      <div className="font-bold text-slate-900 font-mono">{evt.situation_id || 'Global Inventory'}</div>
                      {evt.situation_id && (
                        <button
                          onClick={() => onInspectSituation?.(evt.situation_id!)}
                          className="text-[11px] text-blue-600 hover:underline flex items-center gap-0.5 pt-1 cursor-pointer"
                        >
                          <span>Open Situation Details</span>
                          <ArrowUpRight className="w-3 h-3" />
                        </button>
                      )}
                    </div>

                    <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs space-y-1">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">AFFECTED PLAN</div>
                      <div className="font-bold text-slate-900 font-mono">{evt.coordination_plan_id || 'Pending Plan'}</div>
                      {evt.coordination_plan_id && (
                        <button
                          onClick={() => onInspectPlan?.(evt.situation_id || '')}
                          className="text-[11px] text-purple-600 hover:underline flex items-center gap-0.5 pt-1 cursor-pointer"
                        >
                          <span>Inspect Response Plan</span>
                          <ArrowUpRight className="w-3 h-3" />
                        </button>
                      )}
                    </div>

                    <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-2xs space-y-1">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">OPERATIONAL ASSET</div>
                      <div className="font-bold text-slate-900 font-mono">{evt.source_id}</div>
                      <div className="text-[11px] text-slate-500">{evt.source_type.replace(/_/g, ' ')}</div>
                    </div>
                  </div>

                  {/* State Change Details If Available */}
                  {evt.changed_fields && evt.changed_fields.length > 0 && (
                    <div className="p-2.5 rounded-xl bg-amber-50/60 border border-amber-200/80 text-xs text-amber-900 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                        <span>
                          <strong className="font-semibold">Modified Fields:</strong> {evt.changed_fields.join(', ')}
                        </span>
                      </div>
                      {evt.previous_state && evt.new_state && (
                        <div className="font-mono text-[11px] text-amber-800">
                          {evt.changed_fields.map((f) => (
                            <span key={f}>
                              {f}: {String(evt.previous_state[f] ?? 'N/A')} &rarr; {String(evt.new_state[f] ?? 'N/A')}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-red-100/60">
                    <div className="text-[11px] text-slate-500 font-mono flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      <span>Detected at: {new Date(evt.detected_at).toLocaleString()}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {evt.status === 'RESOLVED' ? (
                        <span className="px-2.5 py-1 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold flex items-center gap-1 shadow-2xs">
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Resolved</span>
                        </span>
                      ) : evt.status === 'ACKNOWLEDGED' ? (
                        <span className="px-2.5 py-1 rounded-xl bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold flex items-center gap-1 shadow-2xs">
                          <Check className="w-3.5 h-3.5 text-blue-600" />
                          <span>Acknowledged</span>
                        </span>
                      ) : (
                        <button
                          onClick={() => setAckEventId(evt.event_id)}
                          className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-2xs flex items-center gap-1 transition-all cursor-pointer"
                        >
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Acknowledge</span>
                        </button>
                      )}

                      <button
                        onClick={() => handleInspectImpact(evt)}
                        className="px-3 py-1.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-all cursor-pointer"
                      >
                        <span>View Full Impact Analysis</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="p-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600 bg-slate-50/50">
            <span>
              Showing Page <strong>{page}</strong> of <strong>{totalPages}</strong> ({totalCount} Total Events)
            </span>
            <div className="flex items-center gap-1">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Impact Assessment Details Drawer / Modal */}
      {selectedEventId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="w-full max-w-2xl bg-white rounded-3xl border border-slate-200 shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-red-50 border border-red-200 text-red-600 flex items-center justify-center font-bold">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Change Impact Assessment — {selectedEventId}
                  </h3>
                  <div className="text-[11px] text-slate-500 font-mono">
                    Deterministic Constraint & Resource Impact Analysis
                  </div>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedEventId(null);
                  setSelectedImpact(null);
                }}
                className="p-1.5 rounded-lg hover:bg-slate-200/60 text-slate-500 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {impactLoading ? (
                <div className="py-12 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-red-600" />
                  <span>Evaluating impact parameters...</span>
                </div>
              ) : selectedImpact ? (
                <>
                  {/* Summary Alert Box */}
                  {selectedImpact.remediation_status === 'RESOLVED' || events.find((e) => e.event_id === selectedEventId)?.status === 'RESOLVED' ? (
                    <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full border bg-emerald-100 text-emerald-800 border-emerald-300 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3 text-emerald-600" />
                          <span>CONSTRAINT RESOLVED</span>
                        </span>
                        {(selectedImpact.resolved_at || events.find((e) => e.event_id === selectedEventId)?.resolved_at) && (
                          <span className="text-[11px] font-mono text-emerald-700">
                            Resolved at: {new Date(selectedImpact.resolved_at || events.find((e) => e.event_id === selectedEventId)!.resolved_at!).toLocaleString()}
                          </span>
                        )}
                      </div>
                      <div className="space-y-1">
                        <div className="text-[11px] font-mono font-bold uppercase text-emerald-800">Resolution Details</div>
                        <p className="text-xs font-semibold text-emerald-950 leading-relaxed">
                          {selectedImpact.resolution_reason || events.find((e) => e.event_id === selectedEventId)?.resolution_reason || 'Underlying operational constraint verified and remediated by active response plan.'}
                        </p>
                      </div>
                      {(selectedImpact.resolved_in_plan_id || events.find((e) => e.event_id === selectedEventId)?.resolved_in_plan_id) && (
                        <div className="text-[11px] font-mono text-emerald-800 font-medium">
                          Remediated in Active Plan: <strong>{selectedImpact.resolved_in_plan_id || events.find((e) => e.event_id === selectedEventId)?.resolved_in_plan_id}</strong> (v{selectedImpact.resolved_in_plan_version || events.find((e) => e.event_id === selectedEventId)?.resolved_in_plan_version || 1})
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className={`p-4 rounded-2xl border space-y-2 ${
                      selectedImpact.impact_level === 'CRITICAL'
                        ? 'bg-red-50/40 border-red-200'
                        : selectedImpact.impact_level === 'HIGH'
                        ? 'bg-amber-50/40 border-amber-200'
                        : 'bg-blue-50/40 border-blue-200'
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full border ${getImpactBadgeClass(selectedImpact.impact_level)}`}>
                          {selectedImpact.impact_level} IMPACT
                        </span>
                        <span className="text-xs font-mono text-slate-600 font-bold">
                          Plan Status: <strong>{selectedImpact.plan_status}</strong>
                        </span>
                      </div>
                      <p className="text-xs font-semibold text-slate-800 leading-relaxed">
                        {selectedImpact.explanation}
                      </p>
                    </div>
                  )}

                  {/* Violated Constraints */}
                  {selectedImpact.violated_constraints.length > 0 && (
                    <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 space-y-1.5">
                      <div className="text-[11px] font-mono font-bold uppercase text-red-700 flex items-center gap-1">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>Violated Constraints</span>
                      </div>
                      <ul className="space-y-1 text-xs text-slate-700 list-disc list-inside">
                        {selectedImpact.violated_constraints.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Affected Agents & Dependency Chain */}
                  <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="text-[11px] font-mono font-bold uppercase text-slate-700 flex items-center gap-1">
                      <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                      <span>Affected Agents & Dynamic Replanning Execution Order</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {selectedImpact.dependency_chain.map((agentName, idx) => (
                        <div key={agentName} className="flex items-center gap-1">
                          <span className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-xs font-mono font-bold text-slate-800 shadow-2xs">
                            {agentName}
                          </span>
                          {idx < selectedImpact.dependency_chain.length - 1 && (
                            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* State Diff (Before vs After) */}
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200 space-y-1">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">STATE BEFORE</div>
                      <pre className="text-[11px] font-mono bg-white p-2 rounded-lg border border-slate-100 overflow-x-auto text-slate-700">
                        {JSON.stringify(selectedImpact.previous_state, null, 2)}
                      </pre>
                    </div>

                    <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200 space-y-1">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold">STATE AFTER</div>
                      <pre className="text-[11px] font-mono bg-white p-2 rounded-lg border border-slate-100 overflow-x-auto text-slate-700">
                        {JSON.stringify(selectedImpact.new_state, null, 2)}
                      </pre>
                    </div>
                  </div>
                </>
              ) : (
                <div className="py-8 text-center text-slate-400 text-xs">
                  No impact record found for this event.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-200 flex items-center justify-between gap-2 bg-slate-50">
              {selectedImpact?.remediation_status === 'RESOLVED' || events.find((e) => e.event_id === selectedEventId)?.status === 'RESOLVED' ? (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-100 text-emerald-800 text-xs font-bold border border-emerald-200">
                  <CheckCircle className="w-4 h-4 text-emerald-600" />
                  <span>Constraint Remediated & Resolved</span>
                </div>
              ) : selectedImpact?.coordination_plan_id ? (
                <button
                  onClick={async () => {
                    if (!selectedEventId) return;
                    setReplanningLoading(true);
                    try {
                      const revisedPlan = await triggerEventReplanning(selectedEventId);
                      if (revisedPlan) {
                        setActiveDiffPlan(revisedPlan);
                        setSelectedEventId(null);
                        setSelectedImpact(null);
                      }
                    } catch (err: any) {
                      alert(err?.response?.data?.detail || 'Re-planning failed.');
                    } finally {
                      setReplanningLoading(false);
                    }
                  }}
                  disabled={replanningLoading}
                  className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold flex items-center gap-1.5 shadow-xs disabled:opacity-50"
                >
                  {replanningLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  <span>Trigger Dynamic Re-Planning</span>
                </button>
              ) : (
                <div />
              )}

              <button
                onClick={() => {
                  setSelectedEventId(null);
                  setSelectedImpact(null);
                }}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-xs font-semibold hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dynamic Re-Planning Diff Modal */}
      {activeDiffPlan && (
        <CoordinationPlanDiffModal
          plan={activeDiffPlan}
          isOpen={!!activeDiffPlan}
          onClose={() => setActiveDiffPlan(null)}
          onPlanActivated={() => {
            fetchMonitoringData();
          }}
        />
      )}

      {/* Acknowledge Event Modal */}
      {ackEventId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-2xl p-5 space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center font-bold">
                <CheckCircle className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Acknowledge Operational Alert
                </h3>
                <div className="text-[11px] text-slate-500 font-mono">
                  Event: {ackEventId}
                </div>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Recording your review of this operational change in the immutable audit timeline.
              This does NOT execute replanning or mutate resource allocations.
            </p>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Officer Notes (Optional)
              </label>
              <textarea
                value={ackNotes}
                onChange={(e) => setAckNotes(e.target.value)}
                placeholder="E.g. Noted resource shortfall, standby for mutual aid."
                rows={3}
                className="w-full p-2.5 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  setAckEventId(null);
                  setAckNotes('');
                }}
                className="px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-xs font-semibold hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={handleAcknowledge}
                disabled={ackSubmitting}
                className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs disabled:opacity-50"
              >
                {ackSubmitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5 text-emerald-400" />}
                <span>Confirm Acknowledge</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LiveMonitoringPanel;
