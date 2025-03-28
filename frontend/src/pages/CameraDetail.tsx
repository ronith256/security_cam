// frontend/src/pages/CameraDetail.tsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Edit, ArrowLeft, Image, Activity } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import HLSStreamViewer from '../components/cameras/HLSStreamViewer';
import CameraStats from '../components/cameras/CameraStats';
import FaceDetections from '../components/faces/FaceDetections';
import TemplateList from '../components/templates/TemplateList';
import Modal from '../components/common/Modal';
import TemplateForm from '../components/templates/TemplateForm';
import { fetchCamera, getCameraStatus } from '../api/cameras';
import { createTemplate, updateTemplate } from '../api/templates';
import { Template } from '../types/template';
import { useApi } from '../hooks/useApi';
import Loader from '../components/common/Loader';
import { useToast } from '../context/ToastContext';

const CameraDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const cameraId = parseInt(id || '0');
  const { showToast } = useToast();
  
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [streamActive, setStreamActive] = useState(false);
  const [cameraStatus, setCameraStatus] = useState<any>(null);

  // Reference to track if the component is mounted
  const isMounted = useRef(true);
  
  // Track status polling interval
  const statusPollingInterval = useRef<NodeJS.Timeout | null>(null);
  
  // Track status polling requests
  const statusRequestInProgress = useRef(false);
  
  // Load camera details - with stable reference to prevent re-fetching
  const cameraIdRef = useRef(cameraId);
  const { execute: loadCamera, data: camera, isLoading: isLoadingCamera, error: cameraError } = useApi(
    useCallback(() => fetchCamera(cameraIdRef.current), []),
    {
      showErrorToast: true,
    }
  );
  
  // Template API hooks
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

  // Function to fetch camera status with debouncing
  const fetchCameraStatus = useCallback(async () => {
    if (!isMounted.current || statusRequestInProgress.current || !streamActive) return;
    
    statusRequestInProgress.current = true;
    
    try {
      const status = await getCameraStatus(cameraId);
      if (isMounted.current) {
        setCameraStatus(status);
      }
    } catch (error) {
      console.error('Error fetching camera status:', error);
    } finally {
      statusRequestInProgress.current = false;
    }
  }, [cameraId, streamActive]);

  // Function to handle stream connection state
  const handleStreamConnection = useCallback((active: boolean) => {
    console.log(`Stream connection state changed: ${active ? 'connected' : 'disconnected'}`);
    
    setStreamActive(active);
    
    // When stream becomes active, start polling for status
    if (active && !statusPollingInterval.current) {
      // First fetch immediately
      fetchCameraStatus();
      
      // Set up interval - 5 second interval to avoid excessive requests
      statusPollingInterval.current = setInterval(() => {
        fetchCameraStatus();
      }, 5000);
    } 
    // When stream becomes inactive, stop polling
    else if (!active && statusPollingInterval.current) {
      clearInterval(statusPollingInterval.current);
      statusPollingInterval.current = null;
    }
  }, [fetchCameraStatus]);
  
  // Load camera details once on mount
  useEffect(() => {
    if (cameraId) {
      loadCamera();
    }
    
    // Cleanup function
    return () => {
      isMounted.current = false;
      
      // Clear status polling interval
      if (statusPollingInterval.current) {
        clearInterval(statusPollingInterval.current);
        statusPollingInterval.current = null;
      }
    };
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
  
  if (cameraError || !camera) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-gray-700">Camera not found</h2>
        <p className="text-gray-600 mt-2">The camera you're looking for doesn't exist or couldn't be loaded.</p>
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
            actions={
              <Button
                variant="secondary"
                size="sm"
                icon={<Activity size={16} />}
                onClick={() => showToast('HLS streaming from camera', 'info')}
              >
                HLS Stream
              </Button>
            }
          >
            <div className="flex-grow">
              <HLSStreamViewer 
                cameraId={cameraId}
                rtspUrl={camera.rtsp_url}
                height="h-96"
                onReady={() => handleStreamConnection(true)}
                onError={() => handleStreamConnection(false)}
              />
            </div>
          </Card>
        </div>
        
        <div className="space-y-6">
          {cameraStatus && streamActive && (
            <CameraStats status={cameraStatus} />
          )}
          
          {camera.recognize_faces && streamActive && (
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