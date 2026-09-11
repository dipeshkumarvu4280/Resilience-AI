import React, { useState, useEffect } from 'react';
import { Settings, Save, RefreshCw, CheckCircle2, AlertTriangle, Sliders, Shield, Bell } from 'lucide-react';
import { getPlatformConfig, updatePlatformConfig } from '../../services/api';
import type { PlatformConfig } from '../../types';

export const AdminPlatformSettingsPanel: React.FC = () => {
  const [config, setConfig] = useState<PlatformConfig>({
    system_name: 'RESILIENCE AI',
    organization_name: 'National Disaster Management Network',
    operational_mode: 'ACTIVE_RESPONSE',
    spatial_cluster_radius_km: 3.5,
    temporal_window_hours: 6,
    ai_coordination_enabled: true,
    require_human_approval_for_dispatch: true,
    monitoring_poll_interval_sec: 15,
    whatsapp_notifications_enabled: true,
    session_timeout_minutes: 120,
    audit_retention_days: 365,
  });

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const fetchConfig = async () => {
    setLoading(true);
    setSaveError(null);
    try {
      const data = await getPlatformConfig();
      if (data) {
        setConfig(data);
      }
    } catch (err: any) {
      console.warn('Failed to load platform settings:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveSuccess(null);
    setSaveError(null);

    try {
      const updated = await updatePlatformConfig(config);
      setConfig(updated);
      setSaveSuccess('Platform configuration updated and persisted to MongoDB Atlas successfully.');
      setTimeout(() => setSaveSuccess(null), 4000);
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || 'Failed to update platform settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Settings className="w-4 h-4 text-purple-600" />
            <span>Operational Platform Settings & Policies</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage system-wide clustering thresholds, multi-agent guards, notification channels, and audit retention.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {config.updated_at && (
            <span className="text-[11px] font-mono text-slate-400">
              Last saved: {new Date(config.updated_at).toLocaleTimeString()}
            </span>
          )}
          <button
            type="button"
            onClick={fetchConfig}
            disabled={loading}
            className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
            title="Reload config"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-purple-600' : ''}`} />
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{saveSuccess}</span>
        </div>
      )}

      {saveError && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-semibold flex items-center gap-2 animate-in fade-in">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{saveError}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Core Identity & Operation Mode */}
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Sliders className="w-3.5 h-3.5 text-purple-600" />
            <span>System Identity & Deployment Mode</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">System Name</label>
              <input
                type="text"
                value={config.system_name}
                onChange={(e) => setConfig({ ...config, system_name: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-500 font-sans"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Organization / Network Authority</label>
              <input
                type="text"
                value={config.organization_name}
                onChange={(e) => setConfig({ ...config, organization_name: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-500 font-sans"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Operational Mode</label>
              <select
                value={config.operational_mode}
                onChange={(e) => setConfig({ ...config, operational_mode: e.target.value })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 font-semibold focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="ACTIVE_RESPONSE">ACTIVE RESPONSE (Live Emergency Dispatch)</option>
                <option value="STANDBY">STANDBY (Monitoring & Preparedness)</option>
                <option value="DRILL">SIMULATION / EXERCISE DRILL</option>
              </select>
            </div>
          </div>
        </div>

        {/* AI & Spatial Fusion Parameters */}
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Shield className="w-3.5 h-3.5 text-purple-600" />
            <span>Situation Intelligence & Multi-Agent Safeguards</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Incident Clustering Radius (km)
              </label>
              <input
                type="number"
                step="0.1"
                min="0.5"
                max="50"
                value={config.spatial_cluster_radius_km}
                onChange={(e) => setConfig({ ...config, spatial_cluster_radius_km: parseFloat(e.target.value) || 3.5 })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-mono text-slate-900"
              />
              <span className="text-[10px] text-slate-400 mt-0.5 block">Distance threshold for auto-fusing citizen reports into a situation cluster</span>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Temporal Window (Hours)
              </label>
              <input
                type="number"
                min="1"
                max="72"
                value={config.temporal_window_hours}
                onChange={(e) => setConfig({ ...config, temporal_window_hours: parseInt(e.target.value, 10) || 6 })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-mono text-slate-900"
              />
              <span className="text-[10px] text-slate-400 mt-0.5 block">Time span for temporal correlation of incoming incident feeds</span>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-200 space-y-2.5 text-xs text-slate-700">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={config.ai_coordination_enabled}
                onChange={(e) => setConfig({ ...config, ai_coordination_enabled: e.target.checked })}
                className="rounded text-purple-600 focus:ring-purple-500 w-4 h-4"
              />
              <span className="font-semibold">Enable Multi-Agent AI Incident Coordination & Resource Suggestion</span>
            </label>

            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={config.require_human_approval_for_dispatch}
                onChange={(e) => setConfig({ ...config, require_human_approval_for_dispatch: e.target.checked })}
                className="rounded text-purple-600 focus:ring-purple-500 w-4 h-4"
              />
              <span className="font-semibold text-emerald-800">
                Enforce Human-in-the-Loop Duty Officer Approval before any field task dispatch (No autonomous dispatch)
              </span>
            </label>
          </div>
        </div>

        {/* Notifications & Audit Retention */}
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700">
            <Bell className="w-3.5 h-3.5 text-purple-600" />
            <span>Notification & Governance Parameters</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Live Monitoring Poll Rate (Seconds)
              </label>
              <input
                type="number"
                min="5"
                max="120"
                value={config.monitoring_poll_interval_sec}
                onChange={(e) => setConfig({ ...config, monitoring_poll_interval_sec: parseInt(e.target.value, 10) || 15 })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-mono text-slate-900"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Audit Trail Retention (Days)
              </label>
              <input
                type="number"
                min="30"
                max="3650"
                value={config.audit_retention_days}
                onChange={(e) => setConfig({ ...config, audit_retention_days: parseInt(e.target.value, 10) || 365 })}
                className="w-full px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-mono text-slate-900"
              />
            </div>
          </div>

          <label className="flex items-center gap-2.5 cursor-pointer pt-2 border-t border-slate-200 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={config.whatsapp_notifications_enabled}
              onChange={(e) => setConfig({ ...config, whatsapp_notifications_enabled: e.target.checked })}
              className="rounded text-purple-600 focus:ring-purple-500 w-4 h-4"
            />
            <span className="font-semibold">Enable Meta WhatsApp Cloud API Notification Channel for Citizens/Volunteers</span>
          </label>
        </div>

        {/* Form Actions */}
        <div className="pt-2 flex items-center justify-end gap-3">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs transition-all disabled:opacity-50"
          >
            {saving ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Persisting Settings...</span>
              </>
            ) : (
              <>
                <Save className="w-3.5 h-3.5" />
                <span>Save Platform Settings</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
