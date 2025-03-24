from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from app.database import Base

class Settings(Base):
    """SQLAlchemy Settings model for global application settings"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    value = Column(JSON, nullable=False)
    description = Column(String, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Pydantic models for API
class SettingBase(BaseModel):
    """Base Setting schema"""
    key: str
    value: Any
    description: Optional[str] = None

class SettingCreate(SettingBase):
    """Setting creation schema"""
    pass

class SettingUpdate(BaseModel):
    """Setting update schema"""
    value: Optional[Any] = None
    description: Optional[str] = None

class SettingResponse(SettingBase):
    """Setting response schema"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True

# Default settings
DEFAULT_SETTINGS = [
    {
        "key": "global_processing_fps",
        "value": 5,
        "description": "Default FPS for video processing across all cameras"
    },
    {
        "key": "global_streaming_fps",
        "value": 30,
        "description": "Default FPS for video streaming across all cameras"
    },
    {
        "key": "detection_threshold",
        "value": 0.5,
        "description": "Confidence threshold for object detection"
    },
    {
        "key": "face_recognition_threshold",
        "value": 0.6,
        "description": "Confidence threshold for face recognition"
    },
    {
        "key": "template_matching_threshold",
        "value": 0.7,
        "description": "Default threshold for template matching"
    },
    {
        "key": "enable_notifications",
        "value": True,
        "description": "Enable/disable global notifications"
    },
    {
        "key": "idle_snapshot_interval", 
        "value": 5,
        "description": "Time between snapshot updates when camera is not actively streaming"
    }
]