import React, { useState, useEffect, useRef } from 'react';
import { Loader2, AlertTriangle, RefreshCw } from 'lucide-react';
import Button from '../common/Button';
import { apiBaseUrl } from '../../api';
import axios from 'axios';

interface CameraSnapshotProps {
  cameraId: number;
  height?: string;
  width?: string;
  interval?: number; // Update interval in ms
  onError?: () => void;
  onLoad?: () => void;
}

const CameraSnapshot: React.FC<CameraSnapshotProps> = ({
  cameraId,
  height = 'h-72',
  width = 'w-full',
  interval = 5000, // Default to 5 seconds between updates
  onError,
  onLoad
}) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [timestamp, setTimestamp] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortController = useRef<AbortController | null>(null);
  const isMounted = useRef(true);

  // Function to fetch snapshot
  const fetchSnapshot = async () => {
    if (!isMounted.current) return;
    
    // Cancel previous request if it exists
    if (abortController.current) {
      abortController.current.abort();
    }
    
    // Create new abort controller for this request
    abortController.current = new AbortController();
    
    try {
      const response = await axios.get(
        `${apiBaseUrl}/cameras/${cameraId}/snapshot/base64`,
        { signal: abortController.current.signal }
      );
      
      if (!isMounted.current) return;
      
      if (response.data && response.data.data) {
        setImageUrl(`data:image/jpeg;base64,${response.data.data}`);
        setTimestamp(response.data.timestamp || new Date().toISOString());
        setIsLoading(false);
        setError(null);
        
        if (onLoad) onLoad();
      } else {
        throw new Error('Invalid response format');
      }
    } catch (err) {
      if (!isMounted.current) return;
      
      if (axios.isCancel(err)) {
        // Request was canceled, do nothing
        return;
      }
      
      const errorMessage = err instanceof Error ? err.message : 'Failed to load snapshot';
      console.error('Snapshot error:', err);
      setError(new Error(errorMessage));
      setIsLoading(false);
      
      if (onError) onError();
    }
  };

  // Set up interval for fetching snapshots
  useEffect(() => {
    isMounted.current = true;
    
    // Initial fetch
    fetchSnapshot();
    
    // Set up interval
    intervalRef.current = setInterval(fetchSnapshot, interval);
    
    // Cleanup function
    return () => {
      isMounted.current = false;
      
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      
      if (abortController.current) {
        abortController.current.abort();
      }
    };
  }, [cameraId, interval]);

  // If we're still loading and don't have an image URL yet
  if (isLoading && !imageUrl) {
    return (
      <div className={`${width} ${height} bg-gray-100 rounded-md flex items-center justify-center`}>
        <div className="flex flex-col items-center">
          <Loader2 size={40} className="animate-spin text-gray-400 mb-2" />
          <p className="text-gray-600">Loading snapshot...</p>
        </div>
      </div>
    );
  }

  // If we have an error
  if (error && !imageUrl) {
    return (
      <div className={`${width} ${height} bg-red-50 rounded-md flex flex-col items-center justify-center p-4`}>
        <AlertTriangle size={40} className="text-red-500 mb-2" />
        <p className="text-red-700 text-center mb-4">{error.message}</p>
        <Button 
          variant="primary" 
          onClick={() => {
            setError(null);
            setIsLoading(true);
            fetchSnapshot();
          }}
          icon={<RefreshCw size={16} />}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {imageUrl && (
        <img 
          src={imageUrl} 
          alt={`Camera ${cameraId} snapshot`}
          className="w-full h-full object-contain"
          onError={() => {
            setError(new Error('Failed to load image'));
            if (onError) onError();
          }}
          onLoad={() => {
            setIsLoading(false);
            if (onLoad) onLoad();
          }}
        />
      )}
      
      {isLoading && imageUrl && (
        <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
          <Loader2 size={40} className="animate-spin text-white" />
        </div>
      )}
      
      {/* Timestamp indicator */}
      <div className="absolute bottom-2 right-2 bg-black bg-opacity-70 text-white text-xs py-1 px-2 rounded">
        Snapshot: {new Date(timestamp).toLocaleTimeString()}
      </div>
    </div>
  );
};

export default CameraSnapshot;