// src/pages/Templates.tsx
import React, { useState } from 'react';
import { Image } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Modal from '../components/common/Modal';
import TemplateList from '../components/templates/TemplateList';
import TemplateForm from '../components/templates/TemplateForm';
import { createTemplate, updateTemplate } from '../api/templates';
import { Template } from '../types/template';
import { useApi } from '../hooks/useApi';
import { useToast } from '../context/ToastContext';

const Templates: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const { showToast } = useToast();
  
  const { execute: createTemplateApi, isLoading: isCreating } = useApi(createTemplate, {
    onSuccess: () => {
      setIsModalOpen(false);
      setSelectedTemplate(null);
      showToast('Template created successfully', 'success');
    },
  });
  
  const { execute: updateTemplateApi, isLoading: isUpdating } = useApi(
    (id: number, data: FormData) => updateTemplate(id, { 
      name: data.get('name') as string,
      description: data.get('description') as string || undefined,
      threshold: parseFloat((data.get('threshold') as string) || '0.7'),
    }),
    {
      onSuccess: () => {
        setIsModalOpen(false);
        setSelectedTemplate(null);
        showToast('Template updated successfully', 'success');
      },
    }
  );
  
  const handleOpenModal = (template?: Template) => {
    setSelectedTemplate(template || null);
    setIsModalOpen(true);
  };
  
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTemplate(null);
  };
  
  const handleSubmit = async (formData: FormData) => {
    if (selectedTemplate) {
      await updateTemplateApi(selectedTemplate.id, formData);
    } else {
      await createTemplateApi(formData);
    }
  };
  
  return (
    <div>
      <PageHeader
        title="Templates"
        subtitle="Manage and create template matching patterns"
        actions={
          <Button
            variant="primary"
            icon={<Image size={16} />}
            onClick={() => handleOpenModal()}
          >
            Add Template
          </Button>
        }
      />
      
      <TemplateList onEdit={handleOpenModal} />
      
      <Modal
        title={selectedTemplate ? 'Edit Template' : 'Add Template'}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
      >
        <TemplateForm
          initialValues={selectedTemplate || undefined}
          onSubmit={handleSubmit}
          onCancel={handleCloseModal}
          isSubmitting={isCreating || isUpdating}
        />
      </Modal>
    </div>
  );
};

export default Templates;