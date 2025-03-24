// frontend/src/components/cameras/WebRTCStream.tsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { RefreshCw, AlertTriangle, Film, Maximize, Minimize, Zap, ZapOff } from 'lucide-react';
import Button from '../common/Button';
import Loader from '../common/Loader';
import WebRTCService, { StreamMode, WebRTCState } from '../../services/WebRTCService';

interface WebRTCStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
  onConnectionChange?: (connected: boolean) => void;
  highQuality?: boolean;  // Force high quality regardless of detailed view
}

const WebRTCStream: React.FC<WebRTCStreamProps> = ({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
  onConnectionChange,
  highQuality = false,
}) => {
  console.log('WebRTCStream component rendering with props:', { cameraId, showControls, height, width, highQuality });
  
  // State
  const [state, setState] = useState<WebRTCState>({
    isConnected: false,
    isLoading: true,
    error: null,
    sessionId: null,
    mode: highQuality ? StreamMode.WEBRTC : StreamMode.SNAPSHOT
  });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  
  // Refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const webrtcService = useRef<WebRTCService | null>(null);
  const cameraIdRef = useRef<number>(cameraId);
  const isMounted = useRef<boolean>(true);
  
  // Initialize WebRTC service
  useEffect(() => {
    console.log('WebRTCStream initialization effect running');
    
    webrtcService.current = WebRTCService.getInstance().init(
      videoRef.current,
      canvasRef.current,
      (newState: WebRTCState) => {
        console.log('WebRTCStream state update from service:', newState);
        if (isMounted.current) {
          setState(prevState => ({ ...prevState, ...newState }));
        }
      }
    );
    
    return () => {
      console.log('WebRTCStream component unmounting');
      isMounted.current = false;
      if (webrtcService.current) {
        webrtcService.current.destroy();
        webrtcService.current = null;
      }
    };
  }, []);
  
  // Update camera ID ref when it changes
  useEffect(() => {
    console.log('Camera ID changed to:', cameraId);
    cameraIdRef.current = cameraId;
  }, [cameraId]);
  
  // Handle fullscreen change events
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, []);
  
  // Connect to the camera with the current mode
  useEffect(() => {
    console.log('WebRTCStream connect effect running for camera:', cameraId);
    
    // Use a small delay to ensure any previous connection is fully cleaned up
    const connectTimer = setTimeout(() => {
      console.log('Connect timer triggered, connecting to camera', cameraIdRef.current);
      
      if (isMounted.current && webrtcService.current) {
        const initialMode = highQuality ? StreamMode.WEBRTC : StreamMode.SNAPSHOT;
        console.log('Connecting with mode:', initialMode);
        
        webrtcService.current.connect({
          cameraId: cameraIdRef.current,
          mode: initialMode,
          onConnectionChange: (connected) => {
            console.log('Connection change callback:', connected);
            if (onConnectionChange) onConnectionChange(connected);
          },
          onError: (error) => {
            console.error('WebRTC connection error:', error);
          }
        }).catch(err => {
          console.error('Error connecting to camera:', err);
        });
      } else {
        console.warn('Cannot connect: component not mounted or service not initialized');
      }
    }, 300);
    
    return () => {
      console.log('Cleaning up WebRTCStream connect effect');
      clearTimeout(connectTimer);
      if (webrtcService.current) {
        webrtcService.current.cleanup();
      }
    };
  }, [cameraId, highQuality, onConnectionChange]);
  
  // Function to toggle fullscreen mode
  const toggleFullscreen = useCallback(() => {
    const videoElement = videoRef.current;
    const canvasElement = canvasRef.current;
    const element = state.mode === StreamMode.WEBRTC ? videoElement : canvasElement;
    
    if (!element) return;
    
    if (!isFullscreen) {
      if (element.requestFullscreen) {
        element.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  }, [isFullscreen, state.mode]);
  
  // Function to toggle stream mode
  const toggleStreamMode = useCallback(() => {
    console.log('Toggling stream mode');
    if (webrtcService.current) {
      webrtcService.current.toggleMode().catch(err => {
        console.error('Error toggling mode:', err);
      });
    }
  }, []);
  
  // Function to take a template snapshot
  const takeTemplateSnapshot = useCallback(async () => {
    console.log('Taking template snapshot');
    if (webrtcService.current) {
      try {
        await webrtcService.current.takeTemplateSnapshot();
        alert('Template snapshot updated successfully!');
      } catch (error) {
        console.error('Error taking template snapshot:', error);
        alert('Failed to take template snapshot: ' + (error instanceof Error ? error.message : 'Unknown error'));
      }
    }
  }, []);
  
  // Function to handle reconnection
  const handleReconnect = useCallback(() => {
    console.log('Manual reconnection requested');
    if (webrtcService.current) {
      webrtcService.current.connect({
        cameraId: cameraIdRef.current,
        mode: state.mode,
        onConnectionChange,
        onError: (error) => {
          console.error('WebRTC connection error during reconnect:', error);
        }
      }).catch(err => {
        console.error('Error during manual reconnect:', err);
      });
    }
  }, [state.mode, onConnectionChange]);
  
  // Render based on current state
  const renderContent = () => {
    if (state.isLoading && !state.isConnected) {
      return (
        <div className="flex items-center justify-center h-full">
          <Loader text={`Loading camera ${state.mode === StreamMode.WEBRTC ? 'stream' : 'snapshot'}...`} />
        </div>
      );
    }
    
    if (state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-red-50 p-4 rounded-md">
          <AlertTriangle className="text-red-500 mb-2" size={32} />
          <p className="text-red-700 text-center">{state.error.message}</p>
          <Button
            variant="primary"
            size="sm"
            className="mt-2"
            onClick={handleReconnect}
            icon={<RefreshCw size={16} />}
          >
            Retry Connection
          </Button>
        </div>
      );
    }
    
    // Select the appropriate element based on mode
    if (state.mode === StreamMode.WEBRTC) {
      console.log('Rendering video element');
      return (
        <video 
          ref={videoRef} 
          className="w-full h-full object-contain rounded-md" 
          autoPlay 
          playsInline
          controls={false}
          onLoadedMetadata={() => console.log('Video metadata loaded')}
          onPlay={() => console.log('Video started playing')}
          onError={(e) => console.error('Video element error:', e)}
        />
      );
    } else {
      console.log('Rendering canvas element');
      return (
        <canvas ref={canvasRef} className="w-full h-full object-contain rounded-md" />
      );
    }
  };
  
  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {renderContent()}
      
      {showControls && !state.error && state.isConnected && (
        <div className="absolute bottom-2 right-2 flex space-x-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={toggleStreamMode}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={state.mode === StreamMode.WEBRTC ? <ZapOff size={16} /> : <Zap size={16} />}
          >
            {state.mode === StreamMode.WEBRTC ? 'Low BW' : 'High Quality'}
          </Button>
          
          <Button
            variant="secondary"
            size="sm"
            onClick={toggleFullscreen}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
          >
            {isFullscreen ? 'Exit Full' : 'Fullscreen'}
          </Button>
          
          <Button
            variant="secondary"
            size="sm"
            onClick={takeTemplateSnapshot}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={<Film size={16} />}
          >
            Set Template
          </Button>
        </div>
      )}
    </div>
  );
};

export default WebRTCStream;