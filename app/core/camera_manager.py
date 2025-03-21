import asyncio
import cv2
import logging
import time
import numpy as np
from typing import Dict, Optional, List, Tuple
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
        self.lock = asyncio.Lock()
        self.initialized = False
    
    async def initialize(self):
        """Initialize camera connections from database"""
        if self.initialized:
            return
        
        async for session in get_db():
            query = select(Camera).where(Camera.enabled == True)
            result = await session.execute(query)
            cameras = result.scalars().all()
            
            for camera in cameras:
                await self.add_camera(camera)
        
        self.initialized = True
        logger.info(f"Camera Manager initialized with {len(self.cameras)} active cameras")
    
    async def add_camera(self, camera: Camera) -> bool:
        """Add a new camera and start processing its stream"""
        async with self.lock:
            try:
                if camera.id in self.cameras:
                    await self.remove_camera(camera.id)
                
                processor = StreamProcessor(
                    camera_id=camera.id,
                    rtsp_url=camera.rtsp_url,
                    processing_fps=camera.processing_fps,
                    streaming_fps=camera.streaming_fps,
                    detect_people=camera.detect_people,
                    count_people=camera.count_people,
                    recognize_faces=camera.recognize_faces,
                    template_matching=camera.template_matching
                )
                
                success = await processor.connect()
                if success:
                    self.cameras[camera.id] = processor
                    # Start stream processing
                    asyncio.create_task(processor.process_stream())
                    logger.info(f"Added camera {camera.id} ({camera.name})")
                    return True
                else:
                    logger.error(f"Failed to connect to camera {camera.id} ({camera.name})")
                    return False
            except Exception as e:
                logger.exception(f"Error adding camera {camera.id}: {str(e)}")
                return False
    
    async def remove_camera(self, camera_id: int) -> bool:
        """Remove a camera and stop its stream processing"""
        async with self.lock:
            if camera_id in self.cameras:
                try:
                    await self.cameras[camera_id].disconnect()
                    del self.cameras[camera_id]
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
        if camera_id in self.cameras:
            return self.cameras[camera_id].get_latest_frame()
        return None
    
    async def get_jpeg_frame(self, camera_id: int) -> Optional[bytes]:
        """Get the latest frame as JPEG bytes"""
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
            
            self.cameras.clear()
            logger.info("Camera Manager shutdown completed")

# Singleton instance
_camera_manager = None

async def get_camera_manager() -> CameraManager:
    """Get or create the camera manager singleton"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager