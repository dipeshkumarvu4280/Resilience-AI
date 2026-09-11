import React from 'react';
import { AuthShell } from '../../components/auth/AuthShell';
import { Shield } from 'lucide-react';

export const OfficerLoginPage: React.FC = () => {
  return (
    <AuthShell
      role="EMERGENCY_OFFICER"
      title="EMERGENCY OPERATIONS"
      subtitle="Command Center Access"
      badgeLabel="OFFICER COMMAND ENTRY"
      submitButtonText="ENTER COMMAND CENTER"
      icon={Shield}
      bottomLink={{
        text: 'Are you a community responder?',
        linkText: 'Switch to Volunteer Network',
        to: '/login/volunteer',
      }}
    />
  );
};
