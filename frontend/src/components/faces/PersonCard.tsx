// src/components/faces/PersonCard.tsx
import React from 'react';
import { Edit, Trash2, BarChart3 } from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import { Person } from '../../types/person';
import { getPersonFace, deletePerson } from '../../api/faceRecognition';
import { useApi } from '../../hooks/useApi';
import { useToast } from '../../context/ToastContext';
import { Link } from 'react-router-dom';

interface PersonCardProps {
  person: Person;
  onDelete: (id: number) => void;
  onEdit: (person: Person) => void;
}

const PersonCard: React.FC<PersonCardProps> = ({ person, onDelete, onEdit }) => {
  const { showToast } = useToast();

  const { execute: executeDelete, isLoading: isDeleting } = useApi(deletePerson, {
    onSuccess: () => {
      onDelete(person.id);
      showToast('Person deleted successfully', 'success');
    },
  });

  const handleDelete = async () => {
    if (window.confirm(`Are you sure you want to delete "${person.name}"?`)) {
      await executeDelete(person.id);
    }
  };

  return (
    <Card
      title={person.name}
      subtitle={person.description || 'No description'}
      className="h-full flex flex-col"
    >
      <div className="flex flex-col h-full">
        <div className="mb-4 bg-gray-100 h-48 rounded-md overflow-hidden flex items-center justify-center">
          <img
            src={getPersonFace(person.id)}
            alt={person.name}
            className="object-cover h-full w-full"
            onError={(e) => {
              const target = e.target as HTMLImageElement;
              target.src = 'https://via.placeholder.com/200x200?text=Face+Not+Found';
            }}
          />
        </div>

        <div className="text-sm text-gray-600 mb-4">
          <p><strong>ID:</strong> {person.id}</p>
          <p>
            <strong>Created:</strong>{' '}
            {new Date(person.created_at).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </p>
          {person.updated_at && (
            <p>
              <strong>Last Updated:</strong>{' '}
              {new Date(person.updated_at).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
              })}
            </p>
          )}
        </div>

        <div className="flex space-x-2 mt-auto">
          <Link to={`/face-recognition/statistics/${person.id}`} className="flex-1">
            <Button
              variant="secondary"
              size="sm"
              icon={<BarChart3 size={16} />}
              className="w-full"
            >
              Statistics
            </Button>
          </Link>

          <Button
            variant="primary"
            size="sm"
            onClick={() => onEdit(person)}
            icon={<Edit size={16} />}
            className="flex-1"
          >
            Edit
          </Button>

          <Button
            variant="danger"
            size="sm"
            onClick={handleDelete}
            isLoading={isDeleting}
            icon={<Trash2 size={16} />}
            className="flex-1"
          >
            Delete
          </Button>
        </div>
      </div>
    </Card>
  );
};

export default PersonCard;