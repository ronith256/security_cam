// frontend/src/components/cameras/WebRTCStream.tsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { RefreshCw, AlertTriangle, Film, Maximize, Minimize, Zap, ZapOff } from 'lucide-react';
import Button from '../common/Button';
import Loader from '../common/Loader';
import axios from 'axios';
import { apiBaseUrl, wsBaseUrl } from '../../api/index';

// Different streaming modes
enum StreamMode {
  SNAPSHOT = 'snapshot',  // Low bandwidth mode - periodic snapshots
  WEBRTC = 'webrtc',      // High quality mode - WebRTC streaming
}

interface WebSocketWithPing extends WebSocket {
  pingInterval?: NodeJS.Timeout;
}

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
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [streamMode, setStreamMode] = useState<StreamMode>(
    highQuality ? StreamMode.WEBRTC : StreamMode.SNAPSHOT
  );
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  
  // WebRTC
  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  
  // WebSocket for snapshot mode
  const wsRef = useRef<WebSocketWithPing | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const connectionAttemptRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const cameraIdRef = useRef<number>(cameraId); // Store camera ID to avoid closure issues
  
  // To track component mount state
  const isMounted = useRef(true);
  
  // Track active connection to prevent multiple connection attempts
  const isConnectingRef = useRef<boolean>(false);
  
  // Track if connection change callback has been called
  const connectionNotifiedRef = useRef<boolean | null>(null);

  // Function to notify parent about connection change
  const notifyConnectionChange = useCallback((connected: boolean) => {
    // Only notify if the state has changed or not been set yet
    if (connectionNotifiedRef.current !== connected && onConnectionChange) {
      connectionNotifiedRef.current = connected;
      onConnectionChange(connected);
    }
  }, [onConnectionChange]);

  // Clean up resources
  const cleanupResources = useCallback(() => {
    console.log('Cleaning up resources');
    
    // Clear any reconnect timeouts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    // Close WebSocket connection for snapshot mode
    if (wsRef.current) {
      // Clear ping interval if it exists
      if (wsRef.current.pingInterval) {
        clearInterval(wsRef.current.pingInterval);
        wsRef.current.pingInterval = undefined;
      }
      
      // Only attempt to close if not already closed
      if (wsRef.current.readyState !== WebSocket.CLOSED && 
          wsRef.current.readyState !== WebSocket.CLOSING) {
        try {
          console.log('Closing WebSocket connection');
          wsRef.current.close();
        } catch (err) {
          console.error('Error closing WebSocket:', err);
        }
      }
      wsRef.current = null;
    }
    
    // Close WebRTC connection
    if (peerConnectionRef.current) {
      try {
        peerConnectionRef.current.close();
      } catch (err) {
        console.error('Error closing peer connection:', err);
      }
      peerConnectionRef.current = null;
    }
    
    // Stop video playback
    if (videoRef.current) {
      if (videoRef.current.srcObject) {
        const mediaStream = videoRef.current.srcObject as MediaStream;
        if (mediaStream) {
          mediaStream.getTracks().forEach(track => track.stop());
        }
      }
      videoRef.current.srcObject = null;
    }
    
    // Reset connection state
    isConnectingRef.current = false;
  }, []);
  
  // Function to toggle fullscreen mode
  const toggleFullscreen = useCallback(() => {
    const videoElement = videoRef.current;
    const canvasElement = canvasRef.current;
    const element = streamMode === StreamMode.WEBRTC ? videoElement : canvasElement;
    
    if (!element) return;
    
    if (!isFullscreen) {
      if (element.requestFullscreen) {
        element.requestFullscreen();
      }
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
      setIsFullscreen(false);
    }
  }, [isFullscreen, streamMode]);
  
  // Function to toggle stream mode
  const toggleStreamMode = useCallback(() => {
    // Clean up existing connections first
    cleanupResources();
    
    // Switch mode
    const newMode = streamMode === StreamMode.SNAPSHOT 
      ? StreamMode.WEBRTC 
      : StreamMode.SNAPSHOT;
    
    setStreamMode(newMode);
    setIsConnected(false);
    setIsLoading(true);
    setError(null);
    
    // Reset connection attempt counter
    connectionAttemptRef.current = 0;
  }, [streamMode, cleanupResources]);
  
  // Connect using WebRTC
  const connectWebRTC = useCallback(async () => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || !isMounted.current) return;
    
    isConnectingRef.current = true;
    setIsLoading(true);
    setError(null);
    
    try {
      console.log(`Setting up WebRTC connection for camera ${cameraIdRef.current}`);
      
      // Clean up any existing connection first
      if (peerConnectionRef.current) {
        try {
          peerConnectionRef.current.close();
        } catch (e) {
          console.error('Error closing existing peer connection:', e);
        }
        peerConnectionRef.current = null;
      }
      
      // Create peer connection with STUN server config
      const pc = new RTCPeerConnection({
        iceServers: [
          {
            urls: 'stun:stun.l.google.com:19302'
          }
        ]
      });
      peerConnectionRef.current = pc;
      
      // Handle ICE candidates
      pc.onicecandidate = async (event) => {
        if (event.candidate) {
          try {
            await axios.post(`${apiBaseUrl}/webrtc/ice-candidate`, {
              cameraId: cameraIdRef.current,
              candidate: event.candidate.candidate,
              sdpMid: event.candidate.sdpMid,
              sdpMLineIndex: event.candidate.sdpMLineIndex,
            });
          } catch (err) {
            console.error('Error sending ICE candidate:', err);
          }
        }
      };
      
      // Handle connection state changes
      pc.onconnectionstatechange = () => {
        console.log(`WebRTC connection state: ${pc.connectionState}`);
        
        if (pc.connectionState === 'connected') {
          setIsConnected(true);
          setIsLoading(false);
          connectionAttemptRef.current = 0;
          notifyConnectionChange(true);
          isConnectingRef.current = false;
        } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected' || pc.connectionState === 'closed') {
          setIsConnected(false);
          notifyConnectionChange(false);
          isConnectingRef.current = false;
          
          // Attempt to reconnect with exponential backoff
          if (isMounted.current && connectionAttemptRef.current < 5) {
            connectionAttemptRef.current += 1;
            const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
            console.log(`WebRTC connection failed. Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
            
            if (reconnectTimeoutRef.current) {
              clearTimeout(reconnectTimeoutRef.current);
            }
            
            reconnectTimeoutRef.current = setTimeout(() => {
              if (isMounted.current) {
                reconnectTimeoutRef.current = null;
                connectWebRTC();
              }
            }, delay);
          } else if (isMounted.current) {
            setError(new Error('Failed to establish a stable WebRTC connection'));
          }
        }
      };
      
      // Handle track events for incoming video
      pc.ontrack = (event) => {
        if (videoRef.current && event.streams && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0];
        }
      };
      
      // Create offer to initialize connection
      const offer = await pc.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: false
      });
      
      await pc.setLocalDescription(offer);
      
      // Send offer to server
      const response = await axios.post(`${apiBaseUrl}/webrtc/offer`, {
        cameraId: cameraIdRef.current,
        sdp: offer.sdp
      });
      
      // Process the SDP answer from server
      const answerSDP = response.data.sdp;
      const answerType = response.data.type;
      
      const remoteDesc = new RTCSessionDescription({
        sdp: answerSDP,
        type: answerType as RTCSdpType
      });
      
      await pc.setRemoteDescription(remoteDesc);
      
      console.log('WebRTC connection established');
      
    } catch (err) {
      if (!isMounted.current) return;
      
      console.error('Error setting up WebRTC:', err);
      setError(err instanceof Error ? err : new Error('Failed to establish WebRTC connection'));
      setIsLoading(false);
      notifyConnectionChange(false);
      isConnectingRef.current = false;
      
      // Clean up failed connection
      if (peerConnectionRef.current) {
        try {
          peerConnectionRef.current.close();
        } catch (e) {
          console.error('Error closing peer connection:', e);
        }
        peerConnectionRef.current = null;
      }
      
      // Attempt reconnection with exponential backoff
      if (isMounted.current && connectionAttemptRef.current < 5) {
        connectionAttemptRef.current += 1;
        const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
        console.log(`WebRTC connection failed. Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
        
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        
        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMounted.current) {
            reconnectTimeoutRef.current = null;
            connectWebRTC();
          }
        }, delay);
      }
    }
  }, [notifyConnectionChange]);
  
  // Connect using WebSocket for snapshots
  const connectWebSocket = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || !isMounted.current) return;
    
    isConnectingRef.current = true;
    
    // Clean up existing connection first
    if (wsRef.current) {
      if (wsRef.current.pingInterval) {
        clearInterval(wsRef.current.pingInterval);
        wsRef.current.pingInterval = undefined;
      }
      
      if (wsRef.current.readyState !== WebSocket.CLOSED && 
          wsRef.current.readyState !== WebSocket.CLOSING) {
        try {
          wsRef.current.close();
        } catch (err) {
          console.error('Error closing WebSocket:', err);
        }
      }
      wsRef.current = null;
    }
    
    if (!isMounted.current) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      // Get the WebSocket URL
      const baseUrl = wsBaseUrl.endsWith('/api') ? wsBaseUrl : 
                    (wsBaseUrl.includes('/api') ? wsBaseUrl : `${wsBaseUrl}/api`);
      
      // Use the snapshot WebSocket endpoint
      const wsUrl = `${baseUrl}/webrtc/snapshot/${cameraIdRef.current}`;
      
      console.log(`Connecting to WebSocket for snapshots: ${wsUrl}`);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        if (!isMounted.current) {
          ws.close();
          return;
        }
        
        console.log(`WebSocket connected for camera ${cameraIdRef.current} snapshots`);
        setIsConnected(true);
        setIsLoading(false);
        connectionAttemptRef.current = 0; // Reset counter on successful connection
        isConnectingRef.current = false;
        
        // Set up ping interval to keep the connection alive
        ws.pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: "ping" }));
            } catch (err) {
              console.error("Error sending ping:", err);
            }
          } else {
            if (ws.pingInterval) {
              clearInterval(ws.pingInterval);
              ws.pingInterval = undefined;
            }
          }
        }, 30000); // 30-second ping
        
        // Notify parent about connection
        notifyConnectionChange(true);
      };
      
      ws.onmessage = (event) => {
        if (!isMounted.current) return;
        
        try {
          const message = JSON.parse(event.data);
          
          if (message.type === 'snapshot') {
            // Handle incoming snapshot (base64 encoded JPEG)
            renderSnapshot(message.data);
          } else if (message.type === 'pong') {
            // Pong response received (optional handling)
            console.debug('Received pong from server');
          } else if (message.type === 'info') {
            console.log(`Info from server: ${message.message || ''}`);
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };
      
      ws.onerror = (event) => {
        if (!isMounted.current) return;
        
        console.error('WebSocket error:', event);
        setError(new Error('Failed to connect to snapshot stream'));
        setIsConnected(false);
        setIsLoading(false);
        isConnectingRef.current = false;
        
        // Notify parent about disconnection
        notifyConnectionChange(false);
        
        // Attempt to reconnect with exponential backoff
        if (isMounted.current && connectionAttemptRef.current < 5) {
          connectionAttemptRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
          console.log(`Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
          
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMounted.current) {
              reconnectTimeoutRef.current = null;
              connectWebSocket();
            }
          }, delay);
        }
      };
      
      ws.onclose = (event) => {
        if (!isMounted.current) return;
        
        console.log('WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        setIsLoading(false);
        isConnectingRef.current = false;
        
        // Clean up ping interval
        if (ws.pingInterval) {
          clearInterval(ws.pingInterval);
          ws.pingInterval = undefined;
        }
        
        // Notify parent about disconnection
        notifyConnectionChange(false);
        
        // Attempt to reconnect with exponential backoff if not closed cleanly
        if (event.code !== 1000 && event.code !== 1001 && 
            isMounted.current && connectionAttemptRef.current < 5) {
          
          connectionAttemptRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
          console.log(`WebSocket closed. Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
          
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMounted.current) {
              reconnectTimeoutRef.current = null;
              connectWebSocket();
            }
          }, delay);
        }
      };
    } catch (err) {
      if (!isMounted.current) return;
      
      console.error('Error setting up WebSocket:', err);
      setError(err instanceof Error ? err : new Error('Failed to connect to snapshot stream'));
      setIsLoading(false);
      isConnectingRef.current = false;
      
      // Notify parent about connection failure
      notifyConnectionChange(false);
    }
  }, [notifyConnectionChange]);
  
  // Render a snapshot from base64 data
  const renderSnapshot = useCallback((base64Data: string) => {
    if (!isMounted.current) return;
    
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
  }, []);
  
  // Function to handle taking a snapshot using the base template API
  const takeTemplateSnapshot = useCallback(async () => {
    try {
      setIsLoading(true);
      
      // Call template snapshot API
      await axios.post(`${apiBaseUrl}/webrtc/template/${cameraIdRef.current}`);
      
      setIsLoading(false);
      alert('Template snapshot updated successfully!');
    } catch (err) {
      console.error('Error taking template snapshot:', err);
      setError(err instanceof Error ? err : new Error('Failed to take template snapshot'));
      setIsLoading(false);
    }
  }, []);
  
  // Store camera ID when it changes
  useEffect(() => {
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
  
  // Connection logic based on current mode - with proper cleanup and state tracking
  useEffect(() => {
    // Set isMounted to true
    isMounted.current = true;
    
    // Clear any existing connection attempts first
    cleanupResources();
    
    // Reset connection state
    connectionAttemptRef.current = 0;
    setIsConnected(false);
    setIsLoading(true);
    setError(null);
    
    console.log(`Initializing camera stream for camera ${cameraId} in ${streamMode} mode`);
    
    // Connect based on current mode
    if (streamMode === StreamMode.WEBRTC) {
      connectWebRTC();
    } else {
      connectWebSocket();
    }
    
    // Cleanup function
    return () => {
      console.log(`Cleaning up camera stream for camera ${cameraId}`);
      isMounted.current = false;
      cleanupResources();
      
      // Make sure we notify the parent about disconnection on unmount
      notifyConnectionChange(false);
    };
  }, [cameraId, streamMode, connectWebRTC, connectWebSocket, cleanupResources, notifyConnectionChange]);
  
  // Switch mode if highQuality prop changes, but only once on init or when it changes
  useEffect(() => {
    const newMode = highQuality ? StreamMode.WEBRTC : StreamMode.SNAPSHOT;
    if (newMode !== streamMode) {
      setStreamMode(newMode);
    }
  }, [highQuality, streamMode]);
  
  // Manual reconnect - fully cleanup first
  const handleReconnect = useCallback(() => {
    // Reset connection attempts
    connectionAttemptRef.current = 0;
    
    // Clean up existing connections
    cleanupResources();
    
    // Reset state
    setIsConnected(false);
    setIsLoading(true);
    setError(null);
    
    // Connect based on current mode
    if (streamMode === StreamMode.WEBRTC) {
      connectWebRTC();
    } else {
      connectWebSocket();
    }
  }, [streamMode, connectWebRTC, connectWebSocket, cleanupResources]);
  
  // Render based on current state and mode
  const renderContent = () => {
    if (isLoading && !isConnected) {
      return (
        <div className="flex items-center justify-center h-full">
          <Loader text={`Loading camera ${streamMode === StreamMode.WEBRTC ? 'stream' : 'snapshot'}...`} />
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
            onClick={handleReconnect}
            icon={<RefreshCw size={16} />}
          >
            Retry Connection
          </Button>
        </div>
      );
    }
    
    // Select the appropriate component for the current mode
    if (streamMode === StreamMode.WEBRTC) {
      return (
        <video 
          ref={videoRef} 
          className="w-full h-full object-contain rounded-md" 
          autoPlay 
          playsInline
        />
      );
    } else {
      return (
        <canvas ref={canvasRef} className="w-full h-full object-contain rounded-md" />
      );
    }
  };
  
  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {renderContent()}
      
      {showControls && !error && isConnected && (
        <div className="absolute bottom-2 right-2 flex space-x-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={toggleStreamMode}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={streamMode === StreamMode.WEBRTC ? <ZapOff size={16} /> : <Zap size={16} />}
          >
            {streamMode === StreamMode.WEBRTC ? 'Low BW' : 'High Quality'}
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