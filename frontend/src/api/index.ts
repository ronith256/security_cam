// src/api/index.ts
import axios from 'axios';

// Create an axios instance with default config
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Export the API base URL for components that need direct access
export const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
export const wsBaseUrl = import.meta.env.VITE_API_URL 
  ? import.meta.env.VITE_API_URL.replace(/^http/, 'ws') 
  : 'ws://localhost:8000/api';

export default api;