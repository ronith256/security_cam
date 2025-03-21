// src/components/templates/TemplateForm.tsx
import React, { useState, useEffect } from 'react';
import { Save, X } from 'lucide-react';
import Button from '../common/Button';
import { Camera } from '../../types/camera';
import { Template } from '../../types/template';
import { fetchCameras } from '../../api/cameras';
import { getTemplateImage } from '../../api/templates';
import { useApi } from '../../hooks/useApi';

interface TemplateFormProps {
  initialValues?: Template;
  onSubmit: (formData: FormData) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

const TemplateForm: React.FC<TemplateFormProps> = ({
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting,
}) => {
  const [name, setName] = useState(initialValues?.name || '');
  const [description, setDescription] = useState(initialValues?.description || '');
  const [cameraId, setCameraId] = useState<number | string>(initialValues?.camera_id || '');
  const [threshold, setThreshold] = useState(initialValues?.threshold || 0.7);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const { execute: loadCameras, isLoading: isLoadingCameras } = useApi(fetchCameras, {
    onSuccess: (data) => {
      setCameras(data);
      // Set default camera if none selected and cameras are available
      if (!cameraId && data.length > 0) {
        setCameraId(data[0].id);
      }
    },
  });

  useEffect(() => {
    loadCameras();
  }, [loadCameras]);

  // Set preview image if editing an existing template
  useEffect(() => {
    if (initialValues && !previewUrl) {
      setPreviewUrl(getTemplateImage(initialValues.id));
    }
  }, [initialValues, previewUrl]);

  // Clean up preview URL when component unmounts
  useEffect(() => {
    return () => {
      if (previewUrl && previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImageFile(file);
      
      // Generate preview URL
      if (previewUrl && previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(previewUrl);
      }
      
      setPreviewUrl(URL.createObjectURL(file));
    }
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Name is required';
    }

    if (!cameraId) {
      newErrors.cameraId = 'Camera is required';
    }

    if (threshold < 0.1 || threshold > 1) {
      newErrors.threshold = 'Threshold must be between 0.1 and 1';
    }

    if (!initialValues && !imageFile) {
      newErrors.imageFile = 'Template image is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('camera_id', cameraId.toString());
      formData.append('threshold', threshold.toString());
      
      if (description) {
        formData.append('description', description);
      }
      
      if (imageFile) {
        formData.append('template_image', imageFile);
      }
      
      await onSubmit(formData);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Template Name *
          </label>
          <input
            type="text"
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.name ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting}
          />
          {errors.name && <p className="mt-1 text-sm text-red-500">{errors.name}</p>}
        </div>

        <div>
          <label htmlFor="camera" className="block text-sm font-medium text-gray-700 mb-1">
            Camera *
          </label>
          <select
            id="camera"
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.cameraId ? 'border-red-500' : 'border-gray-300'
            }`}
            disabled={isSubmitting || isLoadingCameras || !!initialValues}
          >
            {!cameraId && <option value="">Select a camera</option>}
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </select>
          {errors.cameraId && <p className="mt-1 text-sm text-red-500">{errors.cameraId}</p>}
        </div>

        <div>
          <label htmlFor="threshold" className="block text-sm font-medium text-gray-700 mb-1">
            Matching Threshold
          </label>
          <div className="flex items-center">
            <input
              type="range"
              id="threshold"
              min="0.1"
              max="1"
              step="0.05"
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-full mr-2"
              disabled={isSubmitting}
            />
            <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
              {(threshold * 100).toFixed(0)}%
            </span>
          </div>
          {errors.threshold && <p className="mt-1 text-sm text-red-500">{errors.threshold}</p>}
        </div>

        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
            Description
          </label>
          <input
            type="text"
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md"
            disabled={isSubmitting}
          />
        </div>

        <div className="md:col-span-2">
          <label htmlFor="templateImage" className="block text-sm font-medium text-gray-700 mb-1">
            Template Image {!initialValues && '*'}
          </label>
          <div className="mt-1 flex items-center">
            <input
              type="file"
              id="templateImage"
              accept="image/*"
              onChange={handleImageChange}
              className={`block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 ${
                errors.imageFile ? 'border border-red-500 rounded-md' : ''
              }`}
              disabled={isSubmitting}
            />
          </div>
          {errors.imageFile && <p className="mt-1 text-sm text-red-500">{errors.imageFile}</p>}

          {previewUrl && (
            <div className="mt-4 relative">
              <img
                src={previewUrl}
                alt="Template preview"
                className="max-h-64 max-w-full object-contain border border-gray-200 rounded-md"
              />
            </div>
          )}
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
          {initialValues ? 'Update Template' : 'Create Template'}
        </Button>
      </div>
    </form>
  );
};

export default TemplateForm;