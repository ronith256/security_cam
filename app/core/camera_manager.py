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
    
    async def initialize(self):
        """Initialize camera manager (but don't connect to cameras yet)"""
        if self.initialized:
            return
        
        self.initialized = True
        logger.info("Camera Manager initialized")
    
    async def add_camera(self, camera: Camera) -> bool:
        """Add a new camera - only connect if it's in use"""
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
                
                return True
                
            # Create a new processor (but don't connect yet)
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
            
            self.cameras[camera_id] = processor
            
            # Only connect if the camera is in use
            if camera_id in self.cameras_in_use:
                # Create a task for connection to avoid multiple concurrent connections
                self._connection_tasks[camera_id] = asyncio.create_task(self._connect_camera(camera_id))
                
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
    
    async def _connect_camera(self, camera_id: int) -> bool:
        """Internal method to connect to a camera"""
        if camera_id not in self.cameras:
            logger.error(f"Camera {camera_id} not found in manager")
            return False
            
        processor = self.cameras[camera_id]
        
        # Connect to the camera
        success = await processor.connect()
        
        if success:
            # Start stream processing
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
        """Mark a camera as no longer in use - may disconnect after a delay"""
        if camera_id in self.cameras_in_use:
            self.cameras_in_use.remove(camera_id)
            
            # Schedule disconnection after a delay if still not in use
            asyncio.create_task(self._delayed_disconnect(camera_id))
    
    async def _delayed_disconnect(self, camera_id: int, delay_seconds: int = 60):
        """Disconnect a camera after a delay if it's still not in use"""
        await asyncio.sleep(delay_seconds)
        
        async with self.lock:
            # If camera is back in use, don't disconnect
            if camera_id in self.cameras_in_use:
                return
                
            # If camera is not in manager anymore, nothing to do
            if camera_id not in self.cameras:
                return
                
            logger.info(f"Disconnecting unused camera {camera_id}")
            
            # Disconnect the camera
            await self.cameras[camera_id].disconnect()
    
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
        return await self.add_camera(camera)
    
    async def get_frame(self, camera_id: int) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest processed frame from a camera"""
        # Ensure camera is connected
        if not await self.ensure_camera_connected(camera_id):
            return None
            
        if camera_id in self.cameras:
            return self.cameras[camera_id].get_latest_frame()
        return None
    
    async def get_jpeg_frame(self, camera_id: int) -> Optional[bytes]:
        """Get the latest frame as JPEG bytes"""
        # Ensure camera is connected
        if not await self.ensure_camera_connected(camera_id):
            return None
            
        frame_data = await self.get_frame(camera_id)
        if frame_data:
            frame, _ = frame_data
            _, jpeg = cv2.imencode(".jpg", frame)
            return jpeg.tobytes()
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