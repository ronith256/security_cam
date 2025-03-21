// src/components/common/Toast.tsx
import React, { useEffect } from 'react';
import { X, CheckCircle, AlertTriangle, Info, AlertCircle } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  type: ToastType;
  message: string;
  onClose: () => void;
  duration?: number;
}

const Toast: React.FC<ToastProps> = ({ type, message, onClose, duration = 5000 }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);

    return () => clearTimeout(timer);
  }, [onClose, duration]);

  const icons = {
    success: <CheckCircle className="h-5 w-5 text-green-500" />,
    error: <AlertCircle className="h-5 w-5 text-red-500" />,
    warning: <AlertTriangle className="h-5 w-5 text-yellow-500" />,
    info: <Info className="h-5 w-5 text-blue-500" />,
  };

  const backgrounds = {
    success: 'bg-green-50 border-green-200',
    error: 'bg-red-50 border-red-200',
    warning: 'bg-yellow-50 border-yellow-200',
    info: 'bg-blue-50 border-blue-200',
  };

  return (
    <div
      className={`rounded-lg border px-4 py-3 shadow-md ${backgrounds[type]} flex items-center justify-between`}
      role="alert"
    >
      <div className="flex items-center">
        <div className="mr-3">{icons[type]}</div>
        <p className="text-sm font-medium">{message}</p>
      </div>
      <button
        className="text-gray-500 hover:text-gray-700 ml-4 focus:outline-none"
        onClick={onClose}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
};

export default Toast;