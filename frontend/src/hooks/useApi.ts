// src/hooks/useApi.ts
import { useState, useCallback, useRef } from 'react';
import { useToast } from '../context/ToastContext';
import axios, { AxiosError } from 'axios';

interface UseApiOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: Error | AxiosError) => void;
  showSuccessToast?: boolean;
  showErrorToast?: boolean;
  successMessage?: string;
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
  
  const execute = useCallback(
    async (...args: any[]) => {
      setIsLoading(true);
      setError(null);
      
      try {
        const result = await apiFunction(...args);
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
        setIsLoading(false);
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