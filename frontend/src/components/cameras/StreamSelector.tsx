import React, { useState, useEffect, useCallback } from 'react';
import HLSStreamViewer from './HLSStreamViewer';
import WebRTCStream from './WebRTCStream';
import CameraSnapshot from './CameraSnapshot';

type StreamMode = 'webrtc' | 'hls' | 'snapshot';

interface StreamSelectorProps {
  cameraId: number;
  rtspUrl?: string;
  height?: string;
  width?: string;
  onConnectionChange?: (connected: boolean) => void;
  preferredMode?: StreamMode;
}

const StreamSelector: React.FC<StreamSelectorProps> = ({
  cameraId,
  rtspUrl,
  height = 'h-72',
  width = 'w-full',
  onConnectionChange,
  preferredMode = 'webrtc' // Default to WebRTC as it's usually the best option
}) => {
  const [currentMode, setCurrentMode] = useState<StreamMode>(preferredMode);
  const [failedModes, setFailedModes] = useState<StreamMode[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  // Function to handle stream errors and switch to fallback
  const handleStreamError = useCallback((mode: StreamMode) => {
    console.log(`Stream mode ${mode} failed, trying fallback`);
    
    // Add to failed modes
    setFailedModes(prev => {
      if (prev.includes(mode)) return prev;
      return [...prev, mode];
    });
    
    // Select next mode based on priority: webrtc > hls > snapshot
    if (mode === 'webrtc' && !failedModes.includes('hls')) {
      setCurrentMode('hls');
    } else if (mode === 'hls' && !failedModes.includes('snapshot')) {
      setCurrentMode('snapshot');
    } else {
      // If all modes have failed, reset and try webrtc again or use snapshot as last resort
      if (failedModes.length >= 2) {
        setCurrentMode('snapshot');
      }
    }
    
    // Update connection state
    setIsConnected(false);
    if (onConnectionChange) onConnectionChange(false);
  }, [failedModes, onConnectionChange]);

  // Handle connection state changes
  const handleConnectionChange = useCallback((connected: boolean) => {
    setIsConnected(connected);
    if (onConnectionChange) onConnectionChange(connected);
  }, [onConnectionChange]);

  // Reset state when camera changes
  useEffect(() => {
    setFailedModes([]);
    setCurrentMode(preferredMode);
    setIsConnected(false);
  }, [cameraId, preferredMode]);

  // Notify parent of connection changes
  useEffect(() => {
    if (onConnectionChange) onConnectionChange(isConnected);
  }, [isConnected, onConnectionChange]);
  
  // Log current stream mode
  useEffect(() => {
    console.log(`Using ${currentMode} mode for camera ${cameraId}`);
  }, [currentMode, cameraId]);

  // Render the appropriate streaming component based on current mode
  switch (currentMode) {
    case 'webrtc':
      return (
        <WebRTCStream
          cameraId={cameraId}
          height={height}
          width={width}
          onConnectionChange={handleConnectionChange}
          onError={() => handleStreamError('webrtc')}
        />
      );
      
    case 'hls':
      return (
        <HLSStreamViewer
          cameraId={cameraId}
          rtspUrl={rtspUrl}
          height={height}
          width={width}
          onReady={() => handleConnectionChange(true)}
          onError={() => handleStreamError('hls')}
        />
      );
      
    case 'snapshot':
    default:
      return (
        <CameraSnapshot
          cameraId={cameraId}
          height={height}
          width={width}
          interval={2000} // Update every 2 seconds
          onLoad={() => handleConnectionChange(true)}
          onError={() => handleConnectionChange(false)}
        />
      );
  }
};

export default StreamSelector;