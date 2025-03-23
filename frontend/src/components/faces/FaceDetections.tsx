// src/components/faces/FaceDetections.tsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import Card from '../common/Card';
import Loader from '../common/Loader';
import { useApi } from '../../hooks/useApi';
import { getFaceDetections } from '../../api/faceRecognition';
import { FaceDetection } from '../../types/person';
import { AlertCircle, RefreshCw, User } from 'lucide-react';
import Button from '../common/Button';

interface FaceDetectionsProps {
  cameraId: number;
  pollInterval?: number;
}

const FaceDetections: React.FC<FaceDetectionsProps> = ({ 
  cameraId,
  pollInterval = 10000 // Increased to 10 seconds
}) => {
  const [faces, setFaces] = useState<FaceDetection[]>([]);
  const [isPolling, setIsPolling] = useState(true);
  
  // Track component mounted state
  const isMounted = useRef(true);
  
  // Track polling interval
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  // Track if a request is in progress
  const requestInProgressRef = useRef(false);
  
  // Use useCallback to create a stable function reference
  const loadFaces = useCallback(async () => {
    // Skip if unmounted or request in progress or polling disabled
    if (!isMounted.current || requestInProgressRef.current || !isPolling) return;
    
    // Mark request as in progress
    requestInProgressRef.current = true;
    
    try {
      const data = await getFaceDetections(cameraId);
      if (isMounted.current) {
        setFaces(data);
      }
    } catch (error) {
      console.error('Error loading face detections:', error);
    } finally {
      requestInProgressRef.current = false;
    }
  }, [cameraId, isPolling]);

  // Set up and clean up polling
  useEffect(() => {
    isMounted.current = true;
    
    // Load initially
    loadFaces();
    
    // Set up polling if enabled
    if (isPolling) {
      pollingIntervalRef.current = setInterval(loadFaces, pollInterval);
    }
    
    // Cleanup function
    return () => {
      isMounted.current = false;
      
      // Clear interval if it exists
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [loadFaces, isPolling, pollInterval]);

  // Handle toggling polling on/off
  const togglePolling = useCallback(() => {
    setIsPolling(prev => {
      // If turning on, set up interval
      if (!prev) {
        // Clear any existing interval first
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
        }
        
        // Create new interval
        pollingIntervalRef.current = setInterval(loadFaces, pollInterval);
        
        // Immediately load data
        loadFaces();
      } 
      // If turning off, clear interval
      else if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      
      return !prev;
    });
  }, [loadFaces, pollInterval]);

  // Manual refresh function
  const refresh = useCallback(() => {
    // Only if not already in progress
    if (!requestInProgressRef.current) {
      loadFaces();
    }
  }, [loadFaces]);

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
        {requestInProgressRef.current && faces.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <Loader text="Loading face detections..." />
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