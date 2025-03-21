import cv2
import numpy as np
import asyncio
import logging
import time
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from sqlalchemy import select, insert
from app.database import get_db
from app.models.event import Event, EventType

logger = logging.getLogger(__name__)

class PeopleCounter:
    """
    Tracks people movement to count entries and exits from a room.
    Uses object tracking and a virtual line to determine direction.
    """
    def __init__(self, camera_id: int, line_position: float = 0.5, max_disappeared: int = 40):
        self.camera_id = camera_id
        self.line_position = line_position  # Relative position of virtual line (0-1)
        self.max_disappeared = max_disappeared
        
        # Tracking variables
        self.next_object_id = 0
        self.objects = {}  # {object_id: centroid}
        self.disappeared = defaultdict(int)  # {object_id: disappeared_frames}
        self.crossed = defaultdict(lambda: {"direction": None, "counted": False})
        
        # Counters
        self.entry_count = 0
        self.exit_count = 0
        self.current_count = 0
        
        # Last update timestamp
        self.last_update = time.time()
        
        # Line position (will be calculated for each frame)
        self.line_y = None
        
        # Tracker
        self.tracker = cv2.TrackerKCF_create
    
    async def process_frame(
        self, 
        frame: np.ndarray, 
        detections: List[Dict[str, Any]]
    ) -> Tuple[int, int, int]:
        """
        Process a frame to track and count people
        
        Args:
            frame: Video frame
            detections: List of people detections with bounding boxes
            
        Returns:
            Tuple of (entry_count, exit_count, current_count)
        """
        height, width = frame.shape[:2]
        
        # Calculate line position if not already set
        if self.line_y is None:
            self.line_y = int(height * self.line_position)
        
        # Extract centroids from detections
        centroids = []
        rects = []
        for detection in detections:
            bbox = detection["bbox"]
            x1, y1, x2, y2 = bbox
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            centroids.append((cx, cy))
            rects.append((x1, y1, x2 - x1, y2 - y1))
        
        # If we have no objects, register all centroids
        if len(self.objects) == 0:
            for centroid in centroids:
                self._register_object(centroid)
        
        # Otherwise, try to match current centroids to existing objects
        else:
            # Get current object IDs and centroids
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())
            
            # Compute distances between each pair of existing centroids and new centroids
            D = self._compute_distances(object_centroids, centroids)
            
            # Match centroids to minimize distance cost
            rows, cols = self._match_centroids(D)
            
            # Keep track of which object IDs and centroids we've already examined
            used_rows = set()
            used_cols = set()
            
            # Loop over the matched pairs
            for (row, col) in zip(rows, cols):
                # Skip if we've already examined this pair
                if row in used_rows or col in used_cols:
                    continue
                
                # Get the object ID and update its centroid
                object_id = object_ids[row]
                self.objects[object_id] = centroids[col]
                self.disappeared[object_id] = 0
                
                # Check if object crossed the line
                self._check_crossing(object_id, centroids[col])
                
                # Mark this row and column as used
                used_rows.add(row)
                used_cols.add(col)
            
            # Find rows we haven't used yet (missing objects)
            unused_rows = set(range(D.shape[0])).difference(used_rows)
            
            # Update the disappeared count for missing objects
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                
                # Deregister if the object has been missing for too long
                if self.disappeared[object_id] > self.max_disappeared:
                    self._deregister_object(object_id)
            
            # Find columns we haven't used yet (new objects)
            unused_cols = set(range(D.shape[1])).difference(used_cols)
            
            # Register new objects
            for col in unused_cols:
                self._register_object(centroids[col])
        
        # Update current count
        self.current_count = max(0, self.entry_count - self.exit_count)
        
        # Save entry/exit events if count has changed
        if time.time() - self.last_update > 1.0:  # Limit database updates to once per second
            await self._save_count_event()
            self.last_update = time.time()
        
        return self.entry_count, self.exit_count, self.current_count
    
    def _register_object(self, centroid: Tuple[int, int]):
        """Register a new object with the next available ID"""
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1
    
    def _deregister_object(self, object_id: int):
        """Deregister an object that has disappeared"""
        del self.objects[object_id]
        del self.disappeared[object_id]
        if object_id in self.crossed:
            del self.crossed[object_id]
    
    def _compute_distances(self, object_centroids: List[Tuple[int, int]], centroids: List[Tuple[int, int]]) -> np.ndarray:
        """Compute the distance between each pair of centroids"""
        if not object_centroids or not centroids:
            return np.empty((0, 0))
        
        # Compute Euclidean distance
        D = np.zeros((len(object_centroids), len(centroids)))
        for i, object_centroid in enumerate(object_centroids):
            for j, centroid in enumerate(centroids):
                D[i, j] = np.sqrt(
                    (object_centroid[0] - centroid[0]) ** 2 + 
                    (object_centroid[1] - centroid[1]) ** 2
                )
        return D
    
    def _match_centroids(self, D: np.ndarray) -> Tuple[List[int], List[int]]:
        """Match centroids to minimize distance cost using Hungarian algorithm"""
        rows, cols = [], []
        
        if D.size == 0:
            return rows, cols
        
        # Using a simple greedy algorithm for smaller matrices
        if D.shape[0] < 10 and D.shape[1] < 10:
            # Assign each row to nearest column
            for i in range(D.shape[0]):
                if D.shape[1] > 0:
                    j = np.argmin(D[i, :])
                    rows.append(i)
                    cols.append(j)
                    # Mark this column as used by setting to infinity
                    D[:, j] = np.inf
        else:
            # Use Hungarian algorithm for larger matrices
            try:
                from scipy.optimize import linear_sum_assignment
                rows, cols = linear_sum_assignment(D)
            except ImportError:
                # Fallback to greedy algorithm
                for i in range(D.shape[0]):
                    if D.shape[1] > 0:
                        j = np.argmin(D[i, :])
                        rows.append(i)
                        cols.append(j)
                        D[:, j] = np.inf
        
        return rows, cols
    
    def _check_crossing(self, object_id: int, centroid: Tuple[int, int]):
        """Check if an object crosses the virtual line"""
        if object_id not in self.crossed:
            # Initialize crossed state for new objects
            self.crossed[object_id] = {"direction": None, "counted": False}
        
        # Get object's position relative to the line
        _, cy = centroid
        crossed_state = self.crossed[object_id]
        previous_direction = crossed_state["direction"]
        
        # Determine current direction
        if cy < self.line_y:
            current_direction = "above"
        else:
            current_direction = "below"
        
        # Update direction
        crossed_state["direction"] = current_direction
        
        # If direction changed and we haven't counted this object yet
        if (
            previous_direction is not None and 
            previous_direction != current_direction and 
            not crossed_state["counted"]
        ):
            # Count entry (crossing from below to above)
            if previous_direction == "below" and current_direction == "above":
                self.exit_count += 1
                crossed_state["counted"] = True
            
            # Count exit (crossing from above to below)
            elif previous_direction == "above" and current_direction == "below":
                self.entry_count += 1
                crossed_state["counted"] = True
    
    async def _save_count_event(self):
        """Save a count event to the database"""
        try:
            async for session in get_db():
                # Create a new event for the occupancy change
                await session.execute(
                    insert(Event).values(
                        event_type=EventType.OCCUPANCY_CHANGED,
                        camera_id=self.camera_id,
                        occupancy_count=self.current_count
                    )
                )
                await session.commit()
        except Exception as e:
            logger.exception(f"Error saving count event: {str(e)}")
    
    def reset_counts(self):
        """Reset all counters to zero"""
        self.entry_count = 0
        self.exit_count = 0
        self.current_count = 0
        
    def set_line_position(self, position: float):
        """Set the virtual line position (0-1)"""
        self.line_position = max(0.0, min(1.0, position))
        self.line_y = None  # Will be recalculated on next frame