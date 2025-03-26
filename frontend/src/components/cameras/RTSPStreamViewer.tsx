// src/components/cameras/RTSPStreamViewer.tsx
import React, { useState, useEffect, useRef } from 'react';
import ReactPlayer from 'react-player';
import { Loader2, AlertTriangle } from 'lucide-react';
import Button from '../common/Button';
import { wsBaseUrl } from '../../api';

interface RTSPStreamViewerProps {
  cameraId: number;
  rtspUrl?: string;
  height?: string;
  width?: string;
  onError?: (error: Error) => void;
  onReady?: () => void;
  fallbackToWebRTC?: boolean;
}

const RTSPStreamViewer: React.FC<RTSPStreamViewerProps> = ({
  cameraId,
  rtspUrl,
  height = 'h-72',
  width = 'w-full',
  onError,
  onReady,
  fallbackToWebRTC = true
}) => {
  const [streamUrl, setStreamUrl] = useState<string | null>(rtspUrl || null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [isUsingWebRTC, setIsUsingWebRTC] = useState(false);
  const playerRef = useRef<ReactPlayer | null>(null);
  const webRTCSocketRef = useRef<WebSocket | null>(null);

  // Function to set up WebRTC streaming as fallback
  const setupWebRTCStream = () => {
    setIsLoading(true);
    setIsUsingWebRTC(true);
    
    // Close any existing WebSocket
    if (webRTCSocketRef.current) {
      webRTCSocketRef.current.close();
    }
    
    // Create WebSocket connection to our WebRTC server
    const ws = new WebSocket(`${wsBaseUrl}/webrtc/stream/${cameraId}`);
    webRTCSocketRef.current = ws;
    
    // Set up event handlers
    ws.onopen = () => {
      console.log(`WebRTC WebSocket opened for camera ${cameraId}`);
    };
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.type === 'webrtc_url') {
          // We received a WebRTC stream URL from our backend
          setStreamUrl(message.url);
          setIsLoading(false);
          if (onReady) onReady();
        } else if (message.type === 'error') {
          handleError(new Error(message.error));
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };
    
    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      handleError(new Error('Failed to connect to WebRTC stream'));
    };
    
    ws.onclose = () => {
      console.log('WebRTC WebSocket closed');
    };
  };

  // Function to handle errors
  const handleError = (err: Error) => {
    console.error('Stream error:', err);
    setError(err);
    setIsLoading(false);
    
    if (onError) {
      onError(err);
    }
    
    // If direct RTSP failed and fallback is enabled, try WebRTC
    if (!isUsingWebRTC && fallbackToWebRTC) {
      console.log('Falling back to WebRTC stream');
      setupWebRTCStream();
    }
  };

  // Function to handle player ready
  const handleReady = () => {
    setIsLoading(false);
    if (onReady) onReady();
  };

  // Set up the stream when component mounts or rtspUrl changes
  useEffect(() => {
    // If we have an RTSP URL, use it directly first
    if (rtspUrl) {
      setStreamUrl(rtspUrl);
      setIsUsingWebRTC(false);
    } else {
      // Otherwise use WebRTC
      setupWebRTCStream();
    }
    
    // Cleanup function
    return () => {
      if (webRTCSocketRef.current) {
        webRTCSocketRef.current.close();
      }
    };
  }, [rtspUrl, cameraId]);

  // If we're still loading and don't have a stream URL yet
  if (isLoading && !streamUrl) {
    return (
      <div className={`${width} ${height} bg-gray-100 rounded-md flex items-center justify-center`}>
        <div className="flex flex-col items-center">
          <Loader2 size={40} className="animate-spin text-gray-400 mb-2" />
          <p className="text-gray-600">Loading stream...</p>
        </div>
      </div>
    );
  }

  // If we have an error
  if (error && !isUsingWebRTC) {
    return (
      <div className={`${width} ${height} bg-red-50 rounded-md flex flex-col items-center justify-center p-4`}>
        <AlertTriangle size={40} className="text-red-500 mb-2" />
        <p className="text-red-700 text-center mb-4">{error.message}</p>
        <Button 
          variant="primary" 
          onClick={() => window.location.reload()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {streamUrl && (
        <ReactPlayer
          ref={playerRef}
          url={streamUrl}
          width="100%"
          height="100%"
          playing
          controls={false}
          onReady={handleReady}
          onError={handleError}
          onBuffer={() => setIsLoading(true)}
          onBufferEnd={() => setIsLoading(false)}
          config={{
            file: {
              // For WebRTC streams
              forceHLS: !isUsingWebRTC && streamUrl.includes('.m3u8'),
              forceVideo: true,
              attributes: {
                style: { objectFit: 'contain' },
                playsInline: true,
              }
            }
          }}
        />
      )}
      
      {isLoading && streamUrl && (
        <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50">
          <div className="flex flex-col items-center">
            <Loader2 size={40} className="animate-spin text-white mb-2" />
            <p className="text-white">Loading stream...</p>
          </div>
        </div>
      )}
      
      {/* Optional indicator for WebRTC fallback */}
      {isUsingWebRTC && (
        <div className="absolute top-2 right-2 bg-blue-600 text-white text-xs py-1 px-2 rounded">
          WebRTC
        </div>
      )}
    </div>
  );
};

export default RTSPStreamViewer;