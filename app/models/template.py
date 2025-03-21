from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from app.database import Base

class Template(Base):
    """SQLAlchemy Template model for template matching"""
    __tablename__ = "templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    image_path = Column(String, nullable=False)
    
    # Relationship to camera
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    camera = relationship("Camera", back_populates="templates")
    
    # Template matching settings
    enabled = Column(Boolean, default=True)
    threshold = Column(Float, default=0.7)  # Matching threshold
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Pydantic models for API
class TemplateBase(BaseModel):
    """Base Template schema"""
    name: str
    description: Optional[str] = None
    threshold: float = 0.7

class TemplateCreate(TemplateBase):
    """Template creation schema"""
    camera_id: int

class TemplateUpdate(BaseModel):
    """Template update schema"""
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    threshold: Optional[float] = None

class TemplateResponse(TemplateBase):
    """Template response schema"""
    id: int
    camera_id: int
    image_path: str
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True