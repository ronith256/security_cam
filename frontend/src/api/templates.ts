// src/api/templates.ts
import api from './index';
import { Template, TemplateUpdate, TemplateMatch } from '../types/template';

export const fetchTemplates = async (cameraId?: number): Promise<Template[]> => {
    const params = cameraId ? { camera_id: cameraId } : {};
    const response = await api.get('/templates', { params });
    return response.data;
};

export const fetchTemplate = async (id: number): Promise<Template> => {
    const response = await api.get(`/templates/${id}`);
    return response.data;
};

export const createTemplate = async (formData: FormData): Promise<Template> => {
    const response = await api.post('/templates', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const updateTemplate = async (id: number, template: TemplateUpdate): Promise<Template> => {
    const response = await api.put(`/templates/${id}`, template);
    return response.data;
};

export const deleteTemplate = async (id: number): Promise<{ message: string }> => {
    const response = await api.delete(`/templates/${id}`);
    return response.data;
};

export const getTemplateImage = (id: number): string => {
    return `${api.defaults.baseURL}/templates/${id}/image`;
};

export const updateTemplateImage = async (id: number, imageFile: File): Promise<{ message: string }> => {
    const formData = new FormData();
    formData.append('template_image', imageFile);

    const response = await api.post(`/templates/${id}/image`, formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const getTemplateMatches = async (cameraId: number): Promise<TemplateMatch[]> => {
    const response = await api.get(`/templates/matches/${cameraId}`);
    return response.data;
};

export const enableTemplate = async (id: number): Promise<{ message: string }> => {
    const response = await api.post(`/templates/${id}/enable`);
    return response.data;
};

export const disableTemplate = async (id: number): Promise<{ message: string }> => {
    const response = await api.post(`/templates/${id}/disable`);
    return response.data;
};

export const setTemplateThreshold = async (id: number, threshold: number): Promise<{ message: string }> => {
    const response = await api.post(`/templates/${id}/threshold?threshold=${threshold}`);
    return response.data;
};