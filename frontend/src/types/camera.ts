import { FaceDetection } from "./person";
import { TemplateMatch } from "./template";

// src/types/camera.ts
export interface Camera {
    id: number;
    name: string;
    rtsp_url: string;
    location: string | null;
    description: string | null;
    enabled: boolean;
    processing_fps: number;
    streaming_fps: number;
    detect_people: boolean;
    count_people: boolean;
    recognize_faces: boolean;
    template_matching: boolean;
    created_at: string;
    updated_at: string | null;
}

export interface CameraCreate {
    name: string;
    rtsp_url: string;
    location?: string;
    description?: string;
    processing_fps?: number;
    streaming_fps?: number;
    detect_people?: boolean;
    count_people?: boolean;
    recognize_faces?: boolean;
    template_matching?: boolean;
}

export interface CameraUpdate {
    name?: string;
    rtsp_url?: string;
    location?: string;
    description?: string;
    enabled?: boolean;
    processing_fps?: number;
    streaming_fps?: number;
    detect_people?: boolean;
    count_people?: boolean;
    recognize_faces?: boolean;
    template_matching?: boolean;
}

export interface CameraStatus {
    camera_id: number;
    name: string;
    active: boolean;
    detection_results: {
        people?: DetectionResult[];
        faces?: FaceDetection[];
        templates?: TemplateMatch[];
        people_counting?: {
            entries: number;
            exits: number;
            current: number;
        };
    };
    current_occupancy: number;
    fps: number;
}

export interface DetectionResult {
    bbox: number[];
    confidence: number;
    class_id: number;
    class_name: string;
}