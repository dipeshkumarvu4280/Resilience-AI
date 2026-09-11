import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { updateUserProfile } from '../../services/api';
import {
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Save,
  AlertCircle,
  HeartPulse,
  Truck,
  LifeBuoy,
  Radio,
  Home,
  Flame,
  Activity,
} from 'lucide-react';

interface SkillOption {
  name: string;
  category: string;
  description: string;
  icon: any;
}

const AVAILABLE_SKILLS: SkillOption[] = [
  {
    name: 'Community First Response',
    category: 'First Response',
    description: 'Rapid on-scene incident assessment, crowd control, and emergency triage support.',
    icon: ShieldCheck,
  },
  {
    name: 'Emergency First Aid & CPR',
    category: 'Medical',
    description: 'Certified BLS/CPR, wound management, splinting, and basic life support in field emergencies.',
    icon: HeartPulse,
  },
  {
    name: 'Disaster Shelter Support',
    category: 'Logistics',
    description: 'Shelter intake registration, bed assignment, family tracking, and relief supplies disbursement.',
    icon: Home,
  },
  {
    name: 'Search & Rescue (Urban)',
    category: 'Operations',
    description: 'Trained in perimeter sweeps, structural hazard marking, and light debris removal.',
    icon: LifeBuoy,
  },
  {
    name: 'Flood & Water Rescue',
    category: 'Operations',
    description: 'Water safety qualified, inflatable boat operation, and aquatic casualty evacuation.',
    icon: Activity,
  },
  {
    name: 'Emergency Logistics & Transport',
    category: 'Logistics',
    description: 'Fleet driving, warehouse staging, cargo unloading, and last-mile supply dispatching.',
    icon: Truck,
  },
  {
    name: 'Field Radio & Communications',
    category: 'Communications',
    description: 'VHF/UHF field transceiver operation, relay dispatching, and offline incident logging.',
    icon: Radio,
  },
  {
    name: 'Wildfire Defense & Brush Clearance',
    category: 'Operations',
    description: 'Firebreak construction, perimeter hydration, and community evacuation assistance.',
    icon: Flame,
  },
];

export const VolunteerSkillsPanel: React.FC = () => {
  const { user } = useAuth();
  const [selectedSkills, setSelectedSkills] = useState<string[]>(
    user?.volunteer_profile?.skills || [
      'Community First Response',
      'Emergency First Aid & CPR',
      'Disaster Shelter Support',
    ]
  );
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const toggleSkill = (skillName: string) => {
    setSelectedSkills((prev) =>
      prev.includes(skillName) ? prev.filter((s) => s !== skillName) : [...prev, skillName]
    );
  };

  const handleSaveSkills = async () => {
    setSaving(true);
    setStatusMsg(null);
    try {
      await updateUserProfile({
        volunteer_profile: {
          skills: selectedSkills,
          availability: user?.volunteer_profile?.availability || 'Available Immediately',
          zone_or_district: user?.volunteer_profile?.zone_or_district || 'Metro Sector 01',
          address: user?.volunteer_profile?.address || '',
        },
      });
      setStatusMsg({
        type: 'success',
        text: 'Skills & capabilities updated in MongoDB. Volunteer Agent will use these for future AI task assignments.',
      });
    } catch (err: any) {
      console.error('Failed to update skills:', err);
      setStatusMsg({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to update skills. Check network connection.',
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
            <Sparkles className="w-5 h-5 text-blue-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">Verified Skills & Operational Capabilities</h2>
          </div>
          <p className="text-xs text-slate-500">
            Select emergency capabilities you are trained and equipped to perform. The Volunteer Agent matches these against active Incident Command tasks.
          </p>
        </div>
        <button
          onClick={handleSaveSkills}
          disabled={saving}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm flex items-center gap-2 transition-colors disabled:opacity-50 self-start md:self-auto"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? 'Saving...' : 'Save Skills Profile'}
        </button>
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

      {/* Skills Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {AVAILABLE_SKILLS.map((skill) => {
          const isSelected = selectedSkills.includes(skill.name);
          const Icon = skill.icon;
          return (
            <div
              key={skill.name}
              onClick={() => toggleSkill(skill.name)}
              className={`p-5 rounded-2xl border cursor-pointer transition-all ${
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
                    <h4 className="text-sm font-bold text-slate-900">{skill.name}</h4>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      {skill.category}
                    </span>
                  </div>
                </div>

                <div
                  className={`w-5 h-5 rounded-md flex items-center justify-center border transition-colors ${
                    isSelected
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : 'border-slate-300 bg-white'
                  }`}
                >
                  {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                </div>
              </div>

              <p className="text-xs text-slate-600 mt-3 leading-relaxed">{skill.description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
