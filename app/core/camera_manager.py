import cv2
import numpy as np
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from app.models.camera import Camera
from app.core.object_detection import ObjectDetector
from app.core.face_recognition import FaceRecognizer
from app.core.template_matching import TemplateMatcher
from app.core.people_counter import PeopleCounter
from app.config import settings

logger = logging.getLogger(__name__)

class CameraProcessor:
    """Handles processing for a single camera stream"""
    def __init__(
        self, 
        camera: Camera,
        processing_fps: int = 5,
        streaming_fps: int = 30
    ):
        self.camera = camera
        self.camera_id = camera.id
        self.rtsp_url = camera.rtsp_url
        self.processing_fps = processing_fps
        self.streaming_fps = streaming_fps
        
        # Feature flags
        self.detect_people = camera.detect_people
        self.count_people = camera.count_people
        self.recognize_faces = camera.recognize_faces
        self.template_matching = camera.template_matching
        
        # State variables
        self.connected = False
        self.processing = False
        self.capture = None
        self.last_frame = None
        self.last_frame_time = 0
        self.last_processed_time = 0
        self.fps = 0
        
        # Processing components
        self.object_detector = ObjectDetector() if self.detect_people else None
        self.face_recognizer = FaceRecognizer() if self.recognize_faces else None
        self.template_matcher = TemplateMatcher(camera.id) if self.template_matching else None
        self.people_counter = PeopleCounter(camera.id) if self.count_people else None
        
        # Frame buffers
        self.raw_frame_buffer = []
        self.processed_frame_buffer = []
        self.max_buffer_size = 30  # ~1 second at 30fps
        
        # Processing results
        self.detection_results = {}
        self.current_occupancy = 0
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    async def connect(self) -> bool:
        """Connect to the camera stream"""
        try:
            # Initialize video capture
            self.capture = cv2.VideoCapture(self.rtsp_url)
            if not self.capture.isOpened():
                logger.error(f"Failed to open camera {self.camera_id}")
                return False
            
            self.connected = True
            logger.info(f"Connected to camera {self.camera_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error connecting to camera {self.camera_id}: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from the camera stream"""
        try:
            self.connected = False
            self.processing = False
            
            if self.capture:
                self.capture.release()
            
            logger.info(f"Disconnected from camera {self.camera_id}")
            
        except Exception as e:
            logger.exception(f"Error disconnecting camera {self.camera_id}: {str(e)}")
    
    async def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Process a single frame with enabled AI components"""
        try:
            detection_results = {}
            processed_frame = frame.copy()
            
            # Detect people
            if self.detect_people and self.object_detector:
                people = await self.object_detector.detect_people(frame)
                detection_results['people'] = people
                
                # Update people counter if enabled
                if self.count_people and self.people_counter:
                    entry_count, exit_count, current_count = await self.people_counter.process_frame(
                        frame, people
                    )
                    detection_results['occupancy'] = {
                        'entries': entry_count,
                        'exits': exit_count,
                        'current': current_count
                    }
                    self.current_occupancy = current_count
            
            # Detect and recognize faces
            if self.recognize_faces and self.face_recognizer:
                faces = await self.face_recognizer.recognize_faces(frame, self.camera_id)
                detection_results['faces'] = faces
            
            # Match templates
            if self.template_matching and self.template_matcher:
                templates = await self.template_matcher.match_templates(frame)
                detection_results['templates'] = templates
            
            return processed_frame, detection_results
            
        except Exception as e:
            logger.exception(f"Error processing frame for camera {self.camera_id}: {str(e)}")
            return frame, {}
    
    async def capture_frames(self):
        """Continuously capture frames from the camera"""
        frame_interval = 1.0 / self.streaming_fps
        last_capture_time = 0
        
        while self.connected:
            try:
                current_time = time.time()
                
                # Throttle frame capture to desired FPS
                if current_time - last_capture_time < frame_interval:
                    await asyncio.sleep(0.001)  # Small sleep to prevent CPU hogging
                    continue
                
                # Capture frame
                ret, frame = self.capture.read()
                if not ret:
                    logger.warning(f"Failed to read frame from camera {self.camera_id}")
                    await asyncio.sleep(1)  # Wait before retrying
                    continue
                
                # Update frame buffer
                with self.lock:
                    self.raw_frame_buffer.append((frame, current_time))
                    while len(self.raw_frame_buffer) > self.max_buffer_size:
                        self.raw_frame_buffer.pop(0)
                
                last_capture_time = current_time
                
            except Exception as e:
                logger.exception(f"Error capturing frame from camera {self.camera_id}: {str(e)}")
                await asyncio.sleep(1)
    
    async def process_frames(self):
        """Continuously process captured frames"""
        self.processing = True
        process_interval = 1.0 / self.processing_fps
        frames_processed = 0
        start_time = time.time()
        
        while self.processing and self.connected:
            try:
                current_time = time.time()
                
                # Check if it's time to process the next frame
                if current_time - self.last_processed_time < process_interval:
                    await asyncio.sleep(0.001)
                    continue
                
                # Get latest frame from buffer
                frame_data = None
                with self.lock:
                    if self.raw_frame_buffer:
                        frame_data = self.raw_frame_buffer[-1]
                
                if frame_data is None:
                    await asyncio.sleep(0.01)
                    continue
                
                frame, timestamp = frame_data
                
                # Process frame
                processed_frame, results = await self.process_frame(frame)
                
                # Update processed frame buffer and results
                with self.lock:
                    self.processed_frame_buffer.append((processed_frame, current_time))
                    while len(self.processed_frame_buffer) > self.max_buffer_size:
                        self.processed_frame_buffer.pop(0)
                    
                    self.last_frame = processed_frame
                    self.last_frame_time = current_time
                    self.last_processed_time = current_time
                    self.detection_results = results
                
                # Update FPS calculation
                frames_processed += 1
                elapsed_time = current_time - start_time
                if elapsed_time >= 1.0:
                    self.fps = frames_processed / elapsed_time
                    frames_processed = 0
                    start_time = current_time
                
            except Exception as e:
                logger.exception(f"Error processing frames for camera {self.camera_id}: {str(e)}")
                await asyncio.sleep(1)
    
    def get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest processed frame and its timestamp"""
        with self.lock:
            if self.processed_frame_buffer:
                return self.processed_frame_buffer[-1]
            elif self.raw_frame_buffer:
                return self.raw_frame_buffer[-1]
        return None
    
    def get_detection_results(self) -> Dict[str, Any]:
        """Get the latest detection results"""
        return self.detection_results
    
    def get_current_occupancy(self) -> int:
        """Get the current room occupancy count"""
        return self.current_occupancy

class CameraManager:
    """Manages multiple camera streams and their processing"""
    def __init__(self):
        self.cameras: Dict[int, CameraProcessor] = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.initialized = False
    
    async def initialize(self):
        """Initialize the camera manager"""
        if not self.initialized:
            self.initialized = True
            logger.info("Camera manager initialized")
    
    async def add_camera(self, camera: Camera, start_processing: bool = True) -> bool:
        """Add a new camera to the manager"""
        try:
            # Check if camera already exists
            if camera.id in self.cameras:
                logger.warning(f"Camera {camera.id} already exists in manager")
                return True
            
            # Create camera processor
            processor = CameraProcessor(
                camera=camera,
                processing_fps=camera.processing_fps,
                streaming_fps=camera.streaming_fps
            )
            
            # Connect to camera
            if not await processor.connect():
                logger.error(f"Failed to connect to camera {camera.id}")
                return False
            
            # Add to managed cameras
            self.cameras[camera.id] = processor
            
            # Start capture and processing
            asyncio.create_task(processor.capture_frames())
            if start_processing:
                asyncio.create_task(processor.process_frames())
            
            logger.info(f"Added camera {camera.id} to manager")
            return True
            
        except Exception as e:
            logger.exception(f"Error adding camera {camera.id}: {str(e)}")
            return False
    
    async def remove_camera(self, camera_id: int) -> bool:
        """Remove a camera from the manager"""
        try:
            if camera_id in self.cameras:
                processor = self.cameras[camera_id]
                await processor.disconnect()
                del self.cameras[camera_id]
                logger.info(f"Removed camera {camera_id} from manager")
            return True
        except Exception as e:
            logger.exception(f"Error removing camera {camera_id}: {str(e)}")
            return False
    
    async def update_camera(self, camera: Camera) -> bool:
        """Update camera settings"""
        try:
            # Remove existing camera
            await self.remove_camera(camera.id)
            
            # Add camera with new settings
            return await self.add_camera(camera)
        except Exception as e:
            logger.exception(f"Error updating camera {camera.id}: {str(e)}")
            return False
    
    async def get_jpeg_frame(self, camera_id: int) -> Optional[bytes]:
        """Get the latest frame from a camera as JPEG bytes"""
        try:
            if camera_id not in self.cameras:
                return None
            
            frame_data = self.cameras[camera_id].get_latest_frame()
            if frame_data is None:
                return None
            
            frame, _ = frame_data
            _, jpeg_data = cv2.imencode('.jpg', frame)
            return jpeg_data.tobytes()
            
        except Exception as e:
            logger.exception(f"Error getting JPEG frame for camera {camera_id}: {str(e)}")
            return None
    
    async def ensure_camera_connected(self, camera_id: int) -> bool:
        """Ensure a camera is connected and processing"""
        if camera_id not in self.cameras:
            return False
        
        processor = self.cameras[camera_id]
        if not processor.connected:
            return await processor.connect()
        
        return True
    
    async def set_camera_property(self, camera_id: int, property_name: str, value: Any) -> bool:
        """Set a camera property"""
        try:
            if camera_id not in self.cameras:
                return False
            
            processor = self.cameras[camera_id]
            setattr(processor, property_name, value)
            return True
            
        except Exception as e:
            logger.exception(f"Error setting camera property: {str(e)}")
            return False
    
    async def shutdown(self):
        """Shutdown all cameras and release resources"""
        try:
            for camera_id in list(self.cameras.keys()):
                await self.remove_camera(camera_id)
            
            self.executor.shutdown(wait=True)
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