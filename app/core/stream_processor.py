import cv2
import numpy as np
import os
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime
import uuid
from sqlalchemy import select, insert
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.utils.frame_utils import (
    draw_bounding_boxes, draw_line, draw_text_overlay,
    overlay_timestamp, save_frame
)
from app.utils.event_emitter import EventEmitter

logger = logging.getLogger(__name__)

class StreamProcessor:
    """
    Processes RTSP camera streams with AI components for detection, 
    recognition, and counting.
    """
    def __init__(
        self, 
        camera_id: int, 
        name: str,
        rtsp_url: str,
        processing_fps: int = 5,
        streaming_fps: int = 30,
        detect_people: bool = True,
        count_people: bool = True,
        recognize_faces: bool = False,
        template_matching: bool = False
    ):
        self.camera_id = camera_id
        self.name = name
        self.rtsp_url = rtsp_url
        self.processing_fps = processing_fps
        self.streaming_fps = streaming_fps
        
        # Feature flags
        self.detect_people = detect_people
        self.count_people = count_people
        self.recognize_faces = recognize_faces
        self.template_matching = template_matching
        
        # AI components
        self.object_detector = None
        self.face_recognizer = None
        self.template_matcher = None
        self.people_counter = None
        
        # Video settings
        self.record_video = False
        self.video_writer = None
        
        # UI settings
        self.draw_detections = True
        self.draw_count_line = True
        self.draw_timestamps = True
        
        # Frame buffers
        self.raw_frames = []  # List of (frame, timestamp) tuples
        self.processed_frames = []  # List of (frame, timestamp) tuples
        self.max_buffer_size = 30
        self._frame_lock = asyncio.Lock()
        
        # State variables
        self.connected = False
        self.running = False
        self.processing = False
        self.paused = False
        
        # Performance metrics
        self.fps = 0
        self.frames_captured = 0
        self.frames_processed = 0
        self.processing_fps_actual = 0
        self.last_frame_time = 0
        self.last_processed_time = 0
        self.processing_start_time = 0
        
        # OpenCV capture object
        self.capture = None
        
        # Latest detection results
        self.detection_results = {}
        self.current_occupancy = 0
        
        # Event emitter for notifications
        self.events = EventEmitter()
        
        # Notification settings
        self.check_notification_triggers = True  # Enable notification checking
    
    async def connect(self) -> bool:
        """
        Connect to the RTSP stream
        
        Returns:
            Success flag
        """
        try:
            # Disconnect first if already connected
            if self.connected:
                await self.disconnect()
            
            # Create OpenCV capture
            self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            # Check if connection was successful
            if not self.capture.isOpened():
                logger.error(f"Failed to open RTSP stream: {self.rtsp_url}")
                return False
            
            # Get video properties
            width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            
            # Use default FPS if not detected
            if fps <= 0:
                fps = 30.0
            
            logger.info(f"Connected to camera {self.camera_id}: {width}x{height} at {fps}fps")
            
            # Setup video recording if enabled
            if self.record_video:
                await self._setup_video_writer(width, height, fps)
            
            # Update state
            self.connected = True
            self.running = True
            
            # Emit event
            self.events.emit("connected", {
                "camera_id": self.camera_id,
                "width": width,
                "height": height,
                "fps": fps
            })
            
            return True
        
        except Exception as e:
            logger.exception(f"Error connecting to camera {self.camera_id}: {str(e)}")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """Disconnect from the RTSP stream and clean up resources"""
        try:
            # Update state flags
            self.running = False
            self.connected = False
            self.processing = False
            
            # Clean up capture
            if self.capture:
                self.capture.release()
                self.capture = None
            
            # Clean up video writer
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            
            # Clear buffers
            async with self._frame_lock:
                self.raw_frames = []
                self.processed_frames = []
            
            # Emit event
            self.events.emit("disconnected", {
                "camera_id": self.camera_id
            })
            
            logger.info(f"Disconnected from camera {self.camera_id}")
        
        except Exception as e:
            logger.exception(f"Error disconnecting camera {self.camera_id}: {str(e)}")
    
    async def start_capture(self):
        """Start capturing frames from the RTSP stream"""
        if not self.connected or self.running:
            return
        
        self.running = True
        asyncio.create_task(self._capture_frames())
        logger.info(f"Started frame capture for camera {self.camera_id}")
    
    async def stop_capture(self):
        """Stop capturing frames from the RTSP stream"""
        self.running = False
        logger.info(f"Stopped frame capture for camera {self.camera_id}")
    
    async def start_processing(self):
        """Start processing captured frames"""
        if self.processing or not self.connected:
            return
        
        self.processing = True
        self.processing_start_time = time.time()
        self.frames_processed = 0
        
        asyncio.create_task(self._process_frames())
        logger.info(f"Started frame processing for camera {self.camera_id}")
    
    async def stop_processing(self):
        """Stop processing captured frames"""
        self.processing = False
        logger.info(f"Stopped frame processing for camera {self.camera_id}")
    
    async def _capture_frames(self):
        """Continuously capture frames from the RTSP stream for AI processing"""
        # Only capture at the rate needed for processing, not streaming
        frame_interval = 1.0 / self.processing_fps
        last_capture_time = 0
        frames_count = 0
        start_time = time.time()
        
        while self.running and self.connected:
            try:
                current_time = time.time()
                
                # Throttle frame capture to desired FPS
                if current_time - last_capture_time < frame_interval:
                    await asyncio.sleep(0.001)  # Small sleep to prevent CPU hogging
                    continue
                
                # Check connection status periodically
                if frames_count % 30 == 0:
                    if not self.capture.isOpened():
                        logger.warning(f"Camera {self.camera_id} connection lost, attempting to reconnect")
                        await asyncio.sleep(1)
                        # Attempt to reconnect
                        if not await self.connect():
                            await asyncio.sleep(5)  # Wait before retrying
                            continue
                
                # Capture frame
                ret, frame = self.capture.read()
                if not ret:
                    logger.warning(f"Failed to read frame from camera {self.camera_id}")
                    await asyncio.sleep(0.1)  # Short wait before retry
                    continue
                
                # Add frame to buffer
                async with self._frame_lock:
                    timestamp = current_time
                    self.raw_frames.append((frame.copy(), timestamp))
                    
                    # Maintain buffer size
                    while len(self.raw_frames) > self.max_buffer_size:
                        self.raw_frames.pop(0)
                
                # Update frame time
                self.last_frame_time = current_time
                last_capture_time = current_time
                frames_count += 1
                self.frames_captured += 1
                
                # Calculate FPS every second
                if current_time - start_time >= 1.0:
                    self.fps = frames_count / (current_time - start_time)
                    frames_count = 0
                    start_time = current_time
                
                # Record frame if enabled
                if self.record_video and self.video_writer:
                    self.video_writer.write(frame)
                
            except Exception as e:
                logger.exception(f"Error capturing frame from camera {self.camera_id}: {str(e)}")
                await asyncio.sleep(0.1)
    
    async def _process_frames(self):
        """Process frames through the AI pipelines"""
        process_interval = 1.0 / self.processing_fps
        last_process_time = 0
        frames_processed_count = 0
        start_time = time.time()
        
        while self.processing and self.connected:
            try:
                current_time = time.time()
                
                # Skip if processing is paused
                if self.paused:
                    await asyncio.sleep(0.1)
                    continue
                
                # Throttle processing to desired FPS
                if current_time - last_process_time < process_interval:
                    await asyncio.sleep(0.001)
                    continue
                
                # Get latest frame from buffer
                frame_data = await self._get_latest_frame()
                if not frame_data:
                    await asyncio.sleep(0.01)
                    continue
                
                frame, timestamp = frame_data
                
                # Process frame through AI pipeline
                processed_frame, results = await self._process_frame_pipeline(frame)
                
                # Update processed frame buffer
                async with self._frame_lock:
                    self.processed_frames.append((processed_frame, current_time))
                    
                    # Maintain buffer size
                    while len(self.processed_frames) > self.max_buffer_size:
                        self.processed_frames.pop(0)
                
                # Update detection results
                self.detection_results = results
                if "occupancy" in results and "current" in results["occupancy"]:
                    self.current_occupancy = results["occupancy"]["current"]
                
                # Update stats
                self.last_processed_time = current_time
                last_process_time = current_time
                frames_processed_count += 1
                self.frames_processed += 1
                
                # Calculate processing FPS every second
                if current_time - start_time >= 1.0:
                    self.processing_fps_actual = frames_processed_count / (current_time - start_time)
                    frames_processed_count = 0
                    start_time = current_time
                
                # Emit event with results summary
                if frames_processed_count % 5 == 0:  # Only emit every 5 frames to reduce overhead
                    self.events.emit("frame_processed", {
                        "camera_id": self.camera_id,
                        "timestamp": timestamp,
                        "people_count": len(results.get("people", [])),
                        "faces_count": len(results.get("faces", [])),
                        "templates_count": len(results.get("templates", [])),
                        "occupancy": results.get("occupancy", {})
                    })
                
            except Exception as e:
                logger.exception(f"Error processing frame for camera {self.camera_id}: {str(e)}")
                await asyncio.sleep(0.1)
    
    async def _process_frame_pipeline(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Process a frame through all enabled AI components and check for triggers"""
        results = {}
        processed_frame = frame.copy()
        
        try:
            # Run object detection first if enabled
            if self.detect_people and self.object_detector:
                # Detect people
                people = await self.object_detector.detect_people(frame)
                results["people"] = people
                
                # Draw bounding boxes if enabled
                if self.draw_detections:
                    processed_frame = draw_bounding_boxes(
                        processed_frame, people, color=(0, 255, 0), label_key="class_name"
                    )
                
                # Update people counter
                if self.count_people and self.people_counter and people:
                    entry_count, exit_count, current_count = await self.people_counter.process_frame(
                        frame, people
                    )
                    results["occupancy"] = {
                        "entries": entry_count,
                        "exits": exit_count,
                        "current": current_count
                    }
                    
                    # Draw counting line if enabled
                    if self.draw_count_line:
                        line_pos = self.people_counter.line_position
                        processed_frame = draw_line(
                            processed_frame, line_pos, color=(0, 0, 255)
                        )
                        
                        # Draw occupancy info
                        h, w = processed_frame.shape[:2]
                        cv2.putText(
                            processed_frame,
                            f"Current: {current_count} | In: {entry_count} | Out: {exit_count}",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 255),
                            2
                        )
            
            # Face recognition
            if self.recognize_faces and self.face_recognizer:
                faces = await self.face_recognizer.recognize_faces(frame, self.camera_id)
                results["faces"] = faces
                
                # Draw face bounding boxes
                if self.draw_detections and faces:
                    processed_frame = draw_bounding_boxes(
                        processed_frame, faces, color=(255, 0, 0), label_key="person_name"
                    )
            
            # Template matching
            if self.template_matching and self.template_matcher:
                templates = await self.template_matcher.match_templates(frame)
                results["templates"] = templates
                
                # Draw template matches
                if self.draw_detections and templates:
                    processed_frame = draw_bounding_boxes(
                        processed_frame, templates, color=(0, 255, 255), label_key="template_name"
                    )
            
            # Add timestamp if enabled
            if self.draw_timestamps:
                processed_frame = overlay_timestamp(processed_frame)
            
            # Check notification triggers for the results
            # This needs to be done in a non-blocking way to avoid slowing down the pipeline
            if self.check_notification_triggers:
                try:
                    # Import here to avoid circular imports
                    from app.services.notification_service import get_notification_service
                    
                    # Get notification service
                    notification_service = await get_notification_service()
                    
                    # Check triggers in a background task - passing the frame for snapshots
                    asyncio.create_task(notification_service.check_all_triggers(
                        self.camera_id, results, frame.copy()
                    ))
                except Exception as e:
                    logger.exception(f"Error checking notification triggers: {str(e)}")
            
            return processed_frame, results
            
        except Exception as e:
            logger.exception(f"Error in processing pipeline for camera {self.camera_id}: {str(e)}")
            return frame, {}
    
    async def _get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest frame from the raw frame buffer"""
        async with self._frame_lock:
            if not self.raw_frames:
                return None
            return self.raw_frames[-1]
    
    async def get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest processed frame or raw frame if processing is disabled"""
        async with self._frame_lock:
            if self.processed_frames:
                return self.processed_frames[-1]
            elif self.raw_frames:
                return self.raw_frames[-1]
        return None
    
    async def get_latest_frame_jpeg(self, quality: int = 90) -> Optional[bytes]:
        """
        Get the latest frame as JPEG bytes
        
        Note: This is only used for snapshot functionality and debugging,
        not for streaming to frontend.
        """
        frame_data = await self.get_latest_frame()
        if not frame_data:
            return None
        
        frame, _ = frame_data
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)
        return jpeg_data.tobytes()
    
    def get_detection_results(self) -> Dict[str, Any]:
        """Get the latest detection results"""
        return self.detection_results
    
    def get_current_occupancy(self) -> int:
        """Get the current room occupancy count"""
        return self.current_occupancy
    
    async def set_property(self, property_name: str, value: Any) -> bool:
        """Set a property of the stream processor"""
        try:
            if hasattr(self, property_name):
                setattr(self, property_name, value)
                logger.info(f"Set property {property_name}={value} for camera {self.camera_id}")
                return True
            return False
        except Exception as e:
            logger.exception(f"Error setting property {property_name}: {str(e)}")
            return False
    
    async def _setup_video_writer(self, width: int, height: int, fps: float):
        """Setup video writer for recording"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"camera_{self.camera_id}_{timestamp}.mp4"
            filepath = f"{settings.RECORDINGS_DIR}/{filename}"
            
            # Create video writer with H.264 codec
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
            self.video_writer = cv2.VideoWriter(
                filepath, fourcc, fps, (width, height)
            )
            
            logger.info(f"Video recording started for camera {self.camera_id}: {filepath}")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to setup video writer: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            "camera_id": self.camera_id,
            "connected": self.connected,
            "processing": self.processing,
            "processing_fps": self.processing_fps_actual,
            "frames_captured": self.frames_captured,
            "frames_processed": self.frames_processed,
            "last_frame_time": self.last_frame_time,
            "last_processed_time": self.last_processed_time,
            "features": {
                "detect_people": self.detect_people,
                "count_people": self.count_people,
                "recognize_faces": self.recognize_faces,
                "template_matching": self.template_matching,
                "record_video": self.record_video,
                "notification_triggers": self.check_notification_triggers
            }
        }
    
    def subscribe(self, event_name: str, callback: Callable):
        """Subscribe to an event"""
        self.events.on(event_name, callback)
    
    def unsubscribe(self, event_name: str, callback: Callable):
        """Unsubscribe from an event"""
        self.events.off(event_name, callback)