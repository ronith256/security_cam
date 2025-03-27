import cv2
import numpy as np
import os
import logging
import asyncio
import time
import threading
from queue import Queue, Full, Empty
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
        
        # Frame buffers with Thread-safe Queue
        self.raw_frame_queue = Queue(maxsize=30)
        self.processed_frame_queue = Queue(maxsize=30)
        self.max_buffer_size = 30
        
        # Thread safety
        self._frame_lock = asyncio.Lock()
        self._cv_lock = threading.RLock()
        
        # State variables
        self.connected = False
        self.running = False
        self.processing = False
        self.paused = False
        self.reconnecting = False
        
        # Performance metrics
        self.fps = 0
        self.frames_captured = 0
        self.frames_processed = 0
        self.processing_fps_actual = 0
        self.last_frame_time = 0
        self.last_processed_time = 0
        self.processing_start_time = 0
        self.connection_errors = 0
        self.consecutive_errors = 0
        
        # Cache of latest successful frame (to return when stream has issues)
        self.latest_raw_frame = None
        self.latest_raw_timestamp = 0
        self.latest_processed_frame = None
        self.latest_processed_timestamp = 0
        
        # OpenCV capture object and thread
        self.capture = None
        self.capture_thread = None
        self.capture_thread_running = False
        
        # Executor for CPU-bound tasks like CV operations
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Latest detection results
        self.detection_results = {}
        self.current_occupancy = 0
        
        # Event emitter for notifications
        self.events = EventEmitter()
        
        # Notification settings
        self.check_notification_triggers = True  # Enable notification checking
        
        logger.info(f"StreamProcessor initialized for camera {camera_id}: {name}")
    
    async def connect(self) -> bool:
        """
        Connect to the RTSP stream using a separate thread for capture
        
        Returns:
            Success flag
        """
        try:
            # Disconnect first if already connected
            if self.connected:
                await self.disconnect()
            
            logger.info(f"Connecting to RTSP stream: {self.rtsp_url} for camera {self.camera_id}")
            
            # Connect in a background thread to avoid blocking asyncio
            success = await self._connect_rtsp()
            
            if not success:
                logger.error(f"Failed to connect to RTSP stream: {self.rtsp_url}")
                return False
            
            # Update state
            self.connected = True
            self.running = True
            self.connection_errors = 0
            self.consecutive_errors = 0
            
            # Emit event
            self.events.emit("connected", {
                "camera_id": self.camera_id,
                "name": self.name,
                "rtsp_url": self.rtsp_url,
                "timestamp": time.time()
            })
            
            logger.info(f"Successfully connected to camera {self.camera_id}: {self.name}")
            return True
        
        except Exception as e:
            logger.exception(f"Error connecting to camera {self.camera_id}: {str(e)}")
            await self.disconnect()
            return False
    
    async def _connect_rtsp(self) -> bool:
        """
        Establish connection to RTSP stream using OpenCV
        
        Returns:
            Success flag
        """
        try:
            # Create the capture in the main thread but read frames in a separate thread
            with self._cv_lock:
                if self.capture is not None:
                    self.capture.release()
                
                # Create a new capture with optimized parameters
                self.capture = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                
                # Set additional parameters for more reliable streaming
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 3)  # Increase internal buffer
                
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
                
                # Start capture thread if not already running
                if self.capture_thread is None or not self.capture_thread_running:
                    self.capture_thread_running = True
                    self.capture_thread = threading.Thread(
                        target=self._capture_frames_thread,
                        daemon=True,
                        name=f"camera_{self.camera_id}_capture"
                    )
                    self.capture_thread.start()
                    logger.info(f"Started capture thread for camera {self.camera_id}")
                
                return True
        
        except Exception as e:
            logger.exception(f"Error in RTSP connection for camera {self.camera_id}: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from the RTSP stream and clean up resources"""
        try:
            # Update state flags
            self.running = False
            self.connected = False
            self.processing = False
            
            # Stop capture thread
            self.capture_thread_running = False
            if self.capture_thread and self.capture_thread.is_alive():
                logger.info(f"Waiting for capture thread to terminate for camera {self.camera_id}")
                self.capture_thread.join(timeout=5.0)
            
            # Clean up capture
            with self._cv_lock:
                if self.capture is not None:
                    self.capture.release()
                    self.capture = None
            
            # Clean up video writer
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            
            # Clear frame queues
            while not self.raw_frame_queue.empty():
                try:
                    self.raw_frame_queue.get_nowait()
                except Empty:
                    break
            
            while not self.processed_frame_queue.empty():
                try:
                    self.processed_frame_queue.get_nowait()
                except Empty:
                    break
            
            # Emit event
            self.events.emit("disconnected", {
                "camera_id": self.camera_id
            })
            
            logger.info(f"Disconnected from camera {self.camera_id}")
        
        except Exception as e:
            logger.exception(f"Error disconnecting camera {self.camera_id}: {str(e)}")
    
    def _capture_frames_thread(self):
        """Thread function that continuously captures frames from RTSP stream"""
        frame_interval = 1.0 / max(1, self.processing_fps)
        last_capture_time = 0
        frames_count = 0
        start_time = time.time()
        
        logger.info(f"Starting frame capture thread for camera {self.camera_id} at {self.processing_fps} FPS")
        
        while self.capture_thread_running:
            try:
                # Throttle capture to desired FPS
                current_time = time.time()
                if current_time - last_capture_time < frame_interval:
                    time.sleep(0.001)  # Small sleep to prevent CPU hogging
                    continue
                
                # Check if capture is valid
                with self._cv_lock:
                    if self.capture is None or not self.capture.isOpened():
                        logger.warning(f"Camera {self.camera_id} connection lost in capture thread")
                        self.connection_errors += 1
                        self.consecutive_errors += 1
                        time.sleep(0.1)  # Wait a bit before retry
                        continue
                    
                    # Capture frame
                    ret, frame = self.capture.read()
                
                if not ret or frame is None:
                    logger.warning(f"Failed to read frame from camera {self.camera_id}")
                    self.connection_errors += 1
                    self.consecutive_errors += 1
                    
                    # If too many consecutive errors, request reconnection
                    if self.consecutive_errors > 30:
                        logger.error(f"Too many consecutive read failures for camera {self.camera_id}, triggering reconnect")
                        self._trigger_reconnect()
                        time.sleep(1.0)  # Wait before continuing
                    
                    time.sleep(0.1)  # Short wait before retry
                    continue
                
                # Successfully got a frame, reset consecutive error counter
                self.consecutive_errors = 0
                
                # Log occasionally about successful frame grabs
                if frames_count % 100 == 0:
                    logger.debug(f"Successfully grabbed frame #{frames_count} from camera {self.camera_id}")
                
                # Add frame to the queue
                try:
                    # Add frame with timestamp
                    timestamp = time.time()
                    self.raw_frame_queue.put_nowait((frame.copy(), timestamp))
                    
                    # Update latest frame cache (thread-safe access)
                    self.latest_raw_frame = frame.copy()
                    self.latest_raw_timestamp = timestamp
                    
                    # Update metrics
                    self.last_frame_time = timestamp
                    frames_count += 1
                    self.frames_captured += 1
                    
                    # Record frame if enabled
                    if self.record_video and self.video_writer:
                        self.video_writer.write(frame)
                    
                except Full:
                    # Queue is full, remove oldest frame
                    try:
                        self.raw_frame_queue.get_nowait()
                        # Now add the new frame
                        self.raw_frame_queue.put_nowait((frame.copy(), time.time()))
                    except:
                        pass  # In case of race condition
                
                # Calculate FPS every second
                if current_time - start_time >= 1.0:
                    self.fps = frames_count / (current_time - start_time)
                    frames_count = 0
                    start_time = current_time
                
                # Update last capture time
                last_capture_time = current_time
            
            except Exception as e:
                logger.exception(f"Error in capture thread for camera {self.camera_id}: {str(e)}")
                time.sleep(0.1)  # Wait a bit before continuing
    
    def _trigger_reconnect(self):
        """Trigger camera reconnection (called from capture thread)"""
        if not self.reconnecting:
            self.reconnecting = True
            # Create asyncio task to reconnect (properly from event loop)
            asyncio.run_coroutine_threadsafe(self._attempt_reconnect(), asyncio.get_event_loop())
    
    async def _attempt_reconnect(self):
        """Attempt to reconnect to camera (runs in asyncio event loop)"""
        try:
            logger.info(f"Attempting to reconnect camera {self.camera_id}")
            # Try to disconnect first
            await self.disconnect()
            # Wait a moment
            await asyncio.sleep(2.0)
            # Try to reconnect
            success = await self.connect()
            
            if success:
                logger.info(f"Successfully reconnected camera {self.camera_id}")
                # If was processing, restart processing
                if self.processing:
                    await self.start_processing()
            else:
                logger.error(f"Failed to reconnect camera {self.camera_id}")
                
                # Schedule another reconnect attempt in 5 seconds
                await asyncio.sleep(5.0)
                asyncio.create_task(self._attempt_reconnect())
        
        except Exception as e:
            logger.exception(f"Error in reconnect attempt for camera {self.camera_id}: {str(e)}")
        finally:
            self.reconnecting = False
    
    async def start_capture(self):
        """Start capturing frames from the RTSP stream"""
        if not self.connected:
            success = await self.connect()
            if not success:
                logger.error(f"Failed to connect camera {self.camera_id} during start_capture")
                return False
        
        self.running = True
        logger.info(f"Started frame capture for camera {self.camera_id}")
        return True
    
    async def stop_capture(self):
        """Stop capturing frames from the RTSP stream"""
        self.running = False
        # Capture thread will stop on next iteration
        logger.info(f"Requested stop capture for camera {self.camera_id}")
        return True
    
    async def start_processing(self):
        """Start processing captured frames"""
        if self.processing:
            logger.debug(f"Camera {self.camera_id} processing already running")
            return True
        
        if not self.connected:
            logger.warning(f"Cannot start processing for camera {self.camera_id}, not connected")
            return False
        
        self.processing = True
        self.processing_start_time = time.time()
        self.frames_processed = 0
        
        # Create asyncio task for processing
        asyncio.create_task(self._process_frames())
        logger.info(f"Started frame processing for camera {self.camera_id}")
        return True
    
    async def stop_processing(self):
        """Stop processing captured frames"""
        self.processing = False
        logger.info(f"Stopped frame processing for camera {self.camera_id}")
        return True
    
    async def _process_frames(self):
        """Process frames through the AI pipelines"""
        process_interval = 1.0 / max(1, self.processing_fps)
        last_process_time = 0
        frames_processed_count = 0
        processing_errors = 0
        start_time = time.time()
        
        logger.info(f"Starting frame processing loop for camera {self.camera_id} ({self.name}) at {self.processing_fps} FPS")
        
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
                
                # Get latest frame from queue
                frame_data = None
                try:
                    # Non-blocking get with timeout
                    frame_data = self.raw_frame_queue.get_nowait()
                except Empty:
                    # If queue is empty, use cached latest frame if available and recent
                    if (self.latest_raw_frame is not None and 
                        current_time - self.latest_raw_timestamp < 5.0):
                        frame_data = (self.latest_raw_frame.copy(), self.latest_raw_timestamp)
                    else:
                        if processing_errors % 10 == 0:  # Only log every 10 errors to avoid spam
                            logger.warning(f"No frames available for processing from camera {self.camera_id}")
                        processing_errors += 1
                        await asyncio.sleep(0.1)
                        continue
                
                # Reset error counter on successful frame retrieval
                processing_errors = 0
                
                frame, timestamp = frame_data
                
                # Log frame shape to debug if frames are valid
                if frames_processed_count == 0:
                    logger.info(f"Processing first frame from camera {self.camera_id}, shape: {frame.shape}")
                
                # Process frame through AI pipeline
                processed_frame, results = await self._process_frame_pipeline(frame)
                
                # Log the results occasionally
                if frames_processed_count % 50 == 0:
                    people_count = len(results.get("people", []))
                    faces_count = len(results.get("faces", []))
                    logger.debug(f"Camera {self.camera_id} frame #{frames_processed_count} - detected: {people_count} people, {faces_count} faces")
                
                # Update processed frame queue
                try:
                    # Store processed frame
                    self.processed_frame_queue.put_nowait((processed_frame, current_time))
                    
                    # Update cached latest processed frame (thread-safe access)
                    self.latest_processed_frame = processed_frame
                    self.latest_processed_timestamp = current_time
                    
                except Full:
                    # If queue is full, remove oldest
                    try:
                        self.processed_frame_queue.get_nowait()
                        self.processed_frame_queue.put_nowait((processed_frame, current_time))
                    except:
                        pass  # In case of race condition
                
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
                    logger.debug(f"Camera {self.camera_id} processing FPS: {self.processing_fps_actual:.2f}")
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
                processing_errors += 1
                await asyncio.sleep(0.1)
        
        logger.info(f"Processing loop exited for camera {self.camera_id}")
    
    async def _process_frame_pipeline(self, frame: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Process a frame through all enabled AI components and check for triggers"""
        results = {}
        processed_frame = frame.copy()
        processing_start = time.time()
        
        try:
            # Log the start of processing
            logger.debug(f"Processing frame for camera {self.camera_id}", 
                        extra={"camera_id": self.camera_id})
            
            # Run object detection first if enabled
            if self.detect_people and self.object_detector:
                detection_start = time.time()
                
                # Detect people
                people = await self.object_detector.detect_people(frame)
                results["people"] = people
                
                detection_time = time.time() - detection_start
                logger.info(
                    f"Camera {self.camera_id}: Detected {len(people)} people in {detection_time:.3f}s",
                    extra={"camera_id": self.camera_id, "detection": True, "people_count": len(people)}
                )
                
                # Draw bounding boxes if enabled
                if self.draw_detections:
                    processed_frame = draw_bounding_boxes(
                        processed_frame, people, color=(0, 255, 0), label_key="class_name"
                    )
                
                # Update people counter
                if self.count_people and self.people_counter and people:
                    count_start = time.time()
                    
                    # Use executor for counter processing
                    entry_count, exit_count, current_count = await self.people_counter.process_frame(
                        frame, people
                    )
                    count_time = time.time() - count_start
                    
                    results["occupancy"] = {
                        "entries": entry_count,
                        "exits": exit_count,
                        "current": current_count
                    }
                    
                    logger.info(
                        f"Camera {self.camera_id}: Occupancy count - Current: {current_count}, "
                        f"Entries: {entry_count}, Exits: {exit_count} in {count_time:.3f}s",
                        extra={"camera_id": self.camera_id, "people_count": True, 
                            "current_count": current_count, "entries": entry_count, "exits": exit_count}
                    )
                    
                    # Draw counting line if enabled
                    # if self.draw_count_line:
                    #     line_pos = self.people_counter.line_position
                    #     processed_frame = draw_line(
                    #         processed_frame, line_pos, color=(0, 0, 255)
                    #     )
                        
                    #     # Draw occupancy info
                    #     h, w = processed_frame.shape[:2]
                    #     cv2.putText(
                    #         processed_frame,
                    #         f"Current: {current_count} | In: {entry_count} | Out: {exit_count}",
                    #         (10, 30),
                    #         cv2.FONT_HERSHEY_SIMPLEX,
                    #         0.7,
                    #         (0, 255, 255),
                    #         2
                    #     )
            
            # Face recognition
            if self.recognize_faces and self.face_recognizer:
                face_start = time.time()
                faces = await self.face_recognizer.recognize_faces(frame, self.camera_id)
                results["faces"] = faces
                face_time = time.time() - face_start
                
                recognized_faces = [f for f in faces if f.get("person_id") is not None]
                unrecognized_faces = [f for f in faces if f.get("person_id") is None]
                
                logger.info(
                    f"Camera {self.camera_id}: Detected {len(faces)} faces "
                    f"({len(recognized_faces)} recognized, {len(unrecognized_faces)} unknown) "
                    f"in {face_time:.3f}s",
                    extra={"camera_id": self.camera_id, "face": True, 
                        "total_faces": len(faces), "recognized_faces": len(recognized_faces)}
                )
                
                # Draw face bounding boxes
                if self.draw_detections and faces:
                    processed_frame = draw_bounding_boxes(
                        processed_frame, faces, color=(255, 0, 0), label_key="person_name"
                    )
            
            # Template matching
            if self.template_matching and self.template_matcher:
                template_start = time.time()
                templates = await self.template_matcher.match_templates(frame)
                results["templates"] = templates
                template_time = time.time() - template_start
                
                logger.info(
                    f"Camera {self.camera_id}: Matched {len(templates)} templates in {template_time:.3f}s",
                    extra={"camera_id": self.camera_id, "template": True, "matches": len(templates)}
                )
                
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
                    
                    notification_start = time.time()
                    
                    # Get notification service
                    notification_service = await get_notification_service()
                    
                    # Check triggers in a background task - passing the frame for snapshots
                    asyncio.create_task(notification_service.check_all_triggers(
                        self.camera_id, results, frame.copy()
                    ))
                    
                    logger.debug(
                        f"Camera {self.camera_id}: Checking notification triggers",
                        extra={"camera_id": self.camera_id, "notification": True}
                    )
                except Exception as e:
                    logger.exception(
                        f"Error checking notification triggers: {str(e)}",
                        extra={"camera_id": self.camera_id, "notification": True, "error": True}
                    )
            
            # Log total processing time
            total_time = time.time() - processing_start
            logger.debug(
                f"Camera {self.camera_id}: Frame processing completed in {total_time:.3f}s",
                extra={"camera_id": self.camera_id, "processing_time": total_time}
            )
            
            return processed_frame, results
            
        except Exception as e:
            total_time = time.time() - processing_start
            logger.exception(
                f"Error in processing pipeline for camera {self.camera_id}: {str(e)} "
                f"(after {total_time:.3f}s)",
                extra={"camera_id": self.camera_id, "error": True, "processing_time": total_time}
            )
            return frame, {}
    
    async def get_latest_frame(self) -> Optional[Tuple[np.ndarray, float]]:
        """Get the latest processed frame or raw frame if processing is disabled"""
        try:
            # Try to get from processed frames first
            if not self.processed_frame_queue.empty():
                return self.processed_frame_queue.queue[-1]
            
            # If no processed frames, try raw frames
            if not self.raw_frame_queue.empty():
                return self.raw_frame_queue.queue[-1]
            
            # If both queues empty, use cached frames
            if self.latest_processed_frame is not None:
                return (self.latest_processed_frame, self.latest_processed_timestamp)
            
            if self.latest_raw_frame is not None:
                return (self.latest_raw_frame, self.latest_raw_timestamp)
            
            # No frames available
            return None
            
        except Exception as e:
            logger.exception(f"Error getting latest frame for camera {self.camera_id}: {str(e)}")
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
        
        try:
            # Run the JPEG encoding in the executor to avoid blocking
            loop = asyncio.get_event_loop()
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            
            # Need to define this as a separate function for the executor
            def encode_frame(frame, encode_param):
                _, jpeg_data = cv2.imencode('.jpg', frame, encode_param)
                return jpeg_data.tobytes()
            
            # Run in executor
            jpeg_bytes = await loop.run_in_executor(
                self.executor, encode_frame, frame, encode_param
            )
            
            return jpeg_bytes
            
        except Exception as e:
            logger.exception(f"Error encoding JPEG for camera {self.camera_id}: {str(e)}")
            return None
    
    def get_detection_results(self) -> Dict[str, Any]:
        """Get the latest detection results"""
        return self.detection_results.copy()  # Return a copy to avoid threading issues
    
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
            filepath = os.path.join(settings.RECORDINGS_DIR, filename)
            
            # Ensure directory exists
            os.makedirs(settings.RECORDINGS_DIR, exist_ok=True)
            
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
            "name": self.name,
            "connected": self.connected,
            "processing": self.processing,
            "fps": self.fps,
            "processing_fps": self.processing_fps_actual,
            "frames_captured": self.frames_captured,
            "frames_processed": self.frames_processed,
            "connection_errors": self.connection_errors,
            "consecutive_errors": self.consecutive_errors,
            "last_frame_time": self.last_frame_time,
            "last_processed_time": self.last_processed_time,
            "raw_frame_queue_size": self.raw_frame_queue.qsize(),
            "processed_frame_queue_size": self.processed_frame_queue.qsize(),
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