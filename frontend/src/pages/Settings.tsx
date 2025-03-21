// src/pages/Settings.tsx
import React from 'react';
import PageHeader from '../components/common/PageHeader';
import GlobalSettings from '../components/settings/GlobalSettings';

const Settings: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Global Settings"
        subtitle="Configure system-wide settings"
      />
      
      <GlobalSettings />
    </div>
  );
};

export default Settings;