# app/core/camera_manager.py

import asyncio
import cv2
import logging
import time
import numpy as np
from typing import Dict, Optional, List, Tuple, Set
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.camera import Camera
from app.core.stream_processor import StreamProcessor
from app.config import settings

logger = logging.getLogger(__name__)

class CameraManager:
    """
    Manages camera connections and stream processing
    """
    def __init__(self):
        self.cameras: Dict[int, StreamProcessor] = {}
        self.cameras_in_use: Set[int] = set()  # Track cameras that are currently being viewed
        self.lock = asyncio.Lock()
        self.initialized = False
        self._connection_tasks = {}  # Track connection tasks to avoid duplicates
        self._background_task = None  # Background task for monitoring all cameras
    
    async def initialize(self):
        """Initialize camera manager and start background processing for all enabled cameras"""
        if self.initialized:
            return
        
        self.initialized = True
        logger.info("Camera Manager initialized")
        
        # Start background monitoring task
        self._background_task = asyncio.create_task(self._background_monitor_task())
    
    async def _background_monitor_task(self):
        """Background task that ensures all enabled cameras are being processed"""
        logger.info("Starting background camera monitoring task")
        
        while True:
            try:
                # Load all enabled cameras from database
                async for session in get_db():
                    query = select(Camera).where(Camera.enabled == True)
                    result = await session.execute(query)
                    enabled_cameras = result.scalars().all()
                    
                    # Ensure all enabled cameras are added to manager and being processed
                    for camera in enabled_cameras:
                        if camera.id not in self.cameras:
                            await self.add_camera(camera, start_processing=True)
                        elif self.cameras[camera.id].should_process and not self.cameras[camera.id].processing:
                            # Start processing if it's not already running
                            processor = self.cameras[camera.id]
                            if not processor.connected:
                                await processor.connect()
                            if not processor.processing:
                                asyncio.create_task(processor.process_stream())
                    
                    # Clean up any cameras that were disabled in the database
                    camera_ids = set(self.cameras.keys())
                    enabled_ids = set(camera.id for camera in enabled_cameras)
                    disabled_ids = camera_ids - enabled_ids
                    
                    for camera_id in disabled_ids:
                        if camera_id not in self.cameras_in_use:  # Don't remove cameras currently being viewed
                            await self.remove_camera(camera_id)
            
            except Exception as e:
                logger.exception(f"Error in background monitor task: {str(e)}")
            
            # Check every 60 seconds
            await asyncio.sleep(60)
    
    async def add_camera(self, camera: Camera, start_processing: bool = False) -> bool:
        """Add a new camera - connect and start processing if requested"""
        if not camera.enabled:
            logger.warning(f"Attempted to add disabled camera {camera.id}")
            return False
            
        async with self.lock:
            camera_id = camera.id
            
            # If we already have a connection task in progress, wait for it
            if camera_id in self._connection_tasks and not self._connection_tasks[camera_id].done():
                try:
                    return await self._connection_tasks[camera_id]
                except Exception:
                    # If the task failed, we'll try again
                    pass
            
            # If camera already exists, update its settings
            if camera_id in self.cameras:
                processor = self.cameras[camera_id]
                
                # Update settings if needed
                processor.rtsp_url = camera.rtsp_url
                processor.processing_fps = camera.processing_fps
                processor.streaming_fps = camera.streaming_fps
                processor.detect_people = camera.detect_people
                processor.count_people = camera.count_people
                processor.recognize_faces = camera.recognize_faces
                processor.template_matching = camera.template_matching
                processor.should_process = camera.detect_people or camera.count_people or camera.recognize_faces or camera.template_matching
                
                # Start processing if requested and not already processing
                if start_processing and processor.should_process and not processor.processing:
                    if not processor.connected:
                        await processor.connect()
                    asyncio.create_task(processor.process_stream())
                
                return True
                
            # Create a new processor
            processor = StreamProcessor(
                camera_id=camera_id,
                rtsp_url=camera.rtsp_url,
                processing_fps=camera.processing_fps,
                streaming_fps=camera.streaming_fps,
                detect_people=camera.detect_people,
                count_people=camera.count_people,
                recognize_faces=camera.recognize_faces,
                template_matching=camera.template_matching
            )
            
            # Set whether this camera should be processed (based on features enabled)
            processor.should_process = camera.detect_people or camera.count_people or camera.recognize_faces or camera.template_matching
            
            self.cameras[camera_id] = processor
            
            # Connect immediately if needed for viewing or background processing
            if start_processing or camera_id in self.cameras_in_use:
                # Create a task for connection to avoid multiple concurrent connections
                self._connection_tasks[camera_id] = asyncio.create_task(self._connect_camera(camera_id, start_processing))
                
                try:
                    success = await self._connection_tasks[camera_id]
                    if success:
                        logger.info(f"Added and connected camera {camera_id} ({camera.name})")
                    else:
                        logger.error(f"Failed to connect to camera {camera_id} ({camera.name})")
                    return success
                except Exception as e:
                    logger.exception(f"Error connecting to camera {camera_id}: {str(e)}")
                    return False
            else:
                logger.info(f"Added camera {camera_id} ({camera.name}) - will connect on demand")
                return True
    
    async def _connect_camera(self, camera_id: int, start_processing: bool = False) -> bool:
        """Internal method to connect to a camera"""
        if camera_id not in self.cameras:
            logger.error(f"Camera {camera_id} not found in manager")
            return False
            
        processor = self.cameras[camera_id]
        
        # Connect to the camera
        success = await processor.connect()
        
        if success:
            # Start stream processing if requested
            if start_processing and processor.should_process:
                asyncio.create_task(processor.process_stream())
            return True
        else:
            return False
    
    async def ensure_camera_connected(self, camera_id: int) -> bool:
        """Ensure a camera is connected if it's needed"""
        if camera_id not in self.cameras:
            # Try to load the camera from the database
            async for session in get_db():
                camera = await session.get(Camera, camera_id)
                if camera and camera.enabled:
                    return await self.add_camera(camera)
                return False
        
        # Mark this camera as in use
        self.cameras_in_use.add(camera_id)
        
        processor = self.cameras[camera_id]
        
        # If already connected, we're good
        if processor.connected:
            return True
            
        # Create a task for connection to avoid multiple concurrent connections
        if camera_id in self._connection_tasks and not self._connection_tasks[camera_id].done():
            try:
                return await self._connection_tasks[camera_id]
            except Exception:
                # If the task failed, we'll try again
                pass
        
        self._connection_tasks[camera_id] = asyncio.create_task(self._connect_camera(camera_id))
        
        try:
            return await self._connection_tasks[camera_id]
        except Exception as e:
            logger.exception(f"Error ensuring camera {camera_id} is connected: {str(e)}")
            return False
    
    async def release_camera(self, camera_id: int):
        """Mark a camera as no longer in use - may stop streaming but continue processing"""
        if camera_id in self.cameras_in_use:
            self.cameras_in_use.remove(camera_id)
    
    async def remove_camera(self, camera_id: int) -> bool:
        """Remove a camera and stop its stream processing"""
        async with self.lock:
            if camera_id in self.cameras:
                # Stop any connection task
                if camera_id in self._connection_tasks and not self._connection_tasks[camera_id].done():
                    self._connection_tasks[camera_id].cancel()
                    try:
                        await self._connection_tasks[camera_id]
                    except asyncio.CancelledError:
                        pass
                
                # Disconnect processor
                try:
                    await self.cameras[camera_id].disconnect()
                    del self.cameras[camera_id]
                    
                    # Remove from in-use set if present
                    if camera_id in self.cameras_in_use:
                        self.cameras_in_use.remove(camera_id)
                    
                    logger.info(f"Removed camera {camera_id}")
                    return True
                except Exception as e:
                    logger.exception(f"Error removing camera {camera_id}: {str(e)}")
            return False
    
    async def update_camera(self, camera: Camera) -> bool:
        """Update camera settings and restart if needed"""
        return await self.add_camera(camera, start_processing=camera.detect_people or camera.count_people or camera.recognize_faces or camera.template_matching)
    
    async def get_frame(self, camera_id: int) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest processed frame from a camera"""
        # Ensure camera is connected
        if not await self.ensure_camera_connected(camera_id):
            return None
            
        if camera_id in self.cameras:
            return self.cameras[camera_id].get_latest_frame()
        return None
    
    async def get_jpeg_frame(self, camera_id: int, high_quality: bool = False) -> Optional[bytes]:
        """Get the latest frame as JPEG bytes, with optional high quality"""
        logger.debug(f"Request for JPEG frame from camera {camera_id}, high quality: {high_quality}")
        
        # Ensure camera is connected
        if not await self.ensure_camera_connected(camera_id):
            logger.error(f"Failed to connect to camera {camera_id}")
            return None
            
        try:
            frame_data = await self.get_frame(camera_id)
            if frame_data:
                frame, timestamp = frame_data
                logger.debug(f"Got frame from camera {camera_id}, timestamp: {timestamp}")
                
                # Set JPEG quality
                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95 if high_quality else 80]
                
                _, jpeg = cv2.imencode(".jpg", frame, encode_params)
                return jpeg.tobytes()
            else:
                logger.warning(f"No frame data available for camera {camera_id}")
                return None
        except Exception as e:
            logger.exception(f"Error getting JPEG frame for camera {camera_id}: {str(e)}")
            return None
    
    async def take_template_snapshot(self, camera_id: int) -> Optional[bytes]:
        """Take a snapshot to use as a template"""
        # Ensure camera is connected
        if not await self.ensure_camera_connected(camera_id):
            logger.error(f"Failed to connect to camera {camera_id} for template")
            return None
            
        try:
            frame_data = await self.get_frame(camera_id)
            if frame_data:
                frame, _ = frame_data
                # Set template on the processor
                if camera_id in self.cameras:
                    self.cameras[camera_id].set_base_template(frame)
                
                # Return high quality JPEG
                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                _, jpeg = cv2.imencode(".jpg", frame, encode_params)
                return jpeg.tobytes()
            else:
                logger.warning(f"No frame data available for template on camera {camera_id}")
                return None
        except Exception as e:
            logger.exception(f"Error taking template snapshot for camera {camera_id}: {str(e)}")
            return None
    
    async def set_camera_property(self, camera_id: int, property_name: str, value) -> bool:
        """Set a property for a specific camera"""
        if camera_id in self.cameras:
            if hasattr(self.cameras[camera_id], property_name):
                setattr(self.cameras[camera_id], property_name, value)
                return True
        return False
    
    async def shutdown(self):
        """Disconnect all cameras and release resources"""
        # Cancel background monitoring task
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        
        async with self.lock:
            for camera_id, processor in list(self.cameras.items()):
                try:
                    await processor.disconnect()
                    logger.info(f"Disconnected camera {camera_id}")
                except Exception as e:
                    logger.error(f"Error disconnecting camera {camera_id}: {str(e)}")
            
            # Cancel any pending connection tasks
            for task in self._connection_tasks.values():
                if not task.done():
                    task.cancel()
            
            self.cameras.clear()
            self.cameras_in_use.clear()
            self._connection_tasks.clear()
            logger.info("Camera Manager shutdown completed")

# Singleton instance
_camera_manager = None

async def get_camera_manager() -> CameraManager:
    """Get or create the camera manager singleton"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager