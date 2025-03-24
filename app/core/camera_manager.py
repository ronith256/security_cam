import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from app.models.camera import Camera
from app.models.settings import Settings
from app.core.stream_processor import StreamProcessor
from app.core.object_detection import ObjectDetector
from app.core.face_recognition import FaceRecognizer
from app.core.template_matching import TemplateMatcher
from app.core.people_counter import PeopleCounter
from app.config import settings

logger = logging.getLogger(__name__)

class CameraManager:
    """
    Manages multiple camera streams and their processing components.
    Provides a centralized interface for adding, removing, and controlling cameras.
    """
    def __init__(self):
        self.cameras: Dict[int, StreamProcessor] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.initialized = False
        
        # Shared resources for efficiency
        self.shared_object_detector = None
        self.shared_face_recognizer = None
        
        # Status
        self.status = "initializing"
        self.start_time = time.time()
    
    async def initialize(self):
        """Initialize the camera manager and shared resources"""
        if self.initialized:
            return
        
        try:
            # Initialize shared object detector if we'll be using it
            self.shared_object_detector = ObjectDetector()
            
            # Initialize shared face recognizer
            self.shared_face_recognizer = FaceRecognizer()
            
            # Update status
            self.initialized = True
            self.status = "ready"
            logger.info("Camera manager initialized")
        
        except Exception as e:
            self.status = "error"
            logger.exception(f"Failed to initialize camera manager: {str(e)}")
    
    async def add_camera(self, camera: Camera, start_processing: bool = True) -> bool:
        """
        Add a new camera to the manager
        
        Args:
            camera: Camera model with configuration
            start_processing: Whether to start processing immediately
            
        Returns:
            Success flag
        """
        try:
            # Check if camera already exists
            if camera.id in self.cameras:
                logger.warning(f"Camera {camera.id} already exists in manager")
                return await self.update_camera(camera)
            
            # Initialize stream processor
            processor = StreamProcessor(
                camera_id=camera.id,
                name=camera.name,
                rtsp_url=camera.rtsp_url,
                processing_fps=camera.processing_fps,
                streaming_fps=camera.streaming_fps,
                detect_people=camera.detect_people,
                count_people=camera.count_people,
                recognize_faces=camera.recognize_faces,
                template_matching=camera.template_matching
            )
            
            # Assign AI components
            if camera.detect_people:
                processor.object_detector = self.shared_object_detector or ObjectDetector()
            
            if camera.count_people:
                processor.people_counter = PeopleCounter(camera.id)
            
            if camera.recognize_faces:
                processor.face_recognizer = self.shared_face_recognizer or FaceRecognizer()
            
            if camera.template_matching:
                processor.template_matcher = TemplateMatcher(camera.id)
            
            # Connect to the camera stream
            if not await processor.connect():
                logger.error(f"Failed to connect to camera {camera.id}: {camera.rtsp_url}")
                return False
            
            # Add to managed cameras
            self.cameras[camera.id] = processor
            
            # Start capture and processing
            await processor.start_capture()
            
            if start_processing:
                await processor.start_processing()
            
            logger.info(f"Added camera {camera.id}: {camera.name} to manager")
            return True
            
        except Exception as e:
            logger.exception(f"Error adding camera {camera.id}: {str(e)}")
            return False
    
    async def remove_camera(self, camera_id: int) -> bool:
        """
        Remove a camera from the manager
        
        Args:
            camera_id: ID of the camera to remove
            
        Returns:
            Success flag
        """
        try:
            if camera_id in self.cameras:
                processor = self.cameras[camera_id]
                
                # Stop processing and disconnect
                await processor.stop_processing()
                await processor.stop_capture()
                await processor.disconnect()
                
                # Remove from managed cameras
                del self.cameras[camera_id]
                
                logger.info(f"Removed camera {camera_id} from manager")
            return True
        except Exception as e:
            logger.exception(f"Error removing camera {camera_id}: {str(e)}")
            return False
    
    async def update_camera(self, camera: Camera) -> bool:
        """
        Update camera settings
        
        Args:
            camera: Updated camera configuration
            
        Returns:
            Success flag
        """
        try:
            # Check if the camera exists
            if camera.id not in self.cameras:
                logger.warning(f"Camera {camera.id} not found, adding instead of updating")
                return await self.add_camera(camera)
            
            processor = self.cameras[camera.id]
            
            # Check if URL changed, requiring reconnection
            if processor.rtsp_url != camera.rtsp_url:
                await self.remove_camera(camera.id)
                return await self.add_camera(camera)
            
            # Update settings
            await processor.set_property("name", camera.name)
            await processor.set_property("processing_fps", camera.processing_fps)
            await processor.set_property("streaming_fps", camera.streaming_fps)
            
            # Update feature flags
            await processor.set_property("detect_people", camera.detect_people)
            await processor.set_property("count_people", camera.count_people) 
            await processor.set_property("recognize_faces", camera.recognize_faces)
            await processor.set_property("template_matching", camera.template_matching)
            
            # Update AI components
            if camera.detect_people and not processor.object_detector:
                processor.object_detector = self.shared_object_detector or ObjectDetector()
            
            if camera.count_people and not processor.people_counter:
                processor.people_counter = PeopleCounter(camera.id)
            
            if camera.recognize_faces and not processor.face_recognizer:
                processor.face_recognizer = self.shared_face_recognizer or FaceRecognizer()
            
            if camera.template_matching and not processor.template_matcher:
                processor.template_matcher = TemplateMatcher(camera.id)
            
            logger.info(f"Updated camera {camera.id}: {camera.name}")
            return True
            
        except Exception as e:
            logger.exception(f"Error updating camera {camera.id}: {str(e)}")
            return False
    
    async def get_jpeg_frame(self, camera_id: int) -> Optional[bytes]:
        """
        Get the latest frame from a camera as JPEG bytes
        
        Args:
            camera_id: ID of the camera
            
        Returns:
            JPEG encoded frame or None if not available
        """
        try:
            if camera_id not in self.cameras:
                return None
            
            return await self.cameras[camera_id].get_latest_frame_jpeg()
            
        except Exception as e:
            logger.exception(f"Error getting JPEG frame for camera {camera_id}: {str(e)}")
            return None
    
    async def ensure_camera_connected(self, camera_id: int) -> bool:
        """
        Ensure a camera is connected and processing
        
        Args:
            camera_id: ID of the camera
            
        Returns:
            Connection status
        """
        if camera_id not in self.cameras:
            return False
        
        processor = self.cameras[camera_id]
        if not processor.connected:
            return await processor.connect()
        
        return True
    
    async def set_camera_property(self, camera_id: int, property_name: str, value: Any) -> bool:
        """
        Set a camera processor property
        
        Args:
            camera_id: ID of the camera
            property_name: Name of the property to set
            value: New property value
            
        Returns:
            Success flag
        """
        try:
            if camera_id not in self.cameras:
                return False
            
            return await self.cameras[camera_id].set_property(property_name, value)
            
        except Exception as e:
            logger.exception(f"Error setting camera property: {str(e)}")
            return False
    
    async def apply_global_setting(self, setting_key: str, value: Any) -> bool:
        """
        Apply a global setting to all cameras
        
        Args:
            setting_key: Setting key
            value: Setting value
            
        Returns:
            Success flag
        """
        try:
            success = True
            
            # Apply to each camera based on setting type
            for camera_id, processor in self.cameras.items():
                if setting_key == "global_processing_fps":
                    if not await processor.set_property("processing_fps", value):
                        success = False
                
                elif setting_key == "detection_threshold" and processor.object_detector:
                    processor.object_detector.set_threshold(value)
                
                elif setting_key == "face_recognition_threshold" and processor.face_recognizer:
                    processor.face_recognizer.set_threshold(value)
                
                elif setting_key == "template_matching_threshold" and processor.template_matcher:
                    processor.template_matcher.set_threshold(value)
            
            return success
            
        except Exception as e:
            logger.exception(f"Error applying global setting {setting_key}: {str(e)}")
            return False
    
    def get_camera_stats(self, camera_id: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
        """
        Get statistics for one or all cameras
        
        Args:
            camera_id: Optional camera ID, if None returns stats for all cameras
            
        Returns:
            Dictionary of camera stats
        """
        stats = {}
        
        if camera_id is not None:
            if camera_id in self.cameras:
                stats[camera_id] = self.cameras[camera_id].get_stats()
        else:
            for camera_id, processor in self.cameras.items():
                stats[camera_id] = processor.get_stats()
        
        return stats
    
    async def shutdown(self):
        """Shutdown all cameras and release resources"""
        try:
            # Stop and disconnect all cameras
            for camera_id in list(self.cameras.keys()):
                await self.remove_camera(camera_id)
            
            # Release shared resources
            self.shared_object_detector = None
            self.shared_face_recognizer = None
            
            # Shutdown thread pool
            self.executor.shutdown(wait=True)
            
            self.status = "shutdown"
            logger.info("Camera manager shutdown complete")
            
        except Exception as e:
            logger.exception(f"Error during camera manager shutdown: {str(e)}")

# Singleton instance
_camera_manager = None

async def get_camera_manager() -> CameraManager:
    """Get the global camera manager instance"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
        await _camera_manager.initialize()
    return _camera_manager