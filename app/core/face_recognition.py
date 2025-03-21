import cv2
import numpy as np
import os
import logging
import asyncio
import time
import json
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, insert
from app.config import settings
from app.database import get_db
from app.models.person import Person
from app.models.event import Event, EventType

logger = logging.getLogger(__name__)

# Try to import face_recognition library if available
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logger.warning("face_recognition library not available, using OpenCV for face detection")

class FaceRecognizer:
    """
    Handles face detection and recognition
    """
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.face_cascade = None
        self.face_embeddings = {}  # {person_id: face_encoding}
        self.person_details = {}   # {person_id: {"name": name, "image_path": image_path}}
        self.initialized = False
        self.last_db_load = 0
        
        # Initialize the recognizer
        self._initialize()
    
    def _initialize(self):
        """Initialize face detection/recognition models"""
        try:
            if not FACE_RECOGNITION_AVAILABLE:
                # Use OpenCV Haar Cascade for basic face detection
                cascade_path = os.path.join(
                    settings.MODELS_DIR, 
                    "haarcascade_frontalface_default.xml"
                )
                
                if not os.path.exists(cascade_path):
                    # Try to use the one bundled with OpenCV
                    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
                if self.face_cascade.empty():
                    logger.error("Failed to load face cascade classifier")
                    return
            
            self.initialized = True
            logger.info("Face recognizer initialized")
        except Exception as e:
            logger.exception(f"Failed to initialize face recognizer: {str(e)}")
    
    async def load_face_embeddings(self, force_reload: bool = False):
        """Load face embeddings from the database"""
        # Only reload if it's been more than 60 seconds since last load or forced
        if not force_reload and time.time() - self.last_db_load < 60:
            return
        
        try:
            async for session in get_db():
                query = select(Person)
                result = await session.execute(query)
                persons = result.scalars().all()
                
                for person in persons:
                    # Skip if no face encoding saved
                    if not person.face_encoding:
                        continue
                    
                    # Load the face encoding
                    face_encoding = np.array(json.loads(person.face_encoding))
                    
                    # Store the encoding and person details
                    self.face_embeddings[person.id] = face_encoding
                    self.person_details[person.id] = {
                        "name": person.name,
                        "image_path": person.face_image_path
                    }
            
            self.last_db_load = time.time()
            logger.info(f"Loaded {len(self.face_embeddings)} face embeddings from database")
        except Exception as e:
            logger.exception(f"Error loading face embeddings: {str(e)}")
    
    async def register_face(self, image: np.ndarray, person_id: int) -> bool:
        """
        Register a face for a person
        
        Args:
            image: Face image
            person_id: ID of the person
            
        Returns:
            Success flag
        """
        if not self.initialized:
            logger.error("Face recognizer not initialized")
            return False
        
        if not FACE_RECOGNITION_AVAILABLE:
            logger.error("face_recognition library required for registration")
            return False
        
        try:
            # Resize image for faster processing
            small_image = cv2.resize(image, (0, 0), fx=0.25, fy=0.25)
            
            # Convert to RGB (face_recognition uses RGB)
            rgb_small_image = cv2.cvtColor(small_image, cv2.COLOR_BGR2RGB)
            
            # Find face locations
            face_locations = face_recognition.face_locations(rgb_small_image)
            
            if not face_locations:
                logger.warning("No face found in the image")
                return False
            
            # Use the first face found
            face_location = face_locations[0]
            
            # Calculate face encoding
            face_encoding = face_recognition.face_encodings(
                rgb_small_image, [face_location]
            )[0]
            
            # Store in database
            async for session in get_db():
                # Get the person
                person = await session.get(Person, person_id)
                if not person:
                    logger.error(f"Person with ID {person_id} not found")
                    return False
                
                # Update face encoding
                person.face_encoding = json.dumps(face_encoding.tolist())
                await session.commit()
                
                # Update local cache
                self.face_embeddings[person_id] = face_encoding
                self.person_details[person_id] = {
                    "name": person.name,
                    "image_path": person.face_image_path
                }
                
                logger.info(f"Registered face for person {person.name} (ID: {person_id})")
                return True
            
        except Exception as e:
            logger.exception(f"Error registering face: {str(e)}")
            return False
    
    async def recognize_faces(self, frame: np.ndarray, camera_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Detect and recognize faces in a frame
        
        Args:
            frame: Video frame
            camera_id: Optional camera ID for logging events
            
        Returns:
            List of face detections with person info
        """
        if not self.initialized:
            logger.warning("Face recognizer not initialized")
            return []
        
        # Ensure face embeddings are loaded
        await self.load_face_embeddings()
        
        # If we have no embeddings, just detect faces
        if not self.face_embeddings:
            return await self._detect_faces(frame)
        
        try:
            if FACE_RECOGNITION_AVAILABLE:
                return await self._recognize_with_face_recognition(frame, camera_id)
            else:
                # Basic detection with OpenCV if face_recognition not available
                return await self._detect_faces(frame)
        
        except Exception as e:
            logger.exception(f"Error in face recognition: {str(e)}")
            return []
    
    async def _recognize_with_face_recognition(
        self, 
        frame: np.ndarray, 
        camera_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Recognize faces using face_recognition library"""
        # Resize frame for faster processing (1/4 size)
        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
        # Get face locations and encodings
        loop = asyncio.get_event_loop()
        face_locations = await loop.run_in_executor(
            None, face_recognition.face_locations, rgb_small_frame
        )
        face_encodings = await loop.run_in_executor(
            None, face_recognition.face_encodings, rgb_small_frame, face_locations
        )
        
        # List to store results
        face_detections = []
        
        # Loop through each face in the frame
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Scale back up face locations since the frame was scaled to 1/4 size
            scale = 4
            scaled_location = (
                left * scale,
                top * scale,
                right * scale,
                bottom * scale
            )
            
            # Check if this face matches any known face
            best_match_id = None
            best_match_distance = 1.0  # Lower is better, using distance not confidence
            
            for person_id, known_encoding in self.face_embeddings.items():
                # Compute distance between this face and known faces
                face_distances = face_recognition.face_distance([known_encoding], face_encoding)
                distance = face_distances[0]
                
                # Update best match if this is better
                if distance < best_match_distance:
                    best_match_distance = distance
                    best_match_id = person_id
            
            # Convert distance to confidence (1.0 - distance)
            confidence = 1.0 - best_match_distance
            
            # If confidence exceeds threshold, consider it a match
            if confidence >= self.threshold and best_match_id is not None:
                person_name = self.person_details[best_match_id]["name"]
                
                # Add to results
                face_detections.append({
                    "bbox": [
                        scaled_location[0],
                        scaled_location[1],
                        scaled_location[2],
                        scaled_location[3]
                    ],
                    "person_id": best_match_id,
                    "person_name": person_name,
                    "confidence": confidence
                })
                
                # Log face detection event if camera_id is provided
                if camera_id is not None:
                    asyncio.create_task(self._log_face_detection(
                        camera_id=camera_id,
                        person_id=best_match_id,
                        confidence=confidence
                    ))
        
        return face_detections
    
    async def _detect_faces(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Detect faces using OpenCV Haar Cascade"""
        if self.face_cascade is None:
            return []
        
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        loop = asyncio.get_event_loop()
        faces = await loop.run_in_executor(
            None,
            lambda: self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
        )
        
        # List to store results
        face_detections = []
        
        for (x, y, w, h) in faces:
            face_detections.append({
                "bbox": [x, y, x + w, y + h],
                "person_id": None,
                "person_name": "Unknown",
                "confidence": 0.0
            })
        
        return face_detections
    
    async def _log_face_detection(self, camera_id: int, person_id: int, confidence: float):
        """Log a face detection event in the database"""
        try:
            async for session in get_db():
                # Create a new event for the face detection
                await session.execute(
                    insert(Event).values(
                        event_type=EventType.FACE_DETECTED,
                        camera_id=camera_id,
                        person_id=person_id,
                        confidence=confidence
                    )
                )
                await session.commit()
        except Exception as e:
            logger.exception(f"Error logging face detection: {str(e)}")
    
    def set_threshold(self, threshold: float):
        """Update the face recognition threshold"""
        self.threshold = threshold