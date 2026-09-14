import React from 'react';
import {
  LayoutDashboard,
  AlertTriangle,
  FileText,
  Map,
  Truck,
  Home,
  Users,
  Cpu,
  ShieldCheck,
  ClipboardList,
  Settings,
  Package,
  HeartPulse,
  Droplets,
  Layers,
  Send,
  UserCheck,
  Bell,
  Server,
  Key,
  Shield,
  Boxes,
  Lock,
  Activity,
  FlaskConical,
  BarChart3,
  Building2,
  Radio,
  TrendingDown,
  XCircle,
} from 'lucide-react';
import { X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { UserRole } from '../../types';

interface NavItemConfig {
  id: string;
  label: string;
  icon: LucideIcon;
  iconColor: string;
  activeColor: string;
  hoverBg: string;
}

interface CommandSidebarProps {
  role: UserRole;
  activeTab: string;
  onSelectTab: (tabId: string) => void;
  className?: string;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const CommandSidebar: React.FC<CommandSidebarProps> = ({
  role,
  activeTab,
  onSelectTab,
  className = '',
  isOpenMobile = false,
  onCloseMobile,
}) => {
  // Handle escape key to close mobile drawer
  React.useEffect(() => {
    if (!isOpenMobile || !onCloseMobile) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseMobile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpenMobile, onCloseMobile]);

  const getRoleTheme = () => {
    switch (role) {
      case 'EMERGENCY_OFFICER':
        return {
          title: 'EMERGENCY OFFICER',
          badge: 'bg-red-50 text-red-700 border-red-200',
          icon: Shield,
          activeBorder: 'border-l-4 border-l-red-600 bg-red-50/70 text-red-950 font-bold shadow-xs',
          accentText: 'text-red-600',
        };
      case 'RESOURCE_MANAGER':
        return {
          title: 'RESOURCE MANAGER',
          badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
          icon: Boxes,
          activeBorder: 'border-l-4 border-l-emerald-600 bg-emerald-50/70 text-emerald-950 font-bold shadow-xs',
          accentText: 'text-emerald-600',
        };
      case 'VOLUNTEER':
        return {
          title: 'VOLUNTEER RESPONDER',
          badge: 'bg-blue-50 text-blue-700 border-blue-200',
          icon: Users,
          activeBorder: 'border-l-4 border-l-blue-600 bg-blue-50/70 text-blue-950 font-bold shadow-xs',
          accentText: 'text-blue-600',
        };
      case 'ADMIN':
        return {
          title: 'SYSTEM ADMIN',
          badge: 'bg-purple-50 text-purple-700 border-purple-200',
          icon: Lock,
          activeBorder: 'border-l-4 border-l-purple-600 bg-purple-50/70 text-purple-950 font-bold shadow-xs',
          accentText: 'text-purple-600',
        };
      default:
        return {
          title: 'COMMAND CONSOLE',
          badge: 'bg-slate-100 text-slate-700 border-slate-200',
          icon: Shield,
          activeBorder: 'border-l-4 border-l-slate-700 bg-slate-100 text-slate-900 font-bold',
          accentText: 'text-slate-700',
        };
    }
  };

  const getNavItems = (): NavItemConfig[] => {
    switch (role) {
      case 'EMERGENCY_OFFICER':
        return [
          { id: 'command-center', label: 'Command Center', icon: LayoutDashboard, iconColor: 'text-red-500', activeColor: 'text-red-600', hoverBg: 'hover:bg-red-50/50' },
          { id: 'incidents', label: 'Active Incidents', icon: AlertTriangle, iconColor: 'text-amber-500', activeColor: 'text-amber-600', hoverBg: 'hover:bg-amber-50/50' },
          { id: 'reports', label: 'Incident Reports', icon: FileText, iconColor: 'text-blue-500', activeColor: 'text-blue-600', hoverBg: 'hover:bg-blue-50/50' },
          { id: 'rejected-history', label: 'Rejected History', icon: XCircle, iconColor: 'text-rose-500', activeColor: 'text-rose-600', hoverBg: 'hover:bg-rose-50/50' },
          { id: 'live-map', label: 'Live GIS Map', icon: Map, iconColor: 'text-emerald-500', activeColor: 'text-emerald-600', hoverBg: 'hover:bg-emerald-50/50' },
          { id: 'resources', label: 'Resource Coordination', icon: Truck, iconColor: 'text-teal-500', activeColor: 'text-teal-600', hoverBg: 'hover:bg-teal-50/50' },
          { id: 'shelters', label: 'Shelter Facilities', icon: Home, iconColor: 'text-indigo-500', activeColor: 'text-indigo-600', hoverBg: 'hover:bg-indigo-50/50' },
          { id: 'volunteers', label: 'Volunteer Network', icon: Users, iconColor: 'text-sky-500', activeColor: 'text-sky-600', hoverBg: 'hover:bg-sky-50/50' },
          { id: 'sensors', label: 'IoT Sensor Network', icon: Radio, iconColor: 'text-cyan-600', activeColor: 'text-cyan-700', hoverBg: 'hover:bg-cyan-50/50' },
          { id: 'ai-intelligence', label: 'Situation Intelligence', icon: Cpu, iconColor: 'text-purple-500', activeColor: 'text-purple-600', hoverBg: 'hover:bg-purple-50/50' },
          { id: 'response-ops', label: 'Field Operations', icon: ShieldCheck, iconColor: 'text-red-600', activeColor: 'text-red-700', hoverBg: 'hover:bg-red-50/50' },
          { id: 'live-monitoring', label: 'Live Monitoring', icon: Activity, iconColor: 'text-rose-500', activeColor: 'text-rose-600', hoverBg: 'hover:bg-rose-50/50' },
          { id: 'simulation', label: 'What-If Simulation', icon: FlaskConical, iconColor: 'text-violet-500', activeColor: 'text-violet-600', hoverBg: 'hover:bg-violet-50/50' },
          { id: 'analytics', label: 'Emergency Intelligence', icon: BarChart3, iconColor: 'text-red-600', activeColor: 'text-red-700', hoverBg: 'hover:bg-red-50/50' },
          { id: 'audit-log', label: 'Audit Log', icon: ClipboardList, iconColor: 'text-slate-500', activeColor: 'text-slate-700', hoverBg: 'hover:bg-slate-100/60' },
          { id: 'settings', label: 'Settings', icon: Settings, iconColor: 'text-slate-500', activeColor: 'text-slate-700', hoverBg: 'hover:bg-slate-100/60' },
        ];

      case 'RESOURCE_MANAGER':
        return [
          { id: 'operations', label: 'Resource Overview', icon: LayoutDashboard, iconColor: 'text-emerald-500', activeColor: 'text-emerald-600', hoverBg: 'hover:bg-emerald-50/50' },
          { id: 'bottlenecks', label: 'Resource Bottlenecks', icon: TrendingDown, iconColor: 'text-rose-500', activeColor: 'text-rose-600', hoverBg: 'hover:bg-rose-50/50' },
          { id: 'resources', label: 'Inventory Dispatch', icon: Truck, iconColor: 'text-teal-500', activeColor: 'text-teal-600', hoverBg: 'hover:bg-teal-50/50' },
          { id: 'inventory', label: 'Supply Stockpile', icon: Package, iconColor: 'text-amber-500', activeColor: 'text-amber-600', hoverBg: 'hover:bg-amber-50/50' },
          { id: 'vehicles', label: 'Fleet & Vehicles', icon: Truck, iconColor: 'text-blue-500', activeColor: 'text-blue-600', hoverBg: 'hover:bg-blue-50/50' },
          { id: 'medical', label: 'Medical Supplies', icon: HeartPulse, iconColor: 'text-rose-500', activeColor: 'text-rose-600', hoverBg: 'hover:bg-rose-50/50' },
          { id: 'healthcare', label: 'Healthcare Facilities', icon: Building2, iconColor: 'text-indigo-500', activeColor: 'text-indigo-600', hoverBg: 'hover:bg-indigo-50/50' },
          { id: 'food-water', label: 'Rations & Water', icon: Droplets, iconColor: 'text-cyan-500', activeColor: 'text-cyan-600', hoverBg: 'hover:bg-cyan-50/50' },
          { id: 'equipment', label: 'Heavy Equipment', icon: Layers, iconColor: 'text-orange-500', activeColor: 'text-orange-600', hoverBg: 'hover:bg-orange-50/50' },
          { id: 'shelters', label: 'Shelter Capacities', icon: Home, iconColor: 'text-sky-500', activeColor: 'text-sky-600', hoverBg: 'hover:bg-sky-50/50' },
          { id: 'dispatch', label: 'Live Dispatches', icon: Send, iconColor: 'text-emerald-600', activeColor: 'text-emerald-700', hoverBg: 'hover:bg-emerald-50/50' },
          { id: 'settings', label: 'Settings', icon: Settings, iconColor: 'text-slate-500', activeColor: 'text-slate-700', hoverBg: 'hover:bg-slate-100/60' },
        ];

      case 'VOLUNTEER':
        return [
          { id: 'dashboard', label: 'Responder Portal', icon: LayoutDashboard, iconColor: 'text-blue-500', activeColor: 'text-blue-600', hoverBg: 'hover:bg-blue-50/50' },
          { id: 'profile', label: 'My Profile & Zone', icon: UserCheck, iconColor: 'text-indigo-500', activeColor: 'text-indigo-600', hoverBg: 'hover:bg-indigo-50/50' },
          { id: 'skills', label: 'Skills & Capabilities', icon: ShieldCheck, iconColor: 'text-emerald-500', activeColor: 'text-emerald-600', hoverBg: 'hover:bg-emerald-50/50' },
          { id: 'availability', label: 'Availability Status', icon: Layers, iconColor: 'text-amber-500', activeColor: 'text-amber-600', hoverBg: 'hover:bg-amber-50/50' },
          { id: 'assignments', label: 'My Assignments', icon: AlertTriangle, iconColor: 'text-rose-500', activeColor: 'text-rose-600', hoverBg: 'hover:bg-rose-50/50' },
          { id: 'notifications', label: 'Alerts & Broadcasts', icon: Bell, iconColor: 'text-purple-500', activeColor: 'text-purple-600', hoverBg: 'hover:bg-purple-50/50' },
        ];

      case 'ADMIN':
        return [
          { id: 'users', label: 'User & Role Control', icon: Users, iconColor: 'text-purple-500', activeColor: 'text-purple-600', hoverBg: 'hover:bg-purple-50/50' },
          { id: 'analytics', label: 'Executive Intelligence', icon: BarChart3, iconColor: 'text-red-500', activeColor: 'text-red-600', hoverBg: 'hover:bg-red-50/50' },
          { id: 'system-config', label: 'Platform Settings', icon: Settings, iconColor: 'text-slate-500', activeColor: 'text-slate-700', hoverBg: 'hover:bg-slate-100/60' },
          { id: 'security', label: 'Security & OAuth', icon: Key, iconColor: 'text-amber-500', activeColor: 'text-amber-600', hoverBg: 'hover:bg-amber-50/50' },
          { id: 'audit-logs', label: 'Security Audit Logs', icon: ClipboardList, iconColor: 'text-blue-500', activeColor: 'text-blue-600', hoverBg: 'hover:bg-blue-50/50' },
          { id: 'system-health', label: 'System Telemetry', icon: Server, iconColor: 'text-emerald-500', activeColor: 'text-emerald-600', hoverBg: 'hover:bg-emerald-50/50' },
        ];

      default:
        return [];
    }
  };

  const navItems = getNavItems();
  const theme = getRoleTheme();
  const RoleIcon = theme.icon;

  const sidebarContent = (
    <aside
      aria-label="Command Sidebar"
      className={`w-64 bg-white border-r border-slate-200/80 p-3.5 flex flex-col justify-between overflow-y-auto select-none shadow-xs ${className}`}
    >
      <div className="space-y-4">
        {/* Role Portal Indicator Header */}
        <div className="pb-3 border-b border-slate-100 flex items-center justify-between px-2 pt-1">
          <div className="flex items-center gap-2.5">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center border shadow-xs ${theme.badge}`}>
              <RoleIcon className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">
                PORTAL CONSOLE
              </div>
              <div className="text-xs font-bold font-sans text-slate-900 tracking-tight">
                {theme.title}
              </div>
            </div>
          </div>

          {/* Close button inside mobile drawer */}
          {onCloseMobile && (
            <button
              onClick={onCloseMobile}
              className="md:hidden p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
              aria-label="Close navigation drawer"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Navigation Item List */}
        <nav className="space-y-1" role="tablist" aria-orientation="vertical">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                role="tab"
                aria-selected={isActive}
                tabIndex={0}
                onClick={() => {
                  onSelectTab(item.id);
                  if (onCloseMobile) onCloseMobile();
                }}
                className={`group w-full min-h-[44px] flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-sans transition-all duration-200 cursor-pointer text-left focus:outline-hidden focus:ring-2 focus:ring-slate-400/30 touch-manipulation ${
                  isActive
                    ? `${theme.activeBorder}`
                    : `text-slate-600 hover:text-slate-900 ${item.hoverBg} font-medium border-l-4 border-l-transparent`
                }`}
              >
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center transition-transform duration-200 group-hover:scale-110 flex-shrink-0 ${
                    isActive ? 'bg-white shadow-xs' : 'bg-slate-50 group-hover:bg-white'
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 transition-colors duration-200 ${
                      isActive ? item.activeColor : `${item.iconColor} opacity-80 group-hover:opacity-100`
                    }`}
                  />
                </div>
                <span className={`truncate font-medium ${isActive ? 'font-bold text-slate-900' : 'text-slate-700 group-hover:text-slate-900'}`}>
                  {item.label}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Platform Status Card */}
      <div className="pt-4 border-t border-slate-100 px-2 text-xs font-sans text-slate-500">
        <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
          <div className="flex items-center justify-between mb-1">
            <span className="font-mono text-[10px] uppercase text-slate-400 font-bold">SYSTEM STATUS</span>
            <span className="font-mono text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 font-bold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              OPERATIONAL
            </span>
          </div>
          <div className="text-[11px] text-slate-600 font-medium">
            Civil Emergency Response Ready
          </div>
        </div>
      </div>
    </aside>
  );

  // If mobile drawer requested
  if (isOpenMobile) {
    return (
      <div className="fixed inset-0 z-50 md:hidden flex" role="dialog" aria-modal="true" aria-label="Mobile Navigation">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs transition-opacity"
          onClick={onCloseMobile}
        />
        {/* Off-canvas Sidebar Drawer */}
        <div className="relative flex-1 flex flex-col max-w-xs w-full bg-white z-10 shadow-2xl h-full animate-in slide-in-from-left duration-200">
          {sidebarContent}
        </div>
      </div>
    );
  }

  return sidebarContent;
};

export default CommandSidebar;
