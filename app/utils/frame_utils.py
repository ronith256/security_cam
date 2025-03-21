import cv2
import numpy as np
import os
import uuid
import logging
from datetime import datetime
from typing import Tuple, Optional, List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

def resize_frame(frame: np.ndarray, width: Optional[int] = None, height: Optional[int] = None) -> np.ndarray:
    """
    Resize a frame while maintaining aspect ratio
    
    Args:
        frame: Input frame
        width: Target width, if None, will be calculated from height
        height: Target height, if None, will be calculated from width
        
    Returns:
        Resized frame
    """
    if width is None and height is None:
        return frame
    
    h, w = frame.shape[:2]
    
    if width is None:
        aspect = width / float(w)
        dim = (int(w * aspect), height)
    elif height is None:
        aspect = height / float(h)
        dim = (width, int(h * aspect))
    else:
        dim = (width, height)
    
    return cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)

def draw_bounding_boxes(
    frame: np.ndarray, 
    detections: List[Dict[str, Any]], 
    color: Tuple[int, int, int] = (0, 255, 0), 
    thickness: int = 2,
    label_key: str = "class_name"
) -> np.ndarray:
    """
    Draw bounding boxes on a frame
    
    Args:
        frame: Input frame
        detections: List of detections with bounding boxes and labels
        color: BGR color tuple
        thickness: Line thickness
        label_key: Key to use for the label text
        
    Returns:
        Frame with bounding boxes
    """
    result = frame.copy()
    
    for detection in detections:
        if "bbox" not in detection:
            continue
            
        bbox = detection["bbox"]
        if len(bbox) != 4:
            continue
            
        x1, y1, x2, y2 = bbox
        
        # Draw rectangle
        cv2.rectangle(result, (x1, y1), (x2, y2), color, thickness)
        
        # Draw label if available
        if label_key in detection:
            label = str(detection[label_key])
            if "confidence" in detection:
                label = f"{label}: {detection['confidence']:.2f}"
                
            cv2.putText(
                result, 
                label, 
                (x1, y1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                color, 
                thickness
            )
    
    return result

def draw_line(
    frame: np.ndarray, 
    position: float, 
    color: Tuple[int, int, int] = (0, 0, 255), 
    thickness: int = 2,
    horizontal: bool = True
) -> np.ndarray:
    """
    Draw a virtual line on a frame
    
    Args:
        frame: Input frame
        position: Relative position (0-1)
        color: BGR color tuple
        thickness: Line thickness
        horizontal: If True, draw horizontal line, otherwise vertical
        
    Returns:
        Frame with line
    """
    result = frame.copy()
    h, w = result.shape[:2]
    
    if horizontal:
        y = int(h * position)
        cv2.line(result, (0, y), (w, y), color, thickness)
    else:
        x = int(w * position)
        cv2.line(result, (x, 0), (x, h), color, thickness)
    
    return result

def draw_text_overlay(
    frame: np.ndarray, 
    text: str, 
    position: Tuple[int, int] = (10, 30), 
    color: Tuple[int, int, int] = (255, 255, 255), 
    thickness: int = 2,
    font_scale: float = 0.7
) -> np.ndarray:
    """
    Draw text overlay on a frame
    
    Args:
        frame: Input frame
        text: Text to draw
        position: (x, y) position
        color: BGR color tuple
        thickness: Text thickness
        font_scale: Font scale
        
    Returns:
        Frame with text
    """
    result = frame.copy()
    
    cv2.putText(
        result, 
        text, 
        position, 
        cv2.FONT_HERSHEY_SIMPLEX, 
        font_scale, 
        color, 
        thickness
    )
    
    return result

def save_frame(frame: np.ndarray, filename: Optional[str] = None, directory: Optional[str] = None) -> str:
    """
    Save a frame to disk
    
    Args:
        frame: Frame to save
        filename: Optional filename, will generate if None
        directory: Optional directory, defaults to snapshots directory
        
    Returns:
        Path to saved frame
    """
    if directory is None:
        directory = settings.SNAPSHOTS_DIR
    
    os.makedirs(directory, exist_ok=True)
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    
    filepath = os.path.join(directory, filename)
    
    try:
        cv2.imwrite(filepath, frame)
        return filepath
    except Exception as e:
        logger.exception(f"Error saving frame: {str(e)}")
        return ""

def overlay_timestamp(
    frame: np.ndarray, 
    timestamp: Optional[datetime] = None,
    position: Tuple[int, int] = None,
    color: Tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.5,
    thickness: int = 1
) -> np.ndarray:
    """
    Add timestamp overlay to a frame
    
    Args:
        frame: Input frame
        timestamp: Datetime to display, uses current time if None
        position: (x, y) position, defaults to bottom right
        color: BGR color tuple
        font_scale: Font scale
        thickness: Text thickness
        
    Returns:
        Frame with timestamp
    """
    result = frame.copy()
    
    if timestamp is None:
        timestamp = datetime.now()
    
    text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    
    if position is None:
        h, w = result.shape[:2]
        # Default to bottom right with some padding
        position = (w - 150, h - 20)
    
    cv2.putText(
        result, 
        text, 
        position, 
        cv2.FONT_HERSHEY_SIMPLEX, 
        font_scale, 
        color, 
        thickness
    )
    
    return result

def extract_roi(frame: np.ndarray, bbox: List[int]) -> np.ndarray:
    """
    Extract a region of interest from a frame
    
    Args:
        frame: Input frame
        bbox: Bounding box [x1, y1, x2, y2]
        
    Returns:
        ROI as numpy array
    """
    if len(bbox) != 4:
        raise ValueError("Bounding box must have 4 values [x1, y1, x2, y2]")
    
    x1, y1, x2, y2 = bbox
    
    # Ensure within frame bounds
    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w-1))
    y1 = max(0, min(y1, h-1))
    x2 = max(0, min(x2, w-1))
    y2 = max(0, min(y2, h-1))
    
    return frame[y1:y2, x1:x2]

def add_motion_blur(frame: np.ndarray, kernel_size: int = 15) -> np.ndarray:
    """
    Add motion blur effect to a frame (for testing)
    
    Args:
        frame: Input frame
        kernel_size: Size of the blur kernel
        
    Returns:
        Blurred frame
    """
    # Create the motion blur kernel
    kernel = np.zeros((kernel_size, kernel_size))
    kernel[int((kernel_size-1)/2), :] = np.ones(kernel_size)
    kernel = kernel / kernel_size
    
    # Apply the kernel
    return cv2.filter2D(frame, -1, kernel)

def enhance_contrast(frame: np.ndarray, clip_limit: float = 2.0, tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """
    Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
    
    Args:
        frame: Input frame
        clip_limit: Contrast limit
        tile_grid_size: Grid size for adaptive equalization
        
    Returns:
        Enhanced frame
    """
    # Convert to LAB color space
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    
    # Split the LAB channels
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE to the L channel
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    enhanced_l = clahe.apply(l)
    
    # Merge the channels back
    enhanced_lab = cv2.merge((enhanced_l, a, b))
    
    # Convert back to BGR
    return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

def denoise_frame(frame: np.ndarray, strength: int = 7) -> np.ndarray:
    """
    Apply non-local means denoising to a frame
    
    Args:
        frame: Input frame
        strength: Denoising strength
        
    Returns:
        Denoised frame
    """
    return cv2.fastNlMeansDenoisingColored(frame, None, strength, strength, 7, 21)

def detect_edges(frame: np.ndarray, threshold1: int = 100, threshold2: int = 200) -> np.ndarray:
    """
    Detect edges in a frame using Canny edge detector
    
    Args:
        frame: Input frame
        threshold1: First threshold for the hysteresis procedure
        threshold2: Second threshold for the hysteresis procedure
        
    Returns:
        Edge map
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Apply Canny edge detector
    edges = cv2.Canny(blurred, threshold1, threshold2)
    
    # Convert back to BGR for consistent return type
    return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

def overlay_grid(frame: np.ndarray, grid_size: int = 50, color: Tuple[int, int, int] = (0, 255, 0), thickness: int = 1) -> np.ndarray:
    """
    Overlay a grid on a frame
    
    Args:
        frame: Input frame
        grid_size: Size of grid squares in pixels
        color: BGR color tuple
        thickness: Line thickness
        
    Returns:
        Frame with grid overlay
    """
    result = frame.copy()
    h, w = result.shape[:2]
    
    # Draw vertical lines
    for x in range(0, w, grid_size):
        cv2.line(result, (x, 0), (x, h), color, thickness)
    
    # Draw horizontal lines
    for y in range(0, h, grid_size):
        cv2.line(result, (0, y), (w, y), color, thickness)
    
    return result