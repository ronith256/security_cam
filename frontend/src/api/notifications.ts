// src/api/notifications.ts
import api from './index';
import {
    NotificationTrigger,
    NotificationTriggerCreate,
    NotificationTriggerUpdate,
    NotificationEvent,
    NotificationStats
} from '../types/notification';

// Trigger endpoints
export const fetchTriggers = async (active?: boolean): Promise<NotificationTrigger[]> => {
    const params = active !== undefined ? { active } : {};
    const response = await api.get('/notifications/triggers', { params });
    return response.data;
};

export const fetchTrigger = async (id: number): Promise<NotificationTrigger> => {
    const response = await api.get(`/notifications/triggers/${id}`);
    return response.data;
};

export const createTrigger = async (trigger: NotificationTriggerCreate): Promise<NotificationTrigger> => {
    const response = await api.post('/notifications/triggers', trigger);
    return response.data;
};

export const updateTrigger = async (id: number, trigger: NotificationTriggerUpdate): Promise<NotificationTrigger> => {
    const response = await api.put(`/notifications/triggers/${id}`, trigger);
    return response.data;
};

export const deleteTrigger = async (id: number): Promise<{ message: string }> => {
    const response = await api.delete(`/notifications/triggers/${id}`);
    return response.data;
};

export const toggleTrigger = async (id: number, active: boolean): Promise<{ message: string }> => {
    const response = await api.post(`/notifications/triggers/${id}/toggle?active=${active}`);
    return response.data;
};

// Test a trigger with sample data
export const testTrigger = async (id: number, testData: any): Promise<{ message: string }> => {
    const response = await api.post(`/notifications/test/${id}`, testData);
    return response.data;
};

// Notification events endpoints
export const fetchNotificationEvents = async (
    params: {
        trigger_id?: number;
        camera_id?: number;
        start_date?: string;
        end_date?: string;
        successful_only?: boolean;
        skip?: number;
        limit?: number;
    } = {}
): Promise<NotificationEvent[]> => {
    const response = await api.get('/notifications/events', { params });
    return response.data;
};

export const fetchNotificationEvent = async (id: number): Promise<NotificationEvent> => {
    const response = await api.get(`/notifications/events/${id}`);
    return response.data;
};

// Statistics
export const fetchNotificationStats = async (
    startDate?: string,
    endDate?: string
): Promise<NotificationStats> => {
    const params: Record<string, any> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    const response = await api.get('/notifications/stats', { params });
    return response.data;
};