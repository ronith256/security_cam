import cv2
import numpy as np
import os
import logging
import asyncio
import torch
import time
from typing import List, Dict, Any, Optional, Tuple

from app.config import settings

# NanoDet imports
try:
    from nanodet.util import load_config, load_model_weight, cfg
    from nanodet.model.arch import build_model
    from nanodet.data.transform import Pipeline
    from nanodet.data.collate import naive_collate
    from nanodet.data.batch_process import stack_batch_img
    NANODET_AVAILABLE = True
except ImportError:
    NANODET_AVAILABLE = False
    logging.warning("NanoDet is not available. Please install it for object detection.")

logger = logging.getLogger(__name__)

class NanoDetector:
    """
    Handles person detection using NanoDet object detection models
    Provides a drop-in replacement for ObjectDetector class
    """
    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.5, config_path: Optional[str] = None):
        self.model_path = model_path or os.path.join(settings.MODELS_DIR, "nanodet-plus-m_320.pth")
        self.config_path = config_path or os.path.join(settings.MODELS_DIR, "nanodet-plus-m_320.yml")
        self.threshold = threshold
        self.model = None
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.pipeline = None
        self.class_names = None
        self.person_class_id = 0  # Default person class ID for COCO dataset
        self.initialized = False

        # Initialize the model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the NanoDet model"""
        try:
            if not NANODET_AVAILABLE:
                logger.error("NanoDet is not available. Please install it for object detection.")
                return
            
            if not os.path.exists(self.model_path) or not os.path.exists(self.config_path):
                logger.error(f"Model or config file not found: {self.model_path}, {self.config_path}")
                return
            
            # Load config
            load_config(cfg, self.config_path)
            self.class_names = cfg.class_names
            
            # Find person class ID
            if "person" in self.class_names:
                self.person_class_id = self.class_names.index("person")
            
            # Build model
            model = build_model(cfg.model)
            
            # Load weights
            ckpt = torch.load(self.model_path, map_location=lambda storage, loc: storage)
            load_model_weight(model, ckpt, logger)
            
            # Check if RepVGG backbone needs deployment
            if cfg.model.arch.backbone.name == "RepVGG":
                deploy_config = cfg.model
                deploy_config.arch.backbone.update({"deploy": True})
                deploy_model = build_model(deploy_config)
                from nanodet.model.backbone.repvgg import repvgg_det_model_convert
                model = repvgg_det_model_convert(model, deploy_model)
            
            # Set model to evaluation mode
            self.model = model.to(self.device).eval()
            
            # Initialize pipeline for preprocessing
            self.pipeline = Pipeline(cfg.data.val.pipeline, cfg.data.val.keep_ratio)
            
            self.initialized = True
            logger.info(f"NanoDet model initialized with {len(self.class_names)} classes. Person class ID: {self.person_class_id}")
            
        except Exception as e:
            logger.exception(f"Failed to initialize NanoDet model: {str(e)}")
    
    async def detect_people(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect people in the frame
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            List of detections with bounding boxes and confidence scores
        """
        if not self.initialized or self.model is None:
            logger.warning("NanoDet model not initialized")
            return []
        
        loop = asyncio.get_event_loop()
        try:
            # Create metadata for inference
            img_info = {"id": 0, "file_name": None}
            height, width = frame.shape[:2]
            img_info["height"] = height
            img_info["width"] = width
            
            # Preprocess image using the same approach as in the original code
            start_time = time.time()
            meta = dict(img_info=img_info, raw_img=frame, img=frame)
            
            # Run preprocessing in executor to avoid blocking
            def preprocess_image():
                meta_processed = self.pipeline(None, meta, cfg.data.val.input_size)
                meta_processed["img"] = torch.from_numpy(meta_processed["img"].transpose(2, 0, 1)).to(self.device)
                meta_processed = naive_collate([meta_processed])
                meta_processed["img"] = stack_batch_img(meta_processed["img"], divisible=32)
                return meta_processed
            
            # Run preprocessing
            meta_processed = await loop.run_in_executor(None, preprocess_image)
            
            # Run inference
            def run_inference():
                with torch.no_grad():
                    results = self.model.inference(meta_processed)
                return results
            
            # Get results
            results = await loop.run_in_executor(None, run_inference)
            dets = results[0]  # Detections for first image in batch
            
            # Process detections
            detections = []
            for label, boxes in enumerate(dets):
                # Skip if not person class
                if label != self.person_class_id:
                    continue
                
                # Process each detection of a person
                for box in boxes:
                    x1, y1, x2, y2, score = box
                    if score > self.threshold:
                        detections.append({
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "confidence": float(score),
                            "class_id": self.person_class_id,
                            "class_name": "person"
                        })
            
            # Log processing time
            processing_time = time.time() - start_time
            if detections:
                logger.debug(f"NanoDet detected {len(detections)} people in {processing_time:.3f}s")
            
            return detections
        
        except Exception as e:
            logger.exception(f"Error in NanoDet person detection: {str(e)}")
            return []
    
    def set_threshold(self, threshold: float):
        """Update the detection threshold"""
        self.threshold = threshold
        logger.info(f"NanoDet detection threshold updated to {threshold}")

# For compatibility with existing code that uses ObjectDetector
class ObjectDetector(NanoDetector):
    """Alias for NanoDetector for drop-in replacement of ObjectDetector"""
    pass