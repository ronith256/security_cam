// src/components/cameras/WebRTCStream.tsx
import React, { useEffect, useRef, useState } from 'react';
import { RefreshCw, AlertTriangle, Film, Image } from 'lucide-react';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { getCameraSnapshot } from '../../api/cameras';
import api from '../../api';

interface WebRTCStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
}

const WebRTCStream: React.FC<WebRTCStreamProps> = ({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
}) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [streamMode, setStreamMode] = useState<'webrtc' | 'snapshot'>('webrtc');
  const [snapshot, setSnapshot] = useState<string | null>(null);
  
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  
  // For cleanup
  const isComponentMounted = useRef(true);

  // Connect to WebRTC stream
  useEffect(() => {
    if (streamMode !== 'webrtc') return;

    const connect = async () => {
      try {
        setIsLoading(true);
        setError(null);
        
        // Check if the camera is active before attempting to connect
        try {
          const response = await api.get(`/cameras/${cameraId}/status`);
          if (!response.data.active) {
            throw new Error('Camera is not active');
          }
        } catch (err) {
          setError(new Error('Camera is not available'));
          setIsLoading(false);
          return;
        }
        
        // Create WebSocket connection for signaling
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/webrtc/ws/${cameraId}`;
        
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        
        ws.onopen = () => {
          console.log(`WebSocket connected for camera ${cameraId}`);
        };
        
        ws.onmessage = (event) => {
          const message = JSON.parse(event.data);
          
          if (message.type === 'frame') {
            // Handle incoming frame (base64 encoded JPEG)
            renderFrame(message.data);
          } else if (message.type === 'signal') {
            // Handle signaling messages if we implement peer-to-peer WebRTC
            // This would be used for implementing full WebRTC with ICE, SDP, etc.
            console.log('Received signaling message:', message.data);
          }
        };
        
        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setError(new Error('Failed to connect to video stream'));
          setIsConnected(false);
          setIsLoading(false);
        };
        
        ws.onclose = () => {
          console.log('WebSocket closed');
          if (isComponentMounted.current) {
            setIsConnected(false);
            setIsLoading(false);
          }
        };
        
        setIsConnected(true);
        setIsLoading(false);
      } catch (err) {
        console.error('Error setting up WebRTC:', err);
        setError(err instanceof Error ? err : new Error('Failed to connect to video stream'));
        setIsLoading(false);
      }
    };

    connect();
    
    // Cleanup function
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [cameraId, streamMode]);
  
  // Handle component unmount
  useEffect(() => {
    return () => {
      isComponentMounted.current = false;
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);
  
  // Function to render a frame from base64 data
  const renderFrame = (base64Data: string) => {
    if (!isComponentMounted.current) return;
    
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const img = new Image();
    img.onload = () => {
      // Adjust canvas size if needed
      if (canvas.width !== img.width || canvas.height !== img.height) {
        canvas.width = img.width;
        canvas.height = img.height;
      }
      
      // Draw the image
      ctx.drawImage(img, 0, 0);
    };
    
    img.src = 'data:image/jpeg;base64,' + base64Data;
  };
  
  // Switch between WebRTC and snapshot modes
  const toggleStreamMode = async () => {
    if (streamMode === 'webrtc') {
      // Switch to snapshot mode
      try {
        const blob = await getCameraSnapshot(cameraId);
        const url = URL.createObjectURL(blob);
        setSnapshot(url);
        setStreamMode('snapshot');
        
        // Close WebSocket connection
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
      } catch (err) {
        console.error('Error getting snapshot:', err);
        setError(err instanceof Error ? err : new Error('Failed to get snapshot'));
      }
    } else {
      // Switch to WebRTC mode
      if (snapshot) {
        URL.revokeObjectURL(snapshot);
        setSnapshot(null);
      }
      setStreamMode('webrtc');
    }
  };
  
  // Refresh snapshot
  const refreshSnapshot = async () => {
    if (streamMode !== 'snapshot') return;
    
    try {
      setIsLoading(true);
      
      // Clean up previous snapshot
      if (snapshot) {
        URL.revokeObjectURL(snapshot);
      }
      
      const blob = await getCameraSnapshot(cameraId);
      const url = URL.createObjectURL(blob);
      setSnapshot(url);
      setError(null);
    } catch (err) {
      console.error('Error refreshing snapshot:', err);
      setError(err instanceof Error ? err : new Error('Failed to refresh snapshot'));
    } finally {
      setIsLoading(false);
    }
  };
  
  // Render based on current state
  const renderContent = () => {
    if (isLoading && !isConnected && !snapshot) {
      return (
        <div className="flex items-center justify-center h-full">
          <Loader text="Loading camera stream..." />
        </div>
      );
    }
    
    if (error) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-red-50 p-4 rounded-md">
          <AlertTriangle className="text-red-500 mb-2" size={32} />
          <p className="text-red-700 text-center">{error.message}</p>
          <Button
            variant="primary"
            size="sm"
            className="mt-2"
            onClick={streamMode === 'webrtc' ? () => setStreamMode('webrtc') : refreshSnapshot}
            icon={<RefreshCw size={16} />}
          >
            Retry
          </Button>
        </div>
      );
    }
    
    if (streamMode === 'webrtc') {
      return <canvas ref={canvasRef} className="w-full h-full object-contain rounded-md" />;
    }
    
    if (streamMode === 'snapshot' && snapshot) {
      return (
        <img
          src={snapshot}
          alt="Camera snapshot"
          className="w-full h-full object-contain rounded-md"
        />
      );
    }
    
    return (
      <div className="flex items-center justify-center h-full bg-gray-100 rounded-md">
        <Loader text="Waiting for stream..." />
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
            icon={streamMode === 'webrtc' ? <Image size={16} /> : <Film size={16} />}
          >
            {streamMode === 'webrtc' ? 'Snapshot' : 'Stream'}
          </Button>
          
          {streamMode === 'snapshot' && (
            <Button
              variant="secondary"
              size="sm"
              onClick={refreshSnapshot}
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

export default WebRTCStream;