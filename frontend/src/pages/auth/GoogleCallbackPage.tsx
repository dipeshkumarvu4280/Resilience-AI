import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuth, getDashboardRouteForRole } from '../../context/AuthContext';
import { EmergencyEmblem } from '../../components/common/EmergencyEmblem';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { ShieldAlert, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';

export const GoogleCallbackPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleGoogleCallback } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successRole, setSuccessRole] = useState<string | null>(null);

  const hasStartedRef = useRef(false);

  useEffect(() => {
    // Guard against duplicate execution in React 18 Strict Mode or re-renders
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');

    // Check for Google authorization error or cancellation
    if (errorParam) {
      setLoading(false);
      if (errorParam === 'access_denied') {
        setError('Google sign-in was cancelled by the user.');
      } else {
        setError(errorDescription || `Google authentication failed (${errorParam}).`);
      }
      return;
    }

    if (!code) {
      setLoading(false);
      setError('Missing Google authorization response code. Please initiate sign-in again.');
      return;
    }

    // Safety timeout: Ensure loading never hangs indefinitely
    const timeoutId = setTimeout(() => {
      setLoading((prev) => {
        if (prev) {
          setError('Authentication verification timed out. Please check your connection and try again.');
          return false;
        }
        return prev;
      });
    }, 15000);

    const processAuth = async () => {
      try {
        setLoading(true);
        setError(null);
        const user = await handleGoogleCallback(code, state || undefined);
        clearTimeout(timeoutId);
        setSuccessRole(user.role);
        setLoading(false);

        // Immediate redirect to authorized dashboard
        const targetRoute = getDashboardRouteForRole(user.role);
        navigate(targetRoute, { replace: true });
      } catch (err: any) {
        clearTimeout(timeoutId);
        setLoading(false);
        const detail =
          err.response?.data?.detail ||
          err.message ||
          'Google authentication could not be verified by the platform gateway.';
        setError(detail);
      }
    };

    processAuth();

    return () => clearTimeout(timeoutId);
  }, [searchParams, handleGoogleCallback, navigate]);

  return (
    <div className="relative min-h-screen flex flex-col justify-between text-slate-900 selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />

      {/* Top Header */}
      <header className="relative z-10 w-full px-6 py-3.5 flex items-center justify-between border-b border-slate-200 bg-white/95 backdrop-blur-md shadow-sm">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-sans font-semibold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>RETURN TO PLATFORM LANDING</span>
        </Link>

        <div className="flex items-center gap-2 font-mono text-xs text-slate-700">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-sm" />
          <span className="hidden sm:inline font-bold text-slate-800">● OAUTH VERIFICATION GATEWAY</span>
        </div>
      </header>

      {/* Main Container */}
      <main className="relative z-10 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md p-8 rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60 text-center">
          {/* Emblem */}
          <div className="inline-flex justify-center mb-4">
            <EmergencyEmblem size="lg" showText={false} theme="light" />
          </div>

          {loading && (
            <div className="space-y-4 py-4 animate-in fade-in">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-slate-100 text-slate-700">
                <Loader2 className="w-6 h-6 animate-spin text-slate-700" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 tracking-tight uppercase font-sans">
                  Verifying Google Identity
                </h2>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  Authenticating with National Emergency Operations Network...
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-600 font-mono">
                ENCRYPTED TLS SESSION • SERVER-SIDE RBAC VERIFICATION
              </div>
            </div>
          )}

          {!loading && successRole && (
            <div className="space-y-4 py-4 animate-in fade-in">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-600">
                <CheckCircle2 className="w-7 h-7 text-emerald-600" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 tracking-tight uppercase font-sans">
                  Identity Verified
                </h2>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  Access Granted ({successRole}). Loading Operational Console...
                </p>
              </div>
            </div>
          )}

          {!loading && error && (
            <div className="space-y-5 py-2 animate-in fade-in">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-50 text-red-600">
                <ShieldAlert className="w-7 h-7 text-red-600" />
              </div>

              <div>
                <h2 className="text-lg font-bold text-slate-900 tracking-tight uppercase font-sans">
                  Authentication Rejected
                </h2>
                <div className="mt-3 p-4 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 font-medium text-left leading-relaxed">
                  {error}
                </div>
              </div>

              <div className="pt-2 flex flex-col gap-2.5">
                <button
                  onClick={() => (window.history.length > 2 ? navigate(-2) : navigate('/'))}
                  className="w-full py-2.5 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-sans text-xs font-bold tracking-wider uppercase shadow-sm transition-all"
                >
                  Return to Login
                </button>
                <Link
                  to="/"
                  className="text-xs text-slate-500 hover:text-slate-900 font-medium transition-colors"
                >
                  Go to Platform Home
                </Link>
              </div>
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

export default GoogleCallbackPage;
