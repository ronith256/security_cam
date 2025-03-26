// src/components/cameras/CameraCard.tsx
import React, { useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Camera, Play, Pause, Eye, Edit, Trash2 } from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import HLSStreamViewer from './HLSStreamViewer';
import { Camera as CameraType } from '../../types/camera';
import { updateCamera, deleteCamera } from '../../api/cameras';
import { useApi } from '../../hooks/useApi';
import { useToast } from '../../context/ToastContext';

interface CameraCardProps {
  camera: CameraType;
  onDelete: (id: number) => void;
  onUpdate: (camera: CameraType) => void;
  onConnectionChange?: (id: number, isConnected: boolean) => void;
}

const CameraCard: React.FC<CameraCardProps> = ({ 
  camera, 
  onDelete, 
  onUpdate,
  onConnectionChange
}) => {
  const [isEnabled, setIsEnabled] = useState(camera.enabled);
  const [isStreamVisible, setIsStreamVisible] = useState(false);
  const { showToast } = useToast();

  const { execute: executeUpdate, isLoading: isUpdating } = useApi(updateCamera, {
    onSuccess: (updatedCamera) => {
      onUpdate(updatedCamera);
      setIsEnabled(updatedCamera.enabled);
      showToast(`Camera ${updatedCamera.enabled ? 'enabled' : 'disabled'}`, 'success');
    },
  });

  const { execute: executeDelete, isLoading: isDeleting } = useApi(deleteCamera, {
    onSuccess: () => {
      onDelete(camera.id);
      showToast('Camera deleted successfully', 'success');
    },
  });

  const handleToggleEnable = async () => {
    await executeUpdate(camera.id, { enabled: !isEnabled });
  };

  const handleDelete = async () => {
    if (window.confirm(`Are you sure you want to delete camera "${camera.name}"?`)) {
      await executeDelete(camera.id);
    }
  };

  // Handle connection state changes from the stream
  const handleConnectionChange = useCallback((isConnected: boolean) => {
    if (onConnectionChange) {
      onConnectionChange(camera.id, isConnected);
    }
  }, [camera.id, onConnectionChange]);

  return (
    <Card
      title={camera.name}
      subtitle={camera.location || 'No location specified'}
      className="h-full flex flex-col"
    >
      <div className="flex flex-col h-full">
        <div className="mb-4 bg-gray-100 h-40 rounded-md flex items-center justify-center relative">
          {camera.enabled && isStreamVisible ? (
            <div className="w-full h-full">
              <HLSStreamViewer
                cameraId={camera.id}
                rtspUrl={camera.rtsp_url}
                height="h-40"
                onReady={() => handleConnectionChange(true)}
                onError={() => handleConnectionChange(false)}
              />
              <div className="absolute top-2 right-2">
                <Button 
                  variant="secondary" 
                  size="sm" 
                  onClick={() => setIsStreamVisible(false)}
                  className="bg-gray-800 bg-opacity-75 text-white"
                >
                  Hide
                </Button>
              </div>
            </div>
          ) : camera.enabled ? (
            <div className="flex flex-col items-center">
              <Button 
                variant="secondary" 
                size="sm"
                onClick={() => setIsStreamVisible(true)}
              >
                Preview Stream
              </Button>
              <Link 
                to={`/cameras/${camera.id}`} 
                className="mt-2 text-sm text-blue-600 hover:underline"
              >
                Full View
              </Link>
            </div>
          ) : (
            <div className="text-gray-400 flex flex-col items-center justify-center">
              <Camera size={32} />
              <span className="mt-2 text-sm">Camera disabled</span>
            </div>
          )}
        </div>

        <div className="text-sm text-gray-600 mb-4 flex-grow">
          <p><strong>RTSP URL:</strong> {camera.rtsp_url}</p>
          <p><strong>Processing FPS:</strong> {camera.processing_fps}</p>
          <p><strong>Streaming FPS:</strong> {camera.streaming_fps}</p>
          <p><strong>Features:</strong></p>
          <ul className="list-disc ml-5">
            {camera.detect_people && <li>People Detection</li>}
            {camera.count_people && <li>People Counting</li>}
            {camera.recognize_faces && <li>Face Recognition</li>}
            {camera.template_matching && <li>Template Matching</li>}
          </ul>
        </div>

        <div className="flex space-x-2 mt-auto">
          <Button
            variant={isEnabled ? 'warning' : 'success'}
            size="sm"
            onClick={handleToggleEnable}
            isLoading={isUpdating}
            icon={isEnabled ? <Pause size={16} /> : <Play size={16} />}
          >
            {isEnabled ? 'Disable' : 'Enable'}
          </Button>
          
          {isEnabled && (
            <Link to={`/cameras/${camera.id}`}>
              <Button
                variant="primary"
                size="sm"
                icon={<Eye size={16} />}
              >
                View
              </Button>
            </Link>
          )}
          
          <div className="flex ml-auto">
            <Link to={`/cameras/${camera.id}/edit`}>
              <Button
                variant="secondary"
                size="sm"
                icon={<Edit size={16} />}
                className="mr-2"
              >
                Edit
              </Button>
            </Link>
            
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
      </div>
    </Card>
  );
};

export default CameraCard;