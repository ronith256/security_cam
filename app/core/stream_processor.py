import cv2
import asyncio
import time
import logging
import numpy as np
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime
from app.config import settings
from app.core.object_detection import ObjectDetector
from app.core.face_recognition import FaceRecognizer
from app.core.people_counter import PeopleCounter
from app.core.template_matching import TemplateMatcher

logger = logging.getLogger(__name__)

class StreamProcessor:
    """
    Processes video streams from RTSP sources and applies AI processing
    """
    def __init__(
        self,
        camera_id: int,
        rtsp_url: str,
        processing_fps: int = 5,
        streaming_fps: int = 30,
        detect_people: bool = True,
        count_people: bool = True,
        recognize_faces: bool = False,
        template_matching: bool = False
    ):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.processing_fps = processing_fps
        self.streaming_fps = streaming_fps
        self.detect_people = detect_people
        self.count_people = count_people
        self.recognize_faces = recognize_faces
        self.template_matching = template_matching
        
        # Video capture object
        self.cap = None
        self.connected = False
        self.processing = False
        
        # Frame buffer
        self.latest_frame = None
        self.latest_processed_frame = None
        self.last_frame_time = 0
        self.last_processed_time = 0
        
        # AI components (will be initialized lazily)
        self.object_detector = None
        self.face_recognizer = None
        self.people_counter = None
        self.template_matcher = None
        
        # Stats
        self.fps = 0
        self.frame_count = 0
        self.last_fps_update = time.time()
        
        # Results
        self.detection_results = {}
        self.current_occupancy = 0
        
        # Locks
        self.frame_lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """Connect to the RTSP stream"""
        try:
            logger.info(f"Attempting to connect to RTSP stream: {self.rtsp_url}")
            
            # OpenCV VideoCapture is blocking, so run in a thread pool
            loop = asyncio.get_event_loop()
            self.cap = await loop.run_in_executor(
                None, lambda: cv2.VideoCapture(self.rtsp_url)
            )
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open RTSP stream: {self.rtsp_url}")
                return False
            
            # Test read a frame to verify connection
            success, test_frame = await loop.run_in_executor(None, self.cap.read)
            if not success or test_frame is None:
                logger.error(f"Connected to stream {self.rtsp_url} but could not read a frame")
                return False
                
            logger.info(f"Successfully read test frame from {self.rtsp_url}, dimensions: {test_frame.shape}")
            
            # Set buffer size to reduce latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Initialize AI components if needed
            if self.detect_people or self.count_people:
                self.object_detector = ObjectDetector()
            
            if self.count_people:
                self.people_counter = PeopleCounter(camera_id=self.camera_id)
            
            if self.recognize_faces:
                self.face_recognizer = FaceRecognizer()
            
            if self.template_matching:
                self.template_matcher = TemplateMatcher(camera_id=self.camera_id)
            
            self.connected = True
            logger.info(f"Connected to camera {self.camera_id}: {self.rtsp_url}")
            return True
            
        except Exception as e:
            logger.exception(f"Error connecting to RTSP stream {self.rtsp_url}: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from the RTSP stream and clean up resources"""
        self.connected = False
        self.processing = False
        
        # Wait for any processing to complete
        await asyncio.sleep(0.5)
        
        if self.cap:
            # Release capture in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.cap.release())
            self.cap = None
        
        logger.info(f"Disconnected from camera {self.camera_id}")
    
    async def process_stream(self):
        """Main processing loop for the video stream"""
        if not self.connected or not self.cap:
            logger.error(f"Cannot process stream for camera {self.camera_id}: Not connected")
            return
        
        self.processing = True
        loop = asyncio.get_event_loop()
        frames_processed = 0
        processing_start_time = time.time()
        
        try:
            logger.info(f"Starting stream processing for camera {self.camera_id}")
            
            while self.connected and self.processing:
                process_start = time.time()
                
                # Read frame from the stream (in thread pool)
                logger.debug(f"Reading frame from camera {self.camera_id}")
                ret, frame = await loop.run_in_executor(None, lambda: self.cap.read())
                
                if not ret:
                    logger.warning(f"Failed to read frame from camera {self.camera_id}")
                    # Try to reconnect
                    await self.reconnect()
                    await asyncio.sleep(1)  # Wait before trying again
                    continue
                
                frames_processed += 1
                if frames_processed % 100 == 0:
                    elapsed = time.time() - processing_start_time
                    logger.info(f"Camera {self.camera_id}: Processed {frames_processed} frames in {elapsed:.2f}s ({frames_processed/elapsed:.2f} FPS)")
                
                # Update the latest frame
                async with self.frame_lock:
                    self.latest_frame = frame.copy()
                    self.last_frame_time = time.time()
                
                # Process frame if enough time has elapsed since the last processing
                time_since_process = time.time() - self.last_processed_time
                if time_since_process >= (1.0 / self.processing_fps):
                    # Process the frame with AI models
                    processed_frame = await self.process_frame(frame)
                    
                    # Update the latest processed frame
                    async with self.frame_lock:
                        self.latest_processed_frame = processed_frame
                        self.last_processed_time = time.time()
                
                # Calculate FPS
                self.frame_count += 1
                if time.time() - self.last_fps_update >= 1.0:
                    self.fps = self.frame_count / (time.time() - self.last_fps_update)
                    logger.debug(f"Camera {self.camera_id} processing FPS: {self.fps:.2f}")
                    self.frame_count = 0
                    self.last_fps_update = time.time()
                
                # Sleep to maintain target FPS if needed
                process_time = time.time() - process_start
                sleep_time = max(0, (1.0 / self.streaming_fps) - process_time)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        
        except Exception as e:
            logger.exception(f"Error in process_stream for camera {self.camera_id}: {str(e)}")
        finally:
            self.processing = False
            logger.info(f"Stopped stream processing for camera {self.camera_id}")
    
    async def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Apply AI processing to a video frame"""
        processed_frame = frame.copy()
        detection_results = {}
        
        try:
            # Apply object detection for people
            if self.detect_people and self.object_detector:
                people_detections = await self.object_detector.detect_people(frame)
                detection_results['people'] = people_detections
                
                # Draw bounding boxes for people
                for detection in people_detections:
                    bbox = detection["bbox"]
                    confidence = detection["confidence"]
                    label = f"Person: {confidence:.2f}"
                    
                    cv2.rectangle(
                        processed_frame, 
                        (bbox[0], bbox[1]), 
                        (bbox[2], bbox[3]), 
                        (0, 255, 0), 
                        2
                    )
                    cv2.putText(
                        processed_frame, 
                        label, 
                        (bbox[0], bbox[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (0, 255, 0), 
                        2
                    )
            
            # Apply people counting
            if self.count_people and self.people_counter and 'people' in detection_results:
                entry_count, exit_count, current_count = await self.people_counter.process_frame(
                    frame, detection_results['people']
                )
                
                # Update occupancy count
                self.current_occupancy = current_count
                
                # Display counts on the frame
                cv2.putText(
                    processed_frame,
                    f"In: {entry_count} | Out: {exit_count} | Current: {current_count}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2
                )
                
                detection_results['people_counting'] = {
                    'entries': entry_count,
                    'exits': exit_count,
                    'current': current_count
                }
            
            # Apply face recognition
            if self.recognize_faces and self.face_recognizer:
                face_detections = await self.face_recognizer.recognize_faces(frame)
                detection_results['faces'] = face_detections
                
                # Draw faces on the frame
                for face in face_detections:
                    bbox = face["bbox"]
                    name = face["person_name"]
                    confidence = face["confidence"]
                    label = f"{name}: {confidence:.2f}"
                    
                    cv2.rectangle(
                        processed_frame, 
                        (bbox[0], bbox[1]), 
                        (bbox[2], bbox[3]), 
                        (255, 0, 0), 
                        2
                    )
                    cv2.putText(
                        processed_frame, 
                        label, 
                        (bbox[0], bbox[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (255, 0, 0), 
                        2
                    )
            
            # Apply template matching
            if self.template_matching and self.template_matcher:
                template_matches = await self.template_matcher.match_templates(frame)
                detection_results['templates'] = template_matches
                
                # Draw template matches on the frame
                for match in template_matches:
                    bbox = match["bbox"]
                    name = match["template_name"]
                    confidence = match["confidence"]
                    label = f"{name}: {confidence:.2f}"
                    
                    cv2.rectangle(
                        processed_frame, 
                        (bbox[0], bbox[1]), 
                        (bbox[2], bbox[3]), 
                        (0, 0, 255), 
                        2
                    )
                    cv2.putText(
                        processed_frame, 
                        label, 
                        (bbox[0], bbox[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        (0, 0, 255), 
                        2
                    )
            
            # Add stats overlay
            cv2.putText(
                processed_frame,
                f"FPS: {self.fps:.1f}",
                (10, processed_frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )
            
            # Update detection results
            self.detection_results = detection_results
            
        except Exception as e:
            logger.exception(f"Error processing frame for camera {self.camera_id}: {str(e)}")
        
        return processed_frame
    
    def get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest frame and its timestamp"""
        if not self.connected:
            logger.warning(f"Attempted to get frame from camera {self.camera_id} but not connected")
            return None
            
        if self.latest_processed_frame is not None:
            logger.debug(f"Returning latest processed frame for camera {self.camera_id}")
            return self.latest_processed_frame.copy(), self.last_processed_time
        elif self.latest_frame is not None:
            logger.debug(f"Returning latest raw frame for camera {self.camera_id}")
            return self.latest_frame.copy(), self.last_frame_time
            
        logger.warning(f"No frames available for camera {self.camera_id}")
        return None
    
    async def reconnect(self, max_attempts: int = 3) -> bool:
        """Try to reconnect to the RTSP stream"""
        for attempt in range(max_attempts):
            logger.info(f"Reconnecting to camera {self.camera_id}, attempt {attempt + 1}/{max_attempts}")
            
            # Disconnect first
            await self.disconnect()
            
            # Wait before retry
            await asyncio.sleep(2)
            
            # Try to connect again
            if await self.connect():
                return True
        
        logger.error(f"Failed to reconnect to camera {self.camera_id} after {max_attempts} attempts")
        return False
    
    def get_detection_results(self) -> Dict[str, Any]:
        """Get the latest detection results"""
        return self.detection_results
    
    def get_current_occupancy(self) -> int:
        """Get the current room occupancy count"""
        return self.current_occupancy