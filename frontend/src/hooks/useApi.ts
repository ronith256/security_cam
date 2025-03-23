// src/hooks/useApi.ts
import { useState, useCallback, useRef, useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import axios, { AxiosError } from 'axios';

interface UseApiOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: Error | AxiosError) => void;
  showSuccessToast?: boolean;
  showErrorToast?: boolean;
  successMessage?: string;
  executeOnMount?: boolean;  // Add option to execute on mount
  args?: any[];              // Arguments to pass to the function on mount
}

export function useApi<T>(
  apiFunction: (...args: any[]) => Promise<T>,
  options: UseApiOptions<T> = {}
) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | AxiosError | null>(null);
  const { showToast } = useToast();
  
  // Store options in refs to prevent them from causing re-renders
  const optionsRef = useRef(options);
  optionsRef.current = options; // Update ref on each render
  
  // Track component mount state
  const isMounted = useRef(true);
  
  // Track if a request is in progress to prevent concurrent calls
  const requestInProgress = useRef(false);
  
  // Track last request time for debouncing
  const lastRequestTime = useRef(0);
  const minRequestInterval = 300; // ms
  
  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);
  
  // Execute on mount if configured
  useEffect(() => {
    if (optionsRef.current.executeOnMount) {
      const args = optionsRef.current.args || [];
      execute(...args);
    }
  }, [/* empty dependency array to execute only on mount */]);
  
  const execute = useCallback(
    async (...args: any[]) => {
      // Don't allow concurrent requests to the same endpoint
      if (requestInProgress.current) {
        console.warn('Request already in progress, skipping duplicate request');
        return null;
      }
      
      // Implement basic debouncing
      const now = Date.now();
      if (now - lastRequestTime.current < minRequestInterval) {
        const delay = minRequestInterval - (now - lastRequestTime.current);
        console.log(`Delaying request by ${delay}ms to prevent API overload`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
      
      setIsLoading(true);
      setError(null);
      requestInProgress.current = true;
      lastRequestTime.current = Date.now();
      
      try {
        const result = await apiFunction(...args);
        
        if (!isMounted.current) return null;
        
        setData(result);
        
        if (optionsRef.current.onSuccess) {
          optionsRef.current.onSuccess(result);
        }
        
        if (optionsRef.current.showSuccessToast) {
          showToast(optionsRef.current.successMessage || 'Operation successful', 'success');
        }
        
        return result;
      } catch (err) {
        const error = err as Error | AxiosError;
        
        if (!isMounted.current) return null;
        
        setError(error);
        
        if (optionsRef.current.onError) {
          optionsRef.current.onError(error);
        }
        
        if (optionsRef.current.showErrorToast) {
          let errorMessage = 'An error occurred';
          
          if (axios.isAxiosError(error) && error.response?.data?.detail) {
            errorMessage = error.response.data.detail;
          } else if (error.message) {
            errorMessage = error.message;
          }
          
          showToast(errorMessage, 'error');
        }
        
        throw error;
      } finally {
        if (isMounted.current) {
          setIsLoading(false);
        }
        
        // Wait a short time before allowing new requests
        // This helps prevent rapid consecutive requests that might overload the server
        setTimeout(() => {
          requestInProgress.current = false;
        }, 100);
      }
    },
    [apiFunction, showToast] // Only depend on stable dependencies
  );

  return {
    data,
    isLoading,
    error,
    execute,
  };
}