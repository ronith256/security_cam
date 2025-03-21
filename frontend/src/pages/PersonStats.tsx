// src/pages/PersonStats.tsx
import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import PersonStatsComponent from '../components/faces/PersonStats';
import Loader from '../components/common/Loader';
import { useApi } from '../hooks/useApi';
import { fetchPerson } from '../api/faceRecognition';

const PersonStats: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const personId = parseInt(id || '0');
  
  const { execute: loadPerson, data: person, isLoading } = useApi(
    () => fetchPerson(personId),
    {
      showErrorToast: true,
    }
  );
  
  React.useEffect(() => {
    if (personId) {
      loadPerson();
    }
  }, [personId, loadPerson]);
  
  if (isLoading) {
    return (
      <div className="flex justify-center my-12">
        <Loader text="Loading person data..." />
      </div>
    );
  }
  
  if (!person) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-gray-700">Person not found</h2>
        <p className="text-gray-600 mt-2">The person you're looking for doesn't exist.</p>
        <Link to="/face-recognition" className="mt-4 inline-block">
          <Button variant="primary">Back to Face Recognition</Button>
        </Link>
      </div>
    );
  }
  
  return (
    <div>
      <PageHeader
        title={`${person.name}'s Statistics`}
        subtitle="View detection history and analytics"
        actions={
          <Link to="/face-recognition">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              Back
            </Button>
          </Link>
        }
      />
      
      <div className="flex items-center mb-6 bg-white p-4 rounded-lg shadow">
        <div className="w-20 h-20 rounded-full overflow-hidden mr-4 bg-gray-100 flex items-center justify-center">
          <img
            src={`/api/faces/persons/${person.id}/face`}
            alt={person.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              const target = e.target as HTMLImageElement;
              target.src = 'https://via.placeholder.com/80?text=Face';
            }}
          />
        </div>
        <div>
          <h2 className="text-2xl font-bold">{person.name}</h2>
          <p className="text-gray-600">{person.description || 'No description'}</p>
        </div>
      </div>
      
      <PersonStatsComponent personId={personId} />
    </div>
  );
};

export default PersonStats;