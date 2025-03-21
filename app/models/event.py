from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel
from datetime import datetime
import enum
from app.database import Base

class EventType(enum.Enum):
    """Event type enumeration"""
    PERSON_ENTERED = "person_entered"
    PERSON_EXITED = "person_exited"
    FACE_DETECTED = "face_detected"
    TEMPLATE_MATCHED = "template_matched"
    OCCUPANCY_CHANGED = "occupancy_changed"

class Event(Base):
    """SQLAlchemy Event model for tracking detections and counts"""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(Enum(EventType), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    snapshot_path = Column(String, nullable=True)
    
    # Relations
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    camera = relationship("Camera", back_populates="events")
    
    # For face detection events
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    person = relationship("Person", back_populates="events")
    
    # For template matching events
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=True)
    
    # Additional data
    confidence = Column(Float, nullable=True)
    occupancy_count = Column(Integer, nullable=True)  # For occupancy events

# Pydantic models for API
class EventBase(BaseModel):
    """Base Event schema"""
    event_type: str
    camera_id: int
    person_id: Optional[int] = None
    template_id: Optional[int] = None
    confidence: Optional[float] = None
    occupancy_count: Optional[int] = None

class EventCreate(EventBase):
    """Event creation schema"""
    pass

class EventResponse(EventBase):
    """Event response schema"""
    id: int
    timestamp: datetime
    snapshot_path: Optional[str] = None
    
    class Config:
        orm_mode = True

class OccupancyResponse(BaseModel):
    """Current occupancy response schema"""
    camera_id: int
    camera_name: str
    current_count: int
    last_updated: datetime

class PersonStatistics(BaseModel):
    """Person statistics response schema"""
    person_id: int
    person_name: str
    total_entries: int
    total_detections: int
    first_seen: datetime
    last_seen: datetime
    cameras: List[str]  # List of camera names where the person was detected