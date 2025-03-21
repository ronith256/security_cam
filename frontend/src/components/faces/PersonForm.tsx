// src/components/faces/PersonForm.tsx
import React, { useState, useEffect } from 'react';
import { Save, X } from 'lucide-react';
import Button from '../common/Button';
import { Person } from '../../types/person';

interface PersonFormProps {
  initialValues?: Person;
  onSubmit: (formData: FormData) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

const PersonForm: React.FC<PersonFormProps> = ({
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting,
}) => {
  const [name, setName] = useState(initialValues?.name || '');
  const [description, setDescription] = useState(initialValues?.description || '');
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Set preview image if editing an existing person
  useEffect(() => {
    if (initialValues && !previewUrl) {
      // Use API endpoint to get the face image
      setPreviewUrl(`/api/faces/persons/${initialValues.id}/face`);
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

    if (!initialValues && !imageFile) {
      newErrors.imageFile = 'Face image is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
      const formData = new FormData();
      formData.append('name', name);
      
      if (description) {
        formData.append('description', description);
      }
      
      if (imageFile) {
        formData.append('face_image', imageFile);
      }
      
      await onSubmit(formData);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
            Name *
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
          <label htmlFor="faceImage" className="block text-sm font-medium text-gray-700 mb-1">
            Face Image {!initialValues && '*'}
          </label>
          <div className="mt-1 flex items-center">
            <input
              type="file"
              id="faceImage"
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
              <div className="w-40 h-40 border border-gray-200 rounded-md overflow-hidden">
                <img
                  src={previewUrl}
                  alt="Face preview"
                  className="w-full h-full object-cover"
                />
              </div>
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
          {initialValues ? 'Update Person' : 'Register Person'}
        </Button>
      </div>
    </form>
  );
};

export default PersonForm;