import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  Info,
  AlertOctagon,
  RefreshCw,
  CheckCheck,
} from 'lucide-react';
import notificationApi from '../../services/notificationApi';
import type { NotificationUserView, NotificationSeverity } from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';

export const VolunteerNotificationsPanel: React.FC = () => {
  const [notifications, setNotifications] = useState<NotificationUserView[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await notificationApi.getNotifications({
        unread_only: unreadOnly,
        limit: 50,
      });
      setNotifications(data || []);
    } catch (err) {
      console.error('Failed to load notifications:', err);
    } finally {
      setLoading(false);
    }
  }, [unreadOnly]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  const handleMarkAsRead = async (notificationId: string) => {
    try {
      await notificationApi.markAsRead(notificationId);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notificationId ? { ...n, is_read: true } : n))
      );
    } catch (err) {
      console.error('Failed to mark notification as read:', err);
    }
  };

  const handleMarkAllAsRead = async () => {
    try {
      const count = await notificationApi.markAllAsRead();
      setActionSuccess(`Marked ${count} notifications as read.`);
      loadNotifications();
    } catch (err) {
      console.error('Failed to mark all as read:', err);
    }
  };

  const getSeverityBadge = (severity: NotificationSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return {
          icon: AlertOctagon,
          bg: 'bg-red-50 text-red-700 border-red-200',
        };
      case 'HIGH':
        return {
          icon: AlertTriangle,
          bg: 'bg-amber-50 text-amber-700 border-amber-200',
        };
      case 'MEDIUM':
        return {
          icon: Info,
          bg: 'bg-blue-50 text-blue-700 border-blue-200',
        };
      default:
        return {
          icon: Info,
          bg: 'bg-slate-50 text-slate-700 border-slate-200',
        };
    }
  };

  return (
    <div className="space-y-6">
      {actionSuccess && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl flex items-center justify-between text-xs text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-700 font-bold hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Header */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Bell className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Operational Alerts & Broadcasts</h2>
          </div>
          <p className="text-xs text-slate-500">
            Real-time incident dispatches, evacuation notices, and volunteer coordination alerts.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Unread Only
          </label>

          <button
            onClick={handleMarkAllAsRead}
            className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 flex items-center gap-1.5 transition-colors"
          >
            <CheckCheck className="w-3.5 h-3.5" />
            Mark All Read
          </button>

          <button
            onClick={loadNotifications}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl border border-slate-200 transition-colors"
            title="Refresh alerts"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Notifications List */}
      {notifications.length > 0 ? (
        <div className="space-y-3">
          {notifications.map((notif) => {
            const notifId = notif.notification_id || notif.id || '';
            const isRead = notif.read_at !== null || notif.in_app_status === 'READ' || !!notif.is_read;
            const sev = getSeverityBadge(notif.severity);
            const SevIcon = sev.icon;
            return (
              <div
                key={notifId}
                className={`p-5 rounded-2xl border transition-all ${
                  isRead
                    ? 'bg-white border-slate-200 opacity-80'
                    : 'bg-blue-50/20 border-blue-200 shadow-xs'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className={`p-2.5 rounded-xl border ${sev.bg} flex-shrink-0`}>
                      <SevIcon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-slate-900">{notif.title}</h4>
                        {!isRead && (
                          <span className="w-2 h-2 rounded-full bg-blue-600" title="Unread" />
                        )}
                      </div>
                      <p className="text-xs text-slate-600 mt-1 leading-relaxed">{notif.message}</p>
                      <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-slate-400 font-mono">
                        <span>{new Date(notif.created_at).toLocaleString()}</span>
                        <span>•</span>
                        <span>Category: {notif.category}</span>
                        {notif.deep_link && (
                          <>
                            <span>•</span>
                            <span className="text-blue-600 flex items-center gap-1 font-sans">
                              <span>Ref: {notif.deep_link.entity_type || 'Resource'} #{notif.deep_link.entity_id || notif.deep_link.situation_id || ''}</span>
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {!isRead && (
                    <button
                      onClick={() => handleMarkAsRead(notifId)}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800 p-1.5 hover:bg-blue-50 rounded-lg shrink-0"
                    >
                      Mark Read
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-8 shadow-sm">
          <OperationalEmptyState
            icon={Bell}
            title={unreadOnly ? 'NO UNREAD ALERTS' : 'NO OPERATIONAL ALERTS'}
            description="All response broadcasts and notification messages delivered to your profile will appear here."
            phaseBadge="OPERATIONAL ALERTS"
            accentColor="blue"
          />
        </div>
      )}
    </div>
  );
};
