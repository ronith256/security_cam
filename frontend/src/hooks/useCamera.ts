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
    pollInterval = 10000,  // Reduced polling frequency to 10 seconds (longer interval)
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
  const pollingTimer = useRef<NodeJS.Timeout | null>(null);
  
  // Track request in progress
  const requestInProgress = useRef(false);
  
  // Use a ref for camera ID to avoid issues with closure
  const cameraIdRef = useRef(cameraId);
  useEffect(() => {
    cameraIdRef.current = cameraId;
  }, [cameraId]);

  // Fetch camera status with debouncing and request tracking
  const fetchStatus = useCallback(async (force = false) => {
    // Don't fetch if not polling and not forced
    if (!isPolling && !force) return;
    
    // Don't fetch if another request is in progress
    if (requestInProgress.current) return;
    
    // Don't fetch too frequently unless forced
    const now = Date.now();
    if (!force && now - lastFetchTime.current < pollInterval * 0.8) {
      return;
    }
    
    // Set loading only if we don't have data yet
    if (!status) {
      setIsLoading(true);
    }
    
    requestInProgress.current = true;
    
    try {
      lastFetchTime.current = now;
      const newStatus = await getCameraStatus(cameraIdRef.current);
      
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
        requestInProgress.current = false;
      }
    }
  }, [isPolling, status, pollInterval, onStatusChange]);

  // Setup polling with cleanup
  useEffect(() => {
    // Clean up any existing timer
    if (pollingTimer.current) {
      clearTimeout(pollingTimer.current);
      pollingTimer.current = null;
    }
    
    if (isPolling) {
      // Initial fetch
      fetchStatus(true);
      
      // Function to schedule next fetch
      const scheduleNextFetch = () => {
        pollingTimer.current = setTimeout(() => {
          if (isMounted.current) {
            fetchStatus().then(() => {
              if (isMounted.current) {
                scheduleNextFetch();
              }
            });
          }
        }, pollInterval);
      };
      
      scheduleNextFetch();
      
      return () => {
        if (pollingTimer.current) {
          clearTimeout(pollingTimer.current);
          pollingTimer.current = null;
        }
      };
    }
  }, [fetchStatus, isPolling, pollInterval]);

  // Handle cleanup
  useEffect(() => {
    isMounted.current = true;
    
    return () => {
      isMounted.current = false;
      if (pollingTimer.current) {
        clearTimeout(pollingTimer.current);
        pollingTimer.current = null;
      }
    };
  }, []);

  // Stable function references for external components
  const startPolling = useCallback(() => {
    setIsPolling(true);
  }, []);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
    
    // Clean up any existing timer
    if (pollingTimer.current) {
      clearTimeout(pollingTimer.current);
      pollingTimer.current = null;
    }
  }, []);

  // Manual refresh function that forces a new fetch
  const refresh = useCallback(() => {
    return fetchStatus(true);
  }, [fetchStatus]);

  return {
    status,
    isLoading,
    error,
    isPolling,
    startPolling,
    stopPolling,
    refresh,
  };
}