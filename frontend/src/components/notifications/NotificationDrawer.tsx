import React, { useState, useEffect } from 'react';
import {
  X,
  Bell,
  CheckCheck,
  ExternalLink,
  RefreshCw,
  Settings,
} from 'lucide-react';
import { notificationApi } from '../../services/notificationApi';
import type {
  NotificationUserView,
  NotificationSeverity,
  ChannelStatusResponse,
} from '../../types';

interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenPreferences: () => void;
  onNavigateToEntity?: (deepLink: {
    entity_type?: string | null;
    entity_id?: string | null;
    situation_id?: string | null;
    coordination_plan_id?: string | null;
    view_hint?: string | null;
  }) => void;
}

type FilterTab = 'ALL' | 'UNREAD' | 'CRITICAL' | 'OPERATIONAL' | 'PLANS';

export const NotificationDrawer: React.FC<NotificationDrawerProps> = ({
  isOpen,
  onClose,
  onOpenPreferences,
  onNavigateToEntity,
}) => {
  const [notifications, setNotifications] = useState<NotificationUserView[]>([]);
  const [channelStatus, setChannelStatus] = useState<ChannelStatusResponse | null>(null);
  const [activeTab, setActiveTab] = useState<FilterTab>('ALL');
  const [loading, setLoading] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const params: any = { limit: 100 };
      if (activeTab === 'UNREAD') {
        params.unread_only = true;
      } else if (activeTab === 'CRITICAL') {
        params.severity = 'CRITICAL';
      } else if (activeTab === 'OPERATIONAL') {
        params.category = 'RESOURCE_LOGISTICS';
      } else if (activeTab === 'PLANS') {
        params.category = 'COORDINATION_PLAN';
      }

      const [data, count, channels] = await Promise.all([
        notificationApi.getNotifications(params),
        notificationApi.getUnreadCount(),
        notificationApi.getChannelStatus(),
      ]);

      setNotifications(data);
      setUnreadCount(count);
      setChannelStatus(channels);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchNotifications();
    }
  }, [isOpen, activeTab]);

  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await notificationApi.markAsRead(notificationId);
      setNotifications((prev) =>
        prev.map((n) =>
          n.notification_id === notificationId
            ? { ...n, in_app_status: 'READ', read_at: new Date().toISOString() }
            : n
        )
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // Graceful error handling
    }
  };

  const handleMarkAllAsRead = async () => {
    setMarkingAll(true);
    try {
      await notificationApi.markAllAsRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, in_app_status: 'READ', read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch {
      // Graceful error handling
    } finally {
      setMarkingAll(false);
    }
  };

  const getSeverityBadge = (sev: NotificationSeverity) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'HIGH':
        return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'LOW':
      default:
        return 'bg-blue-50 text-blue-700 border-blue-200';
    }
  };

  const getWhatsAppStatusBadge = (status: string) => {
    switch (status) {
      case 'SENT':
      case 'DELIVERED':
      case 'READ':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'QUEUED':
      case 'SENDING':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'FAILED':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'NOT_CONFIGURED':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      case 'SKIPPED':
      default:
        return 'bg-slate-50 text-slate-400 border-slate-200';
    }
  };

  const getSmsStatusBadge = (status?: string) => {
    switch (status) {
      case 'SENT':
      case 'DELIVERED':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'QUEUED':
      case 'SENDING':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'FAILED':
      case 'UNDELIVERED':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'NOT_CONFIGURED':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      case 'SKIPPED':
      default:
        return 'bg-slate-50 text-slate-400 border-slate-200';
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/30 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl border-l border-slate-200 flex flex-col">
          {/* Header */}
          <div className="px-5 py-4 bg-slate-50/80 border-b border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-white border border-slate-200 text-red-600 shadow-sm">
                  <Bell className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-extrabold text-slate-900 font-sans tracking-tight">
                      Notification Center
                    </h2>
                    {unreadCount > 0 && (
                      <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-red-100 text-red-700 border border-red-200">
                        {unreadCount} unread
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 font-sans">
                    Real-time operational alerts & telemetry
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={onOpenPreferences}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-white border border-transparent hover:border-slate-200 transition-all"
                  title="Notification Preferences"
                >
                  <Settings className="w-4 h-4" />
                </button>
                <button
                  onClick={fetchNotifications}
                  disabled={loading}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-white border border-transparent hover:border-slate-200 transition-all disabled:opacity-50"
                  title="Refresh Notifications"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
              {(['ALL', 'UNREAD', 'CRITICAL', 'OPERATIONAL', 'PLANS'] as FilterTab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-2.5 py-1 text-[11px] font-sans font-bold rounded-lg transition-all border whitespace-nowrap ${
                    activeTab === tab
                      ? 'bg-slate-900 text-white border-slate-900 shadow-sm'
                      : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {tab === 'ALL'
                    ? 'All'
                    : tab === 'UNREAD'
                    ? `Unread (${unreadCount})`
                    : tab === 'CRITICAL'
                    ? 'Critical'
                    : tab === 'OPERATIONAL'
                    ? 'Logistics'
                    : 'Plans'}
                </button>
              ))}
            </div>
          </div>

          {/* Channel Health Status Strip */}
          <div className="px-5 py-2 bg-slate-100/70 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-1 text-[10px] font-mono text-slate-600">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span>In-App: <strong className="text-slate-800">OK</strong></span>
              </div>
              <div className="flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    channelStatus?.whatsapp?.configured ? 'bg-emerald-500' : 'bg-slate-400'
                  }`}
                />
                <span>
                  WA:{' '}
                  <strong className={channelStatus?.whatsapp?.configured ? 'text-emerald-700' : 'text-slate-500'}>
                    {channelStatus?.whatsapp?.configured ? 'OK' : 'OFF'}
                  </strong>
                </span>
              </div>
              <div className="flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    channelStatus?.sms?.configured ? 'bg-emerald-500' : 'bg-slate-400'
                  }`}
                />
                <span>
                  SMS:{' '}
                  <strong className={channelStatus?.sms?.configured ? 'text-emerald-700' : 'text-slate-500'}>
                    {channelStatus?.sms?.configured ? 'OK' : 'OFF'}
                  </strong>
                </span>
              </div>
            </div>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllAsRead}
                disabled={markingAll}
                className="text-[10px] font-bold text-red-600 hover:text-red-800 flex items-center gap-1 disabled:opacity-50"
              >
                <CheckCheck className="w-3 h-3" />
                <span>Mark all read</span>
              </button>
            )}
          </div>

          {/* Notifications Feed */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 divide-y divide-slate-100">
            {loading && notifications.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400 font-sans">
                Loading notifications...
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-16 text-center px-4">
                <div className="w-10 h-10 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3 border border-slate-200">
                  <Bell className="w-5 h-5" />
                </div>
                <h4 className="text-xs font-bold text-slate-700 font-sans">
                  Zero Operational Notifications
                </h4>
                <p className="text-[11px] text-slate-500 font-sans mt-1">
                  No notifications match the active filter criteria. Real operational events will appear here automatically.
                </p>
              </div>
            ) : (
              notifications.map((notif) => {
                const isUnread = notif.in_app_status !== 'READ' && !notif.read_at;
                return (
                  <div
                    key={notif.notification_id}
                    className={`pt-3 first:pt-0 transition-colors rounded-xl p-3 border ${
                      isUnread
                        ? notif.severity === 'CRITICAL'
                          ? 'bg-red-50/40 border-red-200/80'
                          : 'bg-amber-50/30 border-amber-200/60'
                        : 'bg-white border-slate-200/70 hover:border-slate-300'
                    }`}
                  >
                    {/* Top Row: Severity, Category, Simulation Tag, Timestamp */}
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`px-1.5 py-0.5 text-[9px] font-mono font-bold rounded border uppercase ${getSeverityBadge(
                            notif.severity
                          )}`}
                        >
                          {notif.severity}
                        </span>

                        {notif.is_simulation && (
                          <span className="px-1.5 py-0.5 text-[9px] font-mono font-bold rounded bg-purple-50 text-purple-700 border border-purple-200 uppercase">
                            [SIMULATION]
                          </span>
                        )}

                        <span className="text-[10px] font-mono font-medium text-slate-500">
                          {notif.category.replace('_', ' ')}
                        </span>
                      </div>

                      <div className="text-[10px] font-mono text-slate-400 shrink-0">
                        {new Date(notif.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>

                    {/* Title & Message */}
                    <h4 className="text-xs font-bold text-slate-900 font-sans tracking-tight mb-1">
                      {notif.title}
                    </h4>
                    <p className="text-[11px] text-slate-600 font-sans leading-relaxed mb-2.5">
                      {notif.message}
                    </p>

                    {/* Bottom Row: Channel Badges & Actions */}
                    <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100 text-[10px]">
                      {/* Channels info */}
                      <div className="flex items-center gap-2 font-mono">
                        <span className="flex items-center gap-1 text-slate-500" title="In-App Delivery">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              isUnread ? 'bg-amber-500' : 'bg-emerald-500'
                            }`}
                          />
                          <span>{isUnread ? 'Unread' : 'Read'}</span>
                        </span>

                        <span
                          className={`px-1.5 py-0.2 rounded border text-[9px] ${getWhatsAppStatusBadge(
                            notif.whatsapp_status
                          )}`}
                          title={`WhatsApp status: ${notif.whatsapp_status}`}
                        >
                          WA: {notif.whatsapp_status.replace('_', ' ')}
                        </span>

                        {notif.sms_status && notif.sms_status !== 'SKIPPED' && notif.sms_status !== 'NOT_CONFIGURED' && (
                          <span
                            className={`px-1.5 py-0.2 rounded border text-[9px] ${getSmsStatusBadge(
                              notif.sms_status
                            )}`}
                            title={`SMS status: ${notif.sms_status}`}
                          >
                            SMS: {notif.sms_status.replace('_', ' ')}
                          </span>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2">
                        {isUnread && (
                          <button
                            onClick={() => handleMarkAsRead(notif.notification_id)}
                            className="text-[10px] font-semibold text-slate-500 hover:text-slate-800"
                          >
                            Mark Read
                          </button>
                        )}

                        {notif.deep_link && onNavigateToEntity && (
                          <button
                            onClick={() => {
                              if (notif.deep_link) {
                                onNavigateToEntity(notif.deep_link);
                                onClose();
                              }
                            }}
                            className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md font-sans font-bold text-[10px] flex items-center gap-1 transition-colors"
                          >
                            <span>Open</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default NotificationDrawer;
