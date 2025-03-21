from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional, Dict, Any
import os
import uuid
import cv2
import numpy as np
from datetime import datetime
import logging

from app.database import get_db
from app.models.template import Template, TemplateCreate, TemplateUpdate, TemplateResponse
from app.models.camera import Camera
from app.config import settings
from app.core.template_matching import TemplateMatcher
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[TemplateResponse])
async def get_templates(
    camera_id: Optional[int] = None,
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all templates or templates for a specific camera"""
    if camera_id is not None:
        query = select(Template).where(Template.camera_id == camera_id).offset(skip).limit(limit)
    else:
        query = select(Template).offset(skip).limit(limit)
    
    result = await db.execute(query)
    templates = result.scalars().all()
    return templates

@router.post("/", response_model=TemplateResponse)
async def create_template(
    name: str = Form(...),
    camera_id: int = Form(...),
    description: Optional[str] = Form(None),
    threshold: float = Form(0.7),
    template_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Create a new template for matching"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    try:
        # Generate unique filename
        file_extension = os.path.splitext(template_image.filename)[1]
        filename = f"template_{camera_id}_{uuid.uuid4()}{file_extension}"
        filepath = os.path.join(settings.TEMPLATES_DIR, filename)
        
        # Read and save the uploaded template image
        contents = await template_image.read()
        with open(filepath, "wb") as f:
            f.write(contents)
        
        # Create database entry
        db_template = Template(
            name=name,
            description=description,
            image_path=filepath,
            camera_id=camera_id,
            threshold=threshold
        )
        
        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        
        # Force reload templates in the matcher
        try:
            # Get camera manager
            camera_manager = await get_camera_manager()
            
            # Get template matcher for this camera
            if camera_id in camera_manager.cameras:
                processor = camera_manager.cameras[camera_id]
                if processor.template_matcher:
                    await processor.template_matcher.load_templates(force_reload=True)
        except Exception as e:
            logger.warning(f"Error reloading templates: {str(e)}")
        
        return db_template
        
    except Exception as e:
        # Clean up if error
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        logger.exception(f"Error creating template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific template by ID"""
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    template_update: TemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a template's information"""
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Update fields
    update_data = template_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    await db.commit()
    await db.refresh(template)
    
    # Force reload templates in the matcher
    try:
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Get template matcher for this camera
        if template.camera_id in camera_manager.cameras:
            processor = camera_manager.cameras[template.camera_id]
            if processor.template_matcher:
                await processor.template_matcher.load_templates(force_reload=True)
    except Exception as e:
        logger.warning(f"Error reloading templates: {str(e)}")
    
    return template

@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a template"""
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Get camera ID for reloading templates later
    camera_id = template.camera_id
    
    # Delete template image if exists
    if os.path.exists(template.image_path):
        os.remove(template.image_path)
    
    # Remove from database
    await db.delete(template)
    await db.commit()
    
    # Force reload templates in the matcher
    try:
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Get template matcher for this camera
        if camera_id in camera_manager.cameras:
            processor = camera_manager.cameras[camera_id]
            if processor.template_matcher:
                await processor.template_matcher.load_templates(force_reload=True)
    except Exception as e:
        logger.warning(f"Error reloading templates: {str(e)}")
    
    return {"message": f"Template {template_id} deleted successfully"}

@router.get("/{template_id}/image")
async def get_template_image(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a template's image"""
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    if not os.path.exists(template.image_path):
        raise HTTPException(status_code=404, detail="Template image not found")
    
    return FileResponse(template.image_path)

@router.post("/{template_id}/image")
async def update_template_image(
    template_id: int,
    template_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Update a template's image"""
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        # Delete old template image if exists
        if os.path.exists(template.image_path):
            os.remove(template.image_path)
        
        # Generate unique filename
        file_extension = os.path.splitext(template_image.filename)[1]
        filename = f"template_{template.camera_id}_{uuid.uuid4()}{file_extension}"
        filepath = os.path.join(settings.TEMPLATES_DIR, filename)
        
        # Read and save the uploaded template image
        contents = await template_image.read()
        with open(filepath, "wb") as f:
            f.write(contents)
        
        # Update path
        template.image_path = filepath
        await db.commit()
        
        # Force reload templates in the matcher
        try:
            # Get camera manager
            camera_manager = await get_camera_manager()
            
            # Get template matcher for this camera
            if template.camera_id in camera_manager.cameras:
                processor = camera_manager.cameras[template.camera_id]
                if processor.template_matcher:
                    await processor.template_matcher.load_templates(force_reload=True)
        except Exception as e:
            logger.warning(f"Error reloading templates: {str(e)}")
        
        return {"message": "Template image updated successfully"}
        
    except Exception as e:
        logger.exception(f"Error updating template image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/matches/{camera_id}")
async def get_template_matches(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get current template matches from a camera"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Check if camera is active
    if camera_id not in camera_manager.cameras:
        raise HTTPException(status_code=400, detail="Camera not active")
    
    # Get latest detection results
    detection_results = camera_manager.cameras[camera_id].get_detection_results()
    
    # Extract template matches
    template_matches = []
    if 'templates' in detection_results:
        template_matches = detection_results['templates']
    
    return template_matches

@router.post("/{template_id}/enable")
async def enable_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Enable a template for matching"""
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Enable template
    template.enabled = True
    await db.commit()
    
    # Force reload templates in the matcher
    try:
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Get template matcher for this camera
        if template.camera_id in camera_manager.cameras:
            processor = camera_manager.cameras[template.camera_id]
            if processor.template_matcher:
                await processor.template_matcher.load_templates(force_reload=True)
    except Exception as e:
        logger.warning(f"Error reloading templates: {str(e)}")
    
    return {"message": f"Template {template_id} enabled"}

@router.post("/{template_id}/disable")
async def disable_template(
    template_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Disable a template for matching"""
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Disable template
    template.enabled = False
    await db.commit()
    
    # Force reload templates in the matcher
    try:
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Get template matcher for this camera
        if template.camera_id in camera_manager.cameras:
            processor = camera_manager.cameras[template.camera_id]
            if processor.template_matcher:
                await processor.template_matcher.load_templates(force_reload=True)
    except Exception as e:
        logger.warning(f"Error reloading templates: {str(e)}")
    
    return {"message": f"Template {template_id} disabled"}

@router.post("/{template_id}/threshold")
async def set_template_threshold(
    template_id: int,
    threshold: float,
    db: AsyncSession = Depends(get_db)
):
    """Set the matching threshold for a template"""
    # Validate threshold
    if threshold < 0 or threshold > 1:
        raise HTTPException(status_code=400, detail="Threshold must be between 0 and 1")
    
    # Get existing template
    template = await db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Update threshold
    template.threshold = threshold
    await db.commit()
    
    # Force reload templates in the matcher
    try:
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Get template matcher for this camera
        if template.camera_id in camera_manager.cameras:
            processor = camera_manager.cameras[template.camera_id]
            if processor.template_matcher:
                await processor.template_matcher.load_templates(force_reload=True)
    except Exception as e:
        logger.warning(f"Error reloading templates: {str(e)}")
    
    return {"message": f"Template {template_id} threshold set to {threshold}"}