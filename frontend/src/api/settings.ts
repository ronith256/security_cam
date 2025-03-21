// src/api/settings.ts
import api from './index';
import { Setting, SettingUpdate } from '../types/settings';

export const getAllSettings = async (): Promise<Setting[]> => {
    const response = await api.get('/settings');
    return response.data;
};

export const getSetting = async (key: string): Promise<Setting> => {
    const response = await api.get(`/settings/${key}`);
    return response.data;
};

export const updateSetting = async (key: string, setting: SettingUpdate): Promise<Setting> => {
    const response = await api.put(`/settings/${key}`, setting);
    return response.data;
};

export const createSetting = async (key: string, value: any, description?: string): Promise<Setting> => {
    const response = await api.post('/settings', { key, value, description });
    return response.data;
};

export const deleteSetting = async (key: string): Promise<{ message: string }> => {
    const response = await api.delete(`/settings/${key}`);
    return response.data;
};

export const applySettings = async (): Promise<{ message: string }> => {
    const response = await api.post('/settings/apply');
    return response.data;
};

export const resetDefaultSettings = async (): Promise<{ message: string }> => {
    const response = await api.post('/settings/reset-defaults');
    return response.data;
};