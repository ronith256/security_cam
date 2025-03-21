import os
import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# URLs for downloading pre-trained models
MODEL_URLS = {
    "yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
    "yolov8n.onnx": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.onnx",
    "haarcascade_frontalface_default.xml": "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml",
    "shape_predictor_68_face_landmarks.dat": "https://github.com/davisking/dlib-models/raw/master/shape_predictor_68_face_landmarks.dat.bz2",
}

async def load_models():
    """
    Load or download required AI models
    """
    logger.info("Loading AI models...")
    
    # Ensure models directory exists
    os.makedirs(settings.MODELS_DIR, exist_ok=True)
    
    # Load object detection model
    detection_model_path = os.path.join(settings.MODELS_DIR, settings.DETECTION_MODEL)
    if not os.path.exists(detection_model_path):
        logger.info(f"Detection model not found at {detection_model_path}")
        await download_model(settings.DETECTION_MODEL)
    
    # Load face recognition model if needed
    if settings.FACE_RECOGNITION_MODEL == "face_recognition_model":
        # For face_recognition library, we need the Haar cascade
        cascade_path = os.path.join(settings.MODELS_DIR, "haarcascade_frontalface_default.xml")
        if not os.path.exists(cascade_path):
            logger.info(f"Face cascade not found at {cascade_path}")
            await download_model("haarcascade_frontalface_default.xml")
    else:
        face_model_path = os.path.join(settings.MODELS_DIR, settings.FACE_RECOGNITION_MODEL)
        if not os.path.exists(face_model_path):
            logger.info(f"Face recognition model not found at {face_model_path}")
            await download_model(settings.FACE_RECOGNITION_MODEL)
    
    logger.info("AI models loaded successfully")

async def download_model(model_name: str) -> bool:
    """
    Download a pre-trained model
    
    Args:
        model_name: Name of the model to download
        
    Returns:
        Success flag
    """
    if model_name not in MODEL_URLS:
        logger.error(f"Unknown model: {model_name}")
        return False
    
    url = MODEL_URLS[model_name]
    output_path = os.path.join(settings.MODELS_DIR, model_name)
    
    logger.info(f"Downloading model {model_name} from {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download model {model_name}, status: {response.status}")
                    return False
                
                data = await response.read()
                
                # Handle bz2 compressed files
                if url.endswith('.bz2'):
                    import bz2
                    data = bz2.decompress(data)
                    output_path = output_path[:-4]  # Remove .bz2 extension
                
                # Save the model
                with open(output_path, 'wb') as f:
                    f.write(data)
                
                logger.info(f"Model {model_name} downloaded to {output_path}")
                return True
                
    except Exception as e:
        logger.exception(f"Error downloading model {model_name}: {str(e)}")
        return False

def get_model_path(model_name: str) -> str:
    """Get the full path to a model file"""
    return os.path.join(settings.MODELS_DIR, model_name)