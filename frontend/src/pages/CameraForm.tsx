// src/pages/CameraForm.tsx
import React, { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Loader from '../components/common/Loader';
import CameraFormComponent from '../components/cameras/CameraForm';
import { fetchCamera, createCamera, updateCamera } from '../api/cameras';
import { CameraCreate, CameraUpdate } from '../types/camera';
import { useApi } from '../hooks/useApi';
import { useToast } from '../context/ToastContext';

const CameraForm: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditing = !!id;
  const { showToast } = useToast();
  
  const { execute: loadCamera, data: camera, isLoading: isLoadingCamera } = useApi(
    () => fetchCamera(parseInt(id || '0')),
    {
      showErrorToast: true,
    }
  );
  
  const { execute: createCameraApi, isLoading: isCreating } = useApi(createCamera, {
    onSuccess: (newCamera) => {
      showToast('Camera created successfully', 'success');
      navigate(`/cameras/${newCamera.id}`);
    },
  });
  
  const { execute: updateCameraApi, isLoading: isUpdating } = useApi(
    (id: number, data: CameraUpdate) => updateCamera(id, data),
    {
      onSuccess: (updatedCamera) => {
        showToast('Camera updated successfully', 'success');
        navigate(`/cameras/${updatedCamera.id}`);
      },
    }
  );
  
  useEffect(() => {
    if (isEditing && id) {
      loadCamera();
    }
  }, [isEditing, id, loadCamera]);
  
  const handleSubmit = async (formData: CameraCreate | CameraUpdate) => {
    if (isEditing && id) {
      await updateCameraApi(parseInt(id), formData as CameraUpdate);
    } else {
      await createCameraApi(formData as CameraCreate);
    }
  };
  
  const handleCancel = () => {
    if (isEditing && id) {
      navigate(`/cameras/${id}`);
    } else {
      navigate('/cameras');
    }
  };
  
  const title = isEditing ? 'Edit Camera' : 'Add Camera';
  const subtitle = isEditing
    ? 'Update camera settings'
    : 'Configure a new camera connection';
  
  if (isEditing && isLoadingCamera && !camera) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader text="Loading camera details..." />
      </div>
    );
  }
  
  return (
    <div>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Link to={isEditing && id ? `/cameras/${id}` : '/cameras'}>
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              Back
            </Button>
          </Link>
        }
      />
      
      <div className="bg-white rounded-lg shadow-md p-6">
        <CameraFormComponent
          initialValues={camera}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isSubmitting={isCreating || isUpdating}
        />
      </div>
    </div>
  );
};

export default CameraForm;