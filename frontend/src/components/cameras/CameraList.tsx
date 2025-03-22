// frontend/src/components/cameras/CameraList.tsx
import React, { useState, useEffect, useRef } from 'react';
import { Camera as CameraType } from '../../types/camera';
import CameraCard from './CameraCard';
import Loader from '../common/Loader';
import { fetchCameras } from '../../api/cameras';
import { useApi } from '../../hooks/useApi';
import { AlertCircle } from 'lucide-react';

interface CameraListProps {
  filter?: (camera: CameraType) => boolean;
  onActiveChange?: (count: number) => void;
}

const CameraList: React.FC<CameraListProps> = ({ 
  filter,
  onActiveChange 
}) => {
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [activeCameras, setActiveCameras] = useState<Set<number>>(new Set());
  const isFirstRender = useRef(true);
  
  const { execute: loadCameras, isLoading, error } = useApi(fetchCameras, {
    onSuccess: (data) => {
      setCameras(data);
    },
  });

  useEffect(() => {
    if (isFirstRender.current) {
      loadCameras();
      isFirstRender.current = false;
    }
  }, [loadCameras]);

  // Notify parent component when active camera count changes
  useEffect(() => {
    if (onActiveChange) {
      onActiveChange(activeCameras.size);
    }
  }, [activeCameras, onActiveChange]);

  const handleDelete = (id: number) => {
    setCameras((prevCameras) => prevCameras.filter((camera) => camera.id !== id));
    
    // Remove from active cameras if present
    if (activeCameras.has(id)) {
      const newActiveCameras = new Set(activeCameras);
      newActiveCameras.delete(id);
      setActiveCameras(newActiveCameras);
    }
  };

  const handleUpdate = (updatedCamera: CameraType) => {
    setCameras((prevCameras) =>
      prevCameras.map((camera) =>
        camera.id === updatedCamera.id ? updatedCamera : camera
      )
    );
  };
  
  const handleCameraConnectionChange = (id: number, isConnected: boolean) => {
    setActiveCameras(prev => {
      const newSet = new Set(prev);
      if (isConnected) {
        newSet.add(id);
      } else {
        newSet.delete(id);
      }
      return newSet;
    });
  };

  // Apply filter if provided
  const filteredCameras = filter ? cameras.filter(filter) : cameras;

  if (isLoading && cameras.length === 0) {
    return <Loader text="Loading cameras..." />;
  }

  if (error && cameras.length === 0) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading cameras</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  if (filteredCameras.length === 0) {
    return (
      <div className="bg-gray-50 p-6 rounded-md text-center">
        <p className="text-gray-600">No cameras found.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {filteredCameras.map((camera) => (
        <CameraCard
          key={camera.id}
          camera={camera}
          onDelete={handleDelete}
          onUpdate={handleUpdate}
          onConnectionChange={(isConnected) => handleCameraConnectionChange(camera.id, isConnected)}
        />
      ))}
    </div>
  );
};

export default CameraList;