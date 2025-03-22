// src/hooks/useCamera.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import { getCameraStatus } from '../api/cameras';
import { CameraStatus } from '../types/camera';

interface UseCameraOptions {
  pollInterval?: number;
  autoStart?: boolean;
  onStatusChange?: (status: CameraStatus | null) => void;
}

export function useCamera(cameraId: number, options: UseCameraOptions = {}) {
  const { 
    pollInterval = 5000,  // Reduced polling frequency to 5 seconds
    autoStart = true,
    onStatusChange
  } = options;

  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [isPolling, setIsPolling] = useState(autoStart);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  // Tracking when component is mounted
  const isMounted = useRef(true);
  
  // Track last fetch time to prevent excessive fetching
  const lastFetchTime = useRef(0);
  
  // Track polling timers
  const pollingTimer = useRef<number | null>(null);

  const fetchStatus = useCallback(async (force = false) => {
    // Don't fetch if not polling and not forced
    if (!isPolling && !force) return;
    
    // Don't fetch too frequently unless forced
    const now = Date.now();
    if (!force && now - lastFetchTime.current < pollInterval) {
      return;
    }
    
    // Set loading only if we don't have data yet
    if (!status) {
      setIsLoading(true);
    }
    
    try {
      lastFetchTime.current = now;
      const newStatus = await getCameraStatus(cameraId);
      
      if (!isMounted.current) return;
      
      setStatus(newStatus);
      setError(null);
      
      if (onStatusChange) {
        onStatusChange(newStatus);
      }
    } catch (err) {
      if (!isMounted.current) return;
      
      const error = err as Error;
      setError(error);
      console.error("Error fetching camera status:", error);
    } finally {
      if (isMounted.current) {
        setIsLoading(false);
      }
    }
  }, [cameraId, isPolling, status, pollInterval, onStatusChange]);

  // Setup polling
  useEffect(() => {
    if (isPolling) {
      // Initial fetch
      fetchStatus(true);
      
      // Set up interval for subsequent fetches
      const intervalId = window.setInterval(() => {
        fetchStatus();
      }, pollInterval);
      
      pollingTimer.current = intervalId;
      
      return () => {
        window.clearInterval(intervalId);
        pollingTimer.current = null;
      };
    } else if (pollingTimer.current !== null) {
      window.clearInterval(pollingTimer.current);
      pollingTimer.current = null;
    }
  }, [fetchStatus, isPolling, pollInterval]);

  // Handle cleanup
  useEffect(() => {
    return () => {
      isMounted.current = false;
      if (pollingTimer.current !== null) {
        window.clearInterval(pollingTimer.current);
      }
    };
  }, []);

  const startPolling = useCallback(() => {
    setIsPolling(true);
  }, []);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
  }, []);

  return {
    status,
    isLoading,
    error,
    isPolling,
    startPolling,
    stopPolling,
    refresh: () => fetchStatus(true),
  };
}