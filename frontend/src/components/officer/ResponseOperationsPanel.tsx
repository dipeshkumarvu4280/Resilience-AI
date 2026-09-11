import React, { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Eye,
  AlertTriangle,
  CheckCircle2,
  Truck,
  Home,
  HeartPulse,
  Layers,
  GitBranch,
  Route as RouteIcon,
  ShieldCheck,
  MapPin,
  Search,
  Send,
  X,
  CheckCircle,
  FileText,
} from 'lucide-react';
import type {
  CoordinationPlan,
  SituationCluster,
  ResponseTask,
  ResponseTaskStatus,
  TaskType,
  OperationsOverview,
  FieldUpdateType,
  UserResponse,
  ResourceResponse,
  IncidentResolutionSummary,
} from '../../types';
import { listSituations } from '../../services/situationsApi';
import { listSituationCoordinationPlans } from '../../services/coordinationApi';
import {
  getOperationsOverview,
  listTasks,
  getTask,
  approveTask,
  assignTask,
  startTask,
  completeTask,
  blockTask,
  submitFieldUpdate,
  resolveIncident,
  closeIncident,
} from '../../services/fieldOperationsApi';
import { listOfficerVolunteers, listResources } from '../../services/api';
import { CoordinationPlanModal } from './CoordinationPlanModal';
import { CoordinationPlanDiffModal } from './CoordinationPlanDiffModal';
import { formatApiError } from '../../utils/errorUtils';

interface ResponseOperationsPanelProps {
  initialSituationId?: string;
  onOpenSituationIntelligence?: (situationId: string) => void;
  onOpenPlanModal?: (situationId: string, title?: string, emergencyType?: string) => void;
}

export const ResponseOperationsPanel: React.FC<ResponseOperationsPanelProps> = ({
  initialSituationId,
  onOpenSituationIntelligence,
  onOpenPlanModal,
}) => {
  const [situations, setSituations] = useState<SituationCluster[]>([]);
  const [selectedSituationId, setSelectedSituationId] = useState<string>(initialSituationId || '');
  const selectedSituation = situations.find((s) => s.situation_id === selectedSituationId);
  const [activePlan, setActivePlan] = useState<CoordinationPlan | null>(null);
  const [plansHistory, setPlansHistory] = useState<CoordinationPlan[]>([]);

  // Overview KPIs & Tasks State
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [tasks, setTasks] = useState<ResponseTask[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [taskTypeFilter, setTaskTypeFilter] = useState<string>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Available Volunteers & Vehicles for Assignment
  const [availableVolunteers, setAvailableVolunteers] = useState<UserResponse[]>([]);
  const [availableVehicles, setAvailableVehicles] = useState<ResourceResponse[]>([]);

  // Selected Task for Detail / Assignment Modal
  const [selectedTask, setSelectedTask] = useState<ResponseTask | null>(null);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState<boolean>(false);
  const [activeTaskModalTab, setActiveTaskModalTab] = useState<'overview' | 'assignment' | 'updates' | 'resources'>('overview');

  // Task Action Modal (Complete / Block)
  const [taskActionModal, setTaskActionModal] = useState<{
    isOpen: boolean;
    taskId: string;
    taskTitle: string;
    action: 'COMPLETE' | 'BLOCK';
    notes: string;
    isSubmitting: boolean;
  } | null>(null);

  // Assignment Modal Form State
  const [selectedVolunteerIds, setSelectedVolunteerIds] = useState<string[]>([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>('');
  const [assignNotes, setAssignNotes] = useState<string>('');
  const [isAssigning, setIsAssigning] = useState<boolean>(false);

  // Field Update Form State inside Task Modal
  const [updateType, setUpdateType] = useState<FieldUpdateType>('TASK_STARTED');
  const [updateMessage, setUpdateMessage] = useState<string>('');
  const [isSubmittingUpdate, setIsSubmittingUpdate] = useState<boolean>(false);

  // Incident Resolution / Closure Modal State
  const [isResolveModalOpen, setIsResolveModalOpen] = useState<boolean>(false);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState<boolean>(false);
  const [resolutionNotes, setResolutionNotes] = useState<string>('');
  const [forceOverride, setForceOverride] = useState<boolean>(false);
  const [closeOverride, setCloseOverride] = useState<boolean>(false);
  const [isResolving, setIsResolving] = useState<boolean>(false);
  const [isClosing, setIsClosing] = useState<boolean>(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [incidentSummary, setIncidentSummary] = useState<IncidentResolutionSummary | null>(null);

  // Coordination Plan Modals
  const [isPlanModalOpen, setIsPlanModalOpen] = useState<boolean>(false);
  const [isDiffModalOpen, setIsDiffModalOpen] = useState<boolean>(false);

  // Load all situations
  const loadSituations = useCallback(async () => {
    try {
      const response = await listSituations();
      const items = response?.items || [];
      setSituations(items);
      if (!selectedSituationId && items.length > 0) {
        setSelectedSituationId(items[0].situation_id);
      }
    } catch (err: unknown) {
      console.error('Failed to load situations:', err);
      setErrorMsg('Failed to load situation clusters. Please retry.');
    }
  }, [selectedSituationId]);

  // Load operational overview & tasks for the selected situation
  const loadOperationsData = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [overviewData, tasksData, situationPlans, volunteersData, resourcesData] = await Promise.all([
        getOperationsOverview(selectedSituationId || undefined),
        listTasks({
          situation_id: selectedSituationId || undefined,
          status: statusFilter !== 'ALL' ? statusFilter : undefined,
          task_type: taskTypeFilter !== 'ALL' ? taskTypeFilter : undefined,
          priority: priorityFilter !== 'ALL' ? priorityFilter : undefined,
          search: searchQuery.trim() || undefined,
          limit: 50,
        }),
        selectedSituationId ? listSituationCoordinationPlans(selectedSituationId) : Promise.resolve([]),
        listOfficerVolunteers().catch(() => []),
        listResources({ limit: 100 }).catch(() => ({ items: [] })),
      ]);

      setOverview(overviewData);
      setTasks(tasksData?.items || []);
      const vols = Array.isArray(volunteersData) ? volunteersData : (volunteersData as any)?.items || [];
      setAvailableVolunteers(vols);

      const resItems = Array.isArray(resourcesData) ? resourcesData : (resourcesData as any)?.items || [];
      const vehicles = resItems.filter(
        (r: ResourceResponse) =>
          r.category?.toUpperCase() === 'VEHICLE' ||
          r.resource_type?.toUpperCase() === 'TRANSPORT' ||
          r.name.toLowerCase().includes('ambulance') ||
          r.name.toLowerCase().includes('truck') ||
          r.name.toLowerCase().includes('bus') ||
          r.name.toLowerCase().includes('boat')
      );
      setAvailableVehicles(vehicles);

      const planList = Array.isArray(situationPlans) ? situationPlans : [];
      setPlansHistory(planList);

      if (planList.length > 0) {
        const active = planList.find((p) => p.status === 'ACTIVE');
        const approved = planList.find((p) => p.status === 'APPROVED');
        const pending = planList.find((p) => p.status === 'PENDING_OFFICER_REVIEW');
        const modified = planList.find((p) => p.status === 'MODIFIED');
        setActivePlan(active || approved || pending || modified || planList[0]);
      } else {
        setActivePlan(null);
      }
    } catch (err: unknown) {
      console.error('Failed to load operations data:', err);
      setErrorMsg(formatApiError(err, 'Failed to retrieve field operations data.'));
    } finally {
      setLoading(false);
    }
  }, [selectedSituationId, statusFilter, taskTypeFilter, priorityFilter, searchQuery]);

  useEffect(() => {
    loadSituations();
  }, [loadSituations]);

  useEffect(() => {
    loadOperationsData();
  }, [loadOperationsData]);

  // Task Actions
  const handleApproveTask = async (taskId: string) => {
    try {
      await approveTask(taskId);
      setSuccessMsg(`Task ${taskId} approved successfully.`);
      loadOperationsData();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to approve task.'));
    }
  };

  const handleStartTask = async (taskId: string) => {
    try {
      await startTask(taskId);
      setSuccessMsg(`Task ${taskId} execution started.`);
      loadOperationsData();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to start task.'));
    }
  };

  const handleOpenTaskActionModal = (task: ResponseTask, action: 'COMPLETE' | 'BLOCK') => {
    setTaskActionModal({
      isOpen: true,
      taskId: task.task_id,
      taskTitle: task.title,
      action,
      notes: action === 'COMPLETE' ? 'Task completed successfully.' : '',
      isSubmitting: false,
    });
  };

  const handleSubmitTaskAction = async () => {
    if (!taskActionModal) return;
    const { taskId, action, notes } = taskActionModal;
    setTaskActionModal((prev) => (prev ? { ...prev, isSubmitting: true } : null));
    try {
      if (action === 'COMPLETE') {
        await completeTask(taskId, { completion_notes: notes.trim() || 'Task completed successfully.' });
        setSuccessMsg(`Task ${taskId} marked as COMPLETED.`);
      } else {
        if (!notes.trim()) {
          setErrorMsg('A blockage reason is required.');
          setTaskActionModal((prev) => (prev ? { ...prev, isSubmitting: false } : null));
          return;
        }
        await blockTask(taskId, { reason: notes.trim() });
        setSuccessMsg(`Task ${taskId} reported as BLOCKED.`);
      }
      setTaskActionModal(null);
      loadOperationsData();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, `Failed to ${action.toLowerCase()} task.`));
      setTaskActionModal((prev) => (prev ? { ...prev, isSubmitting: false } : null));
    }
  };

  const handleOpenAssignModal = (task: ResponseTask) => {
    setSelectedTask(task);
    setSelectedVolunteerIds(task.assigned_volunteer_ids || []);
    setSelectedVehicleId(task.assigned_vehicle_id || '');
    setAssignNotes('');
    setActiveTaskModalTab('assignment');
    setIsTaskModalOpen(true);
  };

  const handleSaveAssignment = async () => {
    if (!selectedTask || isAssigning) return;
    setIsAssigning(true);
    try {
      const selectedVolNames = availableVolunteers
        .filter((v) => selectedVolunteerIds.includes(v.id))
        .map((v) => v.full_name);

      const matchedVeh = availableVehicles.find((v) => v.resource_id === selectedVehicleId);

      await assignTask(selectedTask.task_id, {
        assigned_volunteer_ids: selectedVolunteerIds,
        assigned_volunteer_names: selectedVolNames,
        assigned_vehicle_id: selectedVehicleId || null,
        assigned_vehicle_name: matchedVeh ? matchedVeh.name : null,
        notes: assignNotes,
      });

      setSuccessMsg(`Assignments updated for Task ${selectedTask.task_id}.`);
      setIsTaskModalOpen(false);
      loadOperationsData();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to assign task resources.'));
    } finally {
      setIsAssigning(false);
    }
  };

  const handleSubmitGroundUpdate = async () => {
    if (!selectedTask || !updateMessage.trim() || isSubmittingUpdate) return;
    setIsSubmittingUpdate(true);
    try {
      await submitFieldUpdate(selectedTask.task_id, {
        event_type: updateType,
        message: updateMessage.trim(),
      });
      setSuccessMsg('Field update submitted successfully.');
      setUpdateMessage('');
      const updated = await getTask(selectedTask.task_id);
      setSelectedTask(updated);
      loadOperationsData();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to submit field update.'));
    } finally {
      setIsSubmittingUpdate(false);
    }
  };

  // Incident Resolution / Closure
  const handleResolveSituation = async () => {
    if (!selectedSituationId || isResolving) return;
    if (resolutionNotes.trim().length < 5) {
      setModalError('Resolution notes must be at least 5 characters long.');
      return;
    }
    setIsResolving(true);
    setModalError(null);
    try {
      await resolveIncident(selectedSituationId, {
        resolution_notes: resolutionNotes.trim(),
        force_override_uncompleted: forceOverride,
      });
      setSuccessMsg(`Situation ${selectedSituationId} marked as RESOLVED.`);
      setIsResolveModalOpen(false);
      setResolutionNotes('');
      loadSituations();
      loadOperationsData();
    } catch (err: any) {
      const errFormatted = formatApiError(err, 'Failed to resolve situation.');
      setModalError(errFormatted);
      setErrorMsg(errFormatted);
    } finally {
      setIsResolving(false);
    }
  };

  const handleCloseSituation = async () => {
    if (!selectedSituationId || isClosing) return;
    if (resolutionNotes.trim().length < 5) {
      setModalError('Closure review notes must be at least 5 characters long.');
      return;
    }
    setIsClosing(true);
    setModalError(null);
    try {
      const summary = await closeIncident(selectedSituationId, {
        close_notes: resolutionNotes.trim(),
        force_override_uncompleted: closeOverride,
      });
      setIncidentSummary(summary);
      setSuccessMsg(`Incident ${selectedSituationId} officially CLOSED.`);
      setIsCloseModalOpen(false);
      setResolutionNotes('');
      loadSituations();
      loadOperationsData();
    } catch (err: any) {
      const errFormatted = formatApiError(err, 'Failed to close incident.');
      setModalError(errFormatted);
      setErrorMsg(errFormatted);
    } finally {
      setIsClosing(false);
    }
  };

  const getTaskTypeIcon = (type: TaskType) => {
    switch (type) {
      case 'RESOURCE_DELIVERY':
        return Truck;
      case 'SHELTER_ACTIVATION':
        return Home;
      case 'PATIENT_EVACUATION':
        return HeartPulse;
      case 'SEARCH_AND_RESCUE':
        return ShieldCheck;
      case 'ROUTE_CLEARANCE':
        return RouteIcon;
      default:
        return Layers;
    }
  };

  const getStatusBadge = (status: ResponseTaskStatus) => {
    switch (status) {
      case 'COMPLETED':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'IN_PROGRESS':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'ASSIGNED':
        return 'bg-indigo-50 text-indigo-700 border-indigo-200';
      case 'ACCEPTED':
        return 'bg-cyan-50 text-cyan-700 border-cyan-200';
      case 'APPROVED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300';
      case 'BLOCKED':
        return 'bg-rose-50 text-rose-700 border-rose-200 animate-pulse';
      case 'FAILED':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'ESCALATED':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'HIGH':
        return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* 1. HEADER & SITUATION SELECTOR */}
      {/* ========================================================================= */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 uppercase">
              Operational Command
            </span>
            <span className="text-xs font-mono text-slate-400">Field Operations & Response Execution</span>
          </div>
          <h2 className="text-lg font-bold text-slate-900 mt-1">
            Field Operations & Response Coordination
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Real emergency execution layer: actionable task lifecycles, responder mobilization, fleet routing, and ground updates.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {situations.length > 0 && (
            <div className="flex items-center gap-2">
              <label htmlFor="situation-select" className="text-xs font-bold text-slate-600 whitespace-nowrap">
                Incident Situation:
              </label>
              <select
                id="situation-select"
                value={selectedSituationId}
                onChange={(e) => setSelectedSituationId(e.target.value)}
                className="text-xs font-bold bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-red-500/20 focus:border-red-500 cursor-pointer"
              >
                {situations.map((sit) => (
                  <option key={sit.situation_id} value={sit.situation_id}>
                    {sit.title || `Situation ${sit.situation_id}`} ({sit.status})
                  </option>
                ))}
              </select>
            </div>
          )}

          {selectedSituation && selectedSituation.status !== 'CLOSED' && (
            <div className="flex items-center gap-2">
              {selectedSituation.status !== 'RESOLVED' ? (
                <button
                  onClick={() => {
                    setResolutionNotes('');
                    setIsResolveModalOpen(true);
                  }}
                  className="px-3 py-2 bg-amber-50 hover:bg-amber-100 text-amber-900 text-xs font-bold rounded-xl border border-amber-200 transition-colors shadow-2xs flex items-center gap-1.5 cursor-pointer"
                >
                  <CheckCircle className="w-3.5 h-3.5 text-amber-600" />
                  <span>Resolve Incident</span>
                </button>
              ) : (
                <button
                  onClick={() => {
                    setResolutionNotes('');
                    setIsCloseModalOpen(true);
                  }}
                  className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-2xs transition-colors flex items-center gap-1.5 cursor-pointer"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Close Incident</span>
                </button>
              )}
            </div>
          )}

          <button
            onClick={() => {
              loadSituations();
              loadOperationsData();
            }}
            disabled={loading}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl border border-slate-200 transition-colors disabled:opacity-50 cursor-pointer"
            title="Refresh Operations Stream"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Alerts */}
      {errorMsg && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-2xl flex items-center justify-between text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button
            onClick={() => setErrorMsg(null)}
            className="text-red-700 hover:text-red-900 font-bold text-xs cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-between text-xs text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
          <button
            onClick={() => setSuccessMsg(null)}
            className="text-emerald-700 hover:text-emerald-900 font-bold text-xs cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. OPERATIONAL KPI RIBBON WITH INTERACTIVE DRILL-DOWNS */}
      {/* ========================================================================= */}
      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <div
            onClick={() => {
              if (activePlan) setIsPlanModalOpen(true);
            }}
            className="group bg-white border border-slate-200 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider group-hover:text-slate-700 transition-colors">Active Plans</span>
            <div className="text-xl font-black text-slate-900 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.active_plans_count}</div>
            <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
              <span>Authoritative</span>
              <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
          <div
            onClick={() => setStatusFilter('ALL')}
            className="group bg-white border border-slate-200 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider group-hover:text-slate-700 transition-colors">Total Tasks</span>
            <div className="text-xl font-black text-slate-900 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.total_tasks_count}</div>
            <div className="flex items-center justify-between text-[10px] text-slate-500 mt-0.5">
              <span>All missions</span>
              <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
          <div
            onClick={() => setStatusFilter('IN_PROGRESS')}
            className="group bg-white border border-blue-200/80 bg-blue-50/20 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-blue-600 uppercase tracking-wider group-hover:text-blue-800 transition-colors">In Progress</span>
            <div className="text-xl font-black text-blue-700 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.in_progress_tasks_count}</div>
            <div className="flex items-center justify-between text-[10px] text-blue-600/80 mt-0.5">
              <span>Ground execution</span>
              <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
          <div
            onClick={() => setStatusFilter('BLOCKED')}
            className="group bg-white border border-rose-200/80 bg-rose-50/20 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-rose-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-rose-600 uppercase tracking-wider group-hover:text-rose-800 transition-colors">Blocked / Issues</span>
            <div className="text-xl font-black text-rose-700 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.blocked_tasks_count}</div>
            <div className="flex items-center justify-between text-[10px] text-rose-600/80 mt-0.5">
              <span>Needs review</span>
              <span className="text-rose-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
          <div
            onClick={() => setStatusFilter('COMPLETED')}
            className="group bg-white border border-emerald-200/80 bg-emerald-50/20 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-emerald-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider group-hover:text-emerald-800 transition-colors">Completed</span>
            <div className="text-xl font-black text-emerald-700 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.completed_tasks_count}</div>
            <div className="flex items-center justify-between text-[10px] text-emerald-600/80 mt-0.5">
              <span>Verified closed</span>
              <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
          <div
            onClick={() => setStatusFilter('ALL')}
            className="group bg-white border border-indigo-200/80 bg-indigo-50/20 rounded-2xl p-3.5 shadow-2xs hover:shadow-md hover:border-indigo-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
          >
            <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider group-hover:text-indigo-800 transition-colors">Active Responders</span>
            <div className="text-xl font-black text-indigo-700 mt-1 group-hover:scale-105 transition-transform origin-left">{overview.active_volunteers_count}</div>
            <div className="flex items-center justify-between text-[10px] text-indigo-600/80 mt-0.5">
              <span>Field mobilized</span>
              <span className="text-indigo-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[10px]">View →</span>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. ACTIVE PLAN SUMMARY CARD */}
      {/* ========================================================================= */}
      {activePlan ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${
                activePlan.status === 'ACTIVE'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : activePlan.status === 'APPROVED'
                  ? 'bg-cyan-50 text-cyan-800 border-cyan-200'
                  : 'bg-slate-100 text-slate-700 border-slate-200'
              }`}>
                {selectedSituation?.status === 'RESOLVED' || selectedSituation?.status === 'CLOSED'
                  ? `INCIDENT ${selectedSituation.status} • PLAN v${activePlan.version}`
                  : `PLAN v${activePlan.version} (${activePlan.status})`}
              </span>
              <span className="text-xs font-mono text-slate-400">ID: {activePlan.plan_id}</span>
              {plansHistory.length > 1 && (
                <span className="text-[10px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                  {plansHistory.length} versions in lineage
                </span>
              )}
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${getPriorityBadge(activePlan.assessed_priority)}`}>
                {activePlan.assessed_priority}
              </span>
            </div>
            <p className="text-xs text-slate-600 line-clamp-2 max-w-2xl mt-1 leading-relaxed">
              {activePlan.reasoning}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsPlanModalOpen(true)}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 transition-colors flex items-center gap-1.5"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Inspect Plan</span>
            </button>
            {plansHistory.length > 1 && (
              <button
                onClick={() => setIsDiffModalOpen(true)}
                className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-800 text-xs font-bold rounded-xl border border-blue-200 transition-colors flex items-center gap-1.5"
              >
                <GitBranch className="w-3.5 h-3.5 text-blue-600" />
                <span>View Plan Diff</span>
              </button>
            )}
          </div>
        </div>
      ) : tasks.length > 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 shadow-2xs flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-slate-200 text-slate-700 rounded-xl">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-900">Direct Operational Dispatch Active</h4>
              <p className="text-[11px] text-slate-500">{tasks.length} active/historical response tasks managed for this situation.</p>
            </div>
          </div>
        </div>
      ) : null}

      {/* ========================================================================= */}
      {/* 4. TASK BOARD & CONTROLS */}
      {/* ========================================================================= */}
      <div className="space-y-4">
        {/* Filter Controls & Search */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
          {/* Status Tabs */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'ALL', label: 'All Tasks' },
              { id: 'PENDING_APPROVAL', label: 'Pending' },
              { id: 'APPROVED', label: 'Approved' },
              { id: 'ASSIGNED', label: 'Assigned' },
              { id: 'IN_PROGRESS', label: 'In Progress' },
              { id: 'BLOCKED', label: 'Blocked' },
              { id: 'COMPLETED', label: 'Completed' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 text-xs font-bold rounded-xl transition-all ${
                  statusFilter === tab.id
                    ? 'bg-red-50 text-red-800 border border-red-200 shadow-2xs'
                    : 'bg-slate-50 hover:bg-slate-100 text-slate-600 border border-slate-200/60'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search & Filters */}
          <div className="flex items-center gap-2 w-full md:w-auto">
            <div className="relative flex-1 md:w-56">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search tasks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full text-xs pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
              />
            </div>

            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="text-xs font-bold bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-2 text-slate-700 cursor-pointer focus:outline-hidden"
            >
              <option value="ALL">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>

            <select
              value={taskTypeFilter}
              onChange={(e) => setTaskTypeFilter(e.target.value)}
              className="text-xs font-bold bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-2 text-slate-700 cursor-pointer focus:outline-hidden"
            >
              <option value="ALL">All Types</option>
              <option value="RESOURCE_DELIVERY">Resource Delivery</option>
              <option value="SHELTER_ACTIVATION">Shelter Activation</option>
              <option value="PATIENT_EVACUATION">Patient Evacuation</option>
              <option value="SEARCH_AND_RESCUE">Search & Rescue</option>
              <option value="ROUTE_CLEARANCE">Route Clearance</option>
            </select>
          </div>
        </div>

        {/* If no plan exists for this situation, render action trigger */}
        {!activePlan && tasks.length === 0 && selectedSituation && selectedSituation.status !== 'CLOSED' && selectedSituation.status !== 'RESOLVED' && (
          <div className="bg-blue-50/70 border border-blue-200 rounded-2xl p-6 text-center space-y-3">
            <h4 className="text-sm font-bold text-blue-900">No Multi-Agent Plan Generated For This Situation</h4>
            <p className="text-xs text-blue-700 max-w-lg mx-auto leading-relaxed">
              Generate an AI multi-agent coordination plan to derive actionable resource delivery, evacuation, and rescue tasks.
            </p>
            <div className="flex items-center justify-center gap-2 pt-1">
              <button
                onClick={() => {
                  if (onOpenPlanModal) {
                    onOpenPlanModal(selectedSituation.situation_id, selectedSituation.title, selectedSituation.emergency_type);
                  } else {
                    setIsPlanModalOpen(true);
                  }
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
              >
                Generate Coordination Plan
              </button>
              {onOpenSituationIntelligence && (
                <button
                  onClick={() => onOpenSituationIntelligence(selectedSituation.situation_id)}
                  className="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 transition-colors"
                >
                  Inspect Situation
                </button>
              )}
            </div>
          </div>
        )}

        {/* Task Cards Grid */}
        {tasks.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {tasks.map((task) => {
              const TaskIcon = getTaskTypeIcon(task.task_type);
              return (
                <div
                  key={task.task_id}
                  className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs hover:shadow-xs transition-shadow flex flex-col justify-between space-y-4"
                >
                  {/* Top Bar */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <div className="p-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200">
                          <TaskIcon className="w-4 h-4" />
                        </div>
                        <span className="text-[11px] font-mono font-bold text-slate-500">
                          {task.task_type.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getPriorityBadge(task.priority)}`}>
                        {task.priority}
                      </span>
                    </div>

                    <h4 className="text-sm font-bold text-slate-900 leading-snug">
                      {task.title}
                    </h4>
                    <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                      {task.description}
                    </p>
                  </div>

                  {/* Context Meta */}
                  <div className="space-y-1.5 text-[11px] text-slate-600 bg-slate-50/70 p-3 rounded-xl border border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Status:</span>
                      <span className={`px-2 py-0.5 rounded font-bold text-[10px] border ${getStatusBadge(task.status)}`}>
                        {task.status.replace(/_/g, ' ')}
                      </span>
                    </div>

                    {task.assigned_volunteer_names && task.assigned_volunteer_names.length > 0 && (
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400">Responders:</span>
                        <strong className="text-slate-800 truncate max-w-[150px]">
                          {task.assigned_volunteer_names.join(', ')}
                        </strong>
                      </div>
                    )}

                    {task.assigned_vehicle_name && (
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400">Vehicle:</span>
                        <strong className="text-slate-800 truncate max-w-[150px]">
                          {task.assigned_vehicle_name}
                        </strong>
                      </div>
                    )}

                    {task.destination && (
                      <div className="flex items-center justify-between">
                        <span className="text-slate-400">Destination:</span>
                        <strong className="text-slate-800 truncate max-w-[150px]">
                          {task.destination.name || task.destination.address || 'Incident Site'}
                        </strong>
                      </div>
                    )}

                    {task.blocked_reason && (
                      <div className="mt-1 p-1.5 bg-rose-50 text-rose-800 text-[10px] font-medium rounded border border-rose-200">
                        <strong>Blockage:</strong> {task.blocked_reason}
                      </div>
                    )}
                  </div>

                  {/* Action Bar */}
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                    <button
                      onClick={() => {
                        setSelectedTask(task);
                        setActiveTaskModalTab('overview');
                        setIsTaskModalOpen(true);
                      }}
                      className="text-xs font-bold text-slate-600 hover:text-slate-900 flex items-center gap-1"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>Details</span>
                    </button>

                    <div className="flex items-center gap-1.5">
                      {task.status === 'PENDING_APPROVAL' && (
                        <button
                          onClick={() => handleApproveTask(task.task_id)}
                          className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg transition-colors"
                        >
                          Approve
                        </button>
                      )}

                      {(task.status === 'APPROVED' || task.status === 'ASSIGNED') && (
                        <button
                          onClick={() => handleOpenAssignModal(task)}
                          className="px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg transition-colors"
                        >
                          {task.status === 'ASSIGNED' ? 'Reassign' : 'Assign Team'}
                        </button>
                      )}

                      {task.status === 'ASSIGNED' && (
                        <button
                          onClick={() => handleStartTask(task.task_id)}
                          className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg transition-colors"
                        >
                          Start
                        </button>
                      )}

                      {task.status === 'IN_PROGRESS' && (
                        <>
                          <button
                            onClick={() => handleOpenTaskActionModal(task, 'BLOCK')}
                            className="px-2 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold rounded-lg border border-rose-200 transition-colors"
                            title="Report Blockage"
                          >
                            Block
                          </button>
                          <button
                            onClick={() => handleOpenTaskActionModal(task, 'COMPLETE')}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg transition-colors"
                          >
                            Complete
                          </button>
                        </>
                      )}

                      {task.status === 'BLOCKED' && (
                        <button
                          onClick={() => handleStartTask(task.task_id)}
                          className="px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg transition-colors"
                        >
                          Resume
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-500 flex items-center justify-center mx-auto">
              <Layers className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-bold text-slate-800">No Response Tasks Found</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              {statusFilter !== 'ALL'
                ? `There are no response tasks in '${statusFilter}' status for this situation.`
                : 'Tasks will appear once an active response plan is approved and activated by an Emergency Officer.'}
            </p>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 5. TASK DETAIL & ASSIGNMENT MODAL */}
      {/* ========================================================================= */}
      {isTaskModalOpen && selectedTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-100 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                    {selectedTask.task_id}
                  </span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${getStatusBadge(selectedTask.status)}`}>
                    {selectedTask.status.replace(/_/g, ' ')}
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 mt-1.5">{selectedTask.title}</h3>
              </div>
              <button
                onClick={() => setIsTaskModalOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex items-center gap-2 px-5 pt-3 border-b border-slate-100 bg-slate-50/50">
              {[
                { id: 'overview', label: 'Overview' },
                { id: 'assignment', label: 'Team & Vehicle' },
                { id: 'resources', label: `Resources (${selectedTask.assigned_resources?.length || 0})` },
                { id: 'updates', label: `Field Updates (${selectedTask.field_updates?.length || 0})` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTaskModalTab(tab.id as any)}
                  className={`px-3 py-2 text-xs font-bold border-b-2 transition-colors ${
                    activeTaskModalTab === tab.id
                      ? 'border-red-600 text-red-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              {activeTaskModalTab === 'overview' && (
                <div className="space-y-4 text-xs">
                  <div>
                    <h5 className="font-bold text-slate-700 uppercase tracking-wider text-[10px]">Description</h5>
                    <p className="text-slate-600 mt-1 leading-relaxed">{selectedTask.description}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3.5 rounded-xl border border-slate-200/60">
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Situation ID</span>
                      <strong className="text-slate-800">{selectedTask.situation_id}</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Source Plan</span>
                      <strong className="text-slate-800">{selectedTask.plan_id} (v{selectedTask.plan_version})</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Priority</span>
                      <strong className="text-slate-800">{selectedTask.priority}</strong>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Est. Duration</span>
                      <strong className="text-slate-800">{selectedTask.estimated_duration_minutes || 30} mins</strong>
                    </div>
                  </div>

                  {selectedTask.location && (
                    <div>
                      <h5 className="font-bold text-slate-700 uppercase tracking-wider text-[10px]">Origin / Staging Area</h5>
                      <p className="text-slate-800 mt-0.5 flex items-center gap-1.5">
                        <MapPin className="w-3.5 h-3.5 text-slate-400" />
                        <span>{selectedTask.location.name || selectedTask.location.address || 'Central Logistics Base'}</span>
                      </p>
                    </div>
                  )}

                  {selectedTask.destination && (
                    <div>
                      <h5 className="font-bold text-slate-700 uppercase tracking-wider text-[10px]">Destination / Impact Site</h5>
                      <p className="text-slate-800 mt-0.5 flex items-center gap-1.5">
                        <MapPin className="w-3.5 h-3.5 text-red-500" />
                        <span>{selectedTask.destination.name || selectedTask.destination.address || 'Emergency Site'}</span>
                      </p>
                    </div>
                  )}
                </div>
              )}

              {activeTaskModalTab === 'assignment' && (
                <div className="space-y-4 text-xs">
                  <div>
                    <label className="font-bold text-slate-700 block mb-1.5">
                      Assign Responders / Volunteers:
                    </label>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto border border-slate-200 rounded-xl p-2">
                      {availableVolunteers.length > 0 ? (
                        availableVolunteers.map((vol) => (
                          <label
                            key={vol.id}
                            className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded-lg cursor-pointer text-xs"
                          >
                            <input
                              type="checkbox"
                              checked={selectedVolunteerIds.includes(vol.id)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedVolunteerIds([...selectedVolunteerIds, vol.id]);
                                } else {
                                  setSelectedVolunteerIds(selectedVolunteerIds.filter((id) => id !== vol.id));
                                }
                              }}
                              className="rounded text-red-600 focus:ring-red-500 cursor-pointer"
                            />
                            <div className="flex-1">
                              <span className="font-bold text-slate-900">{vol.full_name}</span>
                              <span className="text-slate-400 text-[10px] ml-2 font-mono">
                                ({vol.volunteer_profile?.skills?.join(', ') || 'General Responder'})
                              </span>
                            </div>
                          </label>
                        ))
                      ) : (
                        <div className="text-slate-400 text-center py-3 text-xs">
                          No registered volunteers available in system.
                        </div>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className="font-bold text-slate-700 block mb-1.5">
                      Assign Fleet Vehicle / Transport:
                    </label>
                    <select
                      value={selectedVehicleId}
                      onChange={(e) => setSelectedVehicleId(e.target.value)}
                      className="w-full text-xs font-bold bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-slate-800"
                    >
                      <option value="">No Vehicle Assigned</option>
                      {availableVehicles.map((veh) => (
                        <option key={veh.resource_id} value={veh.resource_id}>
                          {veh.name} ({veh.status})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="font-bold text-slate-700 block mb-1.5">Assignment Notes / Instructions:</label>
                    <textarea
                      rows={2}
                      value={assignNotes}
                      onChange={(e) => setAssignNotes(e.target.value)}
                      placeholder="Special deployment instructions..."
                      className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-slate-800 placeholder-slate-400"
                    />
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      onClick={handleSaveAssignment}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
                    >
                      Save Assignments
                    </button>
                  </div>
                </div>
              )}

              {activeTaskModalTab === 'resources' && (
                <div className="space-y-3 text-xs">
                  {selectedTask.assigned_resources && selectedTask.assigned_resources.length > 0 ? (
                    <div className="space-y-2">
                      {selectedTask.assigned_resources.map((res, idx) => (
                        <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
                          <div>
                            <strong className="text-slate-900 block">{res.resource_name}</strong>
                            <span className="text-slate-500 text-[11px]">ID: {res.resource_id} • Type: {res.resource_type}</span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-black text-slate-900">{res.allocated_quantity} {res.unit}</span>
                            <span className="text-[10px] text-slate-400 block font-mono">Allocated</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-8 text-center text-slate-400 text-xs">
                      No physical inventory items assigned to this task.
                    </div>
                  )}
                </div>
              )}

              {activeTaskModalTab === 'updates' && (
                <div className="space-y-4 text-xs">
                  {/* Submit New Update */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5">
                    <h5 className="font-bold text-slate-800 text-xs">Record Ground Field Update</h5>
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={updateType}
                        onChange={(e) => setUpdateType(e.target.value as FieldUpdateType)}
                        className="text-xs font-bold bg-white border border-slate-200 rounded-lg p-2 text-slate-800"
                      >
                        <option value="ARRIVED">Arrived on Scene</option>
                        <option value="TASK_STARTED">Task Started</option>
                        <option value="TASK_COMPLETED">Task Completed</option>
                        <option value="TASK_BLOCKED">Task Blocked</option>
                        <option value="ROUTE_BLOCKED">Route Blocked</option>
                        <option value="ADDITIONAL_HELP_REQUIRED">Additional Help Required</option>
                        <option value="OTHER_OPERATIONAL_CHANGE">Other Change</option>
                      </select>
                      <button
                        onClick={handleSubmitGroundUpdate}
                        disabled={!updateMessage.trim()}
                        className="px-3 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold rounded-lg transition-colors flex items-center justify-center gap-1.5"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>Submit Update</span>
                      </button>
                    </div>
                    <input
                      type="text"
                      placeholder="Enter update description..."
                      value={updateMessage}
                      onChange={(e) => setUpdateMessage(e.target.value)}
                      className="w-full text-xs bg-white border border-slate-200 rounded-lg p-2 text-slate-800 placeholder-slate-400"
                    />
                  </div>

                  {/* Updates Stream */}
                  {selectedTask.field_updates && selectedTask.field_updates.length > 0 ? (
                    <div className="space-y-2 max-h-60 overflow-y-auto">
                      {selectedTask.field_updates.map((upd) => (
                        <div key={upd.update_id} className="p-3 bg-white border border-slate-200 rounded-xl space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-red-700">{upd.event_type}</span>
                            <span className="text-slate-400 font-mono text-[10px]">
                              {new Date(upd.timestamp).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="text-slate-700 text-xs">{upd.message}</p>
                          <span className="text-[10px] text-slate-400 block">Reported by: {upd.actor_name} ({upd.actor_role})</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-6 text-center text-slate-400 text-xs">
                      No ground field updates submitted yet.
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 font-mono">Resilience Field Execution Engine</span>
              <button
                onClick={() => setIsTaskModalOpen(false)}
                className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-800 text-xs font-bold rounded-xl transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5.1 TASK ACTION MODAL (Complete / Block) */}
      {/* ========================================================================= */}
      {taskActionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-2xl border ${
                taskActionModal.action === 'COMPLETE'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}>
                {taskActionModal.action === 'COMPLETE' ? <CheckCircle className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {taskActionModal.action === 'COMPLETE' ? 'Complete Task' : 'Report Task Blockage'}
                </h3>
                <p className="text-xs text-slate-500 font-mono">{taskActionModal.taskId} • {taskActionModal.taskTitle}</p>
              </div>
            </div>

            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">
                {taskActionModal.action === 'COMPLETE' ? 'Operational Completion Notes:' : 'Ground Impediment / Blockage Reason:'}
              </label>
              <textarea
                rows={3}
                value={taskActionModal.notes}
                onChange={(e) => setTaskActionModal({ ...taskActionModal, notes: e.target.value })}
                placeholder={taskActionModal.action === 'COMPLETE' ? 'Describe actions taken to finalize task...' : 'Explain obstacle, road closure, hazard, or resource shortfall...'}
                className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-red-500/20"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setTaskActionModal(null)}
                disabled={taskActionModal.isSubmitting}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmitTaskAction}
                disabled={taskActionModal.isSubmitting || (taskActionModal.action === 'BLOCK' && !taskActionModal.notes.trim())}
                className={`px-4 py-2 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50 ${
                  taskActionModal.action === 'COMPLETE'
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-rose-600 hover:bg-rose-700'
                }`}
              >
                {taskActionModal.isSubmitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>{taskActionModal.action === 'COMPLETE' ? 'Confirm Completion' : 'Submit Blockage'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. INCIDENT RESOLUTION MODAL */}
      {/* ========================================================================= */}
      {isResolveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-50 text-amber-700 rounded-2xl border border-amber-200">
                <CheckCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Resolve Incident</h3>
                <p className="text-xs text-slate-500">Verify operational readiness for resolution.</p>
              </div>
            </div>

            {modalError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                <span>{modalError}</span>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-bold text-slate-700">Resolution Summary / Notes:</label>
                <span className={`text-[10px] font-mono ${resolutionNotes.trim().length >= 5 ? 'text-emerald-600 font-bold' : 'text-slate-400'}`}>
                  {resolutionNotes.trim().length}/5 chars min
                </span>
              </div>
              <textarea
                rows={3}
                value={resolutionNotes}
                onChange={(e) => {
                  setResolutionNotes(e.target.value);
                  if (modalError) setModalError(null);
                }}
                placeholder="Explain the incident containment and resolution rationale..."
                className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-500/20"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={forceOverride}
                onChange={(e) => setForceOverride(e.target.checked)}
                className="rounded text-amber-600 focus:ring-amber-500"
              />
              <span>Override and close even if uncompleted tasks remain</span>
            </label>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  setIsResolveModalOpen(false);
                  setModalError(null);
                }}
                disabled={isResolving}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveSituation}
                disabled={isResolving || resolutionNotes.trim().length < 5}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
              >
                {isResolving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Resolution</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 7. INCIDENT CLOSURE MODAL */}
      {/* ========================================================================= */}
      {isCloseModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-50 text-emerald-700 rounded-2xl border border-emerald-200">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Close Incident Permanently</h3>
                <p className="text-xs text-slate-500">Compiles authoritative post-incident summary.</p>
              </div>
            </div>

            {modalError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                <span>{modalError}</span>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-bold text-slate-700">Final Closure Review Notes:</label>
                <span className={`text-[10px] font-mono ${resolutionNotes.trim().length >= 5 ? 'text-emerald-600 font-bold' : 'text-slate-400'}`}>
                  {resolutionNotes.trim().length}/5 chars min
                </span>
              </div>
              <textarea
                rows={3}
                value={resolutionNotes}
                onChange={(e) => {
                  setResolutionNotes(e.target.value);
                  if (modalError) setModalError(null);
                }}
                placeholder="Final operational sign-off and debrief..."
                className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-slate-800 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-emerald-500/20"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={closeOverride}
                onChange={(e) => setCloseOverride(e.target.checked)}
                className="rounded text-emerald-600 focus:ring-emerald-500"
              />
              <span>Override and force close uncompleted tasks if any</span>
            </label>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  setIsCloseModalOpen(false);
                  setModalError(null);
                }}
                disabled={isClosing}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCloseSituation}
                disabled={isClosing || resolutionNotes.trim().length < 5}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
              >
                {isClosing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Close & Archive Incident</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 8. INCIDENT RESOLUTION SUMMARY DEBRIEF MODAL */}
      {/* ========================================================================= */}
      {incidentSummary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl max-w-xl w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-emerald-50 text-emerald-700 rounded-2xl border border-emerald-200">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 uppercase">
                      Incident Summary
                    </span>
                    <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                      CLOSED
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-slate-900 mt-1">{incidentSummary.title}</h3>
                </div>
              </div>
              <button
                onClick={() => setIncidentSummary(null)}
                className="p-1 text-slate-400 hover:text-slate-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-slate-50 p-3.5 rounded-2xl border border-slate-200/60 text-center">
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase">Reports</span>
                <div className="text-base font-black text-slate-900">{incidentSummary.total_citizen_reports}</div>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase">Tasks Done</span>
                <div className="text-base font-black text-emerald-700">{incidentSummary.tasks_completed} / {incidentSummary.total_tasks_created}</div>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase">Plan Revisions</span>
                <div className="text-base font-black text-slate-900">{incidentSummary.replanning_iterations_count}</div>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase">Duration</span>
                <div className="text-base font-black text-slate-900">{incidentSummary.duration_hours}h</div>
              </div>
            </div>

            {/* Additional operational lineage */}
            <div className="grid grid-cols-3 gap-2 bg-slate-50 p-3 rounded-2xl border border-slate-200/60 text-center text-xs">
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase block">Responders</span>
                <strong className="text-slate-800">{incidentSummary.volunteers_involved_count}</strong>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase block">Vehicles</span>
                <strong className="text-slate-800">{incidentSummary.vehicles_involved_count}</strong>
              </div>
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase block">Monitoring Events</span>
                <strong className="text-slate-800">{incidentSummary.monitoring_events_count}</strong>
              </div>
            </div>

            {/* Resources consumed */}
            {incidentSummary.resources_utilized && incidentSummary.resources_utilized.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-bold text-slate-700 block">Authoritative Resources Consumed:</span>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {incidentSummary.resources_utilized.map((res: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs">
                      <span className="text-slate-800 font-medium">{res.resource_name}</span>
                      <strong className="text-emerald-700">{res.quantity_consumed} {res.unit}</strong>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {incidentSummary.resolution_notes && (
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
                <span className="font-bold text-slate-700 block text-[11px] mb-0.5">Closure Notes:</span>
                <p className="text-slate-600 leading-relaxed">{incidentSummary.resolution_notes}</p>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setIncidentSummary(null)}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors"
              >
                Close Debrief
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Coordination Plan Modals */}
      {isPlanModalOpen && activePlan && (
        <CoordinationPlanModal
          situationId={activePlan.situation_id || selectedSituationId}
          situationTitle={selectedSituation?.title || `Situation ${activePlan.situation_id || selectedSituationId}`}
          emergencyType={selectedSituation?.emergency_type || 'EMERGENCY'}
          onClose={() => {
            setIsPlanModalOpen(false);
            loadOperationsData();
          }}
          onPlanUpdated={(updatedPlan) => {
            setIsPlanModalOpen(false);
            setSuccessMsg(`Plan ${updatedPlan?.plan_id || activePlan.plan_id} reviewed successfully (${updatedPlan?.status || 'APPROVED'}).`);
            loadOperationsData();
          }}
        />
      )}

      {isDiffModalOpen && activePlan && (
        <CoordinationPlanDiffModal
          plan={activePlan}
          isOpen={isDiffModalOpen}
          onClose={() => setIsDiffModalOpen(false)}
          onPlanActivated={() => {
            setIsDiffModalOpen(false);
            setSuccessMsg(`Plan ${activePlan.plan_id} activated.`);
            loadOperationsData();
          }}
        />
      )}
    </div>
  );
};
