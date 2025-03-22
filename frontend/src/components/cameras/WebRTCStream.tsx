// src/components/cameras/WebRTCStream.tsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { RefreshCw, AlertTriangle, Film } from 'lucide-react';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { getCameraSnapshot } from '../../api/cameras';

// Import the WebSocket base URL from our API config
import { wsBaseUrl } from '../../api/index';

interface WebSocketWithPing extends WebSocket {
  pingInterval?: NodeJS.Timeout;
}

interface WebRTCStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
  onConnectionChange?: (connected: boolean) => void;
}

const WebRTCStream: React.FC<WebRTCStreamProps> = ({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
  onConnectionChange,
}) => {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocketWithPing | null>(null);
  const connectionAttemptRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const cameraIdRef = useRef<number>(cameraId); // Store camera ID to avoid closure issues
  
  // To track component mount state
  const isMounted = useRef(true);
  
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
    console.log('Cleaning up WebRTC resources');
    // Clear any reconnect timeouts
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    // Close WebSocket connection
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
    
    // Release snapshot URL if it exists
    if (snapshot) {
      URL.revokeObjectURL(snapshot);
    }
  }, [snapshot]);
  
  // Function to render a frame from base64 data
  const renderFrame = useCallback((base64Data: string) => {
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
  
  // Connect to WebRTC stream
  const connectWebSocket = useCallback(() => {
    // Clean up existing connection first
    cleanupResources();
    
    if (!isMounted.current) return;
    
    // Increment connection attempt counter
    connectionAttemptRef.current += 1;
    const currentAttempt = connectionAttemptRef.current;
    
    setIsLoading(true);
    setError(null);
    
    try {
      // Get the WebSocket URL using our API configuration
      // Extract the base path from wsBaseUrl and ensure it ends with /api if it doesn't contain it
      const baseUrl = wsBaseUrl.endsWith('/api') ? wsBaseUrl : 
                    (wsBaseUrl.includes('/api') ? wsBaseUrl : `${wsBaseUrl}/api`);
      
      // Construct the WebSocket URL for the WebRTC endpoint
      const wsUrl = `${baseUrl}/webrtc/ws/${cameraIdRef.current}`;
      
      console.log(`Connecting to WebSocket: ${wsUrl}`);
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        if (!isMounted.current) {
          ws.close();
          return;
        }
        
        console.log(`WebSocket connected for camera ${cameraIdRef.current}`);
        setIsConnected(true);
        setIsLoading(false);
        connectionAttemptRef.current = 0; // Reset counter on successful connection
        
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
          
          if (message.type === 'frame') {
            // Handle incoming frame (base64 encoded JPEG)
            renderFrame(message.data);
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
        setError(new Error('Failed to connect to video stream'));
        setIsConnected(false);
        setIsLoading(false);
        
        // Notify parent about disconnection
        notifyConnectionChange(false);
        
        // Attempt to reconnect with exponential backoff
        if (currentAttempt === connectionAttemptRef.current && connectionAttemptRef.current < 5) {
          const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
          console.log(`Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
          
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
        
        // Clean up ping interval
        if (ws.pingInterval) {
          clearInterval(ws.pingInterval);
          ws.pingInterval = undefined;
        }
        
        // Notify parent about disconnection
        notifyConnectionChange(false);
        
        // Attempt to reconnect with exponential backoff if not closed cleanly
        if (event.code !== 1000 && event.code !== 1001 && 
            currentAttempt === connectionAttemptRef.current && 
            connectionAttemptRef.current < 5) {
          
          const delay = Math.min(1000 * Math.pow(2, connectionAttemptRef.current), 30000);
          console.log(`WebSocket closed. Will attempt reconnection in ${delay}ms (attempt ${connectionAttemptRef.current})`);
          
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
      setError(err instanceof Error ? err : new Error('Failed to connect to video stream'));
      setIsLoading(false);
      
      // Notify parent about connection failure
      notifyConnectionChange(false);
    }
  }, [cleanupResources, notifyConnectionChange, renderFrame]);

  // Take a snapshot
  const takeSnapshot = useCallback(async () => {
    if (!isMounted.current) return;
    
    try {
      setIsLoading(true);
      
      // Clean up previous snapshot
      if (snapshot) {
        URL.revokeObjectURL(snapshot);
      }
      
      const blob = await getCameraSnapshot(cameraIdRef.current);
      const url = URL.createObjectURL(blob);
      setSnapshot(url);
      setError(null);
    } catch (err) {
      console.error('Error taking snapshot:', err);
      setError(err instanceof Error ? err : new Error('Failed to take snapshot'));
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [snapshot]);
  
  // Manual reconnect
  const handleReconnect = useCallback(() => {
    // Reset connection attempts
    connectionAttemptRef.current = 0;
    connectWebSocket();
  }, [connectWebSocket]);
  
  // Store camera ID when it changes
  useEffect(() => {
    cameraIdRef.current = cameraId;
  }, [cameraId]);
  
  // Initial connection setup
  useEffect(() => {
    // Set isMounted to true
    isMounted.current = true;
    
    console.log(`Initializing WebRTC stream for camera ${cameraId}`);
    connectWebSocket();
    
    // Cleanup function
    return () => {
      console.log(`Cleaning up WebRTC stream for camera ${cameraId}`);
      isMounted.current = false;
      cleanupResources();
      
      // Make sure we notify the parent about disconnection on unmount
      notifyConnectionChange(false);
    };
  }, [cameraId, cleanupResources, connectWebSocket, notifyConnectionChange]);
  
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
            onClick={handleReconnect}
            icon={<RefreshCw size={16} />}
          >
            Retry Connection
          </Button>
        </div>
      );
    }
    
    if (snapshot) {
      return (
        <div className="relative w-full h-full">
          <img
            src={snapshot}
            alt="Camera snapshot"
            className="w-full h-full object-contain rounded-md"
          />
          <Button
            variant="secondary"
            size="sm"
            className="absolute top-2 right-2 bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            onClick={() => {
              if (snapshot) {
                URL.revokeObjectURL(snapshot);
                setSnapshot(null);
              }
            }}
          >
            Back to Stream
          </Button>
        </div>
      );
    }
    
    return (
      <canvas ref={canvasRef} className="w-full h-full object-contain rounded-md" />
    );
  };
  
  return (
    <div className={`${width} ${height} bg-black rounded-md overflow-hidden relative`}>
      {renderContent()}
      
      {showControls && !snapshot && !error && isConnected && (
        <div className="absolute bottom-2 right-2 flex space-x-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={takeSnapshot}
            className="bg-gray-800 bg-opacity-75 hover:bg-gray-700"
            icon={<Film size={16} />}
          >
            Snapshot
          </Button>
        </div>
      )}
    </div>
  );
};

export default WebRTCStream;