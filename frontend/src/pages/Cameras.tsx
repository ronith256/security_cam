// src/pages/Cameras.tsx
import React from 'react';
import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import CameraList from '../components/cameras/CameraList';

const Cameras: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Cameras"
        subtitle="Manage your CCTV cameras"
        actions={
          <Link to="/cameras/new">
            <Button variant="primary" icon={<Plus size={16} />}>
              Add Camera
            </Button>
          </Link>
        }
      />

      <CameraList />
    </div>
  );
};

export default Cameras;