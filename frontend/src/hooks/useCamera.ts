// src/hooks/useCamera.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import { getCameraStatus, getCameraSnapshot } from '../api/cameras';
import { CameraStatus } from '../types/camera';
import { useInterval } from './useInterval';

interface UseCameraOptions {
  pollInterval?: number;
  autoStart?: boolean;
}

export function useCamera(cameraId: number, options: UseCameraOptions = {}) {
  const { pollInterval = 1000, autoStart = true } = options;

  const [status, setStatus] = useState<CameraStatus | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(autoStart);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!isPolling) return;

    try {
      setIsLoading(true);
      setError(null);

      const status = await getCameraStatus(cameraId);
      setStatus(status);

      if (status.active) {
        const snapshotBlob = await getCameraSnapshot(cameraId);
        const snapshotUrl = URL.createObjectURL(snapshotBlob);

        // Cleanup old snapshot URL before setting new one
        if (snapshot) {
          URL.revokeObjectURL(snapshot);
        }

        setSnapshot(snapshotUrl);
      }
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [cameraId, isPolling, snapshot]);

  // Initial fetch - with a proper ref to prevent infinite loop
  const initialFetchRef = useRef(autoStart);

  useEffect(() => {
    if (initialFetchRef.current) {
      fetchStatus();
      initialFetchRef.current = false;
    }

    // Clean up any object URLs when unmounting
    return () => {
      if (snapshot) {
        URL.revokeObjectURL(snapshot);
      }
    };
  }, [fetchStatus]);

  const startPolling = useCallback(() => {
    setIsPolling(true);
  }, []);

  const stopPolling = useCallback(() => {
    setIsPolling(false);
  }, []);

  // Initial fetch
  useEffect(() => {
    if (autoStart) {
      fetchStatus();
    }
    // Clean up any object URLs when unmounting
    return () => {
      if (snapshot) {
        URL.revokeObjectURL(snapshot);
      }
    };
  }, [autoStart, fetchStatus, snapshot]);

  // Set up polling
  useInterval(fetchStatus, isPolling ? pollInterval : null);

  return {
    status,
    snapshot,
    isLoading,
    error,
    startPolling,
    stopPolling,
    isPolling,
    refresh: fetchStatus,
  };
}