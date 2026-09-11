import React, { useState, useEffect } from 'react';
import { AlertOctagon, ChevronRight, X } from 'lucide-react';
import { notificationApi } from '../../services/notificationApi';
import type { NotificationUserView } from '../../types';

interface CriticalAlertBannerProps {
  onOpenNotification: (notification: NotificationUserView) => void;
  refreshTrigger?: number;
}

export const CriticalAlertBanner: React.FC<CriticalAlertBannerProps> = ({
  onOpenNotification,
  refreshTrigger = 0,
}) => {
  const [criticalNotif, setCriticalNotif] = useState<NotificationUserView | null>(null);
  const [dismissedId, setDismissedId] = useState<string | null>(null);

  const checkCritical = async () => {
    try {
      const notifs = await notificationApi.getNotifications({
        severity: 'CRITICAL',
        unread_only: true,
        limit: 1,
      });
      if (notifs.length > 0 && notifs[0].notification_id !== dismissedId) {
        setCriticalNotif(notifs[0]);
      } else {
        setCriticalNotif(null);
      }
    } catch {
      // Graceful fallback
    }
  };

  useEffect(() => {
    checkCritical();
    const interval = setInterval(checkCritical, 8000);
    return () => clearInterval(interval);
  }, [refreshTrigger, dismissedId]);

  if (!criticalNotif) return null;

  return (
    <div className="w-full bg-red-600 text-white px-4 py-2.5 flex items-center justify-between shadow-md animate-in slide-in-from-top duration-300">
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="p-1 rounded-md bg-red-700/80 shrink-0">
          <AlertOctagon className="w-4 h-4 text-white animate-pulse" />
        </div>
        <div className="flex items-center gap-2 overflow-hidden text-xs">
          <span className="font-mono font-bold uppercase tracking-wider bg-red-700 px-1.5 py-0.5 rounded text-[10px]">
            CRITICAL ALERT
          </span>
          <strong className="truncate font-sans">{criticalNotif.title}:</strong>
          <span className="truncate text-red-100 hidden sm:inline font-sans">{criticalNotif.message}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => onOpenNotification(criticalNotif)}
          className="px-2.5 py-1 rounded-md bg-white text-red-700 hover:bg-red-50 text-xs font-bold font-sans flex items-center gap-1 shadow-sm transition-colors"
        >
          <span>Review Alert</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => {
            setDismissedId(criticalNotif.notification_id);
            setCriticalNotif(null);
          }}
          className="p-1 rounded text-red-200 hover:text-white hover:bg-red-700 transition-colors"
          title="Dismiss banner"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default CriticalAlertBanner;
