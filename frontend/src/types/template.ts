// src/types/template.ts
export interface Template {
    id: number;
    name: string;
    description: string | null;
    camera_id: number;
    image_path: string;
    enabled: boolean;
    threshold: number;
    created_at: string;
    updated_at: string | null;
}

export interface TemplateCreate {
    name: string;
    camera_id: number;
    description?: string;
    threshold?: number;
}

export interface TemplateUpdate {
    name?: string;
    description?: string;
    enabled?: boolean;
    threshold?: number;
}

export interface TemplateMatch {
    template_id: number;
    template_name: string;
    confidence: number;
    bbox: number[];
}