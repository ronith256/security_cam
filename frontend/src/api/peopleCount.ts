// src/api/peopleCount.ts
import api from './index';
import { OccupancyResponse, OccupancyHistory, EntryExitResponse } from '../types/event';

export const getCurrentOccupancy = async (cameraId?: number): Promise<OccupancyResponse[]> => {
    const params = cameraId ? { camera_id: cameraId } : {};
    const response = await api.get('/people/occupancy', { params });
    return response.data;
};

export const getOccupancyHistory = async (
    cameraId: number,
    startDate?: string,
    endDate?: string,
    interval: string = '1h'
): Promise<OccupancyHistory> => {
    const params: Record<string, any> = { interval };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    const response = await api.get(`/people/history?camera_id=${cameraId}`, { params });
    return response.data;
};

export const getEntriesExits = async (
    cameraId: number,
    startDate?: string,
    endDate?: string
): Promise<EntryExitResponse> => {
    const params: Record<string, any> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    const response = await api.get(`/people/entries-exits?camera_id=${cameraId}`, { params });
    return response.data;
};

export const resetPeopleCounter = async (cameraId: number): Promise<{ message: string }> => {
    const response = await api.post(`/people/${cameraId}/reset`);
    return response.data;
};

export const setLinePosition = async (cameraId: number, position: number): Promise<{ message: string }> => {
    const response = await api.post(`/people/${cameraId}/line-position?position=${position}`);
    return response.data;
};