import React from 'react';
import { AuthShell } from '../../components/auth/AuthShell';
import { Truck } from 'lucide-react';

export const ResourceManagerLoginPage: React.FC = () => {
  return (
    <AuthShell
      role="RESOURCE_MANAGER"
      title="RESOURCE OPERATIONS"
      subtitle="Emergency Logistics & Resource Coordination"
      badgeLabel="LOGISTICS & DISPATCH ACCESS"
      submitButtonText="ENTER RESOURCE OPERATIONS"
      icon={Truck}
      bottomLink={{
        text: 'Incident command officer?',
        linkText: 'Switch to Command Center',
        to: '/login/officer',
      }}
    />
  );
};
