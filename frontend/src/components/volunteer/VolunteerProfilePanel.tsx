import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { updateUserProfile } from '../../services/api';
import {
  UserCheck,
  Save,
  MapPin,
  Phone,
  Mail,
  Building,
  CheckCircle2,
  AlertCircle,
  Shield,
} from 'lucide-react';

export const VolunteerProfilePanel: React.FC = () => {
  const { user } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [zone, setZone] = useState(user?.volunteer_profile?.zone_or_district || 'Metro Sector 01');
  const [department, setDepartment] = useState(user?.department_or_agency || user?.department || 'Civil Defense Volunteer Corps');
  const [badgeNumber, setBadgeNumber] = useState(user?.badge_number || '');
  const [address, setAddress] = useState(user?.volunteer_profile?.address || '');

  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);
    try {
      await updateUserProfile({
        full_name: fullName.trim(),
        phone: phone.trim(),
        department: department.trim(),
        badge_number: badgeNumber.trim(),
        volunteer_profile: {
          skills: user?.volunteer_profile?.skills || [],
          availability: user?.volunteer_profile?.availability || 'Available Immediately',
          zone_or_district: zone.trim(),
          address: address.trim(),
        },
      });
      setStatusMsg({ type: 'success', text: 'Volunteer profile & jurisdiction updated successfully.' });
    } catch (err: any) {
      console.error('Failed to update volunteer profile:', err);
      setStatusMsg({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to update profile. Check network connection.',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <UserCheck className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Responder Identity & Operational Zone</h2>
          </div>
          <p className="text-xs text-slate-500">
            Authoritative contact and geographical zone registration used by the Incident Command Center for field dispatching.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5" />
            VERIFIED RESPONDER
          </span>
        </div>
      </div>

      {statusMsg && (
        <div
          className={`p-4 rounded-2xl border flex items-center gap-2 text-xs ${
            statusMsg.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}
        >
          {statusMsg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
          )}
          <span>{statusMsg.text}</span>
        </div>
      )}

      {/* Form Card */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <UserCheck className="w-3.5 h-3.5 text-blue-600" /> Full Name
              </label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                placeholder="e.g. John Doe"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-slate-400" /> Email Address
              </label>
              <input
                type="email"
                disabled
                value={user?.email || ''}
                className="w-full px-3.5 py-2 text-xs bg-slate-100 border border-slate-200 rounded-xl text-slate-500 cursor-not-allowed"
              />
              <span className="text-[10px] text-slate-400 mt-1 block">Account identity bound to login provider.</span>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5 text-blue-600" /> Operational Contact Phone
              </label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                placeholder="+1 555-0199"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-blue-600" /> Primary Operational Zone / District
              </label>
              <select
                value={zone}
                onChange={(e) => setZone(e.target.value)}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
              >
                <option value="Metro Sector 01">Metro Sector 01 (North Downtown)</option>
                <option value="Metro Sector 02">Metro Sector 02 (Harbor / Coastal)</option>
                <option value="Metro Sector 03">Metro Sector 03 (East Valley)</option>
                <option value="Metro Sector 04">Metro Sector 04 (South Suburbs)</option>
                <option value="Metro Sector 05">Metro Sector 05 (Industrial Corridor)</option>
                <option value="Regional District Central">Regional District Central</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <Building className="w-3.5 h-3.5 text-blue-600" /> Volunteer Unit / Organization
              </label>
              <input
                type="text"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                placeholder="e.g. Civil Defense Volunteer Corps"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-blue-600" /> Responder Call Sign / Badge ID
              </label>
              <input
                type="text"
                value={badgeNumber}
                onChange={(e) => setBadgeNumber(e.target.value)}
                className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                placeholder="e.g. RES-VOL-409"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-blue-600" /> Home Base / Staging Address
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
              placeholder="e.g. 742 Evergreen Terrace, Sector 01"
            />
          </div>

          <div className="pt-4 border-t border-slate-100 flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              <Save className="w-3.5 h-3.5" />
              {saving ? 'Saving...' : 'Save Profile Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
