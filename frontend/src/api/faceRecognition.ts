// src/api/faceRecognition.ts
import api from './index';
import { Person, PersonUpdate, FaceDetection, PersonStatistics } from '../types/person';

export const fetchPersons = async (): Promise<Person[]> => {
    const response = await api.get('/faces/persons');
    return response.data;
};

export const fetchPerson = async (id: number): Promise<Person> => {
    const response = await api.get(`/faces/persons/${id}`);
    return response.data;
};

export const createPerson = async (formData: FormData): Promise<Person> => {
    const response = await api.post('/faces/persons', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const updatePerson = async (id: number, person: PersonUpdate): Promise<Person> => {
    const response = await api.put(`/faces/persons/${id}`, person);
    return response.data;
};

export const deletePerson = async (id: number): Promise<{ message: string }> => {
    const response = await api.delete(`/faces/persons/${id}`);
    return response.data;
};

export const getPersonFace = (id: number): string => {
    return `${api.defaults.baseURL}/faces/persons/${id}/face`;
};

export const updatePersonFace = async (id: number, faceImage: File): Promise<{ message: string }> => {
    const formData = new FormData();
    formData.append('face_image', faceImage);

    const response = await api.post(`/faces/persons/${id}/face`, formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const getPersonStatistics = async (
    id: number,
    startDate?: string,
    endDate?: string
): Promise<PersonStatistics> => {
    const params: Record<string, any> = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;

    const response = await api.get(`/faces/persons/${id}/statistics`, { params });
    return response.data;
};

export const getFaceDetections = async (cameraId: number): Promise<FaceDetection[]> => {
    const response = await api.get(`/faces/detections?camera_id=${cameraId}`);
    return response.data;
};