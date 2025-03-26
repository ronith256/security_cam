import React, { useState, useEffect, useRef } from 'react';
import ReactPlayer from 'react-player';
import { Loader2, AlertTriangle, RefreshCw } from 'lucide-react';
import Button from '../common/Button';
import { apiBaseUrl } from '../../api';
import axios from 'axios';

interface HLSStreamViewerProps {
  cameraId: number;
  rtspUrl?: string;
  height?: string;
  width?: string;
  onError?: (error: Error) => void;
  onReady?: () => void;
}

const HLSStreamViewer: React.FC<HLSStreamViewerProps> = ({
  cameraId,
  rtspUrl,
  height = 'h-72',
  width = 'w-full',
  onError,
  onReady
}) => {
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const playerRef = useRef<ReactPlayer | null>(null);
  const streamCheckInterval = useRef<NodeJS.Timeout | null>(null);
  const retryCount = useRef(0);
  const isMounted = useRef(true);

  // Function to start HLS stream
  const startHLSStream = async () => {
    if (!isMounted.current) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      // Request a new HLS stream for this camera
      const response = await axios.post(`${apiBaseUrl}/hls/start/${cameraId}`);
      
      if (!isMounted.current) return;
      
      if (response.data && response.data.url) {
        console.log(`Received HLS stream URL: ${response.data.url}`);
        
        // Add timestamp to URL to prevent caching issues
        const timestamp = new Date().getTime();
        const streamUrlWithTimestamp = `${response.data.url}?t=${timestamp}`;
        console.log(`Full stream URL with timestamp: ${streamUrlWithTimestamp}`);
        
        setStreamUrl(streamUrlWithTimestamp);
        setSessionId(response.data.session_id);
        
        // Start a periodic keep-alive request to prevent stream termination
        if (streamCheckInterval.current) {
          clearInterval(streamCheckInterval.current);
        }
        
        streamCheckInterval.current = setInterval(() => {
          if (isMounted.current && response.data.session_id) {
            axios.post(`${apiBaseUrl}/hls/keepalive/${response.data.session_id}`)
              .catch(error => console.error('Error sending keepalive:', error));
          }
        }, 30000); // Every 30 seconds
      } else {
        handleError(new Error('Failed to get stream URL from server'));
      }
    } catch (err) {
      if (!isMounted.current) return;
      
      const errorMessage = err instanceof Error ? err.message : 'Failed to start stream';
      console.error('Stream error:', err);
      handleError(new Error(errorMessage));
    }
  };

  // Function to handle errors
  const handleError = (err: Error) => {
    if (!isMounted.current) return;
    
    console.error('Stream error:', err);
    setError(err);
    setIsLoading(false);
    
    if (onError) {
      onError(err);
    }
  };

  // Function to handle player ready
  const handleReady = () => {
    if (!isMounted.current) return;
    
    console.log('ReactPlayer is ready');
    setIsLoading(false);
    retryCount.current = 0;
    
    if (onReady) {
      onReady();
    }
  };

  // Function to handle player errors with retry logic
  const handlePlayerError = (e: any) => {
    console.error('ReactPlayer error:', e);
    
    // Try to reload if we have retries left
    if (retryCount.current < 3) {
      retryCount.current++;
      console.log(`Retrying stream (${retryCount.current}/3)...`);
      
      // Short delay before retry
      setTimeout(() => {
        if (!isMounted.current) return;
        
        // Add new timestamp to force reload
        if (streamUrl) {
          const baseUrl = streamUrl.split('?')[0];
          const newUrl = `${baseUrl}?t=${new Date().getTime()}`;
          setStreamUrl(newUrl);
        } else {
          startHLSStream();
        }
      }, 2000);
    } else {
      handleError(new Error('Failed to play stream after multiple attempts'));
    }
  };

  // Set up the stream when component mounts
  useEffect(() => {
    isMounted.current = true;
    startHLSStream();
    
    // Cleanup function
    return () => {
      isMounted.current = false;
      
      // Stop the keepalive interval
      if (streamCheckInterval.current) {
        clearInterval(streamCheckInterval.current);
        streamCheckInterval.current = null;
      }
      
      // Terminate the stream session if we have one
      if (sessionId) {
        axios.delete(`${apiBaseUrl}/hls/stop/${sessionId}`)
          .catch(error => console.error('Error stopping stream:', error));
      }
    };
  }, [cameraId]); // Only depend on cameraId

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
  if (error) {
    return (
      <div className={`${width} ${height} bg-red-50 rounded-md flex flex-col items-center justify-center p-4`}>
        <AlertTriangle size={40} className="text-red-500 mb-2" />
        <p className="text-red-700 text-center mb-4">{error.message}</p>
        <Button 
          variant="primary" 
          onClick={() => {
            setError(null);
            setIsLoading(true);
            retryCount.current = 0;
            startHLSStream();
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
      {streamUrl && (
        <ReactPlayer
          ref={playerRef}
          url={streamUrl}
          width="100%"
          height="100%"
          playing
          controls={false}
          onReady={handleReady}
          onError={handlePlayerError}
          onBuffer={() => setIsLoading(true)}
          onBufferEnd={() => setIsLoading(false)}
          config={{
            file: {
              forceHLS: true, // Force HLS streaming
              forceVideo: true,
              attributes: {
                style: { objectFit: 'contain' },
                playsInline: true,
                crossorigin: "anonymous"
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
      
      {/* Indicator for HLS streaming */}
      <div className="absolute top-2 right-2 bg-blue-600 text-white text-xs py-1 px-2 rounded">
        HLS Stream
      </div>
    </div>
  );
};

export default HLSStreamViewer;