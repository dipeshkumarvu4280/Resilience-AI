import React, { useState, useEffect } from 'react';
import { X, Bell, Phone, Save, CheckCircle2, AlertCircle } from 'lucide-react';
import { notificationApi } from '../../services/notificationApi';

interface NotificationPreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const NotificationPreferencesModal: React.FC<NotificationPreferencesModalProps> = ({
  isOpen,
  onClose,
  onSaved,
}) => {
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [whatsappEnabled, setWhatsappEnabled] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [notifyCritical, setNotifyCritical] = useState(true);
  const [notifyHigh, setNotifyHigh] = useState(true);
  const [notifyOperational, setNotifyOperational] = useState(true);
  const [notifyPlanUpdates, setNotifyPlanUpdates] = useState(true);
  const [notifyMonitoring, setNotifyMonitoring] = useState(true);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadPreferences();
    }
  }, [isOpen]);

  const loadPreferences = async () => {
    setLoading(true);
    setError(null);
    try {
      const pref = await notificationApi.getPreferences();
      setInAppEnabled(pref.in_app_enabled);
      setWhatsappEnabled(pref.whatsapp_enabled);
      setPhoneNumber(pref.phone_number || '');
      setNotifyCritical(pref.notify_critical);
      setNotifyHigh(pref.notify_high);
      setNotifyOperational(pref.notify_operational);
      setNotifyPlanUpdates(pref.notify_plan_updates);
      setNotifyMonitoring(pref.notify_monitoring);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load preferences');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveSuccess(false);

    try {
      await notificationApi.updatePreferences({
        in_app_enabled: inAppEnabled,
        whatsapp_enabled: whatsappEnabled,
        phone_number: phoneNumber.trim() || undefined,
        notify_critical: notifyCritical,
        notify_high: notifyHigh,
        notify_operational: notifyOperational,
        notify_plan_updates: notifyPlanUpdates,
        notify_monitoring: notifyMonitoring,
      });

      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        if (onSaved) onSaved();
        onClose();
      }, 1000);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save notification preferences');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-red-50 text-red-600 border border-red-200/60 shadow-sm">
              <Bell className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-extrabold text-slate-900 font-sans tracking-tight">
                Notification Preferences
              </h3>
              <p className="text-[11px] text-slate-500 font-sans">
                Configure delivery channels and alert thresholds
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSave} className="p-6 space-y-5">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2 font-medium">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {saveSuccess && (
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2 font-medium">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
              <span>Preferences saved successfully!</span>
            </div>
          )}

          {loading ? (
            <div className="py-8 text-center text-xs text-slate-400">Loading user preferences...</div>
          ) : (
            <>
              {/* Channel Toggles */}
              <div className="space-y-3">
                <label className="block text-[11px] font-mono uppercase tracking-wider font-bold text-slate-500">
                  Delivery Channels
                </label>

                {/* In-App Channel */}
                <div className="flex items-center justify-between p-3 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-colors">
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-lg bg-slate-100 text-slate-700">
                      <Bell className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-slate-900 font-sans">In-App Notifications</div>
                      <div className="text-[11px] text-slate-500">Console bell alerts and drawer updates</div>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={inAppEnabled}
                    onChange={(e) => setInAppEnabled(e.target.checked)}
                    className="w-4 h-4 text-red-600 rounded border-slate-300 focus:ring-red-500"
                  />
                </div>

                {/* WhatsApp Channel */}
                <div className="space-y-2 p-3 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="p-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
                        <Phone className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-slate-900 font-sans">WhatsApp Emergency Alerts</div>
                        <div className="text-[11px] text-slate-500">Urgent operational alerts to phone number</div>
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={whatsappEnabled}
                      onChange={(e) => setWhatsappEnabled(e.target.checked)}
                      className="w-4 h-4 text-emerald-600 rounded border-slate-300 focus:ring-emerald-500"
                    />
                  </div>

                  {whatsappEnabled && (
                    <div className="pt-2 border-t border-slate-100">
                      <label className="block text-[10px] font-mono uppercase font-bold text-slate-600 mb-1">
                        Recipient Phone Number (E.164 format)
                      </label>
                      <input
                        type="tel"
                        value={phoneNumber}
                        onChange={(e) => setPhoneNumber(e.target.value)}
                        placeholder="+1234567890"
                        className="w-full px-3 py-1.5 text-xs font-mono rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Alert Category Thresholds */}
              <div className="space-y-3 pt-2">
                <label className="block text-[11px] font-mono uppercase tracking-wider font-bold text-slate-500">
                  Notification Thresholds
                </label>

                <div className="space-y-2">
                  <label className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 text-xs font-sans text-slate-700 cursor-pointer">
                    <span className="font-semibold text-red-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-red-600" /> Critical Severity Emergencies
                    </span>
                    <input
                      type="checkbox"
                      checked={notifyCritical}
                      onChange={(e) => setNotifyCritical(e.target.checked)}
                      className="w-4 h-4 text-red-600 rounded border-slate-300 focus:ring-red-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 text-xs font-sans text-slate-700 cursor-pointer">
                    <span className="font-semibold text-orange-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-orange-500" /> High Priority Incidents
                    </span>
                    <input
                      type="checkbox"
                      checked={notifyHigh}
                      onChange={(e) => setNotifyHigh(e.target.checked)}
                      className="w-4 h-4 text-orange-600 rounded border-slate-300 focus:ring-orange-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 text-xs font-sans text-slate-700 cursor-pointer">
                    <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-slate-400" /> Operational & Resource Updates
                    </span>
                    <input
                      type="checkbox"
                      checked={notifyOperational}
                      onChange={(e) => setNotifyOperational(e.target.checked)}
                      className="w-4 h-4 text-slate-600 rounded border-slate-300 focus:ring-slate-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 text-xs font-sans text-slate-700 cursor-pointer">
                    <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-slate-400" /> Response Plan & Coordination Updates
                    </span>
                    <input
                      type="checkbox"
                      checked={notifyPlanUpdates}
                      onChange={(e) => setNotifyPlanUpdates(e.target.checked)}
                      className="w-4 h-4 text-slate-600 rounded border-slate-300 focus:ring-slate-500"
                    />
                  </label>

                  <label className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 text-xs font-sans text-slate-700 cursor-pointer">
                    <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-slate-400" /> Live Monitoring & Telemetry Alerts
                    </span>
                    <input
                      type="checkbox"
                      checked={notifyMonitoring}
                      onChange={(e) => setNotifyMonitoring(e.target.checked)}
                      className="w-4 h-4 text-slate-600 rounded border-slate-300 focus:ring-slate-500"
                    />
                  </label>
                </div>
              </div>
            </>
          )}

          {/* Modal Footer */}
          <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-xl hover:bg-slate-50 shadow-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || loading}
              className="px-4 py-2 text-xs font-bold text-white bg-red-600 rounded-xl hover:bg-red-700 transition-colors shadow-sm flex items-center gap-1.5 disabled:opacity-50"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Preferences'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default NotificationPreferencesModal;
