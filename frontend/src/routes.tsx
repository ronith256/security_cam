// src/routes.tsx
import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Cameras from './pages/Cameras';
import CameraDetail from './pages/CameraDetail';
import CameraForm from './pages/CameraForm';
import Templates from './pages/Template';
import PeopleCount from './pages/PeopleCount';
import FaceRecognition from './pages/FaceRecognition';
import PersonStats from './pages/PersonStats';
import Settings from './pages/Settings';
import NotFound from './pages/NotFound';

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/cameras" element={<Cameras />} />
      <Route path="/cameras/new" element={<CameraForm />} />
      <Route path="/cameras/:id" element={<CameraDetail />} />
      <Route path="/cameras/:id/edit" element={<CameraForm />} />
      <Route path="/templates" element={<Templates />} />
      <Route path="/people-count" element={<PeopleCount />} />
      <Route path="/face-recognition" element={<FaceRecognition />} />
      <Route path="/face-recognition/statistics/:id" element={<PersonStats />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
};

export default AppRoutes;