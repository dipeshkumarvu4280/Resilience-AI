import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth, getDashboardRouteForRole } from '../../context/AuthContext';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { EmergencyEmblem } from '../../components/common/EmergencyEmblem';
import {
  Users,
  Check,
  ArrowRight,
  ArrowLeft,
  ShieldAlert,
  HeartPulse,
  Truck,
  Radio,
  Home,
  LifeBuoy,
} from 'lucide-react';

export const VolunteerRegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const { registerVolunteer, initiateGoogleLogin } = useAuth();

  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [zone, setZone] = useState('');
  const [availability, setAvailability] = useState('Available Immediately');
  const [selectedSkills, setSelectedSkills] = useState<string[]>(['First Aid & CPR']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availableSkills = [
    { id: 'first_aid', label: 'First Aid & CPR', icon: HeartPulse },
    { id: 'rescue', label: 'Search & Rescue', icon: LifeBuoy },
    { id: 'medical', label: 'Medical Support (EMT/Nurse)', icon: HeartPulse },
    { id: 'driving', label: 'Emergency / Heavy Driving', icon: Truck },
    { id: 'logistics', label: 'Emergency Logistics & Supply', icon: Truck },
    { id: 'communications', label: 'Radio & Field Comms', icon: Radio },
    { id: 'shelter', label: 'Shelter Coordination', icon: Home },
    { id: 'general', label: 'General Community Support', icon: Users },
  ];

  const toggleSkill = (skillLabel: string) => {
    if (selectedSkills.includes(skillLabel)) {
      setSelectedSkills(selectedSkills.filter((s) => s !== skillLabel));
    } else {
      setSelectedSkills([...selectedSkills, skillLabel]);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError('Password and Confirmation Password do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters in length');
      return;
    }

    if (selectedSkills.length === 0) {
      setError('Please select at least one skill or capability');
      return;
    }

    setLoading(true);

    try {
      const user = await registerVolunteer({
        full_name: fullName,
        phone,
        password,
        skills: selectedSkills,
        availability,
        zone_or_district: zone || undefined,
      });
      navigate(getDashboardRouteForRole(user.role));
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Volunteer registration failed. Please check details.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen text-slate-900 flex flex-col justify-between selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />

      {/* Header Area */}
      <header className="relative z-10 w-full px-6 py-3.5 flex items-center justify-between border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-sm">
        <button
          onClick={() => navigate('/login/volunteer')}
          className="inline-flex items-center gap-2 text-xs font-sans font-semibold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>BACK TO VOLUNTEER LOGIN</span>
        </button>

        <div className="flex items-center gap-2 font-mono text-xs text-slate-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm" />
          <span className="hidden sm:inline font-bold text-slate-800 bg-slate-50 border border-slate-200 px-3 py-1 rounded-full text-[11px]">
            COMMUNITY PORTAL ONLINE
          </span>
        </div>
      </header>

      {/* Registration Card */}
      <main className="relative z-10 max-w-2xl mx-auto px-4 py-8 w-full">
        <div className="p-6 sm:p-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
          {/* Top Title & Badge */}
          <div className="text-center mb-6">
            <div className="inline-flex justify-center mb-3">
              <EmergencyEmblem size="md" showText={false} theme="light" />
            </div>

            <div className="inline-block font-mono text-[10px] uppercase tracking-widest px-3 py-1 rounded-full border border-red-200 bg-red-50 text-[#dc2626] font-bold mb-2">
              PUBLIC VOLUNTEER REGISTRATION
            </div>

            <h1 className="text-xl sm:text-2xl font-black font-sans tracking-tight text-slate-900 uppercase">
              Community Response Network
            </h1>
            <p className="text-xs text-slate-600 mt-1">
              Join your community&apos;s active emergency response network.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-5 p-3.5 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleRegister} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Alex Rivera"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-sans"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Phone Number *
                </label>
                <input
                  type="tel"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="e.g. 9887654321"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Password (min 8 chars) *
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Confirm Password *
                </label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Zone / District / Neighborhood
                </label>
                <input
                  type="text"
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                  placeholder="e.g. North Sector - Ward 4"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-sans"
                />
              </div>

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Current Availability *
                </label>
                <select
                  value={availability}
                  onChange={(e) => setAvailability(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-sans"
                >
                  <option value="Available Immediately">Available Immediately</option>
                  <option value="Standby (Within 2 Hours)">Standby (Within 2 Hours)</option>
                  <option value="Scheduled Shifts Only">Scheduled Shifts Only</option>
                  <option value="Currently Unavailable">Currently Unavailable</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-2 font-bold">
                Select Your Skills & Capabilities *
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {availableSkills.map((sk) => {
                  const Icon = sk.icon;
                  const isSelected = selectedSkills.includes(sk.label);
                  return (
                    <button
                      key={sk.id}
                      type="button"
                      onClick={() => toggleSkill(sk.label)}
                      className={`flex items-center justify-between p-3 rounded-xl border text-left text-xs font-sans font-medium transition-all shadow-sm ${
                        isSelected
                          ? 'border-[#dc2626] bg-red-50/80 text-slate-900 ring-1 ring-red-500/20'
                          : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-slate-100/80'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className={`w-4 h-4 flex-shrink-0 ${isSelected ? 'text-[#dc2626]' : 'text-slate-500'}`} />
                        <span>{sk.label}</span>
                      </div>
                      <div
                        className={`w-4 h-4 rounded flex items-center justify-center border transition-colors ${
                          isSelected ? 'bg-[#dc2626] border-[#dc2626] text-white' : 'border-slate-300 bg-white'
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3.5 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm hover:shadow-md hover:-translate-y-0.5 active:translate-y-0 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>{loading ? 'REGISTERING PROFILE...' : 'COMPLETE VOLUNTEER REGISTRATION'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>

          {/* Google Sign-up Option */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-[10px] uppercase font-mono font-bold">
              <span className="bg-white px-2 text-slate-400">OR</span>
            </div>
          </div>

          <button
            type="button"
            onClick={async () => {
              try {
                await initiateGoogleLogin('VOLUNTEER');
              } catch (err: any) {
                setError(err.response?.data?.detail || err.message || 'Google signup unavailable.');
              }
            }}
            className="w-full py-2.5 px-4 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 font-sans text-xs font-semibold flex items-center justify-center gap-2.5 transition-all shadow-sm"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.26v3.15C3.25 21.37 7.34 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.26C.46 8.16 0 9.94 0 12s.46 3.84 1.26 5.42l4.02-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.25 2.63 1.26 6.58l4.02 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            <span>Register with Google Account</span>
          </button>

          {/* Bottom Sign-In Link */}
          <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs text-slate-500 font-sans">
            Already registered?{' '}
            <Link to="/login/volunteer" className="text-slate-900 hover:text-[#dc2626] font-bold underline">
              Sign In to Volunteer Portal
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 py-4 text-center text-xs font-mono text-slate-400 border-t border-slate-200/60 bg-white/40">
        RESILIENCE COMMUNITY RESPONSE NETWORK • SECURE VOLUNTEER REGISTRATION
      </footer>
    </div>
  );
};


