from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field
import uuid
from app.database import Base

class Camera(Base):
    """SQLAlchemy Camera model"""
    __tablename__ = "cameras"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    rtsp_url = Column(String, nullable=False, unique=True)
    location = Column(String, nullable=True)
    description = Column(String, nullable=True)
    
    # Processing settings
    enabled = Column(Boolean, default=True)
    processing_fps = Column(Integer, default=5)
    streaming_fps = Column(Integer, default=30)
    
    # Feature flags
    detect_people = Column(Boolean, default=True)
    count_people = Column(Boolean, default=True)
    recognize_faces = Column(Boolean, default=False)
    template_matching = Column(Boolean, default=False)
    
    # Relationships
    templates = relationship("Template", back_populates="camera", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="camera", cascade="all, delete-orphan")
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Pydantic models for API
class CameraBase(BaseModel):
    """Base Camera schema"""
    name: str
    rtsp_url: str
    location: Optional[str] = None
    description: Optional[str] = None
    processing_fps: int = 5
    streaming_fps: int = 30
    detect_people: bool = True
    count_people: bool = True
    recognize_faces: bool = False
    template_matching: bool = False

class CameraCreate(CameraBase):
    """Camera creation schema"""
    pass

class CameraUpdate(BaseModel):
    """Camera update schema"""
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    processing_fps: Optional[int] = None
    streaming_fps: Optional[int] = None
    detect_people: Optional[bool] = None
    count_people: Optional[bool] = None
    recognize_faces: Optional[bool] = None
    template_matching: Optional[bool] = None

class CameraResponse(CameraBase):
    """Camera response schema"""
    id: int
    enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True