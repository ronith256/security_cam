// src/components/settings/GlobalSettings.tsx
import React, { useState, useEffect } from 'react';
import { RotateCw, Save } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { getAllSettings, applySettings, resetDefaultSettings } from '../../api/settings';
import { Setting } from '../../types/settings';
import SettingsCard from './SettingsCard';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { useToast } from '../../context/ToastContext';

const GlobalSettings: React.FC = () => {
  const [settings, setSettings] = useState<Setting[]>([]);
  const { showToast } = useToast();

  const { execute: loadSettings, isLoading: isLoadingSettings, error } = useApi(getAllSettings, {
    onSuccess: (data) => {
      setSettings(data);
    },
  });

  const { execute: executeApply, isLoading: isApplying } = useApi(applySettings, {
    onSuccess: () => {
      showToast('Settings applied to all cameras successfully', 'success');
    },
  });

  const { execute: executeReset, isLoading: isResetting } = useApi(resetDefaultSettings, {
    onSuccess: () => {
      showToast('Settings reset to defaults successfully', 'success');
      loadSettings();
    },
  });

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const handleSettingUpdate = (updatedSetting: Setting) => {
    setSettings((prevSettings) =>
      prevSettings.map((setting) =>
        setting.id === updatedSetting.id ? updatedSetting : setting
      )
    );
  };

  const handleApplySettings = async () => {
    await executeApply();
  };

  const handleResetSettings = async () => {
    if (window.confirm('Are you sure you want to reset all settings to defaults?')) {
      await executeReset();
    }
  };

  if (isLoadingSettings && settings.length === 0) {
    return <Loader text="Loading settings..." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end space-x-3">
        <Button
          variant="warning"
          onClick={handleResetSettings}
          isLoading={isResetting}
          icon={<RotateCw size={16} />}
        >
          Reset to Defaults
        </Button>
        <Button
          variant="primary"
          onClick={handleApplySettings}
          isLoading={isApplying}
          icon={<Save size={16} />}
        >
          Apply to All Cameras
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {settings.map((setting) => (
          <SettingsCard key={setting.id} setting={setting} onUpdate={handleSettingUpdate} />
        ))}
      </div>
    </div>
  );
};

export default GlobalSettings;