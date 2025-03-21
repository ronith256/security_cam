// src/components/cameras/CameraForm.tsx
import React, { useState, useEffect } from 'react';
import { Camera as CameraType, CameraCreate, CameraUpdate } from '../../types/camera';
import Button from '../common/Button';
import { Save, X } from 'lucide-react';

interface CameraFormProps {
  initialValues?: CameraType;
  onSubmit: (values: CameraCreate | CameraUpdate) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

const CameraForm: React.FC<CameraFormProps> = ({ 
  initialValues, 
  onSubmit, 
  onCancel,
  isSubmitting 
}) => {
  const [formValues, setFormValues] = useState<CameraCreate | CameraUpdate>({
    name: '',
    rtsp_url: '',
    location: '',
    description: '',
    processing_fps: 5,
    streaming_fps: 30,
    detect_people: true,
    count_people: true,
    recognize_faces: false,
    template_matching: false,
    ...initialValues,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (initialValues) {
      setFormValues(initialValues);
    }
  }, [initialValues]);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formValues.name) {
      newErrors.name = 'Name is required';
    }

    if (!formValues.rtsp_url) {
      newErrors.rtsp_url = 'RTSP URL is required';
    } else if (!formValues.rtsp_url.startsWith('rtsp://')) {
      newErrors.rtsp_url = 'RTSP URL must start with rtsp://';
    }

    if (typeof formValues.processing_fps === 'number' && (formValues.processing_fps < 1 || formValues.processing_fps > 30)) {
      newErrors.processing_fps = 'Processing FPS must be between 1 and 30';
    }

    if (typeof formValues.streaming_fps === 'number' && (formValues.streaming_fps < 1 || formValues.streaming_fps > 60)) {
      newErrors.streaming_fps = 'Streaming FPS must be between 1 and 60';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    
    setFormValues((prev) => ({
      ...prev,
      [name]: type === 'number' ? parseInt(value, 10) : value,
    }));
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    
    setFormValues((prev) => ({
      ...prev,
      [name]: checked,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      await onSubmit(formValues);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Camera Name *
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={formValues.name || ''}
            onChange={handleChange}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.name ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting}
          />
          {errors.name && <p className="mt-1 text-sm text-red-500">{errors.name}</p>}
        </div>

        <div>
          <label htmlFor="rtsp_url" className="block text-sm font-medium text-gray-700 mb-1">
            RTSP URL *
          </label>
          <input
            type="text"
            id="rtsp_url"
            name="rtsp_url"
            value={formValues.rtsp_url || ''}
            onChange={handleChange}
            placeholder="rtsp://"
            className={`w-full px-3 py-2 border rounded-md ${
              errors.rtsp_url ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting}
          />
          {errors.rtsp_url && <p className="mt-1 text-sm text-red-500">{errors.rtsp_url}</p>}
        </div>

        <div>
          <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-1">
            Location
          </label>
          <input
            type="text"
            id="location"
            name="location"
            value={formValues.location || ''}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            disabled={isSubmitting}
          />
        </div>

        <div>
          <label htmlFor="processing_fps" className="block text-sm font-medium text-gray-700 mb-1">
            Processing FPS
          </label>
          <input
            type="number"
            id="processing_fps"
            name="processing_fps"
            min="1"
            max="30"
            value={formValues.processing_fps || 5}
            onChange={handleChange}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.processing_fps ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting}
          />
          {errors.processing_fps && (
            <p className="mt-1 text-sm text-red-500">{errors.processing_fps}</p>
          )}
        </div>

        <div>
          <label htmlFor="streaming_fps" className="block text-sm font-medium text-gray-700 mb-1">
            Streaming FPS
          </label>
          <input
            type="number"
            id="streaming_fps"
            name="streaming_fps"
            min="1"
            max="60"
            value={formValues.streaming_fps || 30}
            onChange={handleChange}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.streaming_fps ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting}
          />
          {errors.streaming_fps && (
            <p className="mt-1 text-sm text-red-500">{errors.streaming_fps}</p>
          )}
        </div>

        <div className="md:col-span-2">
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
            Description
          </label>
          <textarea
            id="description"
            name="description"
            rows={3}
            value={formValues.description || ''}
            onChange={handleChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            disabled={isSubmitting}
          />
        </div>
      </div>

      <div className="space-y-3 bg-gray-50 p-4 rounded-md">
        <h3 className="font-medium text-gray-700">Features</h3>
        
        <div className="flex flex-wrap gap-6">
          <div className="flex items-center">
            <input
              type="checkbox"
              id="detect_people"
              name="detect_people"
              checked={formValues.detect_people}
              onChange={handleCheckboxChange}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
            />
            <label htmlFor="detect_people" className="ml-2 text-sm text-gray-700">
              People Detection
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="count_people"
              name="count_people"
              checked={formValues.count_people}
              onChange={handleCheckboxChange}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
            />
            <label htmlFor="count_people" className="ml-2 text-sm text-gray-700">
              People Counting
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="recognize_faces"
              name="recognize_faces"
              checked={formValues.recognize_faces}
              onChange={handleCheckboxChange}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
            />
            <label htmlFor="recognize_faces" className="ml-2 text-sm text-gray-700">
              Face Recognition
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="template_matching"
              name="template_matching"
              checked={formValues.template_matching}
              onChange={handleCheckboxChange}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
            />
            <label htmlFor="template_matching" className="ml-2 text-sm text-gray-700">
              Template Matching
            </label>
          </div>
        </div>
      </div>

      <div className="flex justify-end space-x-3">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={isSubmitting}
          icon={<X size={16} />}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          icon={<Save size={16} />}
        >
          Save Camera
        </Button>
      </div>
    </form>
  );
};

export default CameraForm;