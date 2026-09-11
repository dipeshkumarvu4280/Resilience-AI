import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { EmergencyEmblem } from '../common/EmergencyEmblem';
import { LogOut, Radio, Clock, Shield, Boxes, Users, Lock, Menu } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { UserRole } from '../../types';

import { NotificationBell } from '../notifications/NotificationBell';
import { NotificationDrawer } from '../notifications/NotificationDrawer';
import { NotificationPreferencesModal } from '../notifications/NotificationPreferencesModal';

interface OperationalHeaderProps {
  portalTitle?: string;
  portalSubtitle?: string;
  onNavigateToEntity?: (deepLink: {
    entity_type?: string | null;
    entity_id?: string | null;
    situation_id?: string | null;
    coordination_plan_id?: string | null;
    view_hint?: string | null;
  }) => void;
  onToggleMobileMenu?: () => void;
}

export const OperationalHeader: React.FC<OperationalHeaderProps> = ({
  portalTitle = 'COMMAND CENTER',
  portalSubtitle = 'Emergency Operations Console',
  onNavigateToEntity,
  onToggleMobileMenu,
}) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [time, setTime] = useState(new Date());
  const [showUtc, setShowUtc] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isPrefModalOpen, setIsPrefModalOpen] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const formatOperationalTime = (d: Date) => {
    if (showUtc) {
      return `${d.toISOString().slice(11, 19)} UTC`;
    }
    return `${d.toLocaleTimeString('en-US', { hour12: false })} LOCAL`;
  };

  const getRoleTheme = (role?: UserRole) => {
    switch (role) {
      case 'EMERGENCY_OFFICER':
        return {
          badge: 'bg-red-50 text-red-700 border-red-200',
          avatar: 'bg-red-50 text-[#dc2626] border-red-200',
          icon: Shield,
        };
      case 'RESOURCE_MANAGER':
        return {
          badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
          avatar: 'bg-emerald-50 text-emerald-600 border-emerald-200',
          icon: Boxes,
        };
      case 'VOLUNTEER':
        return {
          badge: 'bg-blue-50 text-blue-700 border-blue-200',
          avatar: 'bg-blue-50 text-blue-600 border-blue-200',
          icon: Users,
        };
      case 'ADMIN':
        return {
          badge: 'bg-purple-50 text-purple-700 border-purple-200',
          avatar: 'bg-purple-50 text-purple-600 border-purple-200',
          icon: Lock,
        };
      default:
        return {
          badge: 'bg-slate-100 text-slate-700 border-slate-200',
          avatar: 'bg-slate-100 text-slate-700 border-slate-200',
          icon: Shield,
        };
    }
  };

  const theme = getRoleTheme(user?.role);

  return (
    <>
      <header className="w-full bg-white/95 border-b border-slate-200/80 px-3 sm:px-6 py-2.5 sm:py-3 flex items-center justify-between z-30 sticky top-0 backdrop-blur-md shadow-xs">
        {/* Left: Mobile Drawer Trigger + Brand & Console Title */}
        <div className="flex items-center gap-2.5 sm:gap-3.5">
          {onToggleMobileMenu && (
            <button
              onClick={onToggleMobileMenu}
              className="md:hidden p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 transition-colors cursor-pointer min-h-[44px] min-w-[44px] flex items-center justify-center touch-manipulation"
              aria-label="Open navigation menu"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}

          <button onClick={() => navigate('/')} className="hover:opacity-90 transition-opacity flex-shrink-0">
            <EmergencyEmblem size="sm" showText={false} theme="light" />
          </button>

          <div className="border-l border-slate-200 pl-2.5 sm:pl-3.5">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="font-extrabold text-xs sm:text-sm font-sans uppercase tracking-wider text-slate-900 truncate max-w-[120px] xs:max-w-[180px] sm:max-w-none">
                {portalTitle}
              </span>
              <span className={`hidden xs:inline-block font-mono text-[9px] font-bold px-1.5 sm:px-2 py-0.5 rounded-md border ${theme.badge}`}>
                {user?.role ? user.role.replace('_', ' ') : 'OPERATIONS'}
              </span>
            </div>
            <div className="hidden sm:block text-[11px] font-sans text-slate-500 truncate max-w-xs">
              {portalSubtitle}
            </div>
          </div>
        </div>

        {/* Center Operational Status & Telemetry */}
        <div className="hidden md:flex items-center gap-4 font-sans text-xs">
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 font-mono text-[11px] text-emerald-800 font-bold shadow-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>SYSTEM OPERATIONAL</span>
          </div>

          <button
            onClick={() => setShowUtc(!showUtc)}
            className="flex items-center gap-1.5 text-slate-700 hover:text-slate-900 transition-colors px-3 py-1 rounded-lg bg-slate-100 hover:bg-slate-200/70 border border-slate-200 font-mono text-[11px] cursor-pointer"
            title="Click to toggle UTC / Local time"
          >
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span className="font-semibold">{formatOperationalTime(time)}</span>
          </button>

          <div className="flex items-center gap-1.5 text-slate-600 font-mono text-[11px] px-2 py-1">
            <Radio className="w-3.5 h-3.5 text-emerald-600" />
            <span className="font-medium">CONNECTED</span>
          </div>
        </div>

        {/* Right Authenticated Operator & Controls */}
        <div className="flex items-center gap-1.5 sm:gap-3">
          {user ? (
            <>
              {/* Notification Bell */}
              <NotificationBell
                onOpenDrawer={() => setIsDrawerOpen(true)}
                refreshTrigger={refreshTrigger}
              />

              <div className="flex items-center gap-2 pl-2 sm:pl-3 border-l border-slate-200">
                <div className={`w-8 h-8 rounded-xl border flex items-center justify-center font-sans font-bold text-xs shadow-xs ${theme.avatar}`}>
                  {user.full_name.charAt(0)}
                </div>
                <div className="hidden lg:block text-left">
                  <div className="text-xs font-bold text-slate-900 font-sans flex items-center gap-1.5">
                    <span>{user.full_name}</span>
                    {user.badge_number && (
                      <span className="text-[10px] font-mono text-slate-500 font-normal">
                        [{user.badge_number}]
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 uppercase font-medium">
                    {user.role.replace('_', ' ')}
                  </div>
                </div>
              </div>

              <button
                onClick={handleLogout}
                className="p-2 min-h-[38px] min-w-[38px] flex items-center justify-center rounded-xl text-slate-500 hover:text-red-700 hover:bg-red-50 border border-slate-200 hover:border-red-200 transition-all shadow-xs cursor-pointer touch-manipulation"
                title="Terminate Operational Session (Logout)"
                aria-label="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button
              onClick={() => navigate('/')}
              className="px-3 py-1.5 rounded-xl text-xs font-sans font-semibold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 shadow-xs cursor-pointer"
            >
              Return to Landing
            </button>
          )}
        </div>
      </header>

      {/* Slide-over Notification Drawer */}
      <NotificationDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        onOpenPreferences={() => {
          setIsDrawerOpen(false);
          setIsPrefModalOpen(true);
        }}
        onNavigateToEntity={onNavigateToEntity}
      />

      {/* Notification Preferences Modal */}
      <NotificationPreferencesModal
        isOpen={isPrefModalOpen}
        onClose={() => setIsPrefModalOpen(false)}
        onSaved={() => setRefreshTrigger((c) => c + 1)}
      />
    </>
  );
};

export default OperationalHeader;

