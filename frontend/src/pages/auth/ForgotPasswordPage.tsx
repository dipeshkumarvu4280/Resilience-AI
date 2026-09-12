import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { EmergencyEmblem } from '../../components/common/EmergencyEmblem';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OTPInput } from '../../components/common/OTPInput';
import api from '../../services/api';
import type { UserRole, OTPRequestResponse } from '../../types';
import {
  ShieldCheck,
  ShieldAlert,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Lock,
  Phone,
  Eye,
  EyeOff,
  Copy,
  Check,
  Sparkles,
} from 'lucide-react';

type Step = 'PHONE' | 'OTP' | 'PASSWORD' | 'SUCCESS';

export const ForgotPasswordPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const roleParam = (searchParams.get('role') || 'EMERGENCY_OFFICER') as UserRole;

  const [step, setStep] = useState<Step>('PHONE');
  const [phone, setPhone] = useState(searchParams.get('phone') || '');
  const [otp, setOtp] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);

  // Prototype Simulated OTP State
  const [demoOtp, setDemoOtp] = useState<string | null>(null);
  const [simulatedMode, setSimulatedMode] = useState<boolean>(true);
  const [cooldownSeconds, setCooldownSeconds] = useState<number>(30);
  const [copied, setCopied] = useState<boolean>(false);

  // Determine return login route based on role
  const getLoginRoute = (role: UserRole) => {
    switch (role) {
      case 'ADMIN':
        return '/login/admin';
      case 'RESOURCE_MANAGER':
        return '/login/resource-manager';
      case 'VOLUNTEER':
        return '/login/volunteer';
      case 'EMERGENCY_OFFICER':
      default:
        return '/login/officer';
    }
  };

  const getRoleBadgeLabel = (role: UserRole) => {
    switch (role) {
      case 'ADMIN':
        return 'SYSTEM CONTROL RECOVERY';
      case 'RESOURCE_MANAGER':
        return 'LOGISTICS & RESOURCE RECOVERY';
      case 'VOLUNTEER':
        return 'VOLUNTEER NETWORK RECOVERY';
      case 'EMERGENCY_OFFICER':
      default:
        return 'OFFICER COMMAND RECOVERY';
    }
  };

  const handleRequestOtp = async (isResend = false, e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanPhone = phone.trim();
    if (!cleanPhone || cleanPhone.length < 10) {
      setError('Please provide a valid registered phone number (minimum 10 digits)');
      return;
    }

    setLoading(true);
    setError(null);
    if (isResend) {
      setOtp('');
    }

    try {
      const res = await api.post<OTPRequestResponse>('/auth/forgot-password/request-otp', {
        phone: cleanPhone,
      });

      const data = res.data;
      setSimulatedMode(Boolean(data.simulated_mode));
      setDemoOtp(data.demo_otp || null);
      if (data.cooldown_seconds) {
        setCooldownSeconds(data.cooldown_seconds);
      }

      if (isResend) {
        setInfoMessage('New prototype verification code generated. Previous code has been invalidated.');
      } else {
        setInfoMessage(data.message || 'Prototype verification code generated');
      }

      setStep('OTP');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to request verification code';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (otpValue?: string) => {
    const code = (otpValue || otp).trim();
    if (!code || code.length !== 6) {
      setError('Please enter the 6-digit verification code');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/auth/forgot-password/verify-otp', {
        phone: phone.trim(),
        otp: code,
      });
      setResetToken(res.data.reset_token);
      setInfoMessage('Code verified successfully. Please create your new secure password.');
      setStep('PASSWORD');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Invalid or expired verification code';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation password do not match');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters in length');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.post('/auth/forgot-password/reset', {
        phone: phone.trim(),
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setStep('SUCCESS');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Password reset failed. Token may have expired.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyDemoOtp = () => {
    if (!demoOtp) return;
    navigator.clipboard.writeText(demoOtp);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAutofillDemoOtp = () => {
    if (!demoOtp) return;
    setOtp(demoOtp);
    setError(null);
  };

  const targetLoginRoute = getLoginRoute(roleParam);

  return (
    <div className="relative min-h-screen text-slate-900 flex flex-col justify-between selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />

      {/* Header */}
      <header className="relative z-10 w-full px-6 py-3.5 flex items-center justify-between border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-sm">
        <button
          onClick={() => navigate(targetLoginRoute)}
          className="inline-flex items-center gap-2 text-xs font-sans font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>RETURN TO LOGIN</span>
        </button>

        <div className="flex items-center gap-2 font-mono text-xs text-slate-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm" />
          <span className="hidden sm:inline font-bold text-slate-800">● SECURITY RECOVERY GATEWAY</span>
        </div>
      </header>

      {/* Main Container */}
      <main className="relative z-10 flex items-center justify-center px-4 py-8 sm:py-10">
        <div className="w-full max-w-md p-6 sm:p-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
          {/* Emblem & Portal Title */}
          <div className="text-center mb-6">
            <div className="inline-flex justify-center mb-3">
              <EmergencyEmblem size="md" showText={false} theme="light" />
            </div>

            <div className="inline-block font-mono text-[10px] uppercase tracking-widest px-2.5 py-0.5 rounded-md border border-slate-200 bg-slate-100 text-slate-700 font-bold mb-2">
              {getRoleBadgeLabel(roleParam)}
            </div>

            <h1 className="text-xl sm:text-2xl font-black font-sans tracking-tight text-slate-900 uppercase">
              Password Recovery
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              {step === 'PHONE' && 'Enter your registered phone number to receive a verification code.'}
              {step === 'OTP' && 'Verify your identity using the prototype verification code.'}
              {step === 'PASSWORD' && 'Establish a new secure password for your operational account.'}
              {step === 'SUCCESS' && 'Your credentials have been successfully updated.'}
            </p>
          </div>

          {/* Stepper Progress */}
          <div className="flex items-center justify-between mb-6 px-2">
            {[
              { id: 'PHONE', label: '1. PHONE' },
              { id: 'OTP', label: '2. VERIFY' },
              { id: 'PASSWORD', label: '3. RESET' },
            ].map((s, idx) => {
              const isActive = step === s.id;
              const isPast =
                (step === 'OTP' && s.id === 'PHONE') ||
                (step === 'PASSWORD' && (s.id === 'PHONE' || s.id === 'OTP')) ||
                step === 'SUCCESS';

              return (
                <div key={s.id} className="flex items-center gap-2">
                  <div
                    className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded border transition-colors ${
                      isActive
                        ? 'border-red-500 bg-red-50 text-red-700 shadow-2xs'
                        : isPast
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-slate-200 bg-slate-50 text-slate-400'
                    }`}
                  >
                    {s.label}
                  </div>
                  {idx < 2 && <div className="w-4 h-0.5 bg-slate-200" />}
                </div>
              );
            })}
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <span className="leading-snug">{error}</span>
            </div>
          )}

          {/* Info / Notice Message */}
          {infoMessage && !error && (
            <div className="mb-4 p-3 rounded-xl bg-blue-50 border border-blue-200 flex items-start gap-2.5 text-xs text-blue-800 font-medium">
              <ShieldCheck className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <span className="leading-snug">{infoMessage}</span>
            </div>
          )}

          {/* STEP 1: PHONE INPUT */}
          {step === 'PHONE' && (
            <form onSubmit={(e) => handleRequestOtp(false, e)} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Registered Phone Number
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                    <Phone className="w-4 h-4" />
                  </div>
                  <input
                    type="tel"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="e.g. 9999999002"
                    className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-400 focus:bg-white font-mono"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm hover:shadow transition-all flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                <span>{loading ? 'GENERATING CODE...' : 'SEND VERIFICATION CODE'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          {/* STEP 2: SIMULATED OTP VERIFICATION */}
          {step === 'OTP' && (
            <div className="space-y-5">
              {/* Prototype Simulated OTP Display Card */}
              {simulatedMode && (
                <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-300/80 text-amber-950 shadow-xs">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase font-bold text-amber-900 tracking-wider">
                      <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                      <span>Prototype verification code</span>
                    </div>
                    <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-amber-200/80 text-amber-900 font-bold border border-amber-300">
                      DEMO MODE
                    </span>
                  </div>

                  {demoOtp ? (
                    <div className="flex items-center justify-between bg-white border border-amber-200 rounded-lg px-3 py-2.5 my-2 shadow-2xs">
                      <div>
                        <div className="text-[10px] uppercase font-mono text-slate-500 font-semibold">Demo OTP</div>
                        <div className="font-mono text-xl sm:text-2xl font-black text-slate-900 tracking-widest">
                          {demoOtp}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleAutofillDemoOtp}
                          className="px-2.5 py-1.5 rounded-md bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-sans font-bold uppercase transition-colors cursor-pointer"
                        >
                          Auto-fill
                        </button>
                        <button
                          type="button"
                          onClick={handleCopyDemoOtp}
                          aria-label="Copy verification code"
                          className="p-1.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 text-xs transition-colors cursor-pointer"
                        >
                          {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-amber-800 italic py-1">
                      If this account exists, a simulated OTP was generated on the server.
                    </div>
                  )}

                  <p className="text-[11px] text-amber-800/90 leading-tight mt-1">
                    Prototype mode — no SMS/email was sent.
                  </p>
                </div>
              )}

              <div className="text-center">
                <p className="text-xs text-slate-600 mb-3">
                  Enter the 6-digit verification code for{' '}
                  <span className="text-slate-900 font-mono font-bold">{phone}</span>
                </p>

                <OTPInput
                  value={otp}
                  onChange={setOtp}
                  onComplete={(code) => handleVerifyOtp(code)}
                  onResend={() => handleRequestOtp(true)}
                  disabled={loading}
                  expiresInSeconds={300}
                  cooldownSeconds={cooldownSeconds}
                />
              </div>

              <button
                type="button"
                onClick={() => handleVerifyOtp()}
                disabled={loading || otp.length !== 6}
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                <span>{loading ? 'VERIFYING CODE...' : 'VERIFY CODE'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                type="button"
                onClick={() => {
                  setStep('PHONE');
                  setError(null);
                  setInfoMessage(null);
                }}
                className="w-full text-center text-xs font-sans text-slate-500 hover:text-slate-900 font-semibold cursor-pointer"
              >
                ← Change Phone Number
              </button>
            </div>
          )}

          {/* STEP 3: NEW PASSWORD */}
          {step === 'PASSWORD' && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  New Password (min 8 characters)
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full pl-9 pr-10 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-400 focus:bg-white font-mono"
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

              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  Confirm New Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-slate-400 focus:bg-white font-mono"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                <span>{loading ? 'UPDATING CREDENTIALS...' : 'RESET PASSWORD'}</span>
                <CheckCircle2 className="w-4 h-4" />
              </button>
            </form>
          )}

          {/* STEP 4: SUCCESS CONFIRMATION */}
          {step === 'SUCCESS' && (
            <div className="text-center py-4 space-y-4">
              <div className="w-14 h-14 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-600 shadow-sm">
                <CheckCircle2 className="w-8 h-8" />
              </div>

              <h2 className="text-base font-bold text-slate-900 font-sans uppercase">
                Password Successfully Reset
              </h2>

              <p className="text-xs text-slate-600 leading-relaxed">
                Your credentials have been updated securely in the RESILIENCE platform. You may now log in with your new password.
              </p>

              <button
                onClick={() => navigate(targetLoginRoute)}
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs font-bold uppercase tracking-wider transition-all shadow-sm cursor-pointer"
              >
                PROCEED TO LOGIN
              </button>
            </div>
          )}

          {/* Bottom Link */}
          <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs font-sans text-slate-500">
            Remember your credentials?{' '}
            <Link to={targetLoginRoute} className="text-slate-900 hover:text-[#dc2626] font-bold underline">
              Return to Login
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 py-4 text-center text-xs font-mono text-slate-400 border-t border-slate-200/60 bg-white/40">
        RESILIENCE IDENTITY RECOVERY GATEWAY • RBAC SECURITY ENFORCED
      </footer>
    </div>
  );
};

export default ForgotPasswordPage;
