// src/pages/NotFound.tsx
import React from 'react';
import { Link } from 'react-router-dom';
import { Home } from 'lucide-react';
import Button from '../components/common/Button';

const NotFound: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <h1 className="text-6xl font-bold text-gray-800 mb-4">404</h1>
      <h2 className="text-2xl font-semibold text-gray-700 mb-6">Page Not Found</h2>
      <p className="text-gray-600 mb-8 text-center max-w-md">
        The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.
      </p>
      <Link to="/">
        <Button variant="primary" icon={<Home size={16} />}>
          Back to Home
        </Button>
      </Link>
    </div>
  );
};

export default NotFound;