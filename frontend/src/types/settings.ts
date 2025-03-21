// src/types/settings.ts
export interface Setting {
    id: number;
    key: string;
    value: any;
    description: string | null;
    created_at: string;
    updated_at: string | null;
}

export interface SettingUpdate {
    value?: any;
    description?: string;
}