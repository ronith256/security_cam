# app/core/template_matching.py

import cv2
import numpy as np
import os
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, insert
from app.config import settings
from app.database import get_db
from app.models.template import Template
from app.models.event import Event, EventType

logger = logging.getLogger(__name__)

class TemplateMatcher:
    """
    Handles template matching to detect predefined patterns in video streams
    """
    def __init__(self, camera_id: int, threshold: float = 0.7):
        self.camera_id = camera_id
        self.threshold = threshold
        self.templates = {}  # {template_id: {"image": image, "name": name, "threshold": threshold}}
        self.base_template = None  # Used for motion detection
        self.scene_threshold = 0.15  # 15% difference threshold for scene change detection
        self.last_db_load = 0
        self.initialized = False
        
        # Initialize
        self._initialize()
    
    def _initialize(self):
        """Initialize the template matcher"""
        try:
            self.initialized = True
            logger.info(f"Template matcher initialized for camera {self.camera_id}")
        except Exception as e:
            logger.exception(f"Failed to initialize template matcher: {str(e)}")
    
    def set_base_template(self, template: np.ndarray):
        """Set the base template for motion detection"""
        self.base_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        logger.info(f"Base template set for camera {self.camera_id}")
    
    def detect_scene_change(self, frame: np.ndarray) -> Tuple[bool, float]:
        """
        Detect if the current frame has significant changes from the base template
        
        Returns:
            Tuple of (changed_flag, change_percentage)
        """
        if self.base_template is None:
            return True, 1.0
        
        # Convert current frame to grayscale
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Resize if the shapes don't match
        if gray_frame.shape != self.base_template.shape:
            gray_frame = cv2.resize(gray_frame, (self.base_template.shape[1], self.base_template.shape[0]))
        
        # Calculate absolute difference
        diff = cv2.absdiff(gray_frame, self.base_template)
        
        # Calculate the average difference percentage
        change_percentage = np.mean(diff) / 255.0
        
        # Check if difference exceeds threshold
        has_changed = change_percentage > self.scene_threshold
        
        return has_changed, change_percentage
    
    async def load_templates(self, force_reload: bool = False):
        """Load templates from the database"""
        # Only reload if it's been more than 60 seconds since last load or forced
        if not force_reload and time.time() - self.last_db_load < 60:
            return
        
        try:
            async for session in get_db():
                # Get templates for this camera
                query = select(Template).where(
                    Template.camera_id == self.camera_id,
                    Template.enabled == True
                )
                result = await session.execute(query)
                templates = result.scalars().all()
                
                # Clear existing templates
                self.templates = {}
                
                # Load each template image
                for template in templates:
                    image_path = template.image_path
                    if not os.path.exists(image_path):
                        logger.warning(f"Template image not found: {image_path}")
                        continue
                    
                    # Load template image
                    template_image = cv2.imread(image_path)
                    if template_image is None:
                        logger.warning(f"Failed to load template image: {image_path}")
                        continue
                    
                    # Initialize base template with the first template if none exists
                    if self.base_template is None:
                        self.set_base_template(template_image)
                    
                    # Store template
                    self.templates[template.id] = {
                        "image": template_image,
                        "name": template.name,
                        "threshold": template.threshold
                    }
            
            self.last_db_load = time.time()
            logger.info(f"Loaded {len(self.templates)} templates for camera {self.camera_id}")
        
        except Exception as e:
            logger.exception(f"Error loading templates: {str(e)}")
    
    async def add_template(self, name: str, image: np.ndarray, description: Optional[str] = None) -> Optional[int]:
        """
        Add a new template
        
        Args:
            name: Template name
            image: Template image
            description: Optional description
            
        Returns:
            Template ID if successful, None otherwise
        """
        try:
            # Generate a unique filename
            timestamp = int(time.time())
            filename = f"template_{self.camera_id}_{timestamp}.jpg"
            filepath = os.path.join(settings.TEMPLATES_DIR, filename)
            
            # Save the image
            cv2.imwrite(filepath, image)
            
            # Add to database
            async for session in get_db():
                new_template = Template(
                    name=name,
                    description=description,
                    image_path=filepath,
                    camera_id=self.camera_id,
                    threshold=self.threshold
                )
                session.add(new_template)
                await session.commit()
                await session.refresh(new_template)
                
                # Add to in-memory cache
                self.templates[new_template.id] = {
                    "image": image,
                    "name": name,
                    "threshold": self.threshold
                }
                
                # Set base template if this is the first one
                if self.base_template is None:
                    self.set_base_template(image)
                
                logger.info(f"Added template '{name}' for camera {self.camera_id}")
                return new_template.id
            
        except Exception as e:
            logger.exception(f"Error adding template: {str(e)}")
            return None
    
    async def match_templates(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Match templates against a frame
        
        Args:
            frame: Video frame
            
        Returns:
            List of template matches with bounding boxes and confidence scores
        """
        if not self.initialized:
            logger.warning("Template matcher not initialized")
            return []
        
        # Check for scene change
        has_changed, change_percentage = self.detect_scene_change(frame)
        
        # Skip template matching if scene hasn't changed significantly
        if not has_changed:
            return []
        
        # Ensure templates are loaded
        await self.load_templates()
        
        # If we have no templates, return empty list
        if not self.templates:
            return []
        
        matches = []
        loop = asyncio.get_event_loop()
        
        try:
            # Convert to grayscale for better matching
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Process each template
            for template_id, template_data in self.templates.items():
                template_image = template_data["image"]
                template_name = template_data["name"]
                template_threshold = template_data.get("threshold", self.threshold)
                
                # Convert template to grayscale
                gray_template = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY)
                
                # Get template dimensions
                h, w = gray_template.shape
                
                # Skip if template is larger than frame
                if h > frame.shape[0] or w > frame.shape[1]:
                    logger.warning(f"Template {template_name} is larger than frame, skipping")
                    continue
                
                # Perform template matching
                result = await loop.run_in_executor(
                    None,
                    lambda: cv2.matchTemplate(gray_frame, gray_template, cv2.TM_CCOEFF_NORMED)
                )
                
                # Find matches above threshold
                locations = np.where(result >= template_threshold)
                
                # Process matches
                for pt in zip(*locations[::-1]):
                    x, y = pt
                    
                    # Check if this match overlaps with existing matches
                    overlap = False
                    for existing_match in matches:
                        if self._check_overlap(
                            (x, y, x+w, y+h),
                            existing_match["bbox"]
                        ):
                            overlap = True
                            break
                    
                    if not overlap:
                        # Get match confidence
                        confidence = float(result[y, x])
                        
                        # Add match
                        matches.append({
                            "template_id": template_id,
                            "template_name": template_name,
                            "confidence": confidence,
                            "bbox": [x, y, x+w, y+h]
                        })
                        
                        # Log template match event
                        asyncio.create_task(self._log_template_match(
                            template_id=template_id,
                            confidence=confidence
                        ))
            
            # Sort matches by confidence (descending)
            matches.sort(key=lambda x: x["confidence"], reverse=True)
            
            return matches
            
        except Exception as e:
            logger.exception(f"Error in template matching: {str(e)}")
            return []
    
    def _check_overlap(self, bbox1: Tuple[int, int, int, int], bbox2: List[int]) -> bool:
        """Check if two bounding boxes overlap significantly"""
        # Convert list to tuple if needed
        if isinstance(bbox2, list):
            bbox2 = tuple(bbox2)
            
        # Calculate intersection area
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        if x2 < x1 or y2 < y1:
            return False
        
        intersection_area = (x2 - x1) * (y2 - y1)
        
        # Calculate area of each bbox
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        # Calculate percentage overlap relative to smaller box
        min_area = min(area1, area2)
        overlap_percentage = intersection_area / min_area
        
        # Threshold for significant overlap (e.g., 50%)
        return overlap_percentage > 0.5
    
    async def _log_template_match(self, template_id: int, confidence: float):
        """Log a template match event in the database"""
        try:
            async for session in get_db():
                # Create a new event for the template match
                await session.execute(
                    insert(Event).values(
                        event_type=EventType.TEMPLATE_MATCHED,
                        camera_id=self.camera_id,
                        template_id=template_id,
                        confidence=confidence
                    )
                )
                await session.commit()
        except Exception as e:
            logger.exception(f"Error logging template match: {str(e)}")
    
    def set_threshold(self, threshold: float):
        """Update the template matching threshold"""
        self.threshold = threshold
    
    def set_scene_threshold(self, threshold: float):
        """Update the scene change detection threshold"""
        self.scene_threshold = threshold