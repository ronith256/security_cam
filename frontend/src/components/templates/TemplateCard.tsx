// src/components/templates/TemplateCard.tsx
import React, { useState } from 'react';
import { Edit, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import { Template } from '../../types/template';
import { getTemplateImage, enableTemplate, disableTemplate, deleteTemplate } from '../../api/templates';
import { useApi } from '../../hooks/useApi';
import { useToast } from '../../context/ToastContext';

interface TemplateCardProps {
  template: Template;
  onDelete: (id: number) => void;
  onUpdate: (template: Template) => void;
  onEdit: (template: Template) => void;
}

const TemplateCard: React.FC<TemplateCardProps> = ({ template, onDelete, onUpdate, onEdit }) => {
  const [isEnabled, setIsEnabled] = useState(template.enabled);
  const { showToast } = useToast();

  const { execute: executeEnable, isLoading: isEnabling } = useApi(enableTemplate, {
    onSuccess: () => {
      setIsEnabled(true);
      onUpdate({ ...template, enabled: true });
      showToast('Template enabled successfully', 'success');
    },
  });

  const { execute: executeDisable, isLoading: isDisabling } = useApi(disableTemplate, {
    onSuccess: () => {
      setIsEnabled(false);
      onUpdate({ ...template, enabled: false });
      showToast('Template disabled successfully', 'success');
    },
  });

  const { execute: executeDelete, isLoading: isDeleting } = useApi(deleteTemplate, {
    onSuccess: () => {
      onDelete(template.id);
      showToast('Template deleted successfully', 'success');
    },
  });

  const toggleEnabled = async () => {
    if (isEnabled) {
      await executeDisable(template.id);
    } else {
      await executeEnable(template.id);
    }
  };

  const handleDelete = async () => {
    if (window.confirm(`Are you sure you want to delete template "${template.name}"?`)) {
      await executeDelete(template.id);
    }
  };

  return (
    <Card
      title={template.name}
      subtitle={template.description || 'No description'}
      className="h-full flex flex-col"
    >
      <div className="flex flex-col h-full">
        <div className="mb-4 relative h-48 bg-gray-100 rounded-md overflow-hidden flex items-center justify-center">
          <img
            src={getTemplateImage(template.id)}
            alt={template.name}
            className="object-contain max-h-full max-w-full"
            onError={(e) => {
              const target = e.target as HTMLImageElement;
              target.src = 'https://via.placeholder.com/200x150?text=Image+Not+Found';
            }}
          />
          {!isEnabled && (
            <div className="absolute inset-0 bg-gray-800 bg-opacity-50 flex items-center justify-center">
              <span className="text-white font-medium px-3 py-1 bg-red-500 rounded-md">Disabled</span>
            </div>
          )}
        </div>

        <div className="text-sm text-gray-600 mb-4">
          <p><strong>Camera ID:</strong> {template.camera_id}</p>
          <p><strong>Matching Threshold:</strong> {(template.threshold * 100).toFixed(0)}%</p>
          <p><strong>Created:</strong> {new Date(template.created_at).toLocaleDateString()}</p>
        </div>

        <div className="flex space-x-2 mt-auto">
          <Button
            variant={isEnabled ? 'warning' : 'success'}
            size="sm"
            onClick={toggleEnabled}
            isLoading={isEnabling || isDisabling}
            icon={isEnabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
          >
            {isEnabled ? 'Disable' : 'Enable'}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => onEdit(template)}
            icon={<Edit size={16} />}
          >
            Edit
          </Button>

          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            isLoading={isDeleting}
            icon={<Trash2 size={16} />}
          >
            Delete
          </Button>
        </div>
      </div>
    </Card>
  );
};

export default TemplateCard;
