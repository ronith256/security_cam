// src/components/common/Sidebar.tsx
import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  Home, 
  Camera, 
  Image, 
  Users, 
  UserPlus, 
  Settings,
} from 'lucide-react';

const Sidebar: React.FC = () => {
  return (
    <aside className="bg-gray-900 text-white w-64 min-h-screen fixed left-0 top-16 p-4">
      <nav>
        <ul className="space-y-2">
          <li>
            <NavLink 
              to="/" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <Home className="mr-3" size={20} />
              <span>Dashboard</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/cameras" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <Camera className="mr-3" size={20} />
              <span>Cameras</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/templates" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <Image className="mr-3" size={20} />
              <span>Templates</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/people-count" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <Users className="mr-3" size={20} />
              <span>People Count</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/face-recognition" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <UserPlus className="mr-3" size={20} />
              <span>Face Recognition</span>
            </NavLink>
          </li>
          <li>
            <NavLink 
              to="/settings" 
              className={({ isActive }) => 
                `flex items-center p-3 rounded-lg transition-colors ${
                  isActive ? 'bg-blue-600' : 'hover:bg-gray-800'
                }`
              }
            >
              <Settings className="mr-3" size={20} />
              <span>Settings</span>
            </NavLink>
          </li>
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;