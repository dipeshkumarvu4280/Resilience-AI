import React, { useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { EmergencyEmblem } from '../../components/common/EmergencyEmblem';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OTPInput } from '../../components/common/OTPInput';
import api from '../../services/api';
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
} from 'lucide-react';

type Step = 'PHONE' | 'OTP' | 'PASSWORD' | 'SUCCESS';

export const ForgotPasswordPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

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

  const handleRequestOtp = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!phone || phone.length < 10) {
      setError('Please provide a valid registered phone number');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/auth/forgot-password/request-otp', { phone });
      setInfoMessage(res.data.message || 'Verification code dispatched to your phone');
      setStep('OTP');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to dispatch verification code';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (otpValue?: string) => {
    const code = otpValue || otp;
    if (!code || code.length !== 6) {
      setError('Please enter the 6-digit verification code');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await api.post('/auth/forgot-password/verify-otp', {
        phone,
        otp: code,
      });
      setResetToken(res.data.reset_token);
      setInfoMessage('Verification confirmed. Please establish your new secure password.');
      setStep('PASSWORD');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Invalid or expired OTP code';
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
        phone,
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setStep('SUCCESS');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Password reset failed. Session may have expired.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen text-slate-900 flex flex-col justify-between selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />

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
          <span className="hidden sm:inline font-bold text-slate-800">● SECURITY RECOVERY GATEWAY</span>
        </div>
      </header>

      <main className="relative z-10 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-md p-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
          <div className="text-center mb-6">
            <div className="inline-flex justify-center mb-3">
              <EmergencyEmblem size="md" showText={false} theme="light" />
            </div>

            <div className="inline-block font-mono text-[10px] uppercase tracking-widest px-2.5 py-0.5 rounded-md border border-slate-200 bg-slate-100 text-slate-700 font-bold mb-2">
              CREDENTIAL RECOVERY
            </div>

            <h1 className="text-xl sm:text-2xl font-black font-sans tracking-tight text-slate-900 uppercase">
              Password Recovery
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              Verify your registered phone number to establish a new password.
            </p>
          </div>

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
                    className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded border ${
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

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-700">
              <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {infoMessage && !error && (
            <div className="mb-4 p-3 rounded-xl bg-blue-50 border border-blue-200 flex items-start gap-2.5 text-xs text-blue-800 font-medium">
              <ShieldCheck className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <span>{infoMessage}</span>
            </div>
          )}

          {step === 'PHONE' && (
            <form onSubmit={handleRequestOtp} className="space-y-4">
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
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm hover:shadow transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>{loading ? 'DISPATCHING CODE...' : 'DISPATCH VERIFICATION OTP'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          {step === 'OTP' && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="text-xs text-slate-600 mb-4">
                  Enter the 6-digit verification code dispatched to{' '}
                  <span className="text-slate-900 font-mono font-bold">{phone}</span>
                </p>

                <OTPInput
                  value={otp}
                  onChange={setOtp}
                  onComplete={(code) => handleVerifyOtp(code)}
                  onResend={() => handleRequestOtp()}
                  disabled={loading}
                  expiresInSeconds={300}
                />
              </div>

              <button
                type="button"
                onClick={() => handleVerifyOtp()}
                disabled={loading || otp.length !== 6}
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>{loading ? 'VERIFYING CODE...' : 'VERIFY & CONTINUE'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                type="button"
                onClick={() => setStep('PHONE')}
                className="w-full text-center text-xs font-sans text-slate-500 hover:text-slate-900 font-semibold"
              >
                ← Change Phone Number
              </button>
            </div>
          )}

          {step === 'PASSWORD' && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-700 mb-1.5 font-bold">
                  New Password (min 8 chars)
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
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-700"
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
                className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-sans text-xs sm:text-sm font-bold tracking-wider uppercase shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              >
                <span>{loading ? 'UPDATING CREDENTIALS...' : 'CONFIRM & RESET PASSWORD'}</span>
                <CheckCircle2 className="w-4 h-4" />
              </button>
            </form>
          )}

          {step === 'SUCCESS' && (
            <div className="text-center py-4 space-y-4">
              <div className="w-14 h-14 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-600 shadow-sm">
                <CheckCircle2 className="w-8 h-8" />
              </div>

              <h2 className="text-base font-bold text-slate-900 font-sans uppercase">
                Password Successfully Reset
              </h2>

              <p className="text-xs text-slate-600 leading-relaxed">
                Your credentials have been updated securely in the RESILIENCE platform.
              </p>

              <button
                onClick={() => navigate('/login/officer')}
                className="w-full py-3 px-4 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs font-bold uppercase transition-all shadow-sm"
              >
                PROCEED TO LOGIN
              </button>
            </div>
          )}

          <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs font-sans text-slate-500">
            Remember your credentials?{' '}
            <Link to="/" className="text-slate-900 hover:text-[#dc2626] font-bold underline">
              Return to Platform Landing
            </Link>
          </div>
        </div>
      </main>

      <footer className="relative z-10 py-4 text-center text-xs font-mono text-slate-400 border-t border-slate-200/60 bg-white/40">
        RESILIENCE IDENTITY RECOVERY GATEWAY • RBAC SECURITY ENFORCED
      </footer>
    </div>
  );
};

export default ForgotPasswordPage;
