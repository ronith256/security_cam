from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, EmailStr, validator
from datetime import datetime, time
import enum
from app.database import Base

class NotificationType(enum.Enum):
    """Notification type enumeration"""
    EMAIL = "email"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    
class TriggerConditionType(enum.Enum):
    """Trigger condition type enumeration"""
    OCCUPANCY_ABOVE = "occupancy_above"
    OCCUPANCY_BELOW = "occupancy_below"
    UNREGISTERED_FACE = "unregistered_face"
    SPECIFIC_FACE = "specific_face"
    TEMPLATE_MATCHED = "template_matched"
    TIME_RANGE = "time_range"

class TimeRestrictedTrigger(enum.Enum):
    """Time restricted trigger types"""
    ALWAYS = "always"
    ONLY_DURING = "only_during"
    EXCEPT_DURING = "except_during"

class NotificationTrigger(Base):
    """SQLAlchemy NotificationTrigger model for event triggers"""
    __tablename__ = "notification_triggers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    
    # Trigger conditions (stored as JSON)
    condition_type = Column(Enum(TriggerConditionType), nullable=False)
    condition_params = Column(JSON, nullable=False)  # Threshold values, specific IDs, etc.
    
    # Time restrictions
    time_restriction = Column(Enum(TimeRestrictedTrigger), default=TimeRestrictedTrigger.ALWAYS)
    time_start = Column(String, nullable=True)  # Format: "HH:MM" 
    time_end = Column(String, nullable=True)    # Format: "HH:MM"
    
    # Camera restrictions (null means all cameras)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True)
    camera = relationship("Camera", back_populates="triggers")
    
    # Cooldown period to prevent notification spam (in seconds)
    cooldown_period = Column(Integer, default=300)  # 5 minutes default
    last_triggered = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships to triggered events
    triggered_events = relationship("NotificationEvent", back_populates="trigger", cascade="all, delete-orphan")
    
    # Notification method and recipients
    notification_type = Column(Enum(NotificationType), nullable=False)
    notification_config = Column(JSON, nullable=False)  # Email addresses, chat IDs, webhook URLs
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class NotificationEvent(Base):
    """SQLAlchemy NotificationEvent model for triggered notifications"""
    __tablename__ = "notification_events"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Related trigger
    trigger_id = Column(Integer, ForeignKey("notification_triggers.id"), nullable=False)
    trigger = relationship("NotificationTrigger", back_populates="triggered_events")
    
    # Event details
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    camera = relationship("Camera")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    event_data = Column(JSON, nullable=False)  # Details of what triggered the notification
    
    # Notification status
    sent_successfully = Column(Boolean, default=False)
    delivery_error = Column(String, nullable=True)
    
    # Snapshot of the event
    snapshot_path = Column(String, nullable=True)

# Pydantic models for API
class ConditionParamsBase(BaseModel):
    """Base class for condition parameters"""
    pass

class OccupancyConditionParams(ConditionParamsBase):
    """Parameters for occupancy-based conditions"""
    threshold: int
    
class FaceConditionParams(ConditionParamsBase):
    """Parameters for face detection conditions"""
    person_id: Optional[int] = None  # None for any unregistered face
    confidence_threshold: Optional[float] = 0.6
    
class TemplateConditionParams(ConditionParamsBase):
    """Parameters for template matching conditions"""
    template_id: int
    confidence_threshold: Optional[float] = 0.7
    
class TimeRangeConditionParams(ConditionParamsBase):
    """Parameters for time-based conditions"""
    start_time: str  # Format: "HH:MM"
    end_time: str    # Format: "HH:MM"

class EmailNotificationConfig(BaseModel):
    """Configuration for email notifications"""
    recipients: List[EmailStr]
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    include_snapshot: bool = True
    
class TelegramNotificationConfig(BaseModel):
    """Configuration for Telegram notifications"""
    chat_ids: List[str]
    message_template: Optional[str] = None
    include_snapshot: bool = True
    
class WebhookNotificationConfig(BaseModel):
    """Configuration for webhook notifications"""
    url: str
    headers: Optional[Dict[str, str]] = None
    include_snapshot: bool = False

class NotificationTriggerCreate(BaseModel):
    """Schema for creating notification triggers"""
    name: str
    description: Optional[str] = None
    active: bool = True
    condition_type: TriggerConditionType
    condition_params: Dict[str, Any]
    time_restriction: TimeRestrictedTrigger = TimeRestrictedTrigger.ALWAYS
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    camera_id: Optional[int] = None
    cooldown_period: int = 300
    notification_type: NotificationType
    notification_config: Dict[str, Any]
    
    @validator('time_start', 'time_end')
    def validate_time_format(cls, v, values):
        if v is not None:
            try:
                # Validate time format
                time.fromisoformat(v)
            except ValueError:
                raise ValueError('Time must be in "HH:MM" format')
        return v
    
    @validator('condition_params')
    def validate_condition_params(cls, v, values):
        condition_type = values.get('condition_type')
        if condition_type == TriggerConditionType.OCCUPANCY_ABOVE or condition_type == TriggerConditionType.OCCUPANCY_BELOW:
            if 'threshold' not in v:
                raise ValueError('Threshold required for occupancy conditions')
        elif condition_type == TriggerConditionType.SPECIFIC_FACE:
            if 'person_id' not in v:
                raise ValueError('Person ID required for specific face condition')
        elif condition_type == TriggerConditionType.TEMPLATE_MATCHED:
            if 'template_id' not in v:
                raise ValueError('Template ID required for template matching condition')
        return v
    
    @validator('notification_config')
    def validate_notification_config(cls, v, values):
        notification_type = values.get('notification_type')
        if notification_type == NotificationType.EMAIL:
            if 'recipients' not in v:
                raise ValueError('Recipients required for email notifications')
        elif notification_type == NotificationType.TELEGRAM:
            if 'chat_ids' not in v:
                raise ValueError('Chat IDs required for Telegram notifications')
        elif notification_type == NotificationType.WEBHOOK:
            if 'url' not in v:
                raise ValueError('URL required for webhook notifications')
        return v

class NotificationTriggerUpdate(BaseModel):
    """Schema for updating notification triggers"""
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    condition_type: Optional[TriggerConditionType] = None
    condition_params: Optional[Dict[str, Any]] = None
    time_restriction: Optional[TimeRestrictedTrigger] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    camera_id: Optional[int] = None
    cooldown_period: Optional[int] = None
    notification_type: Optional[NotificationType] = None
    notification_config: Optional[Dict[str, Any]] = None

class NotificationTriggerResponse(BaseModel):
    """Schema for trigger responses"""
    id: int
    name: str
    description: Optional[str] = None
    active: bool
    condition_type: TriggerConditionType
    condition_params: Dict[str, Any]
    time_restriction: TimeRestrictedTrigger
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    camera_id: Optional[int] = None
    cooldown_period: int
    last_triggered: Optional[datetime] = None
    notification_type: NotificationType
    notification_config: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True

class NotificationEventResponse(BaseModel):
    """Schema for notification event responses"""
    id: int
    trigger_id: int
    camera_id: int
    timestamp: datetime
    event_data: Dict[str, Any]
    sent_successfully: bool
    delivery_error: Optional[str] = None
    snapshot_path: Optional[str] = None
    
    class Config:
        orm_mode = True