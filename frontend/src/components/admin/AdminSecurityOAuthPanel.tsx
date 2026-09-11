import React from 'react';
import { Shield, CheckCircle2, Lock, KeyRound, Globe, Users } from 'lucide-react';
import type { User } from '../../types';

interface AdminSecurityOAuthPanelProps {
  usersList: User[];
}

export const AdminSecurityOAuthPanel: React.FC<AdminSecurityOAuthPanelProps> = ({ usersList }) => {
  const provisionedCount = usersList.filter((u) => u.email).length;
  const linkedCount = usersList.filter((u) => u.google_sub).length;
  const adminCount = usersList.filter((u) => u.role === 'ADMIN').length;
  const officerCount = usersList.filter((u) => u.role === 'EMERGENCY_OFFICER').length;
  const managerCount = usersList.filter((u) => u.role === 'RESOURCE_MANAGER').length;
  const volunteerCount = usersList.filter((u) => u.role === 'VOLUNTEER').length;

  return (
    <div className="space-y-6">
      {/* Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
            <span>GOOGLE OAUTH IDENTITY</span>
            <Globe className="w-4 h-4 text-purple-600" />
          </div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-purple-700">{linkedCount} Linked</div>
          </div>
          <div className="text-[11px] text-slate-500">
            {provisionedCount} authorized operator identities configured
          </div>
        </div>

        <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
            <span>RBAC ACCESS ISOLATION</span>
            <Shield className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="my-2 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            <span className="text-xl font-extrabold text-emerald-700">Strict Enforcement</span>
          </div>
          <div className="text-[11px] text-slate-500">
            Role guards active on all backend API routes
          </div>
        </div>

        <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs">
          <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
            <span>SESSION SECURITY</span>
            <Lock className="w-4 h-4 text-slate-700" />
          </div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-slate-900">JWT HS256</div>
          </div>
          <div className="text-[11px] text-slate-500">
            IDOR checks & Bearer authorization active
          </div>
        </div>
      </div>

      {/* Role Distribution & Privileged Operators */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-purple-600" />
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Role Authority Distribution
            </h3>
          </div>
          <span className="text-xs font-semibold text-slate-500">{usersList.length} Total Users</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3.5 rounded-xl bg-purple-50 border border-purple-200">
            <span className="text-purple-700 font-bold block">SYSTEM ADMIN</span>
            <span className="text-xl font-extrabold text-purple-900 mt-1 block">{adminCount}</span>
            <span className="text-[10px] text-purple-600">Full system & user authority</span>
          </div>

          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200">
            <span className="text-red-700 font-bold block">EMERGENCY OFFICER</span>
            <span className="text-xl font-extrabold text-red-900 mt-1 block">{officerCount}</span>
            <span className="text-[10px] text-red-600">Command, triage, plan review</span>
          </div>

          <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200">
            <span className="text-emerald-700 font-bold block">RESOURCE MANAGER</span>
            <span className="text-xl font-extrabold text-emerald-900 mt-1 block">{managerCount}</span>
            <span className="text-[10px] text-emerald-600">Logistics & stockpile custody</span>
          </div>

          <div className="p-3.5 rounded-xl bg-blue-50 border border-blue-200">
            <span className="text-blue-700 font-bold block">VOLUNTEER RESPONDER</span>
            <span className="text-xl font-extrabold text-blue-900 mt-1 block">{volunteerCount}</span>
            <span className="text-[10px] text-blue-600">Field operations & ground triage</span>
          </div>
        </div>
      </div>

      {/* Security Configuration Details */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
          <KeyRound className="w-4 h-4 text-purple-600" />
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Google OAuth 2.0 PKCE & Identity Binding Architecture
          </h3>
        </div>

        <div className="space-y-3 text-xs text-slate-600 leading-relaxed">
          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
            <div className="font-bold text-slate-800">1. Privileged Operator Email Provisioning</div>
            <p>
              Administrative authorization requires operators to be pre-provisioned in MongoDB with their official Google account email. When an operator authenticates via Google OAuth, the server validates their email against the pre-provisioned registry before binding their immutable Google subject identifier (`google_sub`).
            </p>
          </div>

          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
            <div className="font-bold text-slate-800">2. Volunteer Self-Registration with Google</div>
            <p>
              Volunteers are permitted to self-register using Google OAuth. The system automatically provisions their account with `VOLUNTEER` role and assigns initial readiness status, preventing unauthorized privilege escalation.
            </p>
          </div>

          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-1.5">
            <div className="font-bold text-slate-800">3. Inviolable Role Boundary Enforcement</div>
            <p>
              Role tokens are strictly signed with server-side HMAC-SHA256 secrets. Direct URL navigation to unpermitted portals is intercepted both client-side via React ProtectedRoutes and server-side via FastAPI role dependencies (`require_admin`, `require_officer`, `require_resource_manager`).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
