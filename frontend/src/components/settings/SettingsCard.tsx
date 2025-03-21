// src/components/settings/SettingsCard.tsx
import React, { useState } from 'react';
import { Save, RefreshCw } from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import { Setting, SettingUpdate } from '../../types/settings';
import { updateSetting } from '../../api/settings';
import { useApi } from '../../hooks/useApi';
import { useToast } from '../../context/ToastContext';

interface SettingsCardProps {
  setting: Setting;
  onUpdate: (setting: Setting) => void;
}

const SettingsCard: React.FC<SettingsCardProps> = ({ setting, onUpdate }) => {
  const [value, setValue] = useState(setting.value);
  const [isEditing, setIsEditing] = useState(false);
  const { showToast } = useToast();

  const { execute: executeSave, isLoading: isSaving } = useApi(
    (key: string, update: SettingUpdate) => updateSetting(key, update),
    {
      onSuccess: (updatedSetting) => {
        onUpdate(updatedSetting);
        setIsEditing(false);
        showToast('Setting updated successfully', 'success');
      },
    }
  );

  const handleSave = async () => {
    await executeSave(setting.key, { value });
  };

  const handleReset = () => {
    setValue(setting.value);
    setIsEditing(false);
  };

  const renderEditor = () => {
    const type = typeof setting.value;

    if (type === 'boolean') {
      return (
        <div className="flex items-center">
          <input
            type="checkbox"
            id={`setting-${setting.id}`}
            checked={value}
            onChange={(e) => setValue(e.target.checked)}
            className="h-4 w-4 text-blue-600 border-gray-300 rounded"
          />
          <label htmlFor={`setting-${setting.id}`} className="ml-2 text-sm text-gray-700">
            {value ? 'Enabled' : 'Disabled'}
          </label>
        </div>
      );
    }

    if (type === 'number') {
      return (
        <input
          type="number"
          value={value}
          onChange={(e) => setValue(parseFloat(e.target.value))}
          className="px-3 py-2 border border-gray-300 rounded-md w-full"
          step="any"
        />
      );
    }

    if (Array.isArray(value)) {
      return (
        <textarea
          value={JSON.stringify(value, null, 2)}
          onChange={(e) => {
            try {
              setValue(JSON.parse(e.target.value));
            } catch (error) {
              // Do nothing, keep the current value
            }
          }}
          className="px-3 py-2 border border-gray-300 rounded-md w-full font-mono text-sm"
          rows={4}
        />
      );
    }

    return (
      <input
        type="text"
        value={typeof value === 'object' ? JSON.stringify(value) : value}
        onChange={(e) => {
          try {
            // Try to parse as JSON if it looks like JSON
            if (e.target.value.trim().startsWith('{') || e.target.value.trim().startsWith('[')) {
              setValue(JSON.parse(e.target.value));
            } else {
              setValue(e.target.value);
            }
          } catch (error) {
            // If not valid JSON, treat as string
            setValue(e.target.value);
          }
        }}
        className="px-3 py-2 border border-gray-300 rounded-md w-full"
      />
    );
  };

  const renderValue = () => {
    const type = typeof setting.value;

    if (type === 'boolean') {
      return (
        <span
          className={`px-2 py-1 text-sm rounded-md ${
            value ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}
        >
          {value ? 'Enabled' : 'Disabled'}
        </span>
      );
    }

    if (type === 'number') {
      return <span className="font-mono">{value}</span>;
    }

    if (type === 'object' || Array.isArray(value)) {
      return (
        <pre className="bg-gray-50 p-2 rounded-md text-sm font-mono overflow-auto max-h-32">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }

    return <span>{value}</span>;
  };

  return (
    <Card className="h-full">
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">{setting.key}</h3>
          {setting.description && <p className="text-sm text-gray-600 mt-1">{setting.description}</p>}
        </div>
        <div>
          {isEditing ? (
            <div className="flex space-x-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleReset}
                icon={<RefreshCw size={16} />}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSave}
                isLoading={isSaving}
                icon={<Save size={16} />}
              >
                Save
              </Button>
            </div>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsEditing(true)}
            >
              Edit
            </Button>
          )}
        </div>
      </div>

      <div className="mt-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">Value</label>
        {isEditing ? renderEditor() : renderValue()}
      </div>
    </Card>
  );
};

export default SettingsCard;