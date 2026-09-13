import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { ErrorBoundary } from './components/common/ErrorBoundary';

// Pages
import { LandingPage } from './pages/LandingPage';
import { ReportEmergencyPage } from './pages/citizen/ReportEmergencyPage';
import { SafetyGuidancePage } from './pages/SafetyGuidancePage';
import { OfficerLoginPage } from './pages/auth/OfficerLoginPage';
import { ResourceManagerLoginPage } from './pages/auth/ResourceManagerLoginPage';
import { VolunteerLoginPage } from './pages/auth/VolunteerLoginPage';
import { AdminLoginPage } from './pages/auth/AdminLoginPage';
import { VolunteerRegisterPage } from './pages/auth/VolunteerRegisterPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { GoogleCallbackPage } from './pages/auth/GoogleCallbackPage';

// Dashboards
import { OfficerCommandCenter } from './pages/dashboards/OfficerCommandCenter';
import { OfficerMapView } from './pages/dashboards/OfficerMapView';
import { ResourceManagerDashboard } from './pages/dashboards/ResourceManagerDashboard';
import { VolunteerPortal } from './pages/dashboards/VolunteerPortal';
import { AdminControlCenter } from './pages/dashboards/AdminControlCenter';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public Routes */}
          <Route path="/" element={<LandingPage />} />
          <Route
            path="/report-emergency"
            element={
              <ErrorBoundary fallbackTitle="Emergency Report Portal Unavailable" fallbackMessage="The citizen emergency reporting interface could not be loaded. Please refresh or contact emergency services directly.">
                <ReportEmergencyPage />
              </ErrorBoundary>
            }
          />
          <Route path="/citizen/report" element={<ReportEmergencyPage />} />
          <Route
            path="/safety-guidance"
            element={
              <ErrorBoundary fallbackTitle="Safety Guidance Unavailable" fallbackMessage="Unable to display safety guidance.">
                <SafetyGuidancePage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/safety-guidance/:token"
            element={
              <ErrorBoundary fallbackTitle="Safety Guidance Unavailable" fallbackMessage="Unable to display safety guidance.">
                <SafetyGuidancePage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/citizen/safety-guidance"
            element={
              <ErrorBoundary fallbackTitle="Safety Guidance Unavailable" fallbackMessage="Unable to display safety guidance.">
                <SafetyGuidancePage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/citizen/safety-guidance/:token"
            element={
              <ErrorBoundary fallbackTitle="Safety Guidance Unavailable" fallbackMessage="Unable to display safety guidance.">
                <SafetyGuidancePage />
              </ErrorBoundary>
            }
          />
          <Route
            path="/citizen/guidance/:token"
            element={
              <ErrorBoundary fallbackTitle="Safety Guidance Unavailable" fallbackMessage="Unable to display safety guidance.">
                <SafetyGuidancePage />
              </ErrorBoundary>
            }
          />

          
          {/* Role-Specific Login Routes */}
          <Route path="/login/officer" element={<OfficerLoginPage />} />
          <Route path="/login/resource-manager" element={<ResourceManagerLoginPage />} />
          <Route path="/login/volunteer" element={<VolunteerLoginPage />} />
          <Route path="/login/admin" element={<AdminLoginPage />} />
          
          {/* Registration & Recovery */}
          <Route path="/register/volunteer" element={<VolunteerRegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/auth/google/callback" element={<GoogleCallbackPage />} />

          {/* Protected Role-Based Dashboards & Integrated Operations */}
          <Route
            path="/command-center"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/operations/officer"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/operations/officer/reports"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/operations/officer/reports/:reportId"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/operations/officer/map"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerMapView />
              </ProtectedRoute>
            }
          />
          <Route
            path="/command-center/map"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerMapView />
              </ProtectedRoute>
            }
          />
          <Route
            path="/operations/officer/analytics"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/command-center/analytics"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute allowedRoles={['EMERGENCY_OFFICER', 'ADMIN']} redirectRoleLogin="/login/officer">
                <OfficerCommandCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/resource-operations"
            element={
              <ProtectedRoute allowedRoles={['RESOURCE_MANAGER']} redirectRoleLogin="/login/resource-manager">
                <ResourceManagerDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/volunteer-portal"
            element={
              <ProtectedRoute allowedRoles={['VOLUNTEER']} redirectRoleLogin="/login/volunteer">
                <VolunteerPortal />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin-control"
            element={
              <ProtectedRoute allowedRoles={['ADMIN']} redirectRoleLogin="/login/admin">
                <AdminControlCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin-control/analytics"
            element={
              <ProtectedRoute allowedRoles={['ADMIN']} redirectRoleLogin="/login/admin">
                <AdminControlCenter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/analytics"
            element={
              <ProtectedRoute allowedRoles={['ADMIN']} redirectRoleLogin="/login/admin">
                <AdminControlCenter />
              </ProtectedRoute>
            }
          />

          {/* Operational Route Aliases */}
          <Route path="/dashboard" element={<Navigate to="/command-center" replace />} />
          <Route path="/officer" element={<Navigate to="/command-center" replace />} />
          <Route path="/officer/dashboard" element={<Navigate to="/command-center" replace />} />

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
