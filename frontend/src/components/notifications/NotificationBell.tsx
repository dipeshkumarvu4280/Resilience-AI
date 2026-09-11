import React, { useState, useEffect } from 'react';
import { Bell } from 'lucide-react';
import { notificationApi } from '../../services/notificationApi';

interface NotificationBellProps {
  onOpenDrawer: () => void;
  refreshTrigger?: number;
}

export const NotificationBell: React.FC<NotificationBellProps> = ({
  onOpenDrawer,
  refreshTrigger = 0,
}) => {
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [hasCritical, setHasCritical] = useState<boolean>(false);

  const fetchCount = async () => {
    try {
      const count = await notificationApi.getUnreadCount();
      setUnreadCount(count);

      if (count > 0) {
        const notifs = await notificationApi.getNotifications({ unread_only: true, limit: 10 });
        const hasCrit = notifs.some((n) => n.severity === 'CRITICAL');
        setHasCritical(hasCrit);
      } else {
        setHasCritical(false);
      }
    } catch {
      // Graceful fallback without crashing header
    }
  };

  useEffect(() => {
    fetchCount();
    // Reconcile with backend authoritative unread state every 10 seconds
    const interval = setInterval(fetchCount, 10000);
    return () => clearInterval(interval);
  }, [refreshTrigger]);

  return (
    <button
      onClick={onOpenDrawer}
      className={`relative p-2 rounded-xl border transition-all shadow-sm ${
        hasCritical
          ? 'bg-red-50 text-red-700 border-red-300 hover:bg-red-100 animate-pulse'
          : unreadCount > 0
          ? 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100'
          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:text-slate-900'
      }`}
      title={unreadCount > 0 ? `${unreadCount} unread emergency notifications` : 'Notification Center'}
      aria-label="Notification Center"
    >
      <Bell className="w-4 h-4" />
      {unreadCount > 0 && (
        <span
          className={`absolute -top-1.5 -right-1.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-mono font-bold rounded-full text-white shadow-sm ${
            hasCritical ? 'bg-red-600 animate-bounce' : 'bg-red-600'
          }`}
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  );
};

export default NotificationBell;
