import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OperationalHeader } from '../../components/layout/OperationalHeader';
import { CommandSidebar } from '../../components/layout/CommandSidebar';
import { OperationalEmptyState } from '../../components/common/OperationalEmptyState';
import { SystemStatusPanel } from '../../components/common/SystemStatusPanel';
import { VolunteerProfilePanel } from '../../components/volunteer/VolunteerProfilePanel';
import { VolunteerSkillsPanel } from '../../components/volunteer/VolunteerSkillsPanel';
import { VolunteerAvailabilityPanel } from '../../components/volunteer/VolunteerAvailabilityPanel';
import { VolunteerAssignmentsPanel } from '../../components/volunteer/VolunteerAssignmentsPanel';
import { VolunteerNotificationsPanel } from '../../components/volunteer/VolunteerNotificationsPanel';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  MapPin,
  Sparkles,
  RefreshCw,
  Truck,
  Home,
  HeartPulse,
  Route as RouteIcon,
} from 'lucide-react';
import {
  listTasks,
  acceptTask,
  startTask,
  completeTask,
  submitFieldUpdate,
  getOperationsOverview,
} from '../../services/fieldOperationsApi';
import { updateUserProfile } from '../../services/api';
import type { ResponseTask, FieldUpdateType, OperationsOverview } from '../../types';

export const VolunteerPortal: React.FC = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [currentAvailability, setCurrentAvailability] = useState(
    user?.volunteer_profile?.availability || 'Available Immediately'
  );

  const volunteerSkills = user?.volunteer_profile?.skills || [
    'Community First Response',
    'Emergency First Aid & CPR',
    'Disaster Shelter Support',
  ];

  // Tasks & Overview State
  const [assignedTasks, setAssignedTasks] = useState<ResponseTask[]>([]);
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [loadingTasks, setLoadingTasks] = useState<boolean>(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Field Update Form State for Active Task
  const [activeUpdateTaskId, setActiveUpdateTaskId] = useState<string | null>(null);
  const [updateType, setUpdateType] = useState<FieldUpdateType>('TASK_STARTED');
  const [updateMessage, setUpdateMessage] = useState<string>('');

  const loadMyAssignments = useCallback(async () => {
    setLoadingTasks(true);
    setActionError(null);
    try {
      const [tasksRes, overviewRes] = await Promise.all([
        listTasks({ assigned_to_me: true, limit: 100 }),
        getOperationsOverview({ assigned_to_me: true }),
      ]);
      setAssignedTasks(tasksRes?.items || []);
      setOverview(overviewRes);
    } catch (err: any) {
      console.error('Failed to load volunteer assignments:', err);
    } finally {
      setLoadingTasks(false);
    }
  }, []);

  useEffect(() => {
    loadMyAssignments();
  }, [loadMyAssignments]);

  const handleQuickAvailabilityChange = async (newAvail: string) => {
    setCurrentAvailability(newAvail);
    try {
      await updateUserProfile({
        volunteer_profile: {
          skills: user?.volunteer_profile?.skills || volunteerSkills,
          availability: newAvail,
          zone_or_district: user?.volunteer_profile?.zone_or_district || 'Metro Sector 01',
          address: user?.volunteer_profile?.address || '',
        },
      });
      setActionSuccess(`Readiness status changed to "${newAvail}".`);
    } catch (err: any) {
      setActionError('Failed to update availability status.');
    }
  };

  const handleAcceptAssignment = async (taskId: string) => {
    try {
      await acceptTask(taskId);
      setActionSuccess(`Mission ${taskId} accepted!`);
      loadMyAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to accept task.');
    }
  };

  const handleStartMission = async (taskId: string) => {
    try {
      await startTask(taskId);
      setActionSuccess(`Mission ${taskId} started.`);
      loadMyAssignments();
    } catch (err: any) {
      setActionError(err.response?.data?.detail || 'Failed to start task.');
    }
  };

  const handleCompleteMission = async (taskId: string) => {
    const notes = prompt('Enter completion report notes:') || 'Mission objectives completed.';
    try {
      await completeTask(taskId, { completion_notes: notes });
      setActionSuccess(`Mission ${taskId} completed successfully!`);
      loadMyAssignments();
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
      setActionSuccess('Ground report logged.');
      setUpdateMessage('');
      setActiveUpdateTaskId(null);
      loadMyAssignments();
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

  return (
    <div className="relative h-screen max-h-screen bg-[#EEF2F6] text-slate-900 flex flex-col font-sans overflow-hidden">
      <TacticalBackground />

      {/* Operational Header */}
      <div className="flex-shrink-0 z-20">
        <OperationalHeader
          portalTitle="COMMUNITY RESPONSE NETWORK"
          portalSubtitle="Volunteer Responder Portal • Rapid Field Tasking"
          onToggleMobileMenu={() => setIsMobileSidebarOpen(true)}
        />
      </div>

      {/* Body Area */}
      <div className="flex-1 flex overflow-hidden min-h-0 z-10">
        {/* Command Navigation Sidebar */}
        <CommandSidebar
          role="VOLUNTEER"
          activeTab={activeTab}
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          onSelectTab={(tab) => {
            setIsMobileSidebarOpen(false);
            setActiveTab(tab);
          }}
          className="hidden md:flex flex-shrink-0 w-64 h-full overflow-y-auto border-r border-slate-200/80 bg-white"
        />

        {/* Main Operational Viewport */}
        <main className="flex-1 h-full overflow-y-auto p-3 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl mx-auto w-full touch-scroll">
          {/* Action Alerts */}
          {actionError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-2xl flex items-center justify-between text-xs text-red-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{actionError}</span>
              </div>
              <button
                onClick={() => setActionError(null)}
                className="text-red-700 font-bold hover:underline cursor-pointer"
              >
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
              <button
                onClick={() => setActionSuccess(null)}
                className="text-emerald-700 font-bold hover:underline cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Conditional View Switching */}
          {activeTab === 'profile' && <VolunteerProfilePanel />}

          {activeTab === 'skills' && <VolunteerSkillsPanel />}

          {activeTab === 'availability' && <VolunteerAvailabilityPanel />}

          {activeTab === 'assignments' && <VolunteerAssignmentsPanel />}

          {activeTab === 'notifications' && <VolunteerNotificationsPanel />}

          {activeTab === 'dashboard' && (
            <>
              {/* Welcome Hero Card */}
              <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-200 text-blue-700 flex items-center justify-center font-bold text-lg flex-shrink-0 shadow-xs">
                    {user?.full_name?.charAt(0) || 'V'}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                        {user?.full_name || 'Volunteer Responder'}
                      </h1>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2.5 py-0.5 rounded-full">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
                        VERIFIED VOLUNTEER
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      Phone: <strong className="text-slate-700">{user?.phone || 'Not recorded'}</strong>{' '}
                      {user?.volunteer_profile?.zone_or_district && `• Zone: ${user.volunteer_profile.zone_or_district}`}
                    </p>
                  </div>
                </div>

                {/* Availability Status Selector */}
                <div className="flex items-center gap-2.5 bg-slate-50 border border-slate-200 p-2 rounded-xl w-full md:w-auto">
                  <span className="text-xs font-semibold text-slate-500 pl-1">STATUS:</span>
                  <select
                    value={currentAvailability}
                    onChange={(e) => handleQuickAvailabilityChange(e.target.value)}
                    className="bg-white border border-slate-200 text-blue-700 text-xs font-semibold rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-2xs cursor-pointer"
                  >
                    <option value="Available Immediately">Available Immediately</option>
                    <option value="Standby (Within 2 Hours)">Standby (Within 2 Hours)</option>
                    <option value="Scheduled Shifts Only">Scheduled Shifts Only</option>
                    <option value="Currently Unavailable">Currently Unavailable</option>
                  </select>
                </div>
              </div>

              {/* Top Operational Telemetry Bar - 5 KPI Cards with Interactive Drill-Downs */}
              {(() => {
                const activeTasks = assignedTasks.filter(
                  (t) => t.status === 'ASSIGNED' || t.status === 'ACCEPTED' || t.status === 'IN_PROGRESS'
                );
                const completedTasks = assignedTasks.filter((t) => t.status === 'COMPLETED');
                const activeCount = overview?.active_tasks_count ?? activeTasks.length;
                const completedCount = overview?.completed_tasks_count ?? completedTasks.length;

                return (
                  <>
                    <div className="grid grid-cols-1 xs:grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                      <div
                        onClick={() => setActiveTab('availability')}
                        className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                      >
                        <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-blue-700 transition-colors">
                          <span>READINESS STATUS</span>
                          <CheckCircle2 className="w-3.5 h-3.5 text-blue-600 group-hover:scale-110 transition-transform" />
                        </div>
                        <div className="my-2">
                          <div className="text-base font-bold text-blue-700 truncate group-hover:scale-105 transition-transform origin-left">{currentAvailability}</div>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>Ready for dispatch</span>
                          <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                        </div>
                      </div>

                      <div
                        onClick={() => setActiveTab('skills')}
                        className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                      >
                        <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-blue-700 transition-colors">
                          <span>REGISTERED SKILLS</span>
                          <Sparkles className="w-3.5 h-3.5 text-blue-600 group-hover:scale-110 transition-transform" />
                        </div>
                        <div className="my-2">
                          <div className="text-2xl font-extrabold text-slate-900 group-hover:scale-105 transition-transform origin-left">{volunteerSkills.length}</div>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>Verified proficiencies</span>
                          <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                        </div>
                      </div>

                      <div
                        onClick={() => setActiveTab('assignments')}
                        className="group p-4 rounded-2xl border border-blue-200/90 bg-blue-50/20 shadow-sm hover:shadow-md hover:border-blue-400 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                      >
                        <div className="flex items-center justify-between text-[11px] font-semibold text-blue-700 uppercase tracking-wider group-hover:text-blue-800 transition-colors">
                          <span>ACTIVE MISSIONS</span>
                          <ShieldCheck className="w-3.5 h-3.5 text-blue-600 group-hover:scale-110 transition-transform" />
                        </div>
                        <div className="my-2 flex items-center gap-2">
                          <span className="text-2xl font-extrabold text-slate-900 group-hover:scale-105 transition-transform origin-left">{activeCount}</span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>{activeCount > 0 ? `${activeCount} task(s) in action` : 'Standby for callouts'}</span>
                          <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                        </div>
                      </div>

                      <div
                        onClick={() => setActiveTab('assignments')}
                        className="group p-4 rounded-2xl border border-emerald-200/90 bg-emerald-50/20 shadow-sm hover:shadow-md hover:border-emerald-400 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                      >
                        <div className="flex items-center justify-between text-[11px] font-semibold text-emerald-700 uppercase tracking-wider group-hover:text-emerald-800 transition-colors">
                          <span>COMPLETED MISSIONS</span>
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 group-hover:scale-110 transition-transform" />
                        </div>
                        <div className="my-2 flex items-center gap-2">
                          <span className="text-2xl font-extrabold text-slate-900 group-hover:scale-105 transition-transform origin-left">{completedCount}</span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>{completedCount > 0 ? `${completedCount} task(s) fulfilled` : 'No completed yet'}</span>
                          <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                        </div>
                      </div>

                      <div
                        onClick={() => setActiveTab('profile')}
                        className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer flex flex-col justify-between col-span-2 sm:col-span-1"
                      >
                        <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-blue-700 transition-colors">
                          <span>ASSIGNED ZONE</span>
                          <MapPin className="w-3.5 h-3.5 text-blue-600 group-hover:scale-110 transition-transform" />
                        </div>
                        <div className="my-2 flex items-center gap-2">
                          <span className="text-base font-bold text-slate-900 truncate group-hover:scale-105 transition-transform origin-left">
                            {user?.volunteer_profile?.zone_or_district || 'Metro Sector 01'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500">
                          <span>Response jurisdiction</span>
                          <span className="text-blue-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                        </div>
                      </div>
                    </div>

                    {/* Registered Capabilities Card */}
                    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm">
                      <div className="flex items-center gap-2 mb-3">
                        <Sparkles className="w-4 h-4 text-blue-600" />
                        <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                          Registered Emergency Skills & Capabilities
                        </h3>
                      </div>
                      <div className="flex flex-wrap gap-2.5">
                        {volunteerSkills.map((sk) => (
                          <span
                            key={sk}
                            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-blue-50/60 border border-blue-200/80 text-blue-800 text-xs font-semibold shadow-2xs"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />
                            <span>{sk}</span>
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Main Layout Grid */}
                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                      {/* Active Emergency Assignments Panel (7 cols) */}
                      <div className="lg:col-span-7 space-y-6">
                        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm">
                          <div className="flex items-center justify-between pb-3.5 border-b border-slate-100 mb-4">
                            <div className="flex items-center gap-2">
                              <AlertTriangle className="w-4 h-4 text-blue-600" />
                              <h3 className="text-sm font-bold text-slate-900 tracking-tight">
                                Active Emergency Assignments
                              </h3>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs px-2.5 py-0.5 rounded-md bg-blue-50 border border-blue-200 text-blue-700 font-semibold">
                                {activeCount} Active Mission{activeCount === 1 ? '' : 's'}
                              </span>
                              <button
                                onClick={loadMyAssignments}
                                className="p-1 text-slate-400 hover:text-slate-700 rounded cursor-pointer"
                                title="Refresh Assignments"
                              >
                                <RefreshCw className={`w-3.5 h-3.5 ${loadingTasks ? 'animate-spin' : ''}`} />
                              </button>
                            </div>
                          </div>

                          {activeTasks.length > 0 ? (
                            <div className="space-y-4">
                              {activeTasks.map((task) => {
                                const TaskIcon = getTaskIcon(task.task_type);
                                return (
                                  <div
                                    key={task.task_id}
                                    className="p-4 bg-slate-50/60 rounded-2xl border border-slate-200 space-y-3"
                                  >
                                    <div className="flex items-start justify-between gap-2">
                                      <div className="flex items-center gap-2">
                                        <div className="p-2 rounded-xl bg-blue-100 text-blue-800">
                                          <TaskIcon className="w-4 h-4" />
                                        </div>
                                        <div>
                                          <h4 className="text-sm font-bold text-slate-900">{task.title}</h4>
                                          <span className="text-[11px] text-slate-500 font-mono">
                                            Task ID: {task.task_id} • Priority: {task.priority}
                                          </span>
                                        </div>
                                      </div>
                                      <span
                                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
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

                                    <p className="text-xs text-slate-600 leading-relaxed">{task.description}</p>

                                    {task.destination && (
                                      <div className="text-[11px] text-slate-500 flex items-center gap-1.5">
                                        <MapPin className="w-3.5 h-3.5 text-blue-600" />
                                        <span>
                                          Rendezvous / Site: <strong>{task.destination.name || task.destination.address}</strong>
                                        </span>
                                      </div>
                                    )}

                                    {/* Action Buttons for Volunteer */}
                                    <div className="pt-2 border-t border-slate-200/60 flex flex-wrap items-center justify-between gap-2">
                                      <div className="flex items-center gap-2">
                                        {task.status === 'ASSIGNED' && (
                                          <button
                                            onClick={() => handleAcceptAssignment(task.task_id)}
                                            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-2xs transition-colors cursor-pointer"
                                          >
                                            Accept Mission
                                          </button>
                                        )}

                                        {task.status === 'ACCEPTED' && (
                                          <button
                                            onClick={() => handleStartMission(task.task_id)}
                                            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-2xs transition-colors cursor-pointer"
                                          >
                                            Start Execution
                                          </button>
                                        )}

                                        {task.status === 'IN_PROGRESS' && (
                                          <>
                                            <button
                                              onClick={() =>
                                                setActiveUpdateTaskId(
                                                  activeUpdateTaskId === task.task_id ? null : task.task_id
                                                )
                                              }
                                              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 transition-colors cursor-pointer"
                                            >
                                              Ground Report
                                            </button>
                                            <button
                                              onClick={() => handleCompleteMission(task.task_id)}
                                              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-2xs transition-colors cursor-pointer"
                                            >
                                              Mark Complete
                                            </button>
                                          </>
                                        )}
                                      </div>
                                    </div>

                                    {/* Ground Report Input Area */}
                                    {activeUpdateTaskId === task.task_id && (
                                      <div className="p-3 bg-white rounded-xl border border-blue-200 space-y-2 text-xs animate-in fade-in duration-100">
                                        <h5 className="font-bold text-slate-800">Submit Ground Status</h5>
                                        <div className="flex gap-2">
                                          <select
                                            value={updateType}
                                            onChange={(e) => setUpdateType(e.target.value as FieldUpdateType)}
                                            className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-1.5 font-bold"
                                          >
                                            <option value="ARRIVED">Arrived on Scene</option>
                                            <option value="TASK_STARTED">Task Started</option>
                                            <option value="TASK_BLOCKED">Route / Task Blocked</option>
                                            <option value="ADDITIONAL_HELP_REQUIRED">Need More Help</option>
                                          </select>
                                          <input
                                            type="text"
                                            placeholder="Update details..."
                                            value={updateMessage}
                                            onChange={(e) => setUpdateMessage(e.target.value)}
                                            className="flex-1 text-xs bg-slate-50 border border-slate-200 rounded-lg p-1.5"
                                          />
                                          <button
                                            onClick={() => handleSubmitGroundReport(task.task_id)}
                                            className="px-3 py-1.5 bg-blue-600 text-white font-bold rounded-lg cursor-pointer"
                                          >
                                            Send
                                          </button>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="py-6">
                              <OperationalEmptyState
                                icon={ShieldCheck}
                                title="NO ACTIVE ASSIGNMENTS"
                                description={`You are currently on standby. All assigned response missions (${completedCount} completed) have been executed successfully.`}
                                phaseBadge="FIELD READY"
                                accentColor="blue"
                              />
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right Column: Completed Missions & System Status (5 cols) */}
                      <div className="lg:col-span-5 space-y-6">
                        {completedTasks.length > 0 && (
                          <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm">
                            <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-3">
                              <div className="flex items-center gap-2">
                                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                <h3 className="text-sm font-bold text-slate-900">
                                  Completed Missions History ({completedTasks.length})
                                </h3>
                              </div>
                            </div>
                            <div className="space-y-2.5 max-h-72 overflow-y-auto pr-1">
                              {completedTasks.map((t) => (
                                <div
                                  key={t.task_id}
                                  className="p-3 bg-slate-50/80 rounded-xl border border-slate-200/80 text-xs space-y-1"
                                >
                                  <div className="flex items-center justify-between font-bold text-slate-900">
                                    <span className="truncate">{t.title}</span>
                                    <span className="text-[10px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                      COMPLETED
                                    </span>
                                  </div>
                                  <div className="text-[11px] text-slate-500 font-mono flex items-center justify-between">
                                    <span>ID: {t.task_id}</span>
                                    <span>{new Date(t.updated_at || t.created_at).toLocaleDateString()}</span>
                                  </div>
                                  {t.completion_notes && (
                                    <p className="text-[11px] text-slate-600 italic bg-white p-2 rounded border border-slate-100 mt-1">
                                      &ldquo;{t.completion_notes}&rdquo;
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <SystemStatusPanel />
                      </div>
                    </div>
                  </>
                );
              })()}
            </>
          )}
        </main>
      </div>
    </div>
  );
};
