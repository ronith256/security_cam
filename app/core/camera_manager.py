# app/core/camera_manager.py

import asyncio
from datetime import datetime
import cv2
import logging
import time
import numpy as np
import gc
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
        
        # Memory usage limits
        self.max_cameras = 10  # Max cameras to process simultaneously
        self.active_cameras = 0  # Number of currently active cameras
        
        # Cache for JPEG frames to reduce CPU usage
        self.frame_cache = {}  # {camera_id: {"frame": jpeg_bytes, "timestamp": time}}
        self.cache_expiry = 1.0  # Cache frames for 1 second
        
        # Set the OpenCV thread count
        cv2.setNumThreads(4)  # Limit OpenCV to 4 threads
    
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
                    
                    # Count active cameras
                    self.active_cameras = sum(1 for processor in self.cameras.values() if processor.processing)
                    logger.info(f"Currently processing {self.active_cameras} cameras")
                    
                    # Sort cameras by priority (those in use first)
                    priority_cameras = []
                    regular_cameras = []
                    
                    for camera in enabled_cameras:
                        if camera.id in self.cameras_in_use:
                            priority_cameras.append(camera)
                        else:
                            regular_cameras.append(camera)
                    
                    # Process priority cameras first, then regular cameras up to the limit
                    all_cameras = priority_cameras + regular_cameras
                    
                    # Check if we need to remove some cameras due to resource limits
                    if len(all_cameras) > self.max_cameras:
                        logger.warning(f"Too many cameras enabled ({len(all_cameras)}), limiting to {self.max_cameras}")
                        # Keep only priority cameras and up to max_cameras total
                        cameras_to_keep = set(camera.id for camera in all_cameras[:self.max_cameras])
                        
                        # Identify cameras to remove
                        for camera_id in list(self.cameras.keys()):
                            if camera_id not in cameras_to_keep and camera_id not in self.cameras_in_use:
                                await self.remove_camera(camera_id)
                    
                    # Ensure all priority cameras are added and processed
                    for camera in priority_cameras:
                        if camera.id not in self.cameras:
                            await self.add_camera(camera, start_processing=True)
                        elif self.cameras[camera.id].should_process and not self.cameras[camera.id].processing:
                            processor = self.cameras[camera.id]
                            if not processor.connected:
                                await processor.connect()
                            if not processor.processing:
                                asyncio.create_task(processor.process_stream())
                    
                    # Add regular cameras up to the limit
                    remaining_slots = self.max_cameras - self.active_cameras
                    for camera in regular_cameras[:remaining_slots]:
                        if camera.id not in self.cameras:
                            await self.add_camera(camera, start_processing=True)
                        elif self.cameras[camera.id].should_process and not self.cameras[camera.id].processing:
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
                
                # Clean expired entries from frame cache
                self._clean_frame_cache()
                
                # Run garbage collection periodically
                gc.collect()
            
            except Exception as e:
                logger.exception(f"Error in background monitor task: {str(e)}")
            
            # Check every 60 seconds
            await asyncio.sleep(60)
    
    def _clean_frame_cache(self):
        """Remove expired entries from the frame cache"""
        now = time.time()
        expired_keys = []
        
        for camera_id, cache_entry in self.frame_cache.items():
            if now - cache_entry["timestamp"] > self.cache_expiry:
                expired_keys.append(camera_id)
        
        for key in expired_keys:
            del self.frame_cache[key]
    
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
                # Start as a background task
                asyncio.create_task(processor.process_stream())
                logger.info(f"Started processing for camera {camera_id}")
            return True
        else:
            return False

    # Next, fix the ensure_camera_connected method to make sure processing starts:
    async def ensure_camera_connected(self, camera_id: int) -> bool:
        """Ensure a camera is connected if it's needed"""
        if camera_id not in self.cameras:
            # Try to load the camera from the database
            async for session in get_db():
                camera = await session.get(Camera, camera_id)
                if camera and camera.enabled:
                    return await self.add_camera(camera, start_processing=True)  # Start processing by default
                return False
        
        # Mark this camera as in use
        self.cameras_in_use.add(camera_id)
        
        processor = self.cameras[camera_id]
        
        # If already connected, we're good
        if processor.connected and processor.processing:
            return True
                
        # Create a task for connection to avoid multiple concurrent connections
        if camera_id in self._connection_tasks and not self._connection_tasks[camera_id].done():
            try:
                return await self._connection_tasks[camera_id]
            except Exception:
                # If the task failed, we'll try again
                pass
        
        # Start processing if not already processing
        if processor.connected and not processor.processing and processor.should_process:
            asyncio.create_task(processor.process_stream())
            logger.info(f"Started processing for previously connected camera {camera_id}")
            return True
        
        # Connect camera if not connected
        self._connection_tasks[camera_id] = asyncio.create_task(self._connect_camera(camera_id, start_processing=True))
        
        try:
            return await self._connection_tasks[camera_id]
        except Exception as e:
            logger.exception(f"Error ensuring camera {camera_id} is connected: {str(e)}")
            return False

    # Modify the add_camera method to properly handle start_processing:
    async def add_camera(self, camera: Camera, start_processing: bool = False) -> bool:
        """Add a new camera - connect and start processing if requested"""
        if not camera.enabled:
            logger.warning(f"Attempted to add disabled camera {camera.id}")
            return False
            
        async with self.lock:
            camera_id = camera.id
            
            # Check resource limits
            if camera_id not in self.cameras and self.active_cameras >= self.max_cameras:
                logger.warning(f"Cannot add camera {camera_id}: resource limit reached ({self.active_cameras}/{self.max_cameras})")
                # Only add if this camera is actively being viewed
                if camera_id not in self.cameras_in_use:
                    return False
            
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
                    logger.info(f"Starting processing for existing camera {camera_id}")
                    if not processor.connected:
                        await processor.connect()
                    asyncio.create_task(processor.process_stream())
                    self.active_cameras += 1
                
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
                        if processor.processing:
                            self.active_cameras += 1
                    else:
                        logger.error(f"Failed to connect to camera {camera_id} ({camera.name})")
                    return success
                except Exception as e:
                    logger.exception(f"Error connecting to camera {camera_id}: {str(e)}")
                    return False
            else:
                logger.info(f"Added camera {camera_id} ({camera.name}) - will connect on demand")
                return True
    
    async def release_camera(self, camera_id: int):
        """Mark a camera as no longer in use - may stop streaming but continue processing"""
        if camera_id in self.cameras_in_use:
            self.cameras_in_use.remove(camera_id)
            
            # If this camera is not actively viewed by anyone, we can stop processing
            # to save resources if we're at the resource limit
            if self.active_cameras >= self.max_cameras and camera_id in self.cameras:
                processor = self.cameras[camera_id]
                if processor.processing:
                    processor.processing = False
                    self.active_cameras -= 1
    
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
                    # Check if camera was active before disconnecting
                    was_active = self.cameras[camera_id].processing
                    
                    await self.cameras[camera_id].disconnect()
                    del self.cameras[camera_id]
                    
                    # Remove from in-use set if present
                    if camera_id in self.cameras_in_use:
                        self.cameras_in_use.remove(camera_id)
                    
                    # Update active camera count
                    if was_active:
                        self.active_cameras -= 1
                    
                    # Remove from frame cache
                    if camera_id in self.frame_cache:
                        del self.frame_cache[camera_id]
                    
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
            logger.warning(f"Failed to connect to camera {camera_id} in get_frame")
            return None
            
        if camera_id in self.cameras:
            frame_data = self.cameras[camera_id].get_latest_frame()
            
            if frame_data is None and camera_id in self.cameras_in_use:
                # If camera is in use but no frame is available, log this issue
                logger.warning(f"No frame data available for camera {camera_id} despite being in use")
                
                # Try to check if processor is truly processing
                processor = self.cameras[camera_id]
                if not processor.processing and processor.should_process:
                    logger.info(f"Starting processing for camera {camera_id} since it was supposed to be processing")
                    asyncio.create_task(processor.process_stream())
            
            return frame_data
        return None
    
    def _create_no_signal_frame(self, camera_id: int) -> bytes:
        """Create a 'No Signal' frame when no actual frame is available"""
        try:
            # Create a blank image
            width, height = 640, 360
            img = np.zeros((height, width, 3), np.uint8)
            
            # Add camera ID and timestamp
            font = cv2.FONT_HERSHEY_SIMPLEX
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Add "No Signal" text
            text = f"Camera {camera_id} - No Signal"
            text_size = cv2.getTextSize(text, font, 1, 2)[0]
            text_x = (width - text_size[0]) // 2
            text_y = (height + text_size[1]) // 2
            cv2.putText(img, text, (text_x, text_y), font, 1, (255, 255, 255), 2)
            
            # Add timestamp
            cv2.putText(img, timestamp, (10, height - 10), font, 0.5, (150, 150, 150), 1)
            
            # Convert to JPEG
            _, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return jpeg.tobytes()
        except Exception as e:
            logger.exception(f"Error creating no signal frame: {str(e)}")
            return None
        
    def _create_error_frame(self, camera_id: int, error_message: str) -> bytes:
        """Create an 'Error' frame when an exception occurs"""
        try:
            # Create a blank image with red tint to indicate error
            width, height = 640, 360
            img = np.zeros((height, width, 3), np.uint8)
            img[:, :, 2] = 40  # Add some red to the background
            
            # Add error header
            font = cv2.FONT_HERSHEY_SIMPLEX
            header = f"Camera {camera_id} - Error"
            header_size = cv2.getTextSize(header, font, 1, 2)[0]
            header_x = (width - header_size[0]) // 2
            header_y = height // 3
            cv2.putText(img, header, (header_x, header_y), font, 1, (50, 50, 255), 2)
            
            # Add error message (truncate if too long)
            max_chars = 50  # Maximum characters per line
            if len(error_message) > max_chars:
                error_message = error_message[:max_chars-3] + "..."
                
            message_size = cv2.getTextSize(error_message, font, 0.5, 1)[0]
            message_x = (width - message_size[0]) // 2
            message_y = height // 2
            cv2.putText(img, error_message, (message_x, message_y), font, 0.5, (200, 200, 255), 1)
            
            # Add timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(img, timestamp, (10, height - 10), font, 0.5, (150, 150, 150), 1)
            
            # Convert to JPEG
            _, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return jpeg.tobytes()
        except Exception as e:
            logger.exception(f"Error creating error frame: {str(e)}")
            return None

    async def get_jpeg_frame(self, camera_id: int, high_quality: bool = False) -> Optional[bytes]:
        """Get the latest frame as JPEG bytes, with optional high quality"""
        # Check cache first for low quality requests
        if not high_quality and camera_id in self.frame_cache:
            cache_entry = self.frame_cache[camera_id]
            # If cache is still valid, return it
            if time.time() - cache_entry["timestamp"] <= self.cache_expiry:
                logger.debug(f"Returning cached JPEG frame for camera {camera_id}")
                return cache_entry["frame"]
        
        # Ensure camera is connected and processing
        connected = await self.ensure_camera_connected(camera_id)
        if not connected:
            logger.error(f"Failed to connect to camera {camera_id} in get_jpeg_frame")
            # Create a blank frame with "No signal" text as fallback
            fallback_frame = self._create_no_signal_frame(camera_id)
            if fallback_frame is not None:
                return fallback_frame
            return None
        
        try:
            frame_data = await self.get_frame(camera_id)
            if frame_data:
                frame, timestamp = frame_data
                logger.debug(f"Got frame from camera {camera_id}, timestamp: {timestamp}")
                
                # Set JPEG quality
                encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95 if high_quality else 80]
                
                _, jpeg = cv2.imencode(".jpg", frame, encode_params)
                jpeg_bytes = jpeg.tobytes()
                
                # Cache the result for low quality requests
                if not high_quality:
                    self.frame_cache[camera_id] = {
                        "frame": jpeg_bytes,
                        "timestamp": time.time()
                    }
                
                return jpeg_bytes
            else:
                logger.warning(f"No frame data available for camera {camera_id}")
                # Create a blank frame with "No signal" text as fallback
                fallback_frame = self._create_no_signal_frame(camera_id)
                return fallback_frame
        except Exception as e:
            logger.exception(f"Error getting JPEG frame for camera {camera_id}: {str(e)}")
            # Create a blank frame with "Error" text as fallback
            error_frame = self._create_error_frame(camera_id, str(e))
            return error_frame
    
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
            self.frame_cache.clear()
            
            # Force garbage collection
            gc.collect()
            
            logger.info("Camera Manager shutdown completed")

# Singleton instance
_camera_manager = None

async def get_camera_manager() -> CameraManager:
    """Get or create the camera manager singleton"""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager