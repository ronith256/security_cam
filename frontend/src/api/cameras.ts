// src/api/cameras.ts
import api from './index';
import { Camera, CameraCreate, CameraUpdate, CameraStatus } from '../types/camera';

export const fetchCameras = async (): Promise<Camera[]> => {
    const response = await api.get('/cameras');
    return response.data;
};

export const fetchCamera = async (id: number): Promise<Camera> => {
    const response = await api.get(`/cameras/${id}`);
    return response.data;
};

export const createCamera = async (camera: CameraCreate): Promise<Camera> => {
    const response = await api.post('/cameras', camera);
    return response.data;
};

export const updateCamera = async (id: number, camera: CameraUpdate): Promise<Camera> => {
    const response = await api.put(`/cameras/${id}`, camera);
    return response.data;
};

export const deleteCamera = async (id: number): Promise<{ message: string }> => {
    const response = await api.delete(`/cameras/${id}`);
    return response.data;
};

export const getCameraStatus = async (id: number): Promise<CameraStatus> => {
    const response = await api.get(`/cameras/${id}/status`);
    return response.data;
};

export const getCameraSnapshot = async (id: number): Promise<Blob> => {
    const response = await api.get(`/cameras/${id}/snapshot`, {
        responseType: 'blob',
    });
    return response.data;
};

export const getCameraStream = (id: number): string => {
    return `${api.defaults.baseURL}/cameras/${id}/stream`;
};

export const updateCameraSettings = async (id: number, settings: Record<string, any>): Promise<{ message: string }> => {
    const response = await api.post(`/cameras/${id}/settings`, settings);
    return response.data;
};
