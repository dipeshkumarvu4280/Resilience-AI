import React, { useState, useEffect } from 'react';
import {
  BarChart3,
  Clock,
  AlertTriangle,
  Layers,
  Truck,
  Home,
  HeartPulse,
  Users,
  RefreshCw,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  Package,
} from 'lucide-react';
import { analyticsApi } from '../../services/analyticsApi';
import type { AnalyticsFilterParams } from '../../services/analyticsApi';
import type {
  EmergencyAnalyticsOverview,
  ResponseMilestoneTimeline,
  BottleneckInsight,
  ResourceUtilizationAnalytics,
  ShelterAnalytics,
  HealthcareAnalytics,
  VolunteerPerformanceAnalytics,
  FleetAnalytics,
  ReplanningIntelligence,
  IncidentComparisonResponse,
  DecisionSupportResponse,
  AnalyticsTimeRange,
} from '../../types/analytics';
import { PostIncidentIntelligenceModal } from './PostIncidentIntelligenceModal';

export const EmergencyAnalyticsWorkspace: React.FC = () => {
  // Filters
  const [timeRange, setTimeRange] = useState<AnalyticsTimeRange>('all');
  const [disasterType, setDisasterType] = useState<string>('');
  const [severity, setSeverity] = useState<string>('');
  const [zone, setZone] = useState<string>('');
  const [activeTab, setActiveTab] = useState<
    'overview' | 'milestones' | 'capacity' | 'fleet' | 'replanning' | 'decision-support' | 'comparison'
  >('overview');

  // Comparison Dimension
  const [compDimension, setCompDimension] = useState<'emergency_type' | 'severity_level' | 'zone'>('emergency_type');

  // Selected Situation for Debrief Modal
  const [selectedDebriefSituationId, setSelectedDebriefSituationId] = useState<string | null>(null);

  // States
  const [overview, setOverview] = useState<EmergencyAnalyticsOverview | null>(null);
  const [milestones, setMilestones] = useState<ResponseMilestoneTimeline | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckInsight[]>([]);
  const [resources, setResources] = useState<ResourceUtilizationAnalytics | null>(null);
  const [shelters, setShelters] = useState<ShelterAnalytics | null>(null);
  const [healthcare, setHealthcare] = useState<HealthcareAnalytics | null>(null);
  const [volunteers, setVolunteers] = useState<VolunteerPerformanceAnalytics | null>(null);
  const [fleet, setFleet] = useState<FleetAnalytics | null>(null);
  const [replanning, setReplanning] = useState<ReplanningIntelligence | null>(null);
  const [comparison, setComparison] = useState<IncidentComparisonResponse | null>(null);
  const [decisionSupport, setDecisionSupport] = useState<DecisionSupportResponse | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAllAnalytics();
  }, [timeRange, disasterType, severity, zone, compDimension]);

  const loadAllAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const filterParams: AnalyticsFilterParams = {
        time_range: timeRange,
        disaster_type: disasterType || undefined,
        severity: severity || undefined,
        zone: zone || undefined,
      };

      const [
        ovRes,
        msRes,
        bnRes,
        resRes,
        shlRes,
        hcRes,
        volRes,
        fltRes,
        repRes,
        compRes,
        dsRes,
      ] = await Promise.all([
        analyticsApi.getOverview(filterParams),
        analyticsApi.getMilestones(filterParams),
        analyticsApi.getBottlenecks(filterParams),
        analyticsApi.getResources(filterParams),
        analyticsApi.getShelters(filterParams),
        analyticsApi.getHealthcare(filterParams),
        analyticsApi.getVolunteers(filterParams),
        analyticsApi.getFleet(filterParams),
        analyticsApi.getReplanning(filterParams),
        analyticsApi.getComparison(compDimension, filterParams),
        analyticsApi.getDecisionSupport(filterParams),
      ]);

      setOverview(ovRes);
      setMilestones(msRes);
      setBottlenecks(bnRes);
      setResources(resRes);
      setShelters(shlRes);
      setHealthcare(hcRes);
      setVolunteers(volRes);
      setFleet(fltRes);
      setReplanning(repRes);
      setComparison(compRes);
      setDecisionSupport(dsRes);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load authoritative emergency analytics.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadAllAnalytics();
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-red-600">
              <BarChart3 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 text-xs font-bold rounded-md bg-red-600 text-white uppercase tracking-wider">
                  OPERATIONAL INTELLIGENCE
                </span>
                <span className="text-xs font-semibold text-slate-500">
                  Authoritative MongoDB Atlas Intelligence
                </span>
              </div>
              <h1 className="text-xl font-black text-slate-900 tracking-tight mt-0.5">
                Emergency Intelligence, Analytics & Decision Support
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={loading || refreshing}
              className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition-all flex items-center gap-2 border border-slate-300 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh Analytics
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="mt-5 pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-[11px] font-bold text-slate-500 uppercase block mb-1">Time Horizon</label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as AnalyticsTimeRange)}
              className="w-full bg-slate-50 border border-slate-200 text-xs font-medium rounded-lg p-2 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-red-500 cursor-pointer"
            >
              <option value="24h">Last 24 Hours</option>
              <option value="7d">Last 7 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="all">All-Time Live Data</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold text-slate-500 uppercase block mb-1">Disaster Type</label>
            <select
              value={disasterType}
              onChange={(e) => setDisasterType(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-xs font-medium rounded-lg p-2 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-red-500 cursor-pointer"
            >
              <option value="">All Disaster Types</option>
              <option value="Cyclone">Cyclone</option>
              <option value="Flood">Flood</option>
              <option value="Earthquake">Earthquake</option>
              <option value="Fire">Fire</option>
              <option value="Landslide">Landslide</option>
              <option value="Building Collapse">Building Collapse</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold text-slate-500 uppercase block mb-1">Severity Filter</label>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-xs font-medium rounded-lg p-2 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-red-500 cursor-pointer"
            >
              <option value="">All Severity Levels</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold text-slate-500 uppercase block mb-1">Operational Zone</label>
            <input
              type="text"
              placeholder="e.g. Ward 4 / Coastal Zone"
              value={zone}
              onChange={(e) => setZone(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 text-xs font-medium rounded-lg p-2 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-red-500"
            />
          </div>
        </div>
      </div>

      {/* KPI Ribbon with Interactive Drill-Downs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div
          onClick={() => setActiveTab('overview')}
          className="group bg-white p-4 rounded-xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider group-hover:text-slate-700 transition-colors">Total Reports</span>
          <span className="text-2xl font-black text-slate-900 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {overview ? overview.total_reports : '-'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
            <span>Citizen Intake</span>
            <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setActiveTab('overview')}
          className="group bg-white p-4 rounded-xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider group-hover:text-slate-700 transition-colors">Active Situations</span>
          <span className="text-2xl font-black text-slate-900 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {overview ? overview.active_situations : '-'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
            <span>{overview ? `${overview.resolved_situations} Resolved` : '-'}</span>
            <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setActiveTab('decision-support')}
          className="group bg-white p-4 rounded-xl border border-red-100 bg-red-50/20 shadow-xs hover:shadow-md hover:border-red-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-red-500 block tracking-wider group-hover:text-red-700 transition-colors">Critical Emergencies</span>
          <span className="text-2xl font-black text-red-600 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {overview ? overview.critical_incidents : '-'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-red-500/80 mt-0.5">
            <span>Urgent Priority</span>
            <span className="text-red-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setActiveTab('milestones')}
          className="group bg-white p-4 rounded-xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider group-hover:text-slate-700 transition-colors">Avg Response Time</span>
          <span className="text-2xl font-black text-slate-900 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {overview?.avg_field_response_minutes.value !== null && overview?.avg_field_response_minutes.value !== undefined
              ? `${overview.avg_field_response_minutes.value}m`
              : 'N/A'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
            <span>{overview?.avg_field_response_minutes.sample_count ?? 0} samples</span>
            <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setActiveTab('fleet')}
          className="group bg-white p-4 rounded-xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider group-hover:text-slate-700 transition-colors">Task Completion</span>
          <span className="text-2xl font-black text-emerald-600 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {overview?.overall_task_completion_rate !== null && overview?.overall_task_completion_rate !== undefined
              ? `${overview.overall_task_completion_rate}%`
              : 'N/A'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
            <span>Field Execution</span>
            <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>

        <div
          onClick={() => setActiveTab('decision-support')}
          className="group bg-white p-4 rounded-xl border border-amber-100 bg-amber-50/20 shadow-xs hover:shadow-md hover:border-amber-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
        >
          <span className="text-[10px] uppercase font-bold text-amber-600 block tracking-wider group-hover:text-amber-800 transition-colors">Decision Signals</span>
          <span className="text-2xl font-black text-amber-600 mt-1 block group-hover:scale-105 transition-transform origin-left">
            {decisionSupport ? decisionSupport.total_signals : '-'}
          </span>
          <div className="flex items-center justify-between text-[10px] text-amber-600/80 mt-0.5">
            <span>Advisory Alerts</span>
            <span className="text-amber-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex border-b border-slate-200 gap-2 overflow-x-auto pb-1">
        {[
          { id: 'overview', label: 'Overview & Highlights', icon: BarChart3 },
          { id: 'milestones', label: 'Response Timeline & Milestones', icon: Clock },
          { id: 'capacity', label: 'Resources & Capacities', icon: Package },
          { id: 'fleet', label: 'Responders & Fleet', icon: Users },
          { id: 'replanning', label: 'Replanning & Bottlenecks', icon: Layers },
          { id: 'decision-support', label: 'Decision Support Engine', icon: Sparkles },
          { id: 'comparison', label: 'Cross-Incident Comparison', icon: TrendingUp },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer shrink-0 ${
                isActive
                  ? 'bg-red-50 text-red-700 border border-red-200 shadow-xs'
                  : 'bg-white text-slate-600 border border-transparent hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-red-600' : 'text-slate-400'}`} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Main Tab Panels */}
      {loading ? (
        <div className="py-24 text-center space-y-3 bg-white rounded-2xl border border-slate-200">
          <div className="w-8 h-8 border-3 border-red-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-semibold text-slate-600">Calculating authoritative intelligence from MongoDB...</p>
        </div>
      ) : error ? (
        <div className="p-6 rounded-2xl bg-red-50 border border-red-200 text-red-700 flex items-center gap-3">
          <AlertCircle className="w-6 h-6 shrink-0" />
          <span className="text-sm font-medium">{error}</span>
        </div>
      ) : (
        <>
          {/* TAB 1: OVERVIEW */}
          {activeTab === 'overview' && overview && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left 2 Cols: Milestone Summary Cards */}
              <div className="lg:col-span-2 space-y-4">
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                  <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <Clock className="w-4 h-4 text-red-600" />
                    Key Operational Response Times
                  </h3>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs font-medium text-slate-500">Intake → Acknowledgement</span>
                      <span className="text-xl font-bold text-slate-900 block mt-1">
                        {overview.avg_acknowledgement_minutes.value !== null
                          ? `${overview.avg_acknowledgement_minutes.value} min`
                          : 'No data'}
                      </span>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        Sample size: {overview.avg_acknowledgement_minutes.sample_count} records
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs font-medium text-slate-500">Plan Generation Latency</span>
                      <span className="text-xl font-bold text-slate-900 block mt-1">
                        {overview.avg_planning_minutes.value !== null
                          ? `${overview.avg_planning_minutes.value} min`
                          : 'No data'}
                      </span>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        Multi-agent orchestrations: {overview.avg_planning_minutes.sample_count}
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs font-medium text-slate-500">Officer Plan Approval</span>
                      <span className="text-xl font-bold text-slate-900 block mt-1">
                        {overview.avg_approval_minutes.value !== null
                          ? `${overview.avg_approval_minutes.value} min`
                          : 'No data'}
                      </span>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        Human-in-the-loop review: {overview.avg_approval_minutes.sample_count} plans
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs font-medium text-slate-500">Incident Resolution Time</span>
                      <span className="text-xl font-bold text-slate-900 block mt-1">
                        {overview.avg_incident_resolution_hours.value !== null
                          ? `${overview.avg_incident_resolution_hours.value} hrs`
                          : 'No data'}
                      </span>
                      <span className="text-[10px] text-slate-400 block mt-0.5">
                        Resolved emergencies: {overview.avg_incident_resolution_hours.sample_count}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Detected Bottlenecks Quick List */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                      Active Response Bottlenecks ({bottlenecks.length})
                    </h3>
                    <button
                      onClick={() => setActiveTab('replanning')}
                      className="text-xs font-bold text-red-600 hover:text-red-700 cursor-pointer"
                    >
                      View All →
                    </button>
                  </div>

                  {bottlenecks.length === 0 ? (
                    <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                      <span>Zero systemic bottlenecks detected. Operational milestones are performing within nominal thresholds.</span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {bottlenecks.slice(0, 3).map((bn, idx) => (
                        <div key={idx} className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-start gap-3">
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md uppercase shrink-0 mt-0.5 ${
                            bn.severity === 'CRITICAL' ? 'bg-red-600 text-white' : 'bg-amber-500 text-white'
                          }`}>
                            {bn.severity}
                          </span>
                          <div className="text-xs">
                            <span className="font-bold text-slate-900 block">{bn.title}</span>
                            <span className="text-slate-600">{bn.evidence}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Right Col: Top Decision Support Signals */}
              <div className="space-y-4">
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-purple-600" />
                      Decision Support Feed
                    </h3>
                    <button
                      onClick={() => setActiveTab('decision-support')}
                      className="text-xs font-bold text-red-600 hover:text-red-700 cursor-pointer"
                    >
                      View All ({decisionSupport?.total_signals || 0}) →
                    </button>
                  </div>

                  {decisionSupport && decisionSupport.signals.length > 0 ? (
                    <div className="space-y-3">
                      {decisionSupport.signals.slice(0, 4).map((sig) => (
                        <div
                          key={sig.signal_id}
                          className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold uppercase text-slate-400">{sig.domain}</span>
                            <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md ${
                              sig.severity === 'CRITICAL' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                            }`}>
                              {sig.severity}
                            </span>
                          </div>
                          <h4 className="text-xs font-bold text-slate-900">{sig.title}</h4>
                          <p className="text-[11px] text-slate-600">{sig.evidence}</p>
                          <div className="pt-1 text-[11px] text-blue-700 font-medium">
                            Action: {sig.recommended_action}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs text-center">
                      No active critical decision signals.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: MILESTONES */}
          {activeTab === 'milestones' && milestones && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-6">
              <div>
                <h3 className="text-base font-bold text-slate-900">End-to-End Response Milestones Timeline</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Calculated from genuine timestamp transitions across {milestones.total_samples} total transition samples.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { title: '1. Citizen Intake → Acknowledgement', data: milestones.intake_to_acknowledgement },
                  { title: '2. Acknowledgement → Situation Fusion', data: milestones.acknowledgement_to_situation },
                  { title: '3. Situation → Coordination Plan Generated', data: milestones.situation_to_plan_generation },
                  { title: '4. Plan Generation → Officer Approval', data: milestones.plan_generation_to_officer_approval },
                  { title: '5. Officer Approval → Task Assignment', data: milestones.approval_to_task_assignment },
                  { title: '6. Task Assignment → Field Responder Start', data: milestones.assignment_to_field_start },
                  { title: '7. Field Execution → Task Completed', data: milestones.field_start_to_completion },
                  { title: '8. Incident Creation → Resolution', data: milestones.incident_creation_to_resolution },
                ].map((item, idx) => (
                  <div key={idx} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-slate-900">{item.title}</h4>
                      <span className="text-[10px] text-slate-400 font-semibold">
                        {item.data.sample_count} samples
                      </span>
                    </div>

                    {item.data.sample_count > 0 ? (
                      <div className="grid grid-cols-4 gap-2 pt-1">
                        <div className="bg-white p-2 rounded-lg border border-slate-200 text-center">
                          <span className="text-[10px] text-slate-400 block uppercase font-bold">Min</span>
                          <span className="text-xs font-bold text-slate-800">{item.data.min_minutes}m</span>
                        </div>
                        <div className="bg-white p-2 rounded-lg border border-slate-200 text-center">
                          <span className="text-[10px] text-slate-400 block uppercase font-bold">Median</span>
                          <span className="text-xs font-bold text-slate-800">{item.data.median_minutes}m</span>
                        </div>
                        <div className="bg-white p-2 rounded-lg border border-red-200 bg-red-50/30 text-center">
                          <span className="text-[10px] text-red-600 block uppercase font-bold">Avg</span>
                          <span className="text-xs font-bold text-red-700">{item.data.avg_minutes}m</span>
                        </div>
                        <div className="bg-white p-2 rounded-lg border border-slate-200 text-center">
                          <span className="text-[10px] text-slate-400 block uppercase font-bold">Max</span>
                          <span className="text-xs font-bold text-slate-800">{item.data.max_minutes}m</span>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3 rounded-lg bg-white border border-slate-200 text-[11px] text-slate-400 italic">
                        Insufficient data for this milestone in the selected range.
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: CAPACITY & UTILIZATION */}
          {activeTab === 'capacity' && (
            <div className="space-y-6">
              {/* Resources */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">Resource Stockpile & Inventory Utilization</h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Aggregated directly from MongoDB resources collection.
                    </p>
                  </div>
                  <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-lg border border-emerald-200">
                    Overall Utilization: {resources?.overall_utilization_rate || 0}%
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 uppercase font-bold text-[10px]">
                        <th className="py-2.5 px-3">Category</th>
                        <th className="py-2.5 px-3">Total Stock</th>
                        <th className="py-2.5 px-3">Allocated</th>
                        <th className="py-2.5 px-3">Consumed</th>
                        <th className="py-2.5 px-3">Remaining</th>
                        <th className="py-2.5 px-3">Utilization</th>
                        <th className="py-2.5 px-3">Shortages</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                      {resources?.categories.map((cat) => (
                        <tr key={cat.category_name} className="hover:bg-slate-50">
                          <td className="py-2.5 px-3 font-bold text-slate-900">{cat.category_name}</td>
                          <td className="py-2.5 px-3">{cat.total_stock}</td>
                          <td className="py-2.5 px-3 text-blue-600">{cat.total_allocated}</td>
                          <td className="py-2.5 px-3 text-purple-600">{cat.total_consumed}</td>
                          <td className="py-2.5 px-3 text-emerald-600">{cat.remaining_available}</td>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded-md bg-slate-100 font-bold">
                              {cat.utilization_percentage}%
                            </span>
                          </td>
                          <td className="py-2.5 px-3">
                            {cat.shortage_count > 0 ? (
                              <span className="px-2 py-0.5 rounded-md bg-red-100 text-red-700 font-bold">
                                {cat.shortage_count}
                              </span>
                            ) : (
                              <span className="text-slate-400">0</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Shelters & Healthcare Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Shelters */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                  <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <Home className="w-4 h-4 text-blue-600" />
                    Shelter Capacities & Occupancy
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Total Capacity</span>
                      <span className="text-lg font-bold text-slate-900">{shelters?.total_capacity_beds || 0} Beds</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Current Occupancy</span>
                      <span className="text-lg font-bold text-slate-900">{shelters?.current_occupancy_beds || 0} Beds</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Occupancy Rate</span>
                      <span className="text-lg font-bold text-blue-600">{shelters?.occupancy_rate_percentage || 0}%</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Saturated Shelters</span>
                      <span className="text-lg font-bold text-amber-600">{shelters?.full_shelters_count || 0}</span>
                    </div>
                  </div>
                </div>

                {/* Healthcare */}
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                  <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <HeartPulse className="w-4 h-4 text-red-600" />
                    Hospital & Critical Care Beds
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Beds Available</span>
                      <span className="text-lg font-bold text-slate-900">{healthcare?.total_beds_available || 0}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Beds Occupied</span>
                      <span className="text-lg font-bold text-slate-900">{healthcare?.total_beds_occupied || 0}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">ICU Beds Available</span>
                      <span className="text-lg font-bold text-emerald-600">{healthcare?.icu_beds_available || 0}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                      <span className="text-xs text-slate-500 block">Evacuation Demand</span>
                      <span className="text-lg font-bold text-purple-600">{healthcare?.patient_evacuation_demand || 0}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: RESPONDERS & FLEET */}
          {activeTab === 'fleet' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Volunteers */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <Users className="w-4 h-4 text-blue-600" />
                  Volunteer Responder Network
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Registered Responders</span>
                    <span className="text-lg font-bold text-slate-900">{volunteers?.registered_volunteers || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Active Status</span>
                    <span className="text-lg font-bold text-emerald-600">{volunteers?.active_responders || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Missions Assigned</span>
                    <span className="text-lg font-bold text-slate-900">{volunteers?.total_missions_assigned || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Completion Rate</span>
                    <span className="text-lg font-bold text-emerald-600">{volunteers?.completion_rate_percentage || 0}%</span>
                  </div>
                </div>

                <div className="pt-2">
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                    Skill Demand Breakdown
                  </h4>
                  <div className="space-y-1.5">
                    {volunteers?.skill_demand_breakdown &&
                      Object.entries(volunteers.skill_demand_breakdown).map(([skill, count]) => (
                        <div key={skill} className="flex items-center justify-between text-xs p-2 rounded-lg bg-slate-50">
                          <span className="text-slate-700 font-medium">{skill}</span>
                          <span className="font-bold text-slate-900">{count} missions</span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>

              {/* Fleet */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <Truck className="w-4 h-4 text-purple-600" />
                  Fleet & Transport Performance
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Total Vehicles</span>
                    <span className="text-lg font-bold text-slate-900">{fleet?.total_vehicles || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Active Missions</span>
                    <span className="text-lg font-bold text-purple-600">{fleet?.active_fleet_missions || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Fleet Utilization</span>
                    <span className="text-lg font-bold text-blue-600">{fleet?.fleet_utilization_rate || 0}%</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Route Disruptions</span>
                    <span className="text-lg font-bold text-amber-600">{fleet?.blocked_routes_reported || 0}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: REPLANNING & BOTTLENECKS */}
          {activeTab === 'replanning' && (
            <div className="space-y-6">
              {/* Replanning Stats */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <Layers className="w-4 h-4 text-red-600" />
                  Dynamic Replanning Dynamics
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Monitoring Events</span>
                    <span className="text-xl font-bold text-slate-900">{replanning?.total_monitoring_events || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Impactful Events</span>
                    <span className="text-xl font-bold text-amber-600">{replanning?.impactful_events_detected || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Total Replans</span>
                    <span className="text-xl font-bold text-red-600">{replanning?.total_replans_executed || 0}</span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-xs text-slate-500 block">Avg Replans/Sit</span>
                    <span className="text-xl font-bold text-slate-900">{replanning?.avg_replans_per_situation || 0}</span>
                  </div>
                </div>
              </div>

              {/* Detected Bottlenecks Cards */}
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  Identified Response Bottlenecks ({bottlenecks.length})
                </h3>

                {bottlenecks.length === 0 ? (
                  <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
                    No active bottlenecks detected across the selected time horizon.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {bottlenecks.map((bn, idx) => (
                      <div key={idx} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md uppercase ${
                            bn.severity === 'CRITICAL' ? 'bg-red-600 text-white' : 'bg-amber-500 text-white'
                          }`}>
                            {bn.severity}
                          </span>
                          <span className="text-[10px] text-slate-400 font-bold uppercase">{bn.affected_domain}</span>
                        </div>
                        <h4 className="text-xs font-bold text-slate-900">{bn.title}</h4>
                        <p className="text-[11px] text-slate-600">{bn.description}</p>
                        <div className="p-2 rounded-lg bg-white border border-slate-200 text-[11px] text-slate-800">
                          <span className="font-bold text-slate-500 block text-[9px] uppercase">Empirical Evidence</span>
                          {bn.evidence}
                        </div>
                        <div className="text-[11px] text-blue-700 font-medium">
                          Recommendation: {bn.actionable_recommendation}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 6: DECISION SUPPORT */}
          {activeTab === 'decision-support' && decisionSupport && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900">Deterministic Operational Decision Support</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Real-time advisory alerts with empirical evidence and recommended actions.
                  </p>
                </div>
                <span className="text-xs font-bold px-3 py-1 rounded-lg bg-purple-50 text-purple-700 border border-purple-200">
                  {decisionSupport.total_signals} Advisory Signals
                </span>
              </div>

              <div className="space-y-3">
                {decisionSupport.signals.map((sig) => (
                  <div
                    key={sig.signal_id}
                    className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2 hover:border-slate-300 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">{sig.domain}</span>
                      <span className={`px-2.5 py-0.5 text-xs font-bold rounded-md ${
                        sig.severity === 'CRITICAL'
                          ? 'bg-red-600 text-white'
                          : sig.severity === 'WARNING'
                          ? 'bg-amber-500 text-white'
                          : 'bg-blue-600 text-white'
                      }`}>
                        {sig.severity}
                      </span>
                    </div>
                    <h4 className="text-sm font-bold text-slate-900">{sig.title}</h4>
                    <p className="text-xs text-slate-600">{sig.evidence}</p>
                    <div className="p-3 rounded-lg bg-blue-50/60 border border-blue-200 text-xs text-blue-900 font-medium flex items-start gap-2">
                      <Sparkles className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <span>{sig.recommended_action}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 7: COMPARISON */}
          {activeTab === 'comparison' && comparison && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-base font-bold text-slate-900">Cross-Incident Comparison Matrix</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Compare performance and response speed across operational dimensions.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-500">Dimension:</span>
                  <select
                    value={compDimension}
                    onChange={(e) => setCompDimension(e.target.value as any)}
                    className="bg-slate-50 border border-slate-200 text-xs font-medium rounded-lg p-2 text-slate-800"
                  >
                    <option value="emergency_type">Disaster Category</option>
                    <option value="severity_level">Severity Level</option>
                    <option value="zone">Operational Zone</option>
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 uppercase font-bold text-[10px]">
                      <th className="py-2.5 px-3">Dimension Group</th>
                      <th className="py-2.5 px-3">Incidents Count</th>
                      <th className="py-2.5 px-3">Avg Response</th>
                      <th className="py-2.5 px-3">Avg Resolution</th>
                      <th className="py-2.5 px-3">Avg Replans</th>
                      <th className="py-2.5 px-3">Task Completion</th>
                      <th className="py-2.5 px-3">Population Impacted</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                    {comparison.groups.map((grp) => (
                      <tr key={grp.group_name} className="hover:bg-slate-50">
                        <td className="py-2.5 px-3 font-bold text-slate-900">{grp.group_name}</td>
                        <td className="py-2.5 px-3">{grp.incident_count}</td>
                        <td className="py-2.5 px-3">{grp.avg_response_minutes ? `${grp.avg_response_minutes}m` : '-'}</td>
                        <td className="py-2.5 px-3">{grp.avg_resolution_minutes ? `${grp.avg_resolution_minutes}m` : '-'}</td>
                        <td className="py-2.5 px-3">{grp.avg_replans}</td>
                        <td className="py-2.5 px-3 text-emerald-600 font-bold">{grp.task_completion_rate}%</td>
                        <td className="py-2.5 px-3 text-purple-600 font-bold">{grp.total_population_impacted}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Post-Incident Intelligence Debrief Modal */}
      {selectedDebriefSituationId && (
        <PostIncidentIntelligenceModal
          situationId={selectedDebriefSituationId}
          isOpen={!!selectedDebriefSituationId}
          onClose={() => setSelectedDebriefSituationId(null)}
        />
      )}
    </div>
  );
};
