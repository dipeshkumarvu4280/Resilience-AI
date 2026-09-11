import React, { useState } from 'react';
import { Settings, Save, CheckCircle2, Building, Phone, Shield } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { updateUserProfile } from '../../services/api';

export const ResourceManagerSettingsPanel: React.FC = () => {
  const { user } = useAuth();
  const [department, setDepartment] = useState(user?.department_or_agency || 'Emergency Logistics & Disaster Supply Depot');
  const [badge, setBadge] = useState(user?.badge_number || 'LOGISTICS-HQ');
  const [phone, setPhone] = useState(user?.phone || '');
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccess(null);
    try {
      await updateUserProfile({
        department_or_agency: department.trim(),
        badge_number: badge.trim(),
        phone: phone.trim() || undefined,
      });
      setSuccess('Logistics station parameters updated successfully.');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.warn('Failed to update settings:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
        <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center font-bold">
          <Settings className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">Resource Manager Logistics Station Settings</h3>
          <p className="text-xs text-slate-500">Facility assignment, dispatch threshold preferences, and operator credentials.</p>
        </div>
      </div>

      {success && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1">Depot / Facility Assignment</label>
          <div className="relative">
            <Building className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 font-sans"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Station Badge / ID</label>
            <input
              type="text"
              value={badge}
              onChange={(e) => setBadge(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Direct Contact Phone</label>
            <div className="relative">
              <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
              />
            </div>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2 text-xs text-slate-600">
          <div className="font-bold text-slate-800 flex items-center gap-1.5">
            <Shield className="w-4 h-4 text-emerald-600" />
            <span>RBAC Logistics Authority Status</span>
          </div>
          <p>
            Role: <strong className="text-emerald-700">RESOURCE_MANAGER</strong> • Authenticated operator authorized to create assets, adjust inventory, manage vehicle fleets, and verify allocations.
          </p>
        </div>

        <div className="pt-2 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-all disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{saving ? 'Saving...' : 'Save Logistics Profile'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
