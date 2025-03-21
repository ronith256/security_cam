// src/App.tsx
import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import Navbar from './components/common/Navbar';
import Sidebar from './components/common/Sidebar';
import AppRoutes from './routes';
import { ToastProvider } from './context/ToastContext';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <ToastProvider>
        <div className="min-h-screen bg-gray-100">
          <Navbar />
          <Sidebar />
          <div className="pt-16 pl-64">
            <main className="p-6">
              <AppRoutes />
            </main>
          </div>
        </div>
      </ToastProvider>
    </BrowserRouter>
  );
};

export default App;