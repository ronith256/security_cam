import cv2
import asyncio
import time
import logging
import numpy as np
import gc
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
        
        # Processing control flag
        self.should_process = detect_people or count_people or recognize_faces or template_matching
        
        # Video capture object
        self.cap = None
        self.connected = False
        self.processing = False
        
        # Frame buffer (with size limit)
        self.latest_frame = None
        self.latest_processed_frame = None
        self.last_frame_time = 0
        self.last_processed_time = 0
        
        # Template matching for scene change detection
        self.base_template = None
        self.last_template_update = 0
        self.change_threshold = 0.10  # 10% change threshold for processing
        self.template_update_interval = 3600  # Update template every hour
        
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
        
        # Memory management
        self.max_frame_size = (1280, 720)  # Max resolution to process
        self.max_frames_without_gc = 100  # Run garbage collection after this many frames
        self.frames_since_gc = 0
    
    async def connect(self) -> bool:
        """Connect to the RTSP stream"""
        try:
            logger.info(f"Attempting to connect to RTSP stream: {self.rtsp_url}")
            
            # If already connected, disconnect first to ensure a clean state
            if self.connected and self.cap:
                logger.info(f"Already connected to {self.rtsp_url}, resetting connection")
                await self.disconnect()
                await asyncio.sleep(1)  # Brief pause before reconnecting
            
            # Add connection options to improve reliability
            # In OpenCV, use TCP instead of UDP (preferred for reliability over speed)
            rtsp_options = {
                "rtsp_transport": "tcp",  # Use TCP instead of UDP for more reliable connection
                "buffer_size": "10485760",  # 10MB buffer
                "max_delay": "500000",    # 0.5 second max delay
                "stimeout": "5000000"     # 5 second timeout
            }
            
            # Build the RTSP URL with options
            rtsp_url_with_options = self.rtsp_url
            if "?" not in rtsp_url_with_options:
                rtsp_url_with_options += "?"
            else:
                rtsp_url_with_options += "&"
            
            for key, value in rtsp_options.items():
                rtsp_url_with_options += f"{key}={value}&"
            
            # Remove the last '&'
            rtsp_url_with_options = rtsp_url_with_options.rstrip("&")
            
            logger.info(f"Using RTSP URL with options: {rtsp_url_with_options}")
            
            # OpenCV VideoCapture is blocking, so run in a thread pool
            loop = asyncio.get_event_loop()
            self.cap = await loop.run_in_executor(
                None, lambda: cv2.VideoCapture(rtsp_url_with_options)
            )
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open RTSP stream: {self.rtsp_url}")
                
                # Try again with the original URL if the options didn't work
                logger.info(f"Retrying with original URL: {self.rtsp_url}")
                self.cap = await loop.run_in_executor(
                    None, lambda: cv2.VideoCapture(self.rtsp_url)
                )
                
                if not self.cap.isOpened():
                    logger.error(f"Still failed to open RTSP stream: {self.rtsp_url}")
                    return False
            
            # Test read a frame to verify connection
            for attempt in range(3):  # Try a few times to get a frame
                logger.info(f"Reading test frame, attempt {attempt+1}/3")
                success, test_frame = await loop.run_in_executor(None, self.cap.read)
                if success and test_frame is not None:
                    logger.info(f"Successfully read test frame from {self.rtsp_url}, dimensions: {test_frame.shape}")
                    break
                
                if attempt < 2:  # Don't sleep on the last attempt
                    await asyncio.sleep(1)  # Wait a bit before trying again
            
            # Final check if we have a valid frame
            if not success or test_frame is None:
                logger.error(f"Connected to stream {self.rtsp_url} but could not read a frame")
                return False
                
            # Store first frame as template if none exists
            if self.base_template is None:
                self.set_base_template(test_frame)
            
            # Set buffer size to reduce latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Initialize AI components if needed - lazy initialization to save memory
            if (self.detect_people or self.count_people) and self.object_detector is None:
                self.object_detector = ObjectDetector()
            
            if self.count_people and self.people_counter is None:
                self.people_counter = PeopleCounter(camera_id=self.camera_id)
            
            if self.recognize_faces and self.face_recognizer is None:
                self.face_recognizer = FaceRecognizer()
            
            if self.template_matching and self.template_matcher is None:
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
        
        # Clear frame buffers to free memory
        self.latest_frame = None
        self.latest_processed_frame = None
        
        # Run garbage collection
        gc.collect()
        
        logger.info(f"Disconnected from camera {self.camera_id}")
    
    def set_base_template(self, frame: np.ndarray):
        """Set the base template for scene change detection"""
        # Resize for faster comparison and lower memory usage
        small_frame = cv2.resize(frame, (320, 240))
        
        # Convert to grayscale for smaller memory footprint
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        self.base_template = gray
        self.last_template_update = time.time()
        logger.info(f"Updated base template for camera {self.camera_id}")
    
    def scene_has_changed(self, frame: np.ndarray) -> bool:
        """Detect if the scene has changed significantly from base template"""
        if self.base_template is None:
            # If no template, always process
            return True
        
        # Check if it's time to update the template
        if time.time() - self.last_template_update > self.template_update_interval:
            self.set_base_template(frame)
            return True
        
        # Resize for faster comparison
        small_frame = cv2.resize(frame, (320, 240))
        
        # Convert to grayscale
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate Mean Absolute Difference (MAD)
        diff = cv2.absdiff(gray, self.base_template)
        mean_diff = np.mean(diff) / 255.0  # Normalize to 0-1 range
        
        # If difference exceeds threshold, scene has changed
        changed = mean_diff > self.change_threshold
        
        return changed
    
    def _limit_frame_size(self, frame: np.ndarray) -> np.ndarray:
        """Limit frame size to reduce memory usage"""
        if frame is None:
            return None
            
        h, w = frame.shape[:2]
        max_w, max_h = self.max_frame_size
        
        if w > max_w or h > max_h:
            # Calculate new dimensions maintaining aspect ratio
            if w/h > max_w/max_h:  # Width limited
                new_w = max_w
                new_h = int(h * (max_w / w))
            else:  # Height limited
                new_h = max_h
                new_w = int(w * (max_h / h))
                
            # Resize frame
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        return frame
    
    async def process_stream(self):
        """Main processing loop for the video stream"""
        if not self.connected or not self.cap:
            logger.error(f"Cannot process stream for camera {self.camera_id}: Not connected")
            return
        
        # Don't start processing if already processing
        if self.processing:
            logger.warning(f"Camera {self.camera_id} is already being processed")
            return
        
        self.processing = True
        loop = asyncio.get_event_loop()
        frames_processed = 0
        frames_skipped = 0
        frames_failed = 0  # Track failed frame reads
        processing_start_time = time.time()
        last_process_time = 0
        consecutive_failures = 0  # Track consecutive frame read failures
        
        try:
            logger.info(f"Starting stream processing for camera {self.camera_id}")
            
            while self.connected and self.processing:
                process_start = time.time()
                
                # Read frame from the stream (in thread pool)
                logger.debug(f"Reading frame from camera {self.camera_id}")
                ret, frame = await loop.run_in_executor(None, lambda: self.cap.read())
                
                if not ret or frame is None:
                    frames_failed += 1
                    consecutive_failures += 1
                    logger.warning(f"Failed to read frame from camera {self.camera_id} (consecutive failures: {consecutive_failures})")
                    
                    # If too many consecutive failures, try to reconnect
                    if consecutive_failures >= 5:
                        logger.error(f"Too many consecutive frame read failures ({consecutive_failures}), attempting to reconnect")
                        # Try to reconnect
                        reconnect_success = await self.reconnect()
                        if reconnect_success:
                            logger.info(f"Successfully reconnected to camera {self.camera_id}")
                            consecutive_failures = 0  # Reset counter after successful reconnection
                        else:
                            logger.error(f"Failed to reconnect to camera {self.camera_id}")
                    
                    # Wait before trying again
                    await asyncio.sleep(1)
                    continue
                
                # Reset consecutive failures counter when we successfully read a frame
                consecutive_failures = 0
                
                # Limit frame size to reduce memory usage
                frame = self._limit_frame_size(frame)
                
                # Update the latest frame
                async with self.frame_lock:
                    # Clear old frame before assigning new one to prevent memory leaks
                    self.latest_frame = None
                    self.latest_frame = frame.copy()
                    self.last_frame_time = time.time()
                
                # Calculate time since last processing
                time_since_process = time.time() - last_process_time
                
                # Process the frame if:
                # 1. Enough time has elapsed since last processing (based on FPS)
                # 2. The scene has changed significantly or we're forcing processing
                should_process = time_since_process >= (1.0 / self.processing_fps)
                
                if should_process and self.should_process:
                    # Check if scene has changed before heavy processing
                    scene_changed = self.scene_has_changed(frame)
                    
                    if scene_changed:
                        # Process the frame with AI models
                        processed_frame = await self.process_frame(frame)
                        
                        # Update the latest processed frame
                        async with self.frame_lock:
                            # Clear old frame before assigning new one
                            self.latest_processed_frame = None
                            self.latest_processed_frame = processed_frame
                            self.last_processed_time = time.time()
                            last_process_time = time.time()
                        
                        frames_processed += 1
                    else:
                        # Only update the latest processed frame with minimal overlay
                        # (showing stats but not running AI processing)
                        minimal_processed = frame.copy()
                        
                        # Add stats overlay
                        cv2.putText(
                            minimal_processed,
                            f"FPS: {self.fps:.1f} (No Motion)",
                            (10, minimal_processed.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 255),
                            1
                        )
                        
                        async with self.frame_lock:
                            # Clear old frame before assigning new one
                            self.latest_processed_frame = None
                            self.latest_processed_frame = minimal_processed
                        
                        frames_skipped += 1
                
                # Calculate FPS
                self.frame_count += 1
                if time.time() - self.last_fps_update >= 1.0:
                    self.fps = self.frame_count / (time.time() - self.last_fps_update)
                    logger.debug(f"Camera {self.camera_id} processing FPS: {self.fps:.2f}")
                    self.frame_count = 0
                    self.last_fps_update = time.time()
                
                # Periodic garbage collection to prevent memory leaks
                self.frames_since_gc += 1
                if self.frames_since_gc >= self.max_frames_without_gc:
                    gc.collect()
                    self.frames_since_gc = 0
                
                # Log stats every 100 frames
                if (frames_processed + frames_skipped) % 100 == 0:
                    elapsed = time.time() - processing_start_time
                    logger.info(
                        f"Camera {self.camera_id}: Processed {frames_processed} frames, "
                        f"skipped {frames_skipped} frames, failed {frames_failed} frames in {elapsed:.2f}s "
                        f"({(frames_processed + frames_skipped)/elapsed:.2f} FPS)"
                    )
                
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
                face_detections = await self.face_recognizer.recognize_faces(frame, self.camera_id)
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
            
            # Add processing status overlay
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(
                processed_frame,
                f"FPS: {self.fps:.1f} | {now}",
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
            
            # Wait before retry with exponential backoff
            wait_time = min(2 ** attempt, 30)  # Max 30 seconds
            await asyncio.sleep(wait_time)
            
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