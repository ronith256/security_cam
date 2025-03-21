from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional, Dict, Any
import logging

from app.database import get_db
from app.models.settings import Settings, SettingCreate, SettingUpdate, SettingResponse, DEFAULT_SETTINGS
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[SettingResponse])
async def get_all_settings(
    db: AsyncSession = Depends(get_db)
):
    """Get all global settings"""
    # Ensure default settings exist
    await ensure_default_settings(db)
    
    # Get all settings
    query = select(Settings)
    result = await db.execute(query)
    settings = result.scalars().all()
    return settings

@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific setting by key"""
    # Ensure default settings exist
    await ensure_default_settings(db)
    
    # Get setting
    query = select(Settings).where(Settings.key == key)
    result = await db.execute(query)
    setting = result.scalar_one_or_none()
    
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting with key '{key}' not found")
    
    return setting

@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_update: SettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a setting value"""
    # Ensure default settings exist
    await ensure_default_settings(db)
    
    # Get setting
    query = select(Settings).where(Settings.key == key)
    result = await db.execute(query)
    setting = result.scalar_one_or_none()
    
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting with key '{key}' not found")
    
    # Update value and description if provided
    update_data = setting_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(setting, field, value)
    
    await db.commit()
    await db.refresh(setting)
    
    # Apply setting to all cameras if it's a global setting
    if key == "global_processing_fps":
        await apply_global_fps_setting(setting.value)
    elif key == "detection_threshold":
        await apply_detection_threshold(setting.value)
    elif key == "face_recognition_threshold":
        await apply_face_recognition_threshold(setting.value)
    elif key == "template_matching_threshold":
        await apply_template_matching_threshold(setting.value)
    
    return setting

@router.post("/", response_model=SettingResponse)
async def create_setting(
    setting: SettingCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new setting"""
    # Check if setting already exists
    query = select(Settings).where(Settings.key == setting.key)
    result = await db.execute(query)
    existing_setting = result.scalar_one_or_none()
    
    if existing_setting is not None:
        raise HTTPException(status_code=400, detail=f"Setting with key '{setting.key}' already exists")
    
    # Create new setting
    db_setting = Settings(**setting.dict())
    db.add(db_setting)
    await db.commit()
    await db.refresh(db_setting)
    
    return db_setting

@router.delete("/{key}")
async def delete_setting(
    key: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a setting"""
    # Get setting
    query = select(Settings).where(Settings.key == key)
    result = await db.execute(query)
    setting = result.scalar_one_or_none()
    
    if setting is None:
        raise HTTPException(status_code=404, detail=f"Setting with key '{key}' not found")
    
    # Check if it's a default setting
    for default_setting in DEFAULT_SETTINGS:
        if default_setting["key"] == key:
            raise HTTPException(status_code=400, detail=f"Cannot delete default setting '{key}'")
    
    # Delete setting
    await db.delete(setting)
    await db.commit()
    
    return {"message": f"Setting '{key}' deleted successfully"}

@router.post("/apply")
async def apply_settings():
    """Apply all global settings to active cameras"""
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Get all settings
    async for session in get_db():
        query = select(Settings)
        result = await session.execute(query)
        settings = result.scalars().all()
        
        # Apply each setting
        for setting in settings:
            if setting.key == "global_processing_fps":
                await apply_global_fps_setting(setting.value)
            elif setting.key == "detection_threshold":
                await apply_detection_threshold(setting.value)
            elif setting.key == "face_recognition_threshold":
                await apply_face_recognition_threshold(setting.value)
            elif setting.key == "template_matching_threshold":
                await apply_template_matching_threshold(setting.value)
    
    return {"message": "All settings applied successfully"}

@router.post("/reset-defaults")
async def reset_default_settings(
    db: AsyncSession = Depends(get_db)
):
    """Reset all settings to default values"""
    for default_setting in DEFAULT_SETTINGS:
        key = default_setting["key"]
        
        # Get setting
        query = select(Settings).where(Settings.key == key)
        result = await db.execute(query)
        setting = result.scalar_one_or_none()
        
        if setting is not None:
            # Update to default value
            setting.value = default_setting["value"]
            setting.description = default_setting["description"]
        else:
            # Create if not exists
            db_setting = Settings(
                key=key,
                value=default_setting["value"],
                description=default_setting["description"]
            )
            db.add(db_setting)
    
    await db.commit()
    
    # Apply reset settings
    await apply_settings()
    
    return {"message": "Settings reset to defaults successfully"}

async def ensure_default_settings(db: AsyncSession):
    """Ensure default settings exist in the database"""
    for default_setting in DEFAULT_SETTINGS:
        key = default_setting["key"]
        
        # Check if setting exists
        query = select(Settings).where(Settings.key == key)
        result = await db.execute(query)
        setting = result.scalar_one_or_none()
        
        if setting is None:
            # Create default setting
            db_setting = Settings(
                key=key,
                value=default_setting["value"],
                description=default_setting["description"]
            )
            db.add(db_setting)
    
    await db.commit()

async def apply_global_fps_setting(fps_value: int):
    """Apply global FPS setting to all cameras"""
    camera_manager = await get_camera_manager()
    
    for camera_id, processor in camera_manager.cameras.items():
        processor.processing_fps = fps_value

async def apply_detection_threshold(threshold: float):
    """Apply detection threshold to all object detectors"""
    camera_manager = await get_camera_manager()
    
    for camera_id, processor in camera_manager.cameras.items():
        if processor.object_detector:
            processor.object_detector.set_threshold(threshold)

async def apply_face_recognition_threshold(threshold: float):
    """Apply face recognition threshold to all face recognizers"""
    camera_manager = await get_camera_manager()
    
    for camera_id, processor in camera_manager.cameras.items():
        if processor.face_recognizer:
            processor.face_recognizer.set_threshold(threshold)

async def apply_template_matching_threshold(threshold: float):
    """Apply template matching threshold to all template matchers"""
    camera_manager = await get_camera_manager()
    
    for camera_id, processor in camera_manager.cameras.items():
        if processor.template_matcher:
            processor.template_matcher.set_threshold(threshold)