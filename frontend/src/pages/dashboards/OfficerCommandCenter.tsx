import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OperationalHeader } from '../../components/layout/OperationalHeader';
import { CommandSidebar } from '../../components/layout/CommandSidebar';
import { ReportDetailsModal } from '../../components/officer/ReportDetailsModal';
import { SituationDetailsModal } from '../../components/officer/SituationDetailsModal';
import { SituationListPanel } from '../../components/officer/SituationListPanel';
import { CoordinationPlanModal } from '../../components/officer/CoordinationPlanModal';
import { LiveMonitoringPanel } from '../../components/officer/LiveMonitoringPanel';
import { WhatIfSimulationPanel } from '../../components/officer/WhatIfSimulationPanel';
import { ResponseOperationsPanel } from '../../components/officer/ResponseOperationsPanel';
import { SensorManagementPanel } from '../../components/officer/SensorManagementPanel';
import { EmergencyAnalyticsWorkspace } from '../../components/analytics/EmergencyAnalyticsWorkspace';
import { CriticalAlertBanner } from '../../components/notifications/CriticalAlertBanner';

import {
  getOfficerReportStats,
  getOfficerReports,
  listResources,
  getResourceStats,
  listOfficerVolunteers,
  listOfficerAuditLogs,
} from '../../services/api';
import type {
  OfficerReportStatsResponse,
  OfficerReportDetailResponse,
  ResourceResponse,
  ResourceStatsResponse,
  UserResponse,
  ResourceType,
} from '../../types';
import {
  AlertTriangle,
  Map,
  RefreshCw,
  Shield,
  Search,
  CheckCircle,
  Activity,
  ChevronLeft,
  ChevronRight,
  Eye,
  MapPin,
  Sparkles,
  Layers,
  Truck,
  Home,
  Users,
  ClipboardList,
  Settings,
  Phone,
  Mail,
  BarChart3,
  Camera,
  ShieldAlert,
} from 'lucide-react';

export const OfficerCommandCenter: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { reportId: routeReportId } = useParams<{ reportId?: string }>();

  const isAnalyticsRoute = window.location.pathname.includes('analytics');
  const initialTab = searchParams.get('tab') || (isAnalyticsRoute ? 'analytics' : 'command-center');
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const [viewMode, setViewMode] = useState<'reports' | 'situations'>('reports');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Real KPI stats for reports
  const [stats, setStats] = useState<OfficerReportStatsResponse>({
    total_incoming: 0,
    acknowledged: 0,
    under_assessment: 0,
    action_required: 0,
    resolved: 0,
    total_reports: 0,
  });

  // Report Inbox state
  const [reports, setReports] = useState<OfficerReportDetailResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Filters & Search for Reports
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [priorityFilter, setPriorityFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Resource Tab State
  const [resources, setResources] = useState<ResourceResponse[]>([]);
  const [resourceStats, setResourceStats] = useState<ResourceStatsResponse | null>(null);
  const [resourceTypeFilter, setResourceTypeFilter] = useState<string>('ALL');
  const [resourceSearch, setResourceSearch] = useState<string>('');
  const [resourceLoading, setResourceLoading] = useState<boolean>(false);

  // Shelters Tab State
  const [shelters, setShelters] = useState<ResourceResponse[]>([]);
  const [shelterLoading, setShelterLoading] = useState<boolean>(false);

  // Volunteers Tab State
  const [volunteers, setVolunteers] = useState<UserResponse[]>([]);
  const [volunteersLoading, setVolunteersLoading] = useState<boolean>(false);

  // Audit Logs Tab State
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditLoading, setAuditLoading] = useState<boolean>(false);

  // Selected Report Modal
  const [selectedReportId, setSelectedReportId] = useState<string | null>(
    routeReportId || searchParams.get('report') || null
  );

  // Selected Situation Modal
  const [selectedSituationId, setSelectedSituationId] = useState<string | null>(null);

  // Selected Situation for AI Multi-Agent Coordination Plan
  const [selectedCoordinationSituation, setSelectedCoordinationSituation] = useState<{
    id: string;
    title: string;
    emergencyType: string;
  } | null>(null);

  // Fetch Reports and Dashboard Stats
  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, reportsData] = await Promise.all([
        getOfficerReportStats(),
        getOfficerReports({
          status: statusFilter || (activeTab === 'incidents' ? 'RECEIVED' : undefined),
          priority: priorityFilter || undefined,
          emergency_type: typeFilter || undefined,
          search: searchTerm.trim() || undefined,
          page: currentPage,
          limit: 15,
        }),
      ]);

      setStats(statsData);
      setReports(reportsData.items || []);
      setTotalCount(reportsData.total || 0);
      setTotalPages(reportsData.total_pages || 1);
    } catch (err) {
      console.warn('Failed to load emergency officer operations data:', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, priorityFilter, typeFilter, searchTerm, currentPage, activeTab]);

  // Fetch Resources Data
  const fetchResourcesData = useCallback(async () => {
    setResourceLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        listResources({
          resource_type: resourceTypeFilter !== 'ALL' ? (resourceTypeFilter as ResourceType) : undefined,
          search: resourceSearch.trim() || undefined,
          limit: 50,
        }),
        getResourceStats(),
      ]);
      setResources(listRes.items || []);
      setResourceStats(statsRes);
    } catch (err) {
      console.warn('Failed to load resources for officer:', err);
    } finally {
      setResourceLoading(false);
    }
  }, [resourceTypeFilter, resourceSearch]);

  // Fetch Shelters Data
  const fetchSheltersData = useCallback(async () => {
    setShelterLoading(true);
    try {
      const res = await listResources({ resource_type: 'Shelter' as ResourceType, limit: 50 });
      setShelters(res.items || []);
    } catch (err) {
      console.warn('Failed to load shelters for officer:', err);
    } finally {
      setShelterLoading(false);
    }
  }, []);

  // Fetch Volunteers Data
  const fetchVolunteersData = useCallback(async () => {
    setVolunteersLoading(true);
    try {
      const data = await listOfficerVolunteers();
      setVolunteers(data || []);
    } catch (err) {
      console.warn('Failed to load volunteers for officer:', err);
    } finally {
      setVolunteersLoading(false);
    }
  }, []);

  // Fetch Audit Logs Data
  const fetchAuditLogsData = useCallback(async () => {
    setAuditLoading(true);
    try {
      const data = await listOfficerAuditLogs(50);
      setAuditLogs(data || []);
    } catch (err) {
      console.warn('Failed to load audit logs for officer:', err);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  // Sync tab with URL search parameter
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [searchParams]);

  useEffect(() => {
    if (activeTab === 'command-center' || activeTab === 'reports' || activeTab === 'incidents') {
      fetchDashboardData();
    } else if (activeTab === 'resources') {
      fetchResourcesData();
    } else if (activeTab === 'shelters') {
      fetchSheltersData();
    } else if (activeTab === 'volunteers') {
      fetchVolunteersData();
    } else if (activeTab === 'audit-log') {
      fetchAuditLogsData();
    }
  }, [activeTab, fetchDashboardData, fetchResourcesData, fetchSheltersData, fetchVolunteersData, fetchAuditLogsData]);

  // Auto-polling for reports in active command center view
  useEffect(() => {
    if (activeTab === 'command-center' || activeTab === 'reports' || activeTab === 'incidents') {
      const interval = setInterval(() => {
        fetchDashboardData();
      }, 15000);
      return () => clearInterval(interval);
    }
  }, [activeTab, fetchDashboardData]);

  // Sync route param changes with modal
  useEffect(() => {
    if (routeReportId) {
      setSelectedReportId(routeReportId);
    }
  }, [routeReportId]);

  const handleOpenReport = (id: string) => {
    setSelectedReportId(id);
    const params = new URLSearchParams(searchParams);
    params.set('report', id);
    setSearchParams(params);
  };

  const handleCloseModal = () => {
    setSelectedReportId(null);
    const params = new URLSearchParams(searchParams);
    params.delete('report');
    setSearchParams(params);
  };

  const handleSidebarTabSelect = (tabId: string) => {
    if (tabId === 'live-map') {
      navigate('/operations/officer/map');
    } else {
      setActiveTab(tabId);
      const params = new URLSearchParams(searchParams);
      params.set('tab', tabId);
      setSearchParams(params);
    }
  };

  const getCitizenImpactBadgeClass = (impact?: string) => {
    switch (impact) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200 font-bold';
      case 'HIGH':
        return 'bg-orange-50 text-orange-700 border-orange-200 font-semibold';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-700 border-amber-200 font-medium';
      case 'LOW':
        return 'bg-blue-50 text-blue-700 border-blue-200 font-medium';
      default:
        return 'bg-slate-50 text-slate-500 border-slate-200 font-medium';
    }
  };

  const getPriorityBadgeClass = (priority?: string) => {
    switch (priority) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-800 border-red-300 font-bold';
      case 'HIGH':
        return 'bg-orange-100 text-orange-800 border-orange-300 font-bold';
      case 'MEDIUM':
        return 'bg-amber-100 text-amber-800 border-amber-300 font-medium';
      case 'LOW':
        return 'bg-blue-100 text-blue-800 border-blue-300 font-medium';
      default:
        return 'bg-slate-100 text-slate-600 border-slate-300 font-medium';
    }
  };

  const getStatusBadgeClass = (status?: string) => {
    switch (status) {
      case 'RECEIVED':
        return 'bg-red-50 text-red-700 border-red-200 font-bold';
      case 'ACKNOWLEDGED':
        return 'bg-amber-50 text-amber-800 border-amber-200 font-semibold';
      case 'UNDER_ASSESSMENT':
        return 'bg-blue-50 text-blue-800 border-blue-200 font-semibold';
      case 'ACTION_REQUIRED':
        return 'bg-purple-50 text-purple-800 border-purple-200 font-semibold';
      case 'RESOLVED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const formatTimeAgo = (dateStr: string) => {
    const diffMs = Date.now() - new Date(dateStr).getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return 'Just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    return new Date(dateStr).toLocaleDateString();
  };

  const handleDeepLinkNavigation = (deepLink: {
    entity_type?: string | null;
    entity_id?: string | null;
    situation_id?: string | null;
    coordination_plan_id?: string | null;
    view_hint?: string | null;
  }) => {
    if (deepLink.view_hint === 'situations' || deepLink.entity_type === 'SITUATION') {
      setActiveTab('situations');
      if (deepLink.entity_id) setSelectedSituationId(deepLink.entity_id);
    } else if (deepLink.view_hint === 'reports' || deepLink.entity_type === 'CITIZEN_REPORT') {
      setActiveTab('command-center');
      if (deepLink.entity_id) setSelectedReportId(deepLink.entity_id);
    } else if (deepLink.view_hint === 'monitoring' || deepLink.entity_type === 'MONITORING_EVENT') {
      setActiveTab('monitoring');
    } else if (deepLink.view_hint === 'simulation' || deepLink.entity_type === 'SIMULATION') {
      setActiveTab('simulation');
    } else if (deepLink.view_hint === 'plans' || deepLink.entity_type === 'COORDINATION_PLAN') {
      setActiveTab('response-ops');
    } else if (deepLink.view_hint === 'resources') {
      setActiveTab('resources');
    }
  };

  return (
    <div className="relative h-screen max-h-screen bg-[#EEF2F6] text-slate-900 flex flex-col font-sans overflow-hidden">
      <TacticalBackground />

      {/* Operational Header */}
      <div className="flex-shrink-0 z-20">
        <OperationalHeader
          portalTitle="COMMAND CENTER"
          portalSubtitle="Watch Desk • Incident Command & Situation Awareness"
          onNavigateToEntity={handleDeepLinkNavigation}
          onToggleMobileMenu={() => setIsMobileSidebarOpen(true)}
        />

        {/* Critical Alert Banner (Real unacknowledged critical emergencies only) */}
        <CriticalAlertBanner
          onOpenNotification={(notif) => {
            if (notif.deep_link) handleDeepLinkNavigation(notif.deep_link);
          }}
        />
      </div>

      {/* Main Body */}
      <div className="flex-1 flex overflow-hidden min-h-0 z-10">
        {/* Command Sidebar (Desktop + Mobile Drawer) */}
        <CommandSidebar
          role="EMERGENCY_OFFICER"
          activeTab={activeTab}
          onSelectTab={handleSidebarTabSelect}
          className="hidden md:flex flex-shrink-0 w-64 h-full overflow-y-auto border-r border-slate-200/80 bg-white"
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
        />

        {/* Viewport Area */}
        <main className="flex-1 h-full overflow-y-auto p-3 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl mx-auto w-full">
          {/* Welcome & Live Status Hero */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 sm:p-6 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-red-50 border border-red-200 text-red-600 flex items-center justify-center flex-shrink-0 shadow-2xs">
                <Shield className="w-5 h-5 sm:w-6 sm:h-6" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                  <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
                    Emergency Officer Operations Console
                  </h1>
                  <span className="inline-flex items-center gap-1.5 text-[10px] sm:text-[11px] font-bold text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse" />
                    LIVE OPERATIONAL FEED
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Duty Watch Officer: <strong className="text-slate-800">{user?.full_name || 'Emergency Officer'}</strong>{user?.email ? ` (${user.email})` : ''}{user?.badge_number ? <> • Badge: <span className="font-semibold text-slate-700">{user.badge_number}</span></> : null}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 sm:gap-2.5 w-full md:w-auto">
              <button
                onClick={() => handleSidebarTabSelect('analytics')}
                className={`inline-flex items-center justify-center gap-2 px-3.5 sm:px-4 py-2 rounded-xl text-xs font-semibold shadow-xs transition-all w-full sm:w-auto cursor-pointer min-h-[40px] touch-manipulation ${
                  activeTab === 'analytics'
                    ? 'bg-red-600 text-white border border-red-600 shadow-sm'
                    : 'bg-white border border-slate-200 hover:bg-red-50 hover:text-red-700 text-slate-700'
                }`}
              >
                <BarChart3 className={`w-3.5 h-3.5 ${activeTab === 'analytics' ? 'text-white' : 'text-red-600'}`} />
                <span>Emergency Intelligence</span>
              </button>
              <button
                onClick={() => navigate('/operations/officer/map')}
                className="inline-flex items-center justify-center gap-2 px-3.5 sm:px-4 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-xs transition-all w-full sm:w-auto cursor-pointer min-h-[40px] touch-manipulation"
              >
                <Map className="w-3.5 h-3.5 text-red-600" />
                <span>Open GIS Map</span>
              </button>
              <button
                onClick={() => {
                  setRefreshKey((k) => k + 1);
                  if (activeTab === 'resources') fetchResourcesData();
                  else if (activeTab === 'shelters') fetchSheltersData();
                  else if (activeTab === 'volunteers') fetchVolunteersData();
                  else if (activeTab === 'audit-log') fetchAuditLogsData();
                  else fetchDashboardData();
                }}
                disabled={loading || resourceLoading || shelterLoading || volunteersLoading || auditLoading}
                className="inline-flex items-center justify-center gap-2 px-3.5 sm:px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition-all w-full sm:w-auto cursor-pointer min-h-[40px] touch-manipulation"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading || resourceLoading || shelterLoading || volunteersLoading || auditLoading ? 'animate-spin' : ''}`} />
                <span>Refresh Live Data</span>
              </button>
            </div>
          </div>

          {/* Mobile / Tablet Horizontal Navigation Tabs */}
          <div className="flex md:hidden items-center gap-1.5 overflow-x-auto pb-2 border-b border-slate-200 no-scrollbar touch-scroll flex-nowrap">
            {[
              { id: 'command-center', label: 'Command' },
              { id: 'incidents', label: 'Incidents' },
              { id: 'reports', label: 'Reports' },
              { id: 'response-ops', label: 'Field Operations' },
              { id: 'live-monitoring', label: 'Live Monitoring' },
              { id: 'simulation', label: 'What-If Simulation' },
              { id: 'analytics', label: 'Emergency Intelligence' },
              { id: 'resources', label: 'Resources' },
              { id: 'shelters', label: 'Shelters' },
              { id: 'volunteers', label: 'Volunteers' },
              { id: 'audit-log', label: 'Audit Log' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleSidebarTabSelect(tab.id)}
                className={`px-3 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer min-h-[38px] flex-shrink-0 touch-manipulation ${
                  activeTab === tab.id
                    ? 'bg-red-600 text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* ========================================================================= */}
          {/* TAB 1: COMMAND CENTER / REPORTS / INCIDENTS */}
          {/* ========================================================================= */}
          {(activeTab === 'command-center' || activeTab === 'reports' || activeTab === 'incidents') && (
            <>
              {/* 4 Real Backend KPI Cards with Drill-Down Interactions */}
              <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div
                  onClick={() => {
                    setViewMode('reports');
                    setStatusFilter('RECEIVED');
                    setCurrentPage(1);
                  }}
                  className="group p-5 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md hover:border-red-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-red-700 transition-colors">
                    <span>INCOMING REPORTS</span>
                    <span className="w-2 h-2 rounded-full bg-red-600 animate-pulse" />
                  </div>
                  <div className="my-2">
                    <div className="text-3xl font-extrabold text-red-600 group-hover:scale-105 transition-transform origin-left">
                      {stats.total_incoming}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>{stats.total_incoming > 0 ? 'Awaiting officer acknowledgement' : 'Zero unacknowledged reports'}</span>
                    <span className="text-red-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                  </div>
                </div>

                <div
                  onClick={() => {
                    setViewMode('reports');
                    setStatusFilter('ACKNOWLEDGED');
                    setCurrentPage(1);
                  }}
                  className="group p-5 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md hover:border-amber-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-amber-700 transition-colors">
                    <span>ACKNOWLEDGED</span>
                    <CheckCircle className="w-3.5 h-3.5 text-amber-600 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="my-2">
                    <div className="text-3xl font-extrabold text-amber-600 group-hover:scale-105 transition-transform origin-left">
                      {stats.acknowledged}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Logged & assigned to watch officer</span>
                    <span className="text-amber-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                  </div>
                </div>

                <div
                  onClick={() => {
                    setViewMode('reports');
                    setStatusFilter('UNDER_ASSESSMENT');
                    setCurrentPage(1);
                  }}
                  className="group p-5 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-blue-700 transition-colors">
                    <span>UNDER ASSESSMENT</span>
                    <Activity className="w-3.5 h-3.5 text-blue-600 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="my-2">
                    <div className="text-3xl font-extrabold text-blue-600 group-hover:scale-105 transition-transform origin-left">
                      {stats.under_assessment}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Field verification & situation triage</span>
                    <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                  </div>
                </div>

                <div
                  onClick={() => {
                    setViewMode('reports');
                    setStatusFilter('ACTION_REQUIRED');
                    setCurrentPage(1);
                  }}
                  className="group p-5 rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md hover:border-purple-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-purple-700 transition-colors">
                    <span>ACTION REQUIRED</span>
                    <AlertTriangle className="w-3.5 h-3.5 text-purple-600 group-hover:scale-110 transition-transform" />
                  </div>
                  <div className="my-2">
                    <div className="text-3xl font-extrabold text-purple-600 group-hover:scale-105 transition-transform origin-left">
                      {stats.action_required}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>Dispatch & field resource action needed</span>
                    <span className="text-purple-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                  </div>
                </div>
              </div>

              {/* View Mode Toggle: Incident Reports Feed vs Situation Intelligence */}
              <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
                <button
                  onClick={() => setViewMode('reports')}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                    viewMode === 'reports'
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <AlertTriangle className="w-4 h-4 text-red-500" />
                  <span>Emergency Reports Feed ({totalCount})</span>
                </button>
                <button
                  onClick={() => setViewMode('situations')}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                    viewMode === 'situations'
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <Sparkles className="w-4 h-4 text-blue-200" />
                  <Layers className="w-4 h-4" />
                  <span>Situation Intelligence (AI & Clusters)</span>
                </button>
              </div>

              {viewMode === 'situations' ? (
                <SituationListPanel
                  onSelectSituation={(situationId) => setSelectedSituationId(situationId)}
                  onOpenCoordination={(sit) =>
                    setSelectedCoordinationSituation({
                      id: sit.situation_id,
                      title: sit.title,
                      emergencyType: sit.emergency_type,
                    })
                  }
                />
              ) : (
                /* Search, Filter Toolbar & Reports Inbox */
                <div className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-xs space-y-4">
                  <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-5 h-5 text-red-600" />
                      <h2 className="text-base font-bold text-slate-900 tracking-tight">
                        {activeTab === 'incidents' ? 'ACTIVE UNRESOLVED INCIDENTS' : 'ACTIVE EMERGENCY REPORTS'}
                      </h2>
                      <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-semibold">
                        {totalCount} Total
                      </span>
                    </div>

                    {/* Filters Group */}
                    <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto">
                      <div className="relative flex-1 sm:w-60">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          value={searchTerm}
                          onChange={(e) => {
                            setSearchTerm(e.target.value);
                            setCurrentPage(1);
                          }}
                          placeholder="Search ID, name, location..."
                          className="w-full pl-9 pr-3 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500 bg-slate-50/50"
                        />
                      </div>

                      <select
                        value={statusFilter}
                        onChange={(e) => {
                          setStatusFilter(e.target.value);
                          setCurrentPage(1);
                        }}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 bg-slate-50/50 focus:outline-none focus:ring-2 focus:ring-red-500/30"
                      >
                        <option value="">All Statuses</option>
                        <option value="RECEIVED">Received</option>
                        <option value="ACKNOWLEDGED">Acknowledged</option>
                        <option value="UNDER_ASSESSMENT">Under Assessment</option>
                        <option value="ACTION_REQUIRED">Action Required</option>
                        <option value="RESOLVED">Resolved</option>
                      </select>

                      <select
                        value={priorityFilter}
                        onChange={(e) => {
                          setPriorityFilter(e.target.value);
                          setCurrentPage(1);
                        }}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 bg-slate-50/50 focus:outline-none focus:ring-2 focus:ring-red-500/30"
                      >
                        <option value="">All Priorities</option>
                        <option value="UNASSESSED">Unassessed</option>
                        <option value="LOW">Low</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="HIGH">High</option>
                        <option value="CRITICAL">Critical</option>
                      </select>

                      <select
                        value={typeFilter}
                        onChange={(e) => {
                          setTypeFilter(e.target.value);
                          setCurrentPage(1);
                        }}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 bg-slate-50/50 focus:outline-none focus:ring-2 focus:ring-red-500/30"
                      >
                        <option value="">All Types</option>
                        <option value="Flood">Flood</option>
                        <option value="Fire">Fire</option>
                        <option value="Medical Emergency">Medical Emergency</option>
                        <option value="Road Accident">Road Accident</option>
                        <option value="Cyclone / Storm">Cyclone / Storm</option>
                        <option value="Landslide">Landslide</option>
                        <option value="Building Collapse">Building Collapse</option>
                        <option value="Missing / Trapped Person">Missing / Trapped Person</option>
                        <option value="Other">Other</option>
                      </select>
                    </div>
                  </div>

                  {/* Reports List / Table */}
                  {loading && reports.length === 0 ? (
                    <div className="py-16 text-center space-y-2">
                      <RefreshCw className="w-6 h-6 text-red-600 animate-spin mx-auto" />
                      <p className="text-xs font-semibold text-slate-500">Loading incoming reports feed...</p>
                    </div>
                  ) : reports.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                            <th className="py-3 px-3">Report ID</th>
                            <th className="py-3 px-3">Emergency Type</th>
                            <th className="py-3 px-3">Location</th>
                            <th className="py-3 px-3">Citizen Impact</th>
                            <th className="py-3 px-3">Live Evidence</th>
                            <th className="py-3 px-3">Officer Priority</th>
                            <th className="py-3 px-3">Status</th>
                            <th className="py-3 px-3">Submitted</th>
                            <th className="py-3 px-3 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {reports.map((report) => (
                            <tr
                              key={report.report_id}
                              className="hover:bg-slate-50/80 transition-colors group cursor-pointer"
                              onClick={() => handleOpenReport(report.report_id)}
                            >
                              <td className="py-3.5 px-3 font-mono font-bold text-slate-900">
                                {report.report_id}
                              </td>
                              <td className="py-3.5 px-3">
                                <span className="font-semibold text-slate-800">
                                  {report.emergency_type}
                                </span>
                              </td>
                              <td className="py-3.5 px-3 max-w-xs truncate text-slate-600">
                                <div className="flex items-center gap-1.5 truncate">
                                  <MapPin className="w-3.5 h-3.5 text-red-600 flex-shrink-0" />
                                  <span className="truncate">
                                    {report.location.street_address || report.location.address || 'Address unavailable'}
                                  </span>
                                </div>
                              </td>
                              <td className="py-3.5 px-3">
                                <span className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${getCitizenImpactBadgeClass(report.citizen_impact_level)}`}>
                                  {report.citizen_impact_level || 'NOT_SURE'}
                                </span>
                              </td>
                              <td className="py-3.5 px-3">
                                {report.evidence?.validation_status === 'VERIFIED' ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-semibold" title="Live Camera Evidence Verified">
                                    <Camera className="w-3 h-3 text-emerald-600" />
                                    <span>Verified</span>
                                  </span>
                                ) : report.evidence?.validation_status === 'MISMATCH' ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-semibold" title="Location / Time Mismatch">
                                    <Camera className="w-3 h-3 text-amber-600" />
                                    <span>Mismatch</span>
                                  </span>
                                ) : report.evidence?.validation_status === 'FLAGGED' ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 text-[11px] font-semibold" title="Evidence Flagged / Duplicate">
                                    <ShieldAlert className="w-3 h-3 text-red-600" />
                                    <span>Flagged</span>
                                  </span>
                                ) : (
                                  <span className="text-slate-400 text-[11px] font-mono">
                                    None
                                  </span>
                                )}
                              </td>
                              <td className="py-3.5 px-3">
                                <span className={`px-2 py-0.5 rounded border text-[11px] ${getPriorityBadgeClass(report.priority)}`}>
                                  {report.priority || 'UNASSESSED'}
                                </span>
                              </td>
                              <td className="py-3.5 px-3">
                                <span className={`px-2.5 py-0.5 rounded border text-[11px] ${getStatusBadgeClass(report.status)}`}>
                                  {report.status}
                                </span>
                              </td>
                              <td className="py-3.5 px-3 text-slate-400 text-[11px] font-mono">
                                {formatTimeAgo(report.created_at)}
                              </td>
                              <td className="py-3.5 px-3 text-right">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleOpenReport(report.report_id);
                                  }}
                                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-100 group-hover:bg-red-600 group-hover:text-white text-slate-700 text-xs font-semibold transition-all shadow-2xs"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                  <span>View</span>
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="py-16 text-center space-y-3">
                      <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                        <Shield className="w-6 h-6" />
                      </div>
                      <h3 className="text-sm font-bold text-slate-800">NO EMERGENCY REPORTS</h3>
                      <p className="text-xs text-slate-500 max-w-sm mx-auto">
                        There are no emergency reports requiring attention. Incoming citizen dispatches will appear here instantly.
                      </p>
                    </div>
                  )}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between pt-4 border-t border-slate-100 text-xs text-slate-500">
                      <div>
                        Page <span className="font-semibold text-slate-800">{currentPage}</span> of{' '}
                        <span className="font-semibold text-slate-800">{totalPages}</span> ({totalCount} items)
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                          disabled={currentPage === 1}
                          className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                          disabled={currentPage === totalPages}
                          className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* ========================================================================= */}
          {/* TAB 2: SITUATION INTELLIGENCE (AI & INCIDENT FUSION) */}
          {/* ========================================================================= */}
          {activeTab === 'ai-intelligence' && (
            <div className="space-y-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-blue-600" />
                    <span>Situation Intelligence & Incident Fusion</span>
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Automated multi-report spatial-temporal clustering with explainable severity analysis and Emergency Officer authority.
                  </p>
                </div>
              </div>
              <SituationListPanel
                onSelectSituation={(situationId) => setSelectedSituationId(situationId)}
              />
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 3: RESOURCE COORDINATION */}
          {/* ========================================================================= */}
          {activeTab === 'resources' && (
            <div className="space-y-6">
              {/* Resource Stats */}
              {resourceStats && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <div
                    onClick={() => {
                      setResourceTypeFilter('ALL');
                      setResourceSearch('');
                    }}
                    className="group bg-white p-5 rounded-2xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-slate-800 transition-colors">
                      <span>TOTAL INVENTORY</span>
                      <Truck className="w-3.5 h-3.5 text-slate-400 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="text-2xl font-extrabold text-slate-900 mt-1 group-hover:scale-105 transition-transform origin-left">
                      {resourceStats.total_resources}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 mt-2">
                      <span>Registered assets</span>
                      <span className="text-slate-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => {
                      setResourceTypeFilter('ALL');
                    }}
                    className="group bg-white p-5 rounded-2xl border border-emerald-200 shadow-xs hover:shadow-md hover:border-emerald-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-emerald-700 uppercase tracking-wider group-hover:text-emerald-800 transition-colors">
                      <span>AVAILABLE SUPPLIES</span>
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-600 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="text-2xl font-extrabold text-emerald-700 mt-1 group-hover:scale-105 transition-transform origin-left">
                      {resourceStats.available_resources}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-emerald-600/80 mt-2">
                      <span>Mission ready</span>
                      <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => {
                      setResourceTypeFilter('ALL');
                    }}
                    className="group bg-white p-5 rounded-2xl border border-amber-200 shadow-xs hover:shadow-md hover:border-amber-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-amber-700 uppercase tracking-wider group-hover:text-amber-800 transition-colors">
                      <span>PARTIALLY AVAILABLE</span>
                      <Activity className="w-3.5 h-3.5 text-amber-600 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="text-2xl font-extrabold text-amber-700 mt-1 group-hover:scale-105 transition-transform origin-left">
                      {resourceStats.partially_available}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-amber-600/80 mt-2">
                      <span>In active allocation</span>
                      <span className="text-amber-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => {
                      setResourceTypeFilter('ALL');
                    }}
                    className="group bg-white p-5 rounded-2xl border border-slate-200 shadow-xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider group-hover:text-slate-800 transition-colors">
                      <span>SUPPLY CATEGORIES</span>
                      <Layers className="w-3.5 h-3.5 text-slate-400 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="text-2xl font-extrabold text-slate-800 mt-1 group-hover:scale-105 transition-transform origin-left">
                      {Object.keys(resourceStats.type_counts).length}
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400 mt-2">
                      <span>Distinct categories</span>
                      <span className="text-slate-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Resource Filter Toolbar */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Truck className="w-5 h-5 text-emerald-600" />
                    <h3 className="text-sm font-bold text-slate-900">EMERGENCY RESOURCE INVENTORY</h3>
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <div className="relative flex-1 sm:w-60">
                      <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        value={resourceSearch}
                        onChange={(e) => setResourceSearch(e.target.value)}
                        placeholder="Search resources..."
                        className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                      />
                    </div>
                    <select
                      value={resourceTypeFilter}
                      onChange={(e) => setResourceTypeFilter(e.target.value)}
                      className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 bg-white"
                    >
                      <option value="ALL">All Types</option>
                      <option value="Water">Water</option>
                      <option value="Food">Food</option>
                      <option value="Medicine">Medicine</option>
                      <option value="First Aid">First Aid</option>
                      <option value="Medical Equipment">Medical Equipment</option>
                      <option value="Rescue Equipment">Rescue Equipment</option>
                      <option value="Shelter">Shelter</option>
                      <option value="Transport">Transport</option>
                    </select>
                  </div>
                </div>

                {resourceLoading ? (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-600" />
                    Loading resource inventory...
                  </div>
                ) : resources.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase text-[10px]">
                          <th className="py-2.5 px-3">Resource ID</th>
                          <th className="py-2.5 px-3">Name</th>
                          <th className="py-2.5 px-3">Type</th>
                          <th className="py-2.5 px-3">Available / Total</th>
                          <th className="py-2.5 px-3">Status</th>
                          <th className="py-2.5 px-3">Location</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {resources.map((r) => (
                          <tr key={r.resource_id} className="hover:bg-slate-50">
                            <td className="py-3 px-3 font-mono font-bold text-slate-900">{r.resource_id}</td>
                            <td className="py-3 px-3 font-semibold text-slate-800">{r.name}</td>
                            <td className="py-3 px-3">
                              <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px] font-medium border border-emerald-200">
                                {r.resource_type}
                              </span>
                            </td>
                            <td className="py-3 px-3 font-mono font-bold text-slate-900">
                              {r.quantity_available} / {r.quantity_total} {r.unit}
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                                  r.status === 'AVAILABLE'
                                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                    : 'bg-amber-50 text-amber-700 border-amber-200'
                                }`}
                              >
                                {r.status}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-slate-600">
                              {r.location.address || r.location.city || 'District Depot'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    No resource inventory records found.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 4: SHELTER FACILITIES */}
          {/* ========================================================================= */}
          {activeTab === 'shelters' && (
            <div className="space-y-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Home className="w-5 h-5 text-blue-600" />
                    <span>Emergency Shelter Facilities</span>
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Designated evacuation shelters, relief camps, and community accommodation hubs.
                  </p>
                </div>
                <span className="text-xs font-mono font-bold px-2.5 py-1 bg-blue-50 text-blue-700 rounded-lg border border-blue-200">
                  {shelters.length} Facilities Active
                </span>
              </div>

              {shelterLoading ? (
                <div className="py-12 text-center text-slate-400 text-xs">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                  Loading shelter facilities...
                </div>
              ) : shelters.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {shelters.map((s) => (
                    <div key={s.resource_id} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold font-mono text-slate-900">{s.resource_id}</span>
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                          {s.status}
                        </span>
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">{s.name}</h4>
                      <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 text-xs space-y-1 text-slate-600">
                        <div>
                          Capacity: <strong>{s.quantity_available} / {s.quantity_total} {s.unit}</strong>
                        </div>
                        <div>
                          Location: <span>{s.location.address || s.location.city || 'District Center'}</span>
                        </div>
                        {s.contact && <div>Contact: <span>{s.contact}</span></div>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center text-slate-400 text-xs">
                  No emergency shelters registered in current active zone.
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 5: VOLUNTEER NETWORK */}
          {/* ========================================================================= */}
          {activeTab === 'volunteers' && (
            <div className="space-y-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Users className="w-5 h-5 text-blue-600" />
                    <span>Volunteer Responder Network</span>
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Verified community volunteer responders available for on-ground assistance and relief distribution.
                  </p>
                </div>
                <span className="text-xs font-mono font-bold px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-lg border border-emerald-200">
                  {volunteers.length} Responders Registered
                </span>
              </div>

              {volunteersLoading ? (
                <div className="py-12 text-center text-slate-400 text-xs">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                  Loading volunteer roster...
                </div>
              ) : volunteers.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {volunteers.map((v) => (
                    <div key={v.id} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-900">{v.full_name}</span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {v.is_active ? 'ACTIVE' : 'INACTIVE'}
                        </span>
                      </div>
                      <div className="text-xs text-slate-600 space-y-1">
                        <div className="flex items-center gap-1.5">
                          <Phone className="w-3.5 h-3.5 text-slate-400" />
                          <span>{v.phone}</span>
                        </div>
                        {v.email && (
                          <div className="flex items-center gap-1.5">
                            <Mail className="w-3.5 h-3.5 text-slate-400" />
                            <span>{v.email}</span>
                          </div>
                        )}
                        {v.volunteer_profile?.zone_or_district && (
                          <div className="flex items-center gap-1.5">
                            <MapPin className="w-3.5 h-3.5 text-slate-400" />
                            <span>District/Zone: {v.volunteer_profile.zone_or_district}</span>
                          </div>
                        )}
                      </div>
                      {v.volunteer_profile?.skills && v.volunteer_profile.skills.length > 0 && (
                        <div className="pt-2 border-t border-slate-100 flex flex-wrap gap-1">
                          {v.volunteer_profile.skills.map((s: string, idx: number) => (
                            <span key={idx} className="text-[10px] font-medium px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center text-slate-400 text-xs">
                  No community volunteers registered in database.
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 6: RESPONSE OPERATIONS & ACTIVE PLANS (PHASE 5/6) */}
          {/* ========================================================================= */}
          {activeTab === 'response-ops' && (
            <ResponseOperationsPanel
              key={refreshKey}
              onOpenSituationIntelligence={(sitId: string) => setSelectedSituationId(sitId)}
              onOpenPlanModal={(sitId: string, title?: string, emergencyType?: string) => {
                setSelectedCoordinationSituation({
                  id: sitId,
                  title: title || `Situation ${sitId}`,
                  emergencyType: emergencyType || 'Emergency Response Plan',
                });
              }}
            />
          )}

          {/* ========================================================================= */}
          {/* TAB 7: AUDIT LOGS */}
          {/* ========================================================================= */}
          {activeTab === 'audit-log' && (
            <div key={refreshKey} className="space-y-6">
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <ClipboardList className="w-5 h-5 text-slate-700" />
                    <span>Operational Audit Trail</span>
                  </h2>
                  <p className="text-xs text-slate-500 mt-1">
                    Immutable chronological timeline events recording all human decisions, AI assessments, and operational state transitions.
                  </p>
                </div>
                <span className="text-xs font-mono font-bold px-2.5 py-1 bg-slate-100 text-slate-700 rounded-lg border border-slate-200">
                  {auditLogs.length} Events Logged
                </span>
              </div>

              {auditLoading ? (
                <div className="py-12 text-center text-slate-400 text-xs">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-600" />
                  Loading audit trail...
                </div>
              ) : auditLogs.length > 0 ? (
                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
                  {auditLogs.map((log, idx) => (
                    <div key={idx} className="py-3 first:pt-0 last:pb-0 flex items-start justify-between gap-4 text-xs">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-slate-900 text-[11px] px-2 py-0.2 bg-slate-100 rounded">
                            {log.event_type || 'AUDIT_EVENT'}
                          </span>
                          {log.report_id && (
                            <span className="font-mono text-slate-500 font-bold">{log.report_id}</span>
                          )}
                        </div>
                        <p className="text-slate-700">{log.details}</p>
                        {log.actor_name && (
                          <div className="text-[11px] text-slate-400">
                            Actor: <strong className="text-slate-600">{log.actor_name}</strong> ({log.actor_role || 'OPERATOR'})
                          </div>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-slate-400 whitespace-nowrap">
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : ''}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center text-slate-400 text-xs">
                  No audit events recorded yet.
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB: IOT SENSOR NETWORK & REAL-TIME MONITORING */}
          {/* ========================================================================= */}
          {activeTab === 'sensors' && (
            <SensorManagementPanel
              key={refreshKey}
              onInspectSituation={(sitId) => setSelectedSituationId(sitId)}
            />
          )}

          {/* ========================================================================= */}
          {/* TAB: LIVE MONITORING & CHANGE IMPACT ANALYSIS (PHASE 6) */}
          {/* ========================================================================= */}
          {activeTab === 'live-monitoring' && (
            <LiveMonitoringPanel
              key={refreshKey}
              onInspectSituation={(sitId) => setSelectedSituationId(sitId)}
              onInspectPlan={(sitId) => {
                setSelectedCoordinationSituation({
                  id: sitId,
                  title: `Situation ${sitId}`,
                  emergencyType: 'Emergency Response Plan',
                });
              }}
            />
          )}

          {/* ========================================================================= */}
          {/* TAB: WHAT-IF SCENARIO SIMULATION ENGINE (PHASE 6.5) */}
          {/* ========================================================================= */}
          {activeTab === 'simulation' && (
            <WhatIfSimulationPanel
              key={refreshKey}
              onInspectSituation={(sitId) => setSelectedSituationId(sitId)}
            />
          )}

          {/* ========================================================================= */}
          {/* TAB: EMERGENCY INTELLIGENCE & ANALYTICS (PHASE 9) */}
          {/* ========================================================================= */}
          {activeTab === 'analytics' && (
            <EmergencyAnalyticsWorkspace
              key={refreshKey}
            />
          )}


          {/* ========================================================================= */}
          {/* TAB 8: SETTINGS */}
          {/* ========================================================================= */}
          {activeTab === 'settings' && (

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-6 max-w-2xl mx-auto">
              <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
                <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-700 flex items-center justify-center font-bold">
                  <Settings className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Emergency Officer Console Settings</h3>
                  <p className="text-xs text-slate-500">Watch desk identity, role credentials, and preferences.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block font-medium">Duty Officer Name</span>
                  <strong className="text-slate-900">{user?.full_name || 'Emergency Officer'}</strong>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block font-medium">Role Authority</span>
                  <strong className="text-red-700">{user?.role || 'EMERGENCY_OFFICER'}</strong>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block font-medium">Phone / Login</span>
                  <strong className="text-slate-900">{user?.phone || 'N/A'}</strong>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <span className="text-slate-400 block font-medium">Badge Number</span>
                  <strong className="text-slate-900">{user?.badge_number || 'OFFICER-HQ'}</strong>
                </div>
              </div>

              <div className="pt-2 text-xs text-slate-500 flex items-center justify-between border-t border-slate-100">
                <span>Session: Authenticated via JWT bearer token</span>
                <span className="font-mono text-emerald-600 font-bold">Active & Secure</span>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Report Details Modal */}
      {selectedReportId && (
        <ReportDetailsModal
          reportId={selectedReportId}
          onClose={handleCloseModal}
          onReportUpdated={fetchDashboardData}
        />
      )}

      {/* Situation Details Modal */}
      {selectedSituationId && (
        <SituationDetailsModal
          situationId={selectedSituationId}
          onClose={() => setSelectedSituationId(null)}
          onSituationUpdated={() => fetchDashboardData()}
          onViewReport={(repId) => {
            setSelectedSituationId(null);
            handleOpenReport(repId);
          }}
          onOpenCoordination={(sitId, title, emergencyType) => {
            setSelectedSituationId(null);
            setSelectedCoordinationSituation({
              id: sitId,
              title,
              emergencyType,
            });
          }}
        />
      )}

      {/* Phase 5: Multi-Agent Coordination Plan Modal */}
      {selectedCoordinationSituation && (
        <CoordinationPlanModal
          situationId={selectedCoordinationSituation.id}
          situationTitle={selectedCoordinationSituation.title}
          emergencyType={selectedCoordinationSituation.emergencyType}
          onClose={() => setSelectedCoordinationSituation(null)}
          onPlanUpdated={() => fetchDashboardData()}
        />
      )}
    </div>
  );
};

export default OfficerCommandCenter;
