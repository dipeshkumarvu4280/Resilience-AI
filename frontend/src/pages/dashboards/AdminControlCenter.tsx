import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OperationalHeader } from '../../components/layout/OperationalHeader';
import { CommandSidebar } from '../../components/layout/CommandSidebar';
import { SystemStatusPanel } from '../../components/common/SystemStatusPanel';
import { EmergencyAnalyticsWorkspace } from '../../components/analytics/EmergencyAnalyticsWorkspace';
import { AdminPlatformSettingsPanel } from '../../components/admin/AdminPlatformSettingsPanel';
import { AdminSecurityOAuthPanel } from '../../components/admin/AdminSecurityOAuthPanel';
import { AdminAuditLogsPanel } from '../../components/admin/AdminAuditLogsPanel';
import api from '../../services/api';
import type { User, UserRole } from '../../types';
import {
  Users,
  Shield,
  RefreshCw,
  CheckCircle2,
  KeyRound,
  X,
  ShieldAlert,
  Loader2,
  Lock,
  Activity,
  FileCheck,
  BarChart3,
} from 'lucide-react';

export const AdminControlCenter: React.FC = () => {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const isAnalyticsRoute = window.location.pathname.includes('analytics');
  const initialTab = searchParams.get('tab') || (isAnalyticsRoute ? 'analytics' : 'users');
  const [activeTab, setActiveTab] = useState(initialTab);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [usersList, setUsersList] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  // Sync tab with URL search parameter
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [searchParams]);

  const handleTabSelect = (tabId: string) => {
    setIsMobileSidebarOpen(false);
    setActiveTab(tabId);
    const params = new URLSearchParams(searchParams);
    params.set('tab', tabId);
    setSearchParams(params);
  };

  // Provisioning Modal State
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [provisionEmail, setProvisionEmail] = useState('');
  const [provisioning, setProvisioning] = useState(false);
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [provisionSuccess, setProvisionSuccess] = useState<string | null>(null);

  const fetchUsers = async () => {
    setLoadingUsers(true);
    try {
      const res = await api.get<User[]>('/users');
      setUsersList(res.data);
    } catch (err) {
      console.warn('Failed to fetch user list:', err);
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const openProvisionModal = (u: User) => {
    setSelectedUser(u);
    setProvisionEmail(u.email || '');
    setProvisionError(null);
    setProvisionSuccess(null);
  };

  const handleSaveProvision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser || !provisionEmail.trim()) {
      setProvisionError('A valid Google email address is required.');
      return;
    }

    setProvisioning(true);
    setProvisionError(null);
    setProvisionSuccess(null);

    try {
      await api.patch(
        `/users/${selectedUser.id}/provision-google`,
        null,
        {
          params: {
            google_email: provisionEmail.trim().toLowerCase(),
          },
        }
      );
      setProvisionSuccess(`Google identity authorized successfully for ${selectedUser.full_name}.`);
      await fetchUsers();
      setTimeout(() => {
        setSelectedUser(null);
      }, 1200);
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || 'Failed to provision Google identity.';
      setProvisionError(detail);
    } finally {
      setProvisioning(false);
    }
  };

  const getRoleBadge = (role: UserRole) => {
    switch (role) {
      case 'ADMIN':
        return (
          <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-purple-50 border border-purple-200 text-purple-700">
            SYSTEM ADMIN
          </span>
        );
      case 'EMERGENCY_OFFICER':
        return (
          <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-red-50 border border-red-200 text-red-700">
            EMERGENCY OFFICER
          </span>
        );
      case 'RESOURCE_MANAGER':
        return (
          <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700">
            RESOURCE MANAGER
          </span>
        );
      case 'VOLUNTEER':
        return (
          <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-blue-50 border border-blue-200 text-blue-700">
            VOLUNTEER
          </span>
        );
      default:
        return (
          <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-slate-100 border border-slate-200 text-slate-700">
            {role}
          </span>
        );
    }
  };

  return (
    <div className="relative h-screen max-h-screen bg-[#EEF2F6] text-slate-900 flex flex-col font-sans overflow-hidden">
      <TacticalBackground />

      {/* Operational Header */}
      <div className="flex-shrink-0 z-20">
        <OperationalHeader
          portalTitle="SYSTEM CONTROL CENTER"
          portalSubtitle="Root Security, RBAC Authorization & Operator Provisioning"
          onToggleMobileMenu={() => setIsMobileSidebarOpen(true)}
        />
      </div>

      {/* Body Area */}
      <div className="flex-1 flex overflow-hidden min-h-0 z-10">
        {/* Command Navigation Sidebar */}
        <CommandSidebar
          role="ADMIN"
          activeTab={activeTab}
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          onSelectTab={handleTabSelect}
          className="hidden md:flex flex-shrink-0 w-64 h-full overflow-y-auto border-r border-slate-200/80 bg-white"
        />

        {/* Main Operational Viewport */}
        <main className="flex-1 h-full overflow-y-auto p-3 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl mx-auto w-full touch-scroll">
          
          {/* Welcome Hero Card */}
          <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-center gap-3 sm:gap-4">
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-purple-50 border border-purple-200 text-purple-700 flex items-center justify-center flex-shrink-0 shadow-xs">
                <Shield className="w-5 h-5 sm:w-6 sm:h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
                    System Administration Control
                  </h1>
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-purple-700 bg-purple-50 border border-purple-200 px-2.5 py-0.5 rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-600 animate-pulse" />
                    ROOT SECURITY ACTIVE
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Logged in as <strong className="text-slate-700 font-semibold">{user?.full_name || 'System Admin'}</strong> ({user?.email}) • Role: <span className="font-semibold text-slate-700">Root Administrator</span>
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
              <button
                onClick={() => handleTabSelect('analytics')}
                className={`inline-flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-xl text-xs font-semibold shadow-xs transition-all w-full sm:w-auto cursor-pointer ${
                  activeTab === 'analytics'
                    ? 'bg-purple-600 text-white border border-purple-600 shadow-sm'
                    : 'bg-white border border-slate-200 hover:bg-purple-50 hover:text-purple-700 text-slate-700'
                }`}
              >
                <BarChart3 className={`w-3.5 h-3.5 ${activeTab === 'analytics' ? 'text-white' : 'text-purple-600'}`} />
                <span>Executive Intelligence</span>
              </button>
              <button
                onClick={fetchUsers}
                disabled={loadingUsers}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition-all w-full sm:w-auto cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingUsers ? 'animate-spin text-purple-400' : 'text-slate-400'}`} />
                <span>Refresh Operators</span>
              </button>
            </div>
          </div>

          {/* Mobile / Tablet Horizontal Navigation Tabs */}
          <div className="flex md:hidden items-center gap-1.5 overflow-x-auto no-scrollbar touch-scroll pb-2 border-b border-slate-200">
            {[
              { id: 'users', label: 'Operators' },
              { id: 'analytics', label: 'Executive Intelligence' },
              { id: 'system-health', label: 'Telemetry' },
              { id: 'security-policies', label: 'Policies' },
              { id: 'audit-logs', label: 'Audit Trail' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => handleTabSelect(tab.id)}
                className={`px-3 py-2 min-h-[36px] rounded-lg text-xs font-semibold whitespace-nowrap transition-colors cursor-pointer ${
                  activeTab === tab.id
                    ? 'bg-purple-600 text-white shadow-xs'
                    : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Top Operational Telemetry Bar - 4 KPI Cards with Interactive Drill-Downs */}
          <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            <div
              onClick={() => handleTabSelect('users')}
              className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-purple-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
            >
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-purple-700 transition-colors">
                <span>AUTHENTICATED OPERATORS</span>
                <Users className="w-3.5 h-3.5 text-purple-600 group-hover:scale-110 transition-transform" />
              </div>
              <div className="my-2">
                <div className="text-2xl font-extrabold text-purple-700 group-hover:scale-105 transition-transform origin-left">
                  {usersList.length} Active
                </div>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>Live database accounts</span>
                <span className="text-purple-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
              </div>
            </div>

            <div
              onClick={() => handleTabSelect('security-policies')}
              className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-purple-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
            >
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-purple-700 transition-colors">
                <span>SYSTEM ADMINISTRATOR</span>
                <Shield className="w-3.5 h-3.5 text-purple-600 group-hover:scale-110 transition-transform" />
              </div>
              <div className="my-2">
                <div className="text-lg font-bold text-slate-900 truncate group-hover:scale-105 transition-transform origin-left">
                  {user?.full_name || 'Admin'}
                </div>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>Role: Full Authority</span>
                <span className="text-purple-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
              </div>
            </div>

            <div
              onClick={() => handleTabSelect('security-policies')}
              className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-emerald-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
            >
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-emerald-700 transition-colors">
                <span>RBAC ENFORCEMENT</span>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 group-hover:scale-110 transition-transform" />
              </div>
              <div className="my-2 flex items-center gap-2">
                <span className="text-base font-bold text-emerald-700 group-hover:scale-105 transition-transform origin-left">
                  Enforced
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>Backend security active</span>
                <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
              </div>
            </div>

            <div
              onClick={() => handleTabSelect('audit-logs')}
              className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-purple-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
            >
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-purple-700 transition-colors">
                <span>DATABASE AUDIT</span>
                <Lock className="w-3.5 h-3.5 text-purple-600 group-hover:scale-110 transition-transform" />
              </div>
              <div className="my-2 flex items-center gap-2">
                <span className="text-base font-bold text-slate-900 group-hover:scale-105 transition-transform origin-left">
                  resilience_db
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>MongoDB Async Motor</span>
                <span className="text-purple-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
              </div>
            </div>
          </div>

          {/* Quick Action Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <button
              onClick={() => handleTabSelect('users')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs cursor-pointer ${
                activeTab === 'users'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center flex-shrink-0 group-hover:bg-purple-600 group-hover:text-white transition-colors">
                <Users className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900 group-hover:text-purple-700">Operator Registry</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Manage accounts & OAuth</div>
              </div>
            </button>

            <button
              onClick={() => handleTabSelect('analytics')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs cursor-pointer ${
                activeTab === 'analytics'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-purple-50/40'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center flex-shrink-0 group-hover:bg-purple-600 group-hover:text-white transition-colors">
                <BarChart3 className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900 group-hover:text-purple-700 flex items-center gap-1">
                  <span>Intelligence</span>
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Response analytics & KPIs</div>
              </div>
            </button>

            <button
              onClick={() => handleTabSelect('system-health')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs ${
                activeTab === 'system-health'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center flex-shrink-0 group-hover:bg-slate-800 group-hover:text-white transition-colors">
                <Activity className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">System Telemetry</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Microservice health</div>
              </div>
            </button>

            <button
              onClick={() => handleTabSelect('system-config')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs ${
                activeTab === 'system-config'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center flex-shrink-0 group-hover:bg-purple-600 group-hover:text-white transition-colors">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Platform Settings</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Parameters & policies</div>
              </div>
            </button>

            <button
              onClick={() => handleTabSelect('security')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs ${
                activeTab === 'security'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center flex-shrink-0 group-hover:bg-slate-800 group-hover:text-white transition-colors">
                <Lock className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Security & OAuth</div>
                <div className="text-[10px] text-slate-500 mt-0.5">RBAC & scope guards</div>
              </div>
            </button>

            <button
              onClick={() => handleTabSelect('audit-logs')}
              className={`p-3.5 rounded-xl border transition-all group flex items-start gap-3 shadow-xs ${
                activeTab === 'audit-logs'
                  ? 'border-purple-300 bg-purple-50/90'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
              }`}
            >
              <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center flex-shrink-0 group-hover:bg-slate-800 group-hover:text-white transition-colors">
                <FileCheck className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-900">Audit Logs</div>
                <div className="text-[10px] text-slate-500 mt-0.5">Immutable trace records</div>
              </div>
            </button>
          </div>

          {/* User & Operator Management Tab */}
          {activeTab === 'users' && (
            <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Users className="w-4 h-4 text-purple-600" />
                    <span>Authorized Operational Accounts & Responders</span>
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Real provisioned operators and registered volunteers in MongoDB. Zero dummy records.
                  </p>
                </div>

                <span className="text-xs font-semibold px-3 py-1 rounded-md bg-purple-50 text-purple-700 border border-purple-200">
                  {usersList.length} Accounts in resilience_db
                </span>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 text-[11px] font-semibold uppercase tracking-wider">
                      <th className="py-3 px-3.5">Operator Name</th>
                      <th className="py-3 px-3.5">Phone Number</th>
                      <th className="py-3 px-3.5">Operational Role</th>
                      <th className="py-3 px-3.5">Google OAuth Identity</th>
                      <th className="py-3 px-3.5">Badge / Sector</th>
                      <th className="py-3 px-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {usersList.map((u) => (
                      <tr key={u.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3.5 px-3.5 font-bold text-slate-900">
                          {u.full_name}
                        </td>
                        <td className="py-3.5 px-3.5 font-mono text-slate-600">
                          {u.phone}
                        </td>
                        <td className="py-3.5 px-3.5">
                          {getRoleBadge(u.role)}
                        </td>
                        <td className="py-3.5 px-3.5">
                          {u.email ? (
                            <div className="flex flex-col">
                              <span className="font-medium text-slate-800">{u.email}</span>
                              {u.google_sub ? (
                                <span className="text-[10px] text-emerald-700 font-semibold flex items-center gap-1 mt-0.5">
                                  ● Sub Linked ({u.google_sub.slice(0, 10)}...)
                                </span>
                              ) : (
                                <span className="text-[10px] text-purple-700 font-semibold mt-0.5">
                                  ○ Authorized (Pending Google Login)
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-400 text-xs italic">Not Provisioned</span>
                          )}
                        </td>
                        <td className="py-3.5 px-3.5 text-slate-500">
                          {u.badge_number || u.volunteer_profile?.zone_or_district || '—'}
                        </td>
                        <td className="py-3.5 px-3.5 text-right">
                          <button
                            onClick={() => openProvisionModal(u)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 text-xs font-semibold transition-all shadow-2xs"
                          >
                            <KeyRound className="w-3.5 h-3.5" />
                            <span>{u.email ? 'Update Google' : 'Provision Google'}</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Platform Settings Tab */}
          {activeTab === 'system-config' && (
            <AdminPlatformSettingsPanel />
          )}

          {/* Security & OAuth Tab */}
          {activeTab === 'security' && (
            <AdminSecurityOAuthPanel usersList={usersList} />
          )}

          {/* Security Audit Logs Tab */}
          {activeTab === 'audit-logs' && (
            <AdminAuditLogsPanel />
          )}

          {activeTab === 'system-health' && (
            <div className="space-y-6">
              <SystemStatusPanel />
            </div>
          )}

          {activeTab === 'analytics' && (
            <EmergencyAnalyticsWorkspace />
          )}
        </main>
      </div>

      {/* Admin Google OAuth Identity Provisioning Modal */}
      {selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="relative w-full max-w-md p-6 rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <button
              onClick={() => setSelectedUser(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-700 p-1 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 mb-3 text-purple-700">
              <div className="w-10 h-10 rounded-xl bg-purple-50 border border-purple-200 flex items-center justify-center">
                <KeyRound className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Provision Operator Google Identity
                </h3>
                <p className="text-xs text-slate-500">
                  Official identity binding for {selectedUser.full_name}
                </p>
              </div>
            </div>

            {provisionError && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2 text-xs text-red-700">
                <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <span>{provisionError}</span>
              </div>
            )}

            {provisionSuccess && (
              <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 flex items-start gap-2 text-xs text-emerald-700">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                <span>{provisionSuccess}</span>
              </div>
            )}

            <form onSubmit={handleSaveProvision} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Authorized Google Email Address
                </label>
                <input
                  type="email"
                  required
                  value={provisionEmail}
                  onChange={(e) => setProvisionEmail(e.target.value)}
                  placeholder="e.g. officer@example.com"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 shadow-2xs font-sans"
                />
                <p className="text-[11px] text-slate-500 mt-1.5 leading-relaxed">
                  When the operator authenticates via Google OAuth, the server validates this email and securely binds their immutable Google sub.
                </p>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setSelectedUser(null)}
                  className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={provisioning}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold transition-all disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
                >
                  {provisioning ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Authorizing...</span>
                    </>
                  ) : (
                    <span>Authorize Operator</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminControlCenter;
