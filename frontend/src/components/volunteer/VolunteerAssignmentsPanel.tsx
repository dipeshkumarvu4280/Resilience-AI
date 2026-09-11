import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  MapPin,
  RefreshCw,
  Truck,
  Home,
  HeartPulse,
  Route as RouteIcon,
  Filter,
  Clock,
  Send,
  Eye,
} from 'lucide-react';
import { listTasks, acceptTask, startTask, completeTask, submitFieldUpdate } from '../../services/fieldOperationsApi';
import type { ResponseTask, FieldUpdateType } from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';
import { SubmitFieldVerificationModal } from './SubmitFieldVerificationModal';

export const VolunteerAssignmentsPanel: React.FC = () => {
  const [tasks, setTasks] = useState<ResponseTask[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Field Verification Modal State
  const [verifyingTask, setVerifyingTask] = useState<ResponseTask | null>(null);

  // Field Update Form State for Active Task
  const [activeUpdateTaskId, setActiveUpdateTaskId] = useState<string | null>(null);
  const [updateType, setUpdateType] = useState<FieldUpdateType>('TASK_STARTED');
  const [updateMessage, setUpdateMessage] = useState<string>('');

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    setActionError(null);
    try {
      const res = await listTasks({ assigned_to_me: true, limit: 100 });
      setTasks(res?.items || []);
    } catch (err: any) {
      console.error('Failed to load volunteer assignments:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  const handleAcceptAssignment = async (taskId: string) => {
    try {
      await acceptTask(taskId);
      setActionSuccess(`Mission ${taskId} accepted!`);
      loadAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to accept task.');
    }
  };

  const handleStartMission = async (taskId: string) => {
    try {
      await startTask(taskId);
      setActionSuccess(`Mission ${taskId} execution started.`);
      loadAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to start task.');
    }
  };

  const handleCompleteMission = async (taskId: string) => {
    const notes = prompt('Enter field completion report notes:') || 'Mission objectives completed on scene.';
    try {
      await completeTask(taskId, { completion_notes: notes });
      setActionSuccess(`Mission ${taskId} marked as completed!`);
      loadAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to complete task.');
    }
  };

  const handleSubmitGroundReport = async (taskId: string) => {
    if (!updateMessage.trim()) return;
    try {
      await submitFieldUpdate(taskId, {
        event_type: updateType,
        message: updateMessage.trim(),
      });
      setActionSuccess('Ground report logged successfully.');
      setUpdateMessage('');
      setActiveUpdateTaskId(null);
      loadAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to submit ground update.');
    }
  };

  const getTaskIcon = (type: string) => {
    switch (type) {
      case 'RESOURCE_DELIVERY':
        return Truck;
      case 'SHELTER_ACTIVATION':
        return Home;
      case 'PATIENT_EVACUATION':
        return HeartPulse;
      case 'ROUTE_CLEARANCE':
        return RouteIcon;
      default:
        return ShieldCheck;
    }
  };

  const activeCount = tasks.filter(
    (t) => t.status === 'ASSIGNED' || t.status === 'ACCEPTED' || t.status === 'IN_PROGRESS'
  ).length;
  const completedCount = tasks.filter((t) => t.status === 'COMPLETED').length;

  const filteredTasks = tasks.filter((t) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'ACTIVE') {
      return t.status === 'ASSIGNED' || t.status === 'ACCEPTED' || t.status === 'IN_PROGRESS';
    }
    return t.status === statusFilter;
  });

  return (
    <div className="space-y-6">
      {/* Action Alerts */}
      {actionError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-2xl flex items-center justify-between text-xs text-red-800">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{actionError}</span>
          </div>
          <button onClick={() => setActionError(null)} className="text-red-700 font-bold hover:underline cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-between text-xs text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-700 font-bold hover:underline cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {/* Header with Filter Controls */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Field Operations & Response Missions</h2>
          </div>
          <p className="text-xs text-slate-500">
            Emergency response tasks assigned to your volunteer profile by the Incident Commander.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-semibold text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-800 font-bold focus:outline-none cursor-pointer"
            >
              <option value="ALL">All Statuses ({tasks.length})</option>
              <option value="ACTIVE">Active Missions ({activeCount})</option>
              <option value="ASSIGNED">Assigned / Pending Acceptance</option>
              <option value="ACCEPTED">Accepted</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="COMPLETED">Completed ({completedCount})</option>
            </select>
          </div>

          <button
            onClick={loadAssignments}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl border border-slate-200 transition-colors cursor-pointer"
            title="Refresh assignments"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Task List */}
      {filteredTasks.length > 0 ? (
        <div className="space-y-4">
          {filteredTasks.map((task) => {
            const TaskIcon = getTaskIcon(task.task_type);
            return (
              <div
                key={task.task_id}
                className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4 hover:border-slate-300 transition-all"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="flex items-start gap-3.5">
                    <div className="p-3 rounded-2xl bg-blue-50 border border-blue-200 text-blue-700 flex-shrink-0">
                      <TaskIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-base font-bold text-slate-900">{task.title}</h4>
                      <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-500 font-mono">
                        <span>Task ID: {task.task_id}</span>
                        <span>•</span>
                        <span>Type: {task.task_type}</span>
                        <span>•</span>
                        <span className="text-amber-700 font-bold">Priority: {task.priority}</span>
                      </div>
                    </div>
                  </div>

                  <span
                    className={`text-xs font-bold px-3 py-1 rounded-full border self-start ${
                      task.status === 'COMPLETED'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : task.status === 'IN_PROGRESS'
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                    }`}
                  >
                    {task.status.replace(/_/g, ' ')}
                  </span>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 p-3.5 rounded-xl border border-slate-100">
                  {task.description}
                </p>

                {task.destination && (
                  <div className="text-xs text-slate-600 flex items-center gap-2 bg-blue-50/50 border border-blue-100 p-2.5 rounded-xl">
                    <MapPin className="w-4 h-4 text-blue-600 shrink-0" />
                    <span>
                      Rendezvous Site:{' '}
                      <strong className="text-slate-800">{task.destination.name || task.destination.address}</strong>
                    </span>
                  </div>
                )}

                {/* Action Controls */}
                <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Created: {new Date(task.created_at).toLocaleString()}</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {task.status === 'ASSIGNED' && (
                      <button
                        onClick={() => handleAcceptAssignment(task.task_id)}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
                      >
                        Accept Mission
                      </button>
                    )}

                    {task.status === 'ACCEPTED' && (
                      <button
                        onClick={() => handleStartMission(task.task_id)}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
                      >
                        Start Mission
                      </button>
                    )}

                    {task.status === 'IN_PROGRESS' && (
                      <>
                        <button
                          onClick={() => setVerifyingTask(task)}
                          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Field Verification</span>
                        </button>
                        <button
                          onClick={() =>
                            setActiveUpdateTaskId(activeUpdateTaskId === task.task_id ? null : task.task_id)
                          }
                          className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 transition-colors"
                        >
                          Log Ground Update
                        </button>
                        <button
                          onClick={() => handleCompleteMission(task.task_id)}
                          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
                        >
                          Mark Complete
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Ground Report Input Area */}
                {activeUpdateTaskId === task.task_id && (
                  <div className="p-4 bg-slate-50 rounded-xl border border-blue-200 space-y-3 text-xs animate-in fade-in duration-100">
                    <h5 className="font-bold text-slate-800 flex items-center gap-1.5">
                      <Send className="w-3.5 h-3.5 text-blue-600" /> Submit Real-time Ground Update
                    </h5>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <select
                        value={updateType}
                        onChange={(e) => setUpdateType(e.target.value as FieldUpdateType)}
                        className="text-xs bg-white border border-slate-200 rounded-lg p-2 font-bold focus:outline-none"
                      >
                        <option value="ARRIVED">Arrived on Scene</option>
                        <option value="TASK_STARTED">Task Started</option>
                        <option value="TASK_BLOCKED">Route / Task Blocked</option>
                        <option value="ADDITIONAL_HELP_REQUIRED">Need More Help</option>
                      </select>
                      <input
                        type="text"
                        placeholder="Detail situation on the ground..."
                        value={updateMessage}
                        onChange={(e) => setUpdateMessage(e.target.value)}
                        className="flex-1 text-xs bg-white border border-slate-200 rounded-lg p-2 focus:outline-none"
                      />
                      <button
                        onClick={() => handleSubmitGroundReport(task.task_id)}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg transition-colors"
                      >
                        Send Report
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-8 shadow-sm">
          <OperationalEmptyState
            icon={ShieldCheck}
            title={statusFilter === 'ALL' ? 'NO ACTIVE ASSIGNMENTS' : `NO ${statusFilter} MISSIONS`}
            description="Authoritative response tasks dispatched to your profile will appear here in real-time."
            phaseBadge="FIELD READY"
            accentColor="blue"
          />
        </div>
      )}

      {/* Field Verification Modal */}
      {verifyingTask && (
        <SubmitFieldVerificationModal
          isOpen={!!verifyingTask}
          onClose={() => setVerifyingTask(null)}
          targetId={verifyingTask.situation_id || verifyingTask.task_id}
          targetType={verifyingTask.situation_id ? 'SITUATION' : 'GENERAL_FIELD'}
          targetTitle={verifyingTask.title}
          targetCoords={
            verifyingTask.destination?.latitude !== undefined &&
            verifyingTask.destination?.latitude !== null &&
            verifyingTask.destination?.longitude !== undefined &&
            verifyingTask.destination?.longitude !== null
              ? {
                  latitude: verifyingTask.destination.latitude,
                  longitude: verifyingTask.destination.longitude,
                }
              : null
          }
          onSuccess={() => {
            setActionSuccess('Field verification recorded successfully and contributed to ground truth!');
            loadAssignments();
          }}
        />
      )}
    </div>
  );
};
