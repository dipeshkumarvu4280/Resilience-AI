import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { updateUserProfile } from '../../services/api';
import {
  Layers,
  CheckCircle2,
  Clock,
  Calendar,
  AlertOctagon,
  AlertCircle,
} from 'lucide-react';

interface AvailabilityTier {
  id: string;
  title: string;
  badge: string;
  description: string;
  noticeRequirement: string;
  icon: any;
  colorClass: string;
}

const AVAILABILITY_TIERS: AvailabilityTier[] = [
  {
    id: 'Available Immediately',
    title: 'Available Immediately',
    badge: 'RAPID MOBILIZATION',
    description: 'You are ready to be dispatched within 15 minutes of an incident notification.',
    noticeRequirement: 'Immediate (0-15m)',
    icon: CheckCircle2,
    colorClass: 'emerald',
  },
  {
    id: 'Standby (Within 2 Hours)',
    title: 'Standby (Within 2 Hours)',
    badge: 'ON CALL',
    description: 'Available for mobilization with up to 2 hours of advance notice.',
    noticeRequirement: 'Short Notice (1-2h)',
    icon: Clock,
    colorClass: 'blue',
  },
  {
    id: 'Scheduled Shifts Only',
    title: 'Scheduled Shifts Only',
    badge: 'PLANNED DUTY',
    description: 'Available only during pre-arranged weekend or evening deployment rosters.',
    noticeRequirement: 'Pre-scheduled',
    icon: Calendar,
    colorClass: 'amber',
  },
  {
    id: 'Currently Unavailable',
    title: 'Currently Unavailable',
    badge: 'OFF DUTY',
    description: 'Temporarily off duty due to travel, rest, or work commitments. No tasks will be dispatched.',
    noticeRequirement: 'Inactive',
    icon: AlertOctagon,
    colorClass: 'slate',
  },
];

export const VolunteerAvailabilityPanel: React.FC = () => {
  const { user } = useAuth();
  const [availability, setAvailability] = useState(
    user?.volunteer_profile?.availability || 'Available Immediately'
  );
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleUpdateAvailability = async (newStatus: string) => {
    setAvailability(newStatus);
    setSaving(true);
    setStatusMsg(null);
    try {
      await updateUserProfile({
        volunteer_profile: {
          skills: user?.volunteer_profile?.skills || [],
          availability: newStatus,
          zone_or_district: user?.volunteer_profile?.zone_or_district || 'Metro Sector 01',
          address: user?.volunteer_profile?.address || '',
        },
      });
      setStatusMsg({
        type: 'success',
        text: `Availability status updated to "${newStatus}". Volunteer matching algorithms updated immediately.`,
      });
    } catch (err: any) {
      console.error('Failed to update availability:', err);
      setStatusMsg({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to update availability status.',
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
            <Layers className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Readiness & Mobilization Lifecycle</h2>
          </div>
          <p className="text-xs text-slate-500">
            Current operational readiness status. Volunteer Agents use this authoritative setting to determine automated dispatch eligibility.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-500">CURRENT STATUS:</span>
          <span className="px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
            {availability}
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

      {/* Availability Tier Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {AVAILABILITY_TIERS.map((tier) => {
          const isSelected = availability === tier.id;
          const Icon = tier.icon;
          return (
            <div
              key={tier.id}
              onClick={() => !saving && handleUpdateAvailability(tier.id)}
              className={`p-5 rounded-2xl border transition-all ${saving ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'} ${
                isSelected
                  ? 'bg-blue-50/40 border-blue-300 shadow-xs'
                  : 'bg-white border-slate-200 hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div
                    className={`p-2.5 rounded-xl border ${
                      isSelected
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-slate-50 text-slate-500 border-slate-200'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-slate-900">{tier.title}</h4>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      {tier.badge}
                    </span>
                  </div>
                </div>

                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center border transition-colors ${
                    isSelected
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : 'border-slate-300 bg-white'
                  }`}
                >
                  {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
                </div>
              </div>

              <p className="text-xs text-slate-600 mt-3 leading-relaxed">{tier.description}</p>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                <span>Response Window: <strong>{tier.noticeRequirement}</strong></span>
                {isSelected ? (
                  <span className="text-blue-700 font-bold">Active Setting</span>
                ) : (
                  <span className="text-slate-400 group-hover:text-slate-600">Click to activate</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
