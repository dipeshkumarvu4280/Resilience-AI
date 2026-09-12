import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { EmergencyEmblem } from '../common/EmergencyEmblem';
import { TacticalBackground } from '../layout/TacticalBackground';
import { useAuth, getDashboardRouteForRole } from '../../context/AuthContext';
import type { UserRole } from '../../types';
import { Eye, EyeOff, Lock, Phone, ArrowRight, ShieldAlert, ArrowLeft, Loader2 } from 'lucide-react';

interface AuthShellProps {
  role: UserRole;
  title: string;
  subtitle: string;
  accentColor?: string;
  badgeLabel?: string;
  submitButtonText: string;
  bottomLink?: { text: string; linkText: string; to: string };
  defaultPhone?: string;
  icon?: any;
}

export const AuthShell: React.FC<AuthShellProps> = ({
  role,
  title,
  subtitle,
  badgeLabel = 'OFFICIAL ACCESS',
  submitButtonText,
  bottomLink,
  defaultPhone = '',
}) => {
  const navigate = useNavigate();
  const { login, initiateGoogleLogin } = useAuth();

  const [phone, setPhone] = useState(defaultPhone);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanPhone = phone.replace(/\D/g, '').trim();
    if (!cleanPhone) {
      setError('Please enter your registered 10-digit mobile number.');
      return;
    }

    if (cleanPhone.length !== 10) {
      setError('Mobile number must be exactly 10 digits.');
      return;
    }

    if (!password) {
      setError('Please provide your password.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const user = await login(cleanPhone, password, role);
      const target = getDashboardRouteForRole(user.role);
      navigate(target);
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Operational authentication failed. Verify credentials.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleClick = async () => {
    setGoogleLoading(true);
    setError(null);
    try {
      await initiateGoogleLogin(role);
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        err.message ||
        'Unable to initiate Google sign-in. Please try again.';
      setError(detail);
      setGoogleLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen flex flex-col justify-between text-slate-900 selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />

      {/* Top Header */}
      <header className="relative z-10 w-full px-6 py-3.5 flex items-center justify-between border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-sm">
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 text-xs font-sans font-semibold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>RETURN TO PLATFORM LANDING</span>
        </button>

        <div className="flex items-center gap-2 font-mono text-xs text-slate-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm" />
          <span className="hidden sm:inline font-bold text-slate-800">● SYSTEM OPERATIONAL</span>
        </div>
      </header>

      {/* Main Login Card */}
      <main className="relative z-10 flex items-center justify-center px-3 sm:px-4 py-6 sm:py-10">
        <div className="w-full max-w-md p-5 sm:p-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
          {/* Emblem & Portal Title */}
          <div className="text-center mb-6">
            <div className="inline-flex justify-center mb-3">
              <EmergencyEmblem size="lg" showText={false} theme="light" />
            </div>

            <div className="inline-block font-mono text-[10px] uppercase tracking-widest px-2.5 py-0.5 rounded-md border border-slate-200 bg-slate-100 text-slate-700 font-bold mb-2">
              {badgeLabel}
            </div>

            <h1 className="text-xl sm:text-2xl font-black font-sans tracking-tight text-slate-900 uppercase">
              {title}
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              {subtitle}
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1 font-bold">
                Mobile Number
              </label>
              <p className="text-[11px] text-slate-500 mb-1.5 font-sans">
                Enter your registered 10-digit mobile number.
              </p>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Phone className="w-4 h-4" />
                </div>
                <input
                  type="tel"
                  inputMode="numeric"
                  autoComplete="tel"
                  maxLength={10}
                  required
                  value={phone}
                  onChange={(e) => {
                    const val = e.target.value.replace(/\D/g, '').slice(0, 10);
                    setPhone(val);
                  }}
                  placeholder="e.g. 9999999002"
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-400 focus:bg-white transition-all font-mono"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 font-bold">
                  Password
                </label>
                <Link
                  to={`/forgot-password?role=${encodeURIComponent(role)}&phone=${encodeURIComponent(phone)}`}
                  className="text-xs font-sans text-slate-500 hover:text-slate-900 font-medium transition-colors"
                >
                  Forgot Password?
                </Link>
              </div>

              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-9 pr-10 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-400 focus:bg-white transition-all font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-700 cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || googleLoading}
              className="w-full min-h-[44px] py-2.5 px-4 rounded-xl bg-[#dc2626] hover:bg-red-700 text-white font-sans text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-md shadow-red-500/20 disabled:opacity-50 cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                  <span>AUTHENTICATING...</span>
                </>
              ) : (
                <>
                  <span>{submitButtonText}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Social / Alternative Divider */}
          <div className="relative my-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-[10px] uppercase font-mono font-bold">
              <span className="bg-white px-2 text-slate-400">OR</span>
            </div>
          </div>

          {/* Continue with Google */}
          <button
            type="button"
            onClick={handleGoogleClick}
            disabled={googleLoading || loading}
            className="w-full min-h-[44px] py-2.5 px-4 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 font-sans text-xs font-semibold flex items-center justify-center gap-2.5 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
          >
            {googleLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-slate-700" />
                <span>CONNECTING TO GOOGLE OAUTH...</span>
              </>
            ) : (
              <>
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
                <span>Continue with Google</span>
              </>
            )}
          </button>

          {/* Bottom Link */}
          {bottomLink && (
            <div className="mt-5 pt-4 border-t border-slate-100 text-center text-xs text-slate-500 font-sans">
              {bottomLink.text}{' '}
              <Link to={bottomLink.to} className="text-slate-900 hover:text-[#dc2626] font-bold underline">
                {bottomLink.linkText}
              </Link>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 py-4 text-center text-xs font-mono text-slate-400 border-t border-slate-200/60 bg-white/40">
        AUTHORIZED EOC OPERATOR TERMINAL • RBAC SECURITY ENFORCED
      </footer>
    </div>
  );
};

