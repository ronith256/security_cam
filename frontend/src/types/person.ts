// src/types/person.ts
export interface Person {
    id: number;
    name: string;
    description: string | null;
    face_image_path: string;
    created_at: string;
    updated_at: string | null;
}

export interface PersonCreate {
    name: string;
    description?: string;
}

export interface PersonUpdate {
    name?: string;
    description?: string;
}

export interface FaceDetection {
    person_id: number;
    person_name: string;
    confidence: number;
    bbox: number[];
}

export interface PersonStatistics {
    person_id: number;
    person_name: string;
    total_entries: number;
    total_detections: number;
    first_seen: string;
    last_seen: string;
    cameras: string[];
}
