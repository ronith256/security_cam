// src/pages/NotificationTriggers.tsx
import React, { useState } from 'react';
import { Bell, Plus } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Modal from '../components/common/Modal';
import NotificationTriggerList from '../components/notifications/NotificationTriggerList';
import NotificationTriggerForm from '../components/notifications/NotificationTriggerForm';
import { NotificationTrigger, NotificationTriggerCreate } from '../types/notification';
import { useApi } from '../hooks/useApi';
import { createTrigger, updateTrigger } from '../api/notifications';
import { useToast } from '../context/ToastContext';

const NotificationTriggers: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTrigger, setSelectedTrigger] = useState<NotificationTrigger | null>(null);
  const [showOnlyActive, setShowOnlyActive] = useState(false);
  const { showToast } = useToast();
  
  // API hooks
  const { execute: createTriggerApi, isLoading: isCreating } = useApi(createTrigger, {
    onSuccess: () => {
      setIsModalOpen(false);
      setSelectedTrigger(null);
      showToast('Notification trigger created successfully', 'success');
    }
  });
  
  const { execute: updateTriggerApi, isLoading: isUpdating } = useApi(
    (id: number, data: NotificationTriggerCreate) => updateTrigger(id, data),
    {
      onSuccess: () => {
        setIsModalOpen(false);
        setSelectedTrigger(null);
        showToast('Notification trigger updated successfully', 'success');
      }
    }
  );

  // Modal handlers
  const handleOpenModal = (trigger?: NotificationTrigger) => {
    setSelectedTrigger(trigger || null);
    setIsModalOpen(true);
  };
  
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedTrigger(null);
  };
  
  // Form submission handler
  const handleSubmit = async (formData: NotificationTriggerCreate) => {
    if (selectedTrigger) {
      await updateTriggerApi(selectedTrigger.id, formData);
    } else {
      await createTriggerApi(formData);
    }
  };

  return (
    <div>
      <PageHeader
        title="Notification Triggers"
        subtitle="Create and manage notification triggers for camera events"
        actions={
          <div className="flex space-x-3">
            <Button
              variant="secondary"
              onClick={() => setShowOnlyActive(!showOnlyActive)}
            >
              {showOnlyActive ? 'Show All' : 'Show Active Only'}
            </Button>
            <Button
              variant="primary"
              icon={<Plus size={16} />}
              onClick={() => handleOpenModal()}
            >
              Add Trigger
            </Button>
          </div>
        }
      />
      
      <NotificationTriggerList 
        onEdit={handleOpenModal} 
        filterActive={showOnlyActive ? true : undefined}
      />
      
      <Modal
        title={selectedTrigger ? 'Edit Notification Trigger' : 'Create Notification Trigger'}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        size="xl"
      >
        <NotificationTriggerForm
          initialValues={selectedTrigger || undefined}
          onSubmit={handleSubmit}
          onCancel={handleCloseModal}
          isSubmitting={isCreating || isUpdating}
        />
      </Modal>
    </div>
  );
};

export default NotificationTriggers;