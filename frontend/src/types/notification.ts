// src/types/notification.ts

export enum NotificationType {
    EMAIL = "email",
    TELEGRAM = "telegram",
    WEBHOOK = "webhook"
}

export enum TriggerConditionType {
    OCCUPANCY_ABOVE = "occupancy_above",
    OCCUPANCY_BELOW = "occupancy_below",
    UNREGISTERED_FACE = "unregistered_face",
    SPECIFIC_FACE = "specific_face",
    TEMPLATE_MATCHED = "template_matched",
    TIME_RANGE = "time_range"
}

export enum TimeRestrictedTrigger {
    ALWAYS = "always",
    ONLY_DURING = "only_during",
    EXCEPT_DURING = "except_during"
}

// Base models for condition parameters
export interface ConditionParams {
    [key: string]: any;
}

export interface OccupancyConditionParams extends ConditionParams {
    threshold: number;
}

export interface FaceConditionParams extends ConditionParams {
    person_id?: number;
    confidence_threshold?: number;
}

export interface TemplateConditionParams extends ConditionParams {
    template_id: number;
    confidence_threshold?: number;
}

export interface TimeRangeConditionParams extends ConditionParams {
    start_time: string; // Format: "HH:MM"
    end_time: string;   // Format: "HH:MM"
}

// Notification configuration models
export interface EmailNotificationConfig {
    recipients: string[];
    subject_template?: string;
    body_template?: string;
    include_snapshot: boolean;
}

export interface TelegramNotificationConfig {
    chat_ids: string[];
    message_template?: string;
    include_snapshot: boolean;
}

export interface WebhookNotificationConfig {
    url: string;
    headers?: Record<string, string>;
    include_snapshot: boolean;
}

// API models
export interface NotificationTriggerBase {
    name: string;
    description?: string;
    active: boolean;
    condition_type: TriggerConditionType;
    condition_params: ConditionParams;
    time_restriction: TimeRestrictedTrigger;
    time_start?: string;
    time_end?: string;
    camera_id?: number;
    cooldown_period: number;
    notification_type: NotificationType;
    notification_config: Record<string, any>;
}

export interface NotificationTriggerCreate extends NotificationTriggerBase { }

export interface NotificationTriggerUpdate {
    name?: string;
    description?: string;
    active?: boolean;
    condition_type?: TriggerConditionType;
    condition_params?: ConditionParams;
    time_restriction?: TimeRestrictedTrigger;
    time_start?: string;
    time_end?: string;
    camera_id?: number;
    cooldown_period?: number;
    notification_type?: NotificationType;
    notification_config?: Record<string, any>;
}

export interface NotificationTrigger extends NotificationTriggerBase {
    id: number;
    last_triggered?: string;
    created_at: string;
    updated_at?: string;
}

export interface NotificationEvent {
    id: number;
    trigger_id: number;
    camera_id: number;
    timestamp: string;
    event_data: Record<string, any>;
    sent_successfully: boolean;
    delivery_error?: string;
    snapshot_path?: string;
}

export interface NotificationStats {
    start_date: string;
    end_date: string;
    total_count: number;
    success_count: number;
    failed_count: number;
    success_rate: number;
    trigger_stats: {
        trigger_id: number;
        trigger_name: string;
        condition_type: string;
        event_count: number;
    }[];
}