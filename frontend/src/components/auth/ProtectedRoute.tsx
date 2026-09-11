import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth, getDashboardRouteForRole } from '../../context/AuthContext';
import type { UserRole } from '../../types';
import { EmergencyEmblem } from '../common/EmergencyEmblem';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  redirectRoleLogin?: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
  redirectRoleLogin = '/login/officer',
}) => {
  const { user, token, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center text-slate-800">
        <EmergencyEmblem size="lg" theme="light" />
        <div className="mt-6 flex items-center gap-2 font-mono text-xs text-slate-600">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          VERIFYING OPERATIONAL IDENTITY & RBAC TOKENS...
        </div>
      </div>
    );
  }

  if (!token || !user) {
    return <Navigate to={redirectRoleLogin} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role) && user.role !== 'ADMIN') {
    const correctRoute = getDashboardRouteForRole(user.role);
    return <Navigate to={correctRoute} replace />;
  }

  return <>{children}</>;
};
