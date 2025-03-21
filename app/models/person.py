from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from app.database import Base

class Person(Base):
    """SQLAlchemy Person model for face recognition"""
    __tablename__ = "persons"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    # Face recognition data
    face_image_path = Column(String, nullable=False)
    face_encoding = Column(JSON, nullable=True)  # Stored as JSON
    
    # Events related to this person
    events = relationship("Event", back_populates="person", cascade="all, delete-orphan")
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Pydantic models for API
class PersonBase(BaseModel):
    """Base Person schema"""
    name: str
    description: Optional[str] = None

class PersonCreate(PersonBase):
    """Person creation schema"""
    pass

class PersonUpdate(BaseModel):
    """Person update schema"""
    name: Optional[str] = None
    description: Optional[str] = None

class PersonResponse(PersonBase):
    """Person response schema"""
    id: int
    face_image_path: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        
class FaceDetection(BaseModel):
    """Face detection result model"""
    person_id: int
    person_name: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]