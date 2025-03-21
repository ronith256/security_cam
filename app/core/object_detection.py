import cv2
import numpy as np
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings

# Try to import ultralytics if installed
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logging.warning("Ultralytics YOLO not available. Using OpenCV DNN for object detection.")

logger = logging.getLogger(__name__)

class ObjectDetector:
    """
    Handles person detection using YOLOv8 or other object detection models
    """
    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.5):
        self.model_path = model_path or os.path.join(settings.MODELS_DIR, settings.DETECTION_MODEL)
        self.threshold = threshold
        self.model = None
        self.initialized = False
        self.person_class_id = 0  # YOLO uses 0 for person class

        # Initialize the model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the object detection model"""
        try:
            if YOLO_AVAILABLE:
                # Use YOLOv8 from ultralytics
                logger.info(f"Loading YOLOv8 model from {self.model_path}")
                self.model = YOLO(self.model_path)
                self.initialized = True
            else:
                # Fallback to OpenCV DNN
                logger.info("Using OpenCV DNN with YOLO model")
                self._initialize_opencv_dnn()
        except Exception as e:
            logger.exception(f"Failed to initialize object detection model: {str(e)}")
    
    def _initialize_opencv_dnn(self):
        """Initialize OpenCV DNN with YOLO model"""
        try:
            # Check if we have a YOLOv8 ONNX model
            onnx_path = self.model_path
            if not onnx_path.endswith(".onnx"):
                # Convert .pt to .onnx if needed or use a default model
                onnx_path = os.path.join(settings.MODELS_DIR, "yolov8n.onnx")
                if not os.path.exists(onnx_path):
                    logger.warning(f"ONNX model not found at {onnx_path}. Using OpenCV DNN models.")
                    # Use pre-trained models available in OpenCV
                    self.model = cv2.dnn.readNetFromDarknet(
                        os.path.join(settings.MODELS_DIR, "yolov4.cfg"),
                        os.path.join(settings.MODELS_DIR, "yolov4.weights")
                    )
                    self.initialized = True
                    return
            
            # Load ONNX model with OpenCV
            self.model = cv2.dnn.readNetFromONNX(onnx_path)
            self.initialized = True
        except Exception as e:
            logger.exception(f"Failed to initialize OpenCV DNN model: {str(e)}")
    
    async def detect_people(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect people in the frame
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            List of detections with bounding boxes and confidence scores
        """
        if not self.initialized or self.model is None:
            logger.warning("Object detector not initialized")
            return []
        
        loop = asyncio.get_event_loop()
        try:
            if YOLO_AVAILABLE and isinstance(self.model, YOLO):
                # Use YOLOv8 from ultralytics
                results = await loop.run_in_executor(
                    None, 
                    lambda: self.model(frame, classes=[self.person_class_id], conf=self.threshold)
                )
                
                detections = []
                for result in results:
                    boxes = result.boxes.cpu().numpy()
                    for i, box in enumerate(boxes):
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        confidence = float(box.conf[0])
                        detections.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": confidence,
                            "class_id": self.person_class_id,
                            "class_name": "person"
                        })
                
                return detections
            
            else:
                # Use OpenCV DNN
                return await self._detect_with_opencv_dnn(frame)
        
        except Exception as e:
            logger.exception(f"Error in person detection: {str(e)}")
            return []
    
    async def _detect_with_opencv_dnn(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Use OpenCV DNN for object detection"""
        height, width = frame.shape[:2]
        
        # Create blob from image
        blob = cv2.dnn.blobFromImage(
            frame, 1/255.0, (416, 416), swapRB=True, crop=False
        )
        
        # Set input and run forward pass
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.model.setInput(blob))
        outputs = await loop.run_in_executor(None, self.model.forward)
        
        # Process the outputs
        detections = []
        for output in outputs:
            for detection in output:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]
                
                # Filter for person class (class 0) and confidence threshold
                if class_id == self.person_class_id and confidence > self.threshold:
                    # YOLO format is center_x, center_y, width, height
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)
                    
                    # Rectangle coordinates
                    x1 = max(0, int(center_x - w/2))
                    y1 = max(0, int(center_y - h/2))
                    x2 = min(width, int(center_x + w/2))
                    y2 = min(height, int(center_y + h/2))
                    
                    detections.append({
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(confidence),
                        "class_id": class_id,
                        "class_name": "person"
                    })
        
        return detections
    
    def set_threshold(self, threshold: float):
        """Update the detection threshold"""
        self.threshold = threshold