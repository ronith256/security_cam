// src/components/common/Navbar.tsx
import React from 'react';
import { Link } from 'react-router-dom';

const Navbar: React.FC = () => {
  return (
    <nav className="bg-gray-800 text-white h-16 fixed w-full z-10">
      <div className="container mx-auto px-4 h-full flex items-center justify-between">
        <div className="flex items-center">
          <Link to="/" className="text-xl font-bold">CCTV Monitoring System</Link>
        </div>
        <div className="flex items-center space-x-4">
          <span>Server Room Monitoring</span>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;