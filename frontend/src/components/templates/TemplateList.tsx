// src/components/templates/TemplateList.tsx
import React, { useState, useEffect } from 'react';
import { Template } from '../../types/template';
import TemplateCard from './TemplateCard';
import Loader from '../common/Loader';
import { fetchTemplates } from '../../api/templates';
import { useApi } from '../../hooks/useApi';
import { AlertCircle } from 'lucide-react';

interface TemplateListProps {
  cameraId?: number;
  onEdit: (template: Template) => void;
}

const TemplateList: React.FC<TemplateListProps> = ({ cameraId, onEdit }) => {
  const [templates, setTemplates] = useState<Template[]>([]);
  
  const { execute: loadTemplates, isLoading, error } = useApi(
    () => fetchTemplates(cameraId),
    {
      onSuccess: (data) => {
        setTemplates(data);
      },
    }
  );

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates, cameraId]);

  const handleDelete = (id: number) => {
    setTemplates((prevTemplates) => prevTemplates.filter((template) => template.id !== id));
  };

  const handleUpdate = (updatedTemplate: Template) => {
    setTemplates((prevTemplates) =>
      prevTemplates.map((template) =>
        template.id === updatedTemplate.id ? updatedTemplate : template
      )
    );
  };

  if (isLoading && templates.length === 0) {
    return <Loader text="Loading templates..." />;
  }

  if (error && templates.length === 0) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading templates</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="bg-gray-50 p-6 rounded-md text-center">
        <p className="text-gray-600">No templates found.</p>
        {cameraId && (
          <p className="text-gray-500 text-sm mt-1">
            Create a template for camera ID: {cameraId}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {templates.map((template) => (
        <TemplateCard
          key={template.id}
          template={template}
          onDelete={handleDelete}
          onUpdate={handleUpdate}
          onEdit={onEdit}
        />
      ))}
    </div>
  );
};

export default TemplateList