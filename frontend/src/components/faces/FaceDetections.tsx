// src/components/faces/FaceDetections.tsx
import React, { useState, useEffect } from 'react';
import Card from '../common/Card';
import Loader from '../common/Loader';
import { useApi } from '../../hooks/useApi';
import { getFaceDetections } from '../../api/faceRecognition';
import { FaceDetection } from '../../types/person';
import { useInterval } from '../../hooks/useInterval';
import { AlertCircle, RefreshCw, User } from 'lucide-react';
import Button from '../common/Button';

interface FaceDetectionsProps {
  cameraId: number;
  pollInterval?: number;
}

const FaceDetections: React.FC<FaceDetectionsProps> = ({ 
  cameraId,
  pollInterval = 5000 // 5 seconds
}) => {
  const [faces, setFaces] = useState<FaceDetection[]>([]);
  const [isPolling, setIsPolling] = useState(true);
  
  const { execute: loadFaces, isLoading, error } = useApi(
    () => getFaceDetections(cameraId),
    {
      onSuccess: (data) => {
        setFaces(data);
      },
      showErrorToast: false,
    }
  );

  // Initial load
  useEffect(() => {
    loadFaces();
  }, [loadFaces]);
  
  // Set up polling
  useInterval(() => {
    if (isPolling) {
      loadFaces();
    }
  }, pollInterval);

  const togglePolling = () => {
    setIsPolling(!isPolling);
  };

  const refresh = () => {
    loadFaces();
  };

  return (
    <Card
      title="Face Detections"
      subtitle="Currently detected faces"
      className="h-full flex flex-col"
      actions={
        <div className="flex space-x-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={refresh}
            icon={<RefreshCw size={16} />}
          >
            Refresh
          </Button>
          <Button
            variant={isPolling ? 'warning' : 'success'}
            size="sm"
            onClick={togglePolling}
          >
            {isPolling ? 'Stop' : 'Start'} Auto-Refresh
          </Button>
        </div>
      }
    >
      <div className="flex-grow">
        {isLoading && faces.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <Loader text="Loading face detections..." />
          </div>
        ) : error && faces.length === 0 ? (
          <div className="bg-red-50 p-4 rounded-md flex items-start">
            <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
            <div>
              <h3 className="text-red-800 font-medium">Error loading face detections</h3>
              <p className="text-red-700 text-sm">{error.message}</p>
            </div>
          </div>
        ) : faces.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 bg-gray-50 rounded-md">
            <User className="text-gray-400 mb-2" size={48} />
            <p className="text-gray-600">No faces detected</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {faces.map((face, index) => (
              <div
                key={`${face.person_id}-${index}`}
                className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 flex items-center"
              >
                <div className="bg-blue-100 p-3 rounded-full mr-4">
                  <User className="text-blue-600" size={24} />
                </div>
                <div>
                  <h3 className="font-medium text-lg">{face.person_name}</h3>
                  <p className="text-sm text-gray-600">
                    Confidence: {(face.confidence * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
};

export default FaceDetections;