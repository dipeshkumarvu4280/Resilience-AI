import React from 'react';
import { AuthShell } from '../../components/auth/AuthShell';
import { Users } from 'lucide-react';

export const VolunteerLoginPage: React.FC = () => {
  return (
    <AuthShell
      role="VOLUNTEER"
      title="COMMUNITY RESPONSE NETWORK"
      subtitle="Help your community respond faster."
      badgeLabel="VOLUNTEER RESPONDER ENTRY"
      submitButtonText="SIGN IN"
      icon={Users}
      bottomLink={{
        text: 'New volunteer responder?',
        linkText: 'Create Volunteer Profile',
        to: '/register/volunteer',
      }}
    />
  );
};
