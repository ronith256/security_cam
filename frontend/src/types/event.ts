// src/types/event.ts
export enum EventType {
    PERSON_ENTERED = "person_entered",
    PERSON_EXITED = "person_exited",
    FACE_DETECTED = "face_detected",
    TEMPLATE_MATCHED = "template_matched",
    OCCUPANCY_CHANGED = "occupancy_changed"
}

export interface Event {
    id: number;
    event_type: EventType;
    timestamp: string;
    camera_id: number;
    person_id?: number;
    template_id?: number;
    confidence?: number;
    occupancy_count?: number;
    snapshot_path?: string;
}

export interface OccupancyResponse {
    camera_id: number;
    camera_name: string;
    current_count: number;
    last_updated: string;
}

export interface OccupancyHistory {
    camera_id: number;
    camera_name: string;
    start_date: string;
    end_date: string;
    interval: string;
    data: {
        timestamp: string;
        count: number;
    }[];
}

export interface EntryExitResponse {
    camera_id: number;
    camera_name: string;
    start_date: string;
    end_date: string;
    entry_count: number;
    exit_count: number;
    current_occupancy: number;
}