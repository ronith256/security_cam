from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
import os
import uuid
import cv2
import numpy as np
from datetime import datetime, timedelta
import asyncio
import logging

from app.database import get_db
from app.models.camera import Camera
from app.models.person import Person, PersonCreate, PersonUpdate, PersonResponse, FaceDetection
from app.models.event import Event, EventType, PersonStatistics
from app.config import settings
from app.core.face_recognition import FaceRecognizer
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/persons", response_model=List[PersonResponse])
async def get_persons(
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all registered persons"""
    query = select(Person).offset(skip).limit(limit)
    result = await db.execute(query)
    persons = result.scalars().all()
    return persons

@router.post("/persons", response_model=PersonResponse)
async def create_person(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Register a new person with face image"""
    try:
        # Generate unique filename
        file_extension = os.path.splitext(face_image.filename)[1]
        filename = f"{uuid.uuid4()}{file_extension}"
        filepath = os.path.join(settings.FACES_DIR, filename)
        
        # Read and save the uploaded face image
        contents = await face_image.read()
        with open(filepath, "wb") as f:
            f.write(contents)
        
        # Create database entry
        db_person = Person(
            name=name,
            description=description,
            face_image_path=filepath
        )
        
        db.add(db_person)
        await db.commit()
        await db.refresh(db_person)
        
        # Register face in the face recognizer
        try:
            # Read the image
            img = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
            
            # Initialize face recognizer
            face_recognizer = FaceRecognizer()
            
            # Register the face
            success = await face_recognizer.register_face(img, db_person.id)
            
            if not success:
                logger.warning(f"Failed to register face for person {db_person.id}")
        except Exception as e:
            logger.exception(f"Error registering face: {str(e)}")
        
        return db_person
        
    except Exception as e:
        # Clean up if error
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        logger.exception(f"Error creating person: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/persons/{person_id}", response_model=PersonResponse)
async def get_person(
    person_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific person by ID"""
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person

@router.put("/persons/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: int,
    person_update: PersonUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a person's information"""
    # Get existing person
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Update fields
    update_data = person_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(person, key, value)
    
    await db.commit()
    await db.refresh(person)
    
    return person

@router.delete("/persons/{person_id}")
async def delete_person(
    person_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a person"""
    # Get existing person
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Delete face image if exists
    if os.path.exists(person.face_image_path):
        os.remove(person.face_image_path)
    
    # Remove from database
    await db.delete(person)
    await db.commit()
    
    return {"message": f"Person {person_id} deleted successfully"}

@router.get("/persons/{person_id}/face")
async def get_person_face(
    person_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a person's face image"""
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    
    if not os.path.exists(person.face_image_path):
        raise HTTPException(status_code=404, detail="Face image not found")
    
    return FileResponse(person.face_image_path)

@router.post("/persons/{person_id}/face")
async def update_person_face(
    person_id: int,
    face_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Update a person's face image"""
    # Get existing person
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    
    try:
        # Delete old face image if exists
        if os.path.exists(person.face_image_path):
            os.remove(person.face_image_path)
        
        # Generate unique filename
        file_extension = os.path.splitext(face_image.filename)[1]
        filename = f"{uuid.uuid4()}{file_extension}"
        filepath = os.path.join(settings.FACES_DIR, filename)
        
        # Read and save the uploaded face image
        contents = await face_image.read()
        with open(filepath, "wb") as f:
            f.write(contents)
        
        # Update path
        person.face_image_path = filepath
        
        # Clear existing face encoding to force re-encoding
        person.face_encoding = None
        
        await db.commit()
        
        # Register face in the face recognizer
        try:
            # Read the image
            img = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
            
            # Initialize face recognizer
            face_recognizer = FaceRecognizer()
            
            # Register the face
            success = await face_recognizer.register_face(img, person.id)
            
            if not success:
                logger.warning(f"Failed to register face for person {person.id}")
        except Exception as e:
            logger.exception(f"Error registering face: {str(e)}")
        
        return {"message": "Face image updated successfully"}
        
    except Exception as e:
        logger.exception(f"Error updating face image: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/persons/{person_id}/statistics", response_model=PersonStatistics)
async def get_person_statistics(
    person_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get statistics for a person"""
    # Get person
    person = await db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    
    # Set default date range if not provided (last 7 days)
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=7)
    
    # Query events
    query = select(
        Event, 
        func.count(Event.id).label("count")
    ).where(
        Event.person_id == person_id,
        Event.timestamp >= start_date,
        Event.timestamp <= end_date
    ).group_by(
        Event.event_type
    )
    
    result = await db.execute(query)
    events_by_type = dict(result.all())
    
    # Get entry events
    entry_events = events_by_type.get(EventType.PERSON_ENTERED, 0)
    
    # Get detection events
    detection_events = events_by_type.get(EventType.FACE_DETECTED, 0)
    
    # Get first/last detection
    first_seen_query = select(func.min(Event.timestamp)).where(
        Event.person_id == person_id
    )
    last_seen_query = select(func.max(Event.timestamp)).where(
        Event.person_id == person_id
    )
    
    first_seen_result = await db.execute(first_seen_query)
    last_seen_result = await db.execute(last_seen_query)
    
    first_seen = first_seen_result.scalar_one_or_none() or start_date
    last_seen = last_seen_result.scalar_one_or_none() or end_date
    
    # Get cameras where the person was detected
    cameras_query = select(
        func.distinct(Event.camera_id)
    ).where(
        Event.person_id == person_id
    )
    
    cameras_result = await db.execute(cameras_query)
    camera_ids = cameras_result.scalars().all()
    
    # Get camera names
    camera_names = []
    for camera_id in camera_ids:
        camera_query = select(Camera.name).where(Camera.id == camera_id)
        camera_result = await db.execute(camera_query)
        camera_name = camera_result.scalar_one_or_none()
        if camera_name:
            camera_names.append(camera_name)
    
    return {
        "person_id": person_id,
        "person_name": person.name,
        "total_entries": entry_events,
        "total_detections": detection_events,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "cameras": camera_names
    }

@router.get("/detections", response_model=List[FaceDetection])
async def detect_faces_in_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get current face detections from a camera"""
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Check if camera exists in manager
    if camera_id not in camera_manager.cameras:
        raise HTTPException(status_code=404, detail="Camera not found or not active")
    
    # Get latest detection results
    detection_results = camera_manager.cameras[camera_id].get_detection_results()
    
    # Extract face detections
    face_detections = []
    if 'faces' in detection_results:
        face_detections = detection_results['faces']
    
    return face_detections