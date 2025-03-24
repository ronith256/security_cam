from datetime import datetime
import time
import cv2
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional, Dict, Any
import asyncio
import logging

from app.database import get_db
from app.models.camera import Camera, CameraCreate, CameraUpdate, CameraResponse
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[CameraResponse])
async def get_cameras(
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all cameras"""
    query = select(Camera).offset(skip).limit(limit)
    result = await db.execute(query)
    cameras = result.scalars().all()
    return cameras

@router.post("/", response_model=CameraResponse)
async def create_camera(
    camera: CameraCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Create a new camera"""
    # Create database entry
    db_camera = Camera(**camera.dict())
    db.add(db_camera)
    await db.commit()
    await db.refresh(db_camera)
    
    # Add camera to the manager in the background
    background_tasks.add_task(add_camera_to_manager, db_camera.id)
    
    return db_camera

@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific camera by ID"""
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera

@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: int,
    camera_update: CameraUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Update a camera"""
    # Get existing camera
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Update fields
    update_data = camera_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(camera, key, value)
    
    await db.commit()
    await db.refresh(camera)
    
    # Update camera in the manager in the background
    background_tasks.add_task(update_camera_in_manager, camera.id)
    
    return camera

@router.delete("/{camera_id}")
async def delete_camera(
    camera_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Delete a camera"""
    # Get existing camera
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Remove from database
    await db.delete(camera)
    await db.commit()
    
    # Remove camera from the manager in the background
    background_tasks.add_task(remove_camera_from_manager, camera_id)
    
    return {"message": f"Camera {camera_id} deleted successfully"}


@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get the latest snapshot from a camera"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Get latest frame
    jpeg_frame = await camera_manager.get_jpeg_frame(camera_id)
    if jpeg_frame is None:
        raise HTTPException(status_code=503, detail="Camera stream not available")
    
    return Response(content=jpeg_frame, media_type="image/jpeg")

@router.get("/{camera_id}/status")
async def get_camera_status(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get the status of a camera including detection results"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Check if camera is active
    camera_active = camera_id in camera_manager.cameras
    
    if not camera_active:
        return {
            "camera_id": camera_id,
            "name": camera.name,
            "active": False,
            "detection_results": {},
            "current_occupancy": 0,
            "fps": 0
        }
    
    # Get camera processor
    processor = camera_manager.cameras.get(camera_id)
    
    return {
        "camera_id": camera_id,
        "name": camera.name,
        "active": True,
        "detection_results": processor.get_detection_results(),
        "current_occupancy": processor.get_current_occupancy(),
        "fps": processor.fps
    }

@router.post("/{camera_id}/settings")
async def update_camera_settings(
    camera_id: int,
    settings: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Update camera settings in real-time"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Update settings
    success = True
    for key, value in settings.items():
        if not await camera_manager.set_camera_property(camera_id, key, value):
            success = False
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update some settings")
    
    return {"message": "Camera settings updated successfully"}

# Background tasks for camera management
async def add_camera_to_manager(camera_id: int):
    """Add a camera to the camera manager"""
    try:
        # Get camera from database
        async for session in get_db():
            camera = await session.get(Camera, camera_id)
            if camera is None:
                logger.error(f"Camera {camera_id} not found")
                return
            
            # Add to camera manager
            camera_manager = await get_camera_manager()
            success = await camera_manager.add_camera(camera)
            
            if not success:
                logger.error(f"Failed to add camera {camera_id} to manager")
    except Exception as e:
        logger.exception(f"Error adding camera to manager: {str(e)}")

async def update_camera_in_manager(camera_id: int):
    """Update a camera in the camera manager"""
    try:
        # Get camera from database
        async for session in get_db():
            camera = await session.get(Camera, camera_id)
            if camera is None:
                logger.error(f"Camera {camera_id} not found")
                return
            
            # Update in camera manager
            camera_manager = await get_camera_manager()
            success = await camera_manager.update_camera(camera)
            
            if not success:
                logger.error(f"Failed to update camera {camera_id} in manager")
    except Exception as e:
        logger.exception(f"Error updating camera in manager: {str(e)}")

async def remove_camera_from_manager(camera_id: int):
    """Remove a camera from the camera manager"""
    try:
        # Remove from camera manager
        camera_manager = await get_camera_manager()
        success = await camera_manager.remove_camera(camera_id)
        
        if not success:
            logger.error(f"Failed to remove camera {camera_id} from manager")
    except Exception as e:
        logger.exception(f"Error removing camera from manager: {str(e)}")

@router.get("/{camera_id}/test", response_model=Dict[str, Any])
async def test_camera_connection(
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Test the connection to a camera and return diagnostic information"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Get camera manager
    camera_manager = await get_camera_manager()
    
    # Start with basic test info
    test_results = {
        "camera_id": camera_id,
        "camera_name": camera.name,
        "rtsp_url": camera.rtsp_url,
        "timestamp": datetime.now().isoformat(),
        "camera_enabled": camera.enabled,
        "tests": {}
    }
    
    # Test 1: Check if camera is in manager
    in_manager = camera_id in camera_manager.cameras
    test_results["tests"]["in_manager"] = in_manager
    
    # Test 2: Try to ensure camera is connected
    connection_success = False
    connection_error = None
    try:
        connection_success = await camera_manager.ensure_camera_connected(camera_id)
    except Exception as e:
        connection_error = str(e)
    
    test_results["tests"]["connection"] = {
        "success": connection_success,
        "error": connection_error
    }
    
    # Test 3: Try to get a single frame
    frame_success = False
    frame_error = None
    frame_info = {}
    
    if connection_success:
        try:
            processor = camera_manager.cameras[camera_id]
            frame_data = processor.get_latest_frame()
            
            if frame_data:
                frame, timestamp = frame_data
                frame_success = True
                frame_info = {
                    "shape": frame.shape,
                    "type": str(frame.dtype),
                    "timestamp": timestamp,
                    "age": time.time() - timestamp
                }
                
                # Convert to JPEG for test
                _, jpeg_data = cv2.imencode(".jpg", frame)
                jpeg_size = len(jpeg_data.tobytes())
                frame_info["jpeg_size"] = jpeg_size
            else:
                frame_error = "No frame available"
        except Exception as e:
            frame_error = str(e)
    
    test_results["tests"]["frame"] = {
        "success": frame_success,
        "error": frame_error,
        "info": frame_info
    }
    
    # Test 4: Processor info
    processor_info = {}
    if in_manager:
        processor = camera_manager.cameras[camera_id]
        processor_info = {
            "connected": processor.connected,
            "processing": processor.processing,
            "fps": processor.fps,
            "last_frame_time": processor.last_frame_time,
            "last_processed_time": processor.last_processed_time,
            "features": {
                "detect_people": processor.detect_people,
                "count_people": processor.count_people,
                "recognize_faces": processor.recognize_faces,
                "template_matching": processor.template_matching
            }
        }
    
    test_results["processor_info"] = processor_info
    
    return test_results