// src/pages/CameraDetail.tsx
import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Edit, ArrowLeft, Image, UserPlus } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import CameraStream from '../components/cameras/CameraStream';
import CameraStats from '../components/cameras/CameraStats';
import FaceDetections from '../components/faces/FaceDetections';
import TemplateList from '../components/templates/TemplateList';
import Modal from '../components/common/Modal';
import TemplateForm from '../components/templates/TemplateForm';
import { fetchCamera } from '../api/cameras';
import { createTemplate, updateTemplate } from '../api/templates';
import { Template } from '../types/template';
import { getCameraStatus } from '../api/cameras';
import { useApi } from '../hooks/useApi';
import { useCamera } from '../hooks/useCamera';
import { useInterval } from '../hooks/useInterval';
import Loader from '../components/common/Loader';
import { useToast } from '../context/ToastContext';

const CameraDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const cameraId = parseInt(id || '0');
  const navigate = useNavigate();
  const { showToast } = useToast();
  
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  
  const { execute: loadCamera, data: camera, isLoading: isLoadingCamera } = useApi(
    () => fetchCamera(cameraId),
    {
      showErrorToast: true,
    }
  );
  
  const { status, isLoading: isLoadingStatus } = useCamera(cameraId, {
    pollInterval: 2000,
    autoStart: true,
  });
  
  const { execute: createTemplateApi, isLoading: isCreatingTemplate } = useApi(createTemplate, {
    onSuccess: () => {
      setIsTemplateModalOpen(false);
      setSelectedTemplate(null);
      showToast('Template created successfully', 'success');
    },
  });
  
  const { execute: updateTemplateApi, isLoading: isUpdatingTemplate } = useApi(
    (id: number, data: FormData) => updateTemplate(id, { 
      name: data.get('name') as string,
      description: data.get('description') as string || undefined,
      threshold: parseFloat((data.get('threshold') as string) || '0.7'),
    }),
    {
      onSuccess: () => {
        setIsTemplateModalOpen(false);
        setSelectedTemplate(null);
        showToast('Template updated successfully', 'success');
      },
    }
  );
  
  useEffect(() => {
    if (cameraId) {
      loadCamera();
    }
  }, [cameraId, loadCamera]);
  
  const handleOpenTemplateModal = (template?: Template) => {
    setSelectedTemplate(template || null);
    setIsTemplateModalOpen(true);
  };
  
  const handleCloseTemplateModal = () => {
    setIsTemplateModalOpen(false);
    setSelectedTemplate(null);
  };
  
  const handleTemplateSubmit = async (formData: FormData) => {
    if (selectedTemplate) {
      await updateTemplateApi(selectedTemplate.id, formData);
    } else {
      await createTemplateApi(formData);
    }
  };
  
  if (isLoadingCamera && !camera) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader text="Loading camera details..." />
      </div>
    );
  }
  
  if (!camera) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-gray-700">Camera not found</h2>
        <p className="text-gray-600 mt-2">The camera you're looking for doesn't exist.</p>
        <Link to="/cameras" className="mt-4 inline-block">
          <Button variant="primary">Back to Cameras</Button>
        </Link>
      </div>
    );
  }
  
  return (
    <div>
      <PageHeader
        title={camera.name}
        subtitle={camera.location || 'No location specified'}
        actions={
          <div className="flex space-x-2">
            <Link to="/cameras">
              <Button
                variant="secondary"
                icon={<ArrowLeft size={16} />}
              >
                Back
              </Button>
            </Link>
            <Link to={`/cameras/${cameraId}/edit`}>
              <Button
                variant="primary"
                icon={<Edit size={16} />}
              >
                Edit
              </Button>
            </Link>
          </div>
        }
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="lg:col-span-2">
          <Card
            title="Live View"
            subtitle={camera.rtsp_url}
            className="h-full flex flex-col"
          >
            <div className="flex-grow">
              <CameraStream cameraId={cameraId} height="h-96" />
            </div>
          </Card>
        </div>
        
        <div className="space-y-6">
          {status && (
            <CameraStats status={status} />
          )}
          
          {camera.recognize_faces && (
            <FaceDetections cameraId={cameraId} />
          )}
        </div>
      </div>
      
      {camera.template_matching && (
        <div className="mb-8">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold">Templates</h2>
            <Button
              variant="primary"
              icon={<Image size={16} />}
              onClick={() => handleOpenTemplateModal()}
            >
              Add Template
            </Button>
          </div>
          <TemplateList
            cameraId={cameraId}
            onEdit={handleOpenTemplateModal}
          />
        </div>
      )}
      
      <Modal
        title={selectedTemplate ? 'Edit Template' : 'Add Template'}
        isOpen={isTemplateModalOpen}
        onClose={handleCloseTemplateModal}
      >
        <TemplateForm
          initialValues={selectedTemplate || undefined}
          onSubmit={handleTemplateSubmit}
          onCancel={handleCloseTemplateModal}
          isSubmitting={isCreatingTemplate || isUpdatingTemplate}
        />
      </Modal>
    </div>
  );
};

export default CameraDetail;