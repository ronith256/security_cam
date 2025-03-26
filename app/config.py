import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # App settings
    APP_NAME: str = "CCTV Monitoring System"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    PORT: int = int(os.getenv("PORT", "8000"))
    API_URL: str = os.getenv("API_URL", "http://localhost:8000")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./cctv_monitoring.db")
    
    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
        "https://127.0.0.1:8501",
        "*"
    ]
    
    # JWT settings for authentication
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # AI models settings
    MODELS_DIR: str = os.getenv("MODELS_DIR", "models")
    DETECTION_MODEL: str = os.getenv("DETECTION_MODEL", "yolov8n.pt")  # Default to YOLOv8 nano
    FACE_RECOGNITION_MODEL: str = os.getenv("FACE_RECOGNITION_MODEL", "face_recognition_model")
    
    # Video processing settings
    DEFAULT_FPS: int = int(os.getenv("DEFAULT_FPS", "5"))  # Default processing FPS
    TEMPLATE_MATCH_THRESHOLD: float = float(os.getenv("TEMPLATE_MATCH_THRESHOLD", "0.7"))
    FACE_RECOGNITION_THRESHOLD: float = float(os.getenv("FACE_RECOGNITION_THRESHOLD", "0.6"))
    
    # HLS Streaming settings
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")  # Path to ffmpeg executable
    FFMPEG_BUFFER_SIZE: str = os.getenv("FFMPEG_BUFFER_SIZE", "5000k")
    HLS_SEGMENT_TIME: int = int(os.getenv("HLS_SEGMENT_TIME", "1"))  # Segment time in seconds
    HLS_LIST_SIZE: int = int(os.getenv("HLS_LIST_SIZE", "5"))  # Number of segments in playlist
    HLS_TTL: int = int(os.getenv("HLS_TTL", "3600"))  # Time-to-live for sessions in seconds
    
    # Storage settings
    STATIC_DIR: str = "static"
    TEMPLATES_DIR: str = f"{STATIC_DIR}/templates"
    FACES_DIR: str = f"{STATIC_DIR}/faces"
    SNAPSHOTS_DIR: str = f"{STATIC_DIR}/snapshots"
    RECORDINGS_DIR: str = f"{STATIC_DIR}/recordings"
    HLS_DIR: str = f"{STATIC_DIR}/hls"
    
    # Email settings for notifications
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    
    # Telegram settings for notifications
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Ensure required directories exist
os.makedirs(settings.STATIC_DIR, exist_ok=True)
os.makedirs(settings.TEMPLATES_DIR, exist_ok=True)
os.makedirs(settings.FACES_DIR, exist_ok=True)
os.makedirs(settings.SNAPSHOTS_DIR, exist_ok=True)
os.makedirs(settings.RECORDINGS_DIR, exist_ok=True)
os.makedirs(settings.HLS_DIR, exist_ok=True)
os.makedirs(settings.MODELS_DIR, exist_ok=True)