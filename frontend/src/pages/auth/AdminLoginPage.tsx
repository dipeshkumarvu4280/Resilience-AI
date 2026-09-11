import React from 'react';
import { AuthShell } from '../../components/auth/AuthShell';
import { Lock } from 'lucide-react';

export const AdminLoginPage: React.FC = () => {
  return (
    <AuthShell
      role="ADMIN"
      title="SYSTEM CONTROL CENTER"
      subtitle="Authorized Administration Access"
      badgeLabel="ROOT SYSTEM CONTROL ACCESS"
      submitButtonText="AUTHENTICATE"
      icon={Lock}
    />
  );
};
