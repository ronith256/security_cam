// src/components/cameras/CameraStream.tsx
import React, { useState, useEffect, useRef } from 'react';
import { Camera as CameraIcon, RefreshCw, Film, Image, AlertTriangle } from 'lucide-react';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { getCameraStream } from '../../api/cameras';
import { useCamera } from '../../hooks/useCamera';

interface CameraStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
}

const CameraStream: React.FC<CameraStreamProps> = ({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
}) => {
  const [streamMode, setStreamMode] = useState<'mjpeg' | 'snapshot'>('mjpeg');
  const streamRef = useRef<HTMLImageElement>(null);
  
  const {
    status,
    snapshot,
    isLoading,
    error,
    refresh,
    startPolling,
    stopPolling,
    isPolling,
  } = useCamera(cameraId, { autoStart: streamMode === 'snapshot' });

  // Switch to snapshot mode if the camera is inactive
  useEffect(() => {
    if (status && !status.active && streamMode === 'mjpeg') {
      setStreamMode('snapshot');
    }
  }, [status, streamMode]);

  const handleRefresh = () => {
    refresh();
  };

  const toggleStreamMode = () => {
    if (streamMode === 'mjpeg') {
      setStreamMode('snapshot');
      startPolling();
    } else {
      setStreamMode('mjpeg');
      stopPolling();
    }
  };

  const renderContent = () => {
    if (isLoading && !snapshot && !status) {
      return (
        <div className="flex items-center justify-center h-full">
          <Loader text="Loading camera..." />
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-red-50 p-4 rounded-md">
          <AlertTriangle className="text-red-500 mb-2" size={32} />
          <p className="text-red-700 text-center">Error connecting to camera</p>
          <Button
            variant="primary"
            size="sm"
            className="mt-2"
            onClick={handleRefresh}
            icon={<RefreshCw size={16} />}
          >
            Retry
          </Button>
        </div>
      );
    }

    if (status && !status.active) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-gray-100 rounded-md">
          <CameraIcon className="text-gray-400" size={40} />
          <p className="text-gray-500 mt-2">Camera is not active</p>
        </div>
      );
    }

    if (streamMode === 'mjpeg') {
      return (
        <img
          src={getCameraStream(cameraId)}
          alt="Camera stream"
          className="w-full h-full object-contain rounded-md"
        />
      );
    }

    if (streamMode === 'snapshot' && snapshot) {
      return (
        <img
          ref={streamRef}
          src={snapshot}
          alt="Camera snapshot"
          className="w-full h-full object-contain rounded-md"
        />
      );
    }

    return (
      <div className="flex items-center justify-center h-full bg-gray-100 rounded-md">
        <Loader text="Loading stream..." />
      </div>
    );
  };

  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {renderContent()}

      {showControls && (
        <div className="absolute bottom-2 right-2 flex space-x-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={toggleStreamMode}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={streamMode === 'mjpeg' ? <Image size={16} /> : <Film size={16} />}
          >
            {streamMode === 'mjpeg' ? 'Snapshot' : 'Stream'}
          </Button>

          {streamMode === 'snapshot' && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRefresh}
              className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
              icon={<RefreshCw size={16} />}
            >
              Refresh
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

export default CameraStream;