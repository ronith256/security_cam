// src/components/faces/PersonList.tsx
import React, { useState, useEffect } from 'react';
import { Person } from '../../types/person';
import PersonCard from './PersonCard';
import Loader from '../common/Loader';
import { fetchPersons } from '../../api/faceRecognition';
import { useApi } from '../../hooks/useApi';
import { AlertCircle } from 'lucide-react';

interface PersonListProps {
  onEdit: (person: Person) => void;
}

const PersonList: React.FC<PersonListProps> = ({ onEdit }) => {
  const [persons, setPersons] = useState<Person[]>([]);
  
  const { execute: loadPersons, isLoading, error } = useApi(fetchPersons, {
    onSuccess: (data) => {
      setPersons(data);
    },
  });

  useEffect(() => {
    loadPersons();
  }, [loadPersons]);

  const handleDelete = (id: number) => {
    setPersons((prevPersons) => prevPersons.filter((person) => person.id !== id));
  };

  if (isLoading && persons.length === 0) {
    return <Loader text="Loading registered persons..." />;
  }

  if (error && persons.length === 0) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading persons</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  if (persons.length === 0) {
    return (
      <div className="bg-gray-50 p-6 rounded-md text-center">
        <p className="text-gray-600">No persons registered.</p>
        <p className="text-gray-500 text-sm mt-1">
          Register a person to use face recognition.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {persons.map((person) => (
        <PersonCard
          key={person.id}
          person={person}
          onDelete={handleDelete}
          onEdit={onEdit}
        />
      ))}
    </div>
  );
};

export default PersonList;