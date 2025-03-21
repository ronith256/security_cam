// src/pages/FaceRecognition.tsx
import React, { useState } from 'react';
import { UserPlus } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import PersonList from '../components/faces/PersonList';
import PersonForm from '../components/faces/PersonForm';
import Modal from '../components/common/Modal';
import { Person } from '../types/person';
import { createPerson, updatePerson, updatePersonFace } from '../api/faceRecognition';
import { useApi } from '../hooks/useApi';
import { useToast } from '../context/ToastContext';

const FaceRecognition: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null);
  const { showToast } = useToast();
  
  const { execute: createPersonApi, isLoading: isCreating } = useApi(createPerson, {
    onSuccess: () => {
      setIsModalOpen(false);
      setSelectedPerson(null);
      showToast('Person registered successfully', 'success');
    },
  });
  
  const { execute: updatePersonApi, isLoading: isUpdating } = useApi(
    (id: number, name: string, description?: string) => updatePerson(id, { name, description }),
    {
      onSuccess: () => {
        showToast('Person updated successfully', 'success');
      },
    }
  );
  
  const { execute: updateFaceApi, isLoading: isUpdatingFace } = useApi(
    updatePersonFace,
    {
      onSuccess: () => {
        showToast('Face image updated successfully', 'success');
      },
    }
  );
  
  const handleOpenModal = (person?: Person) => {
    setSelectedPerson(person || null);
    setIsModalOpen(true);
  };
  
  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedPerson(null);
  };
  
  const handleSubmit = async (formData: FormData) => {
    if (selectedPerson) {
      // Update existing person
      const name = formData.get('name') as string;
      const description = formData.get('description') as string || undefined;
      
      await updatePersonApi(selectedPerson.id, name, description);
      
      // Update face image if provided
      const faceImage = formData.get('face_image') as File;
      if (faceImage && faceImage.size > 0) {
        await updateFaceApi(selectedPerson.id, faceImage);
      }
      
      setIsModalOpen(false);
      setSelectedPerson(null);
    } else {
      // Create new person
      await createPersonApi(formData);
    }
  };
  
  return (
    <div>
      <PageHeader
        title="Face Recognition"
        subtitle="Register and track people by face"
        actions={
          <Button
            variant="primary"
            icon={<UserPlus size={16} />}
            onClick={() => handleOpenModal()}
          >
            Register Person
          </Button>
        }
      />
      
      <PersonList onEdit={handleOpenModal} />
      
      <Modal
        title={selectedPerson ? 'Edit Person' : 'Register Person'}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
      >
        <PersonForm
          initialValues={selectedPerson || undefined}
          onSubmit={handleSubmit}
          onCancel={handleCloseModal}
          isSubmitting={isCreating || isUpdating || isUpdatingFace}
        />
      </Modal>
    </div>
  );
};

export default FaceRecognition;