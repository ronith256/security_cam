// src/context/ToastContext.tsx
import React, { createContext, useCallback, useContext, useState } from 'react';
import { createPortal } from 'react-dom';
import Toast, { ToastType } from '../components/common/Toast';

interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (message: string, type: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback((message: string, type: ToastType) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prevToasts) => [...prevToasts, { id, type, message }]);
  }, []);

  const closeToast = useCallback((id: string) => {
    setToasts((prevToasts) => prevToasts.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {createPortal(
        <div className="fixed bottom-4 right-4 z-50 flex flex-col space-y-2 max-w-md">
          {toasts.map((toast) => (
            <Toast
              key={toast.id}
              type={toast.type}
              message={toast.message}
              onClose={() => closeToast(toast.id)}
            />
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
