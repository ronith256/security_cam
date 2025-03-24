from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
import logging
from app.config import settings
from app.database import init_db, get_db
from app.api import cameras, templates, people_counting, face_recognition, settings as app_settings
from app.api.webrtc import router as webrtc_router
from app.models.camera import Camera
from app.utils.logging_config import setup_logging

# Setup detailed logging
logger = setup_logging(
    log_file="cctv_monitoring.log", 
    console_level=logging.INFO, 
    file_level=logging.DEBUG
)

# Create the FastAPI app
app = FastAPI(
    title="CCTV Monitoring System",
    description="API for CCTV monitoring with AI capabilities",
    version="1.0.0",
    docs_url="/docs"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(people_counting.router, prefix="/api/people", tags=["people-counting"])
app.include_router(face_recognition.router, prefix="/api/faces", tags=["face-recognition"])
app.include_router(app_settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(webrtc_router, prefix="/api/webrtc", tags=["webrtc"])

# Mount static files for storing images, templates, etc.
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    """Initialize database and essential services on startup"""
    logger.info("Application starting up")
    try:
        # Initialize database
        logger.info("Initializing database")
        await init_db()
        
        # Load AI models
        logger.info("Loading AI models")
        from app.utils.model_loader import load_models
        await load_models()
        
        # Initialize camera manager
        logger.info("Initializing camera manager")
        from app.core.camera_manager import get_camera_manager
        camera_manager = await get_camera_manager()
        await camera_manager.initialize()
        
        # Start processing for all enabled cameras
        logger.info("Starting processing for enabled cameras")
        async for session in get_db():
            # Get all enabled cameras
            query = select(Camera).where(Camera.enabled == True)
            result = await session.execute(query)
            enabled_cameras = result.scalars().all()
            
            logger.info(f"Found {len(enabled_cameras)} enabled cameras")
            
            # Initialize processing for each camera
            for camera in enabled_cameras:
                # Check if camera should be processed for AI
                needs_ai_processing = (
                    camera.detect_people or 
                    camera.count_people or 
                    camera.recognize_faces or 
                    camera.template_matching
                )
                
                if needs_ai_processing:
                    # Add camera to manager and start AI processing
                    logger.info(f"Starting processing for camera {camera.id}: {camera.name}")
                    await camera_manager.add_camera(camera, start_processing=True)
                else:
                    # Add camera to manager for streaming only
                    logger.info(f"Adding camera {camera.id}: {camera.name} for streaming only")
                    await camera_manager.add_camera(camera, start_processing=False)
        
        # Debug log of available cameras
        logger.info(f"Available Cameras: {camera_manager.cameras.keys()}")
        
        logger.info("Application startup complete")
    
    except Exception as e:
        logger.exception(f"Error during startup: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Release resources on shutdown"""
    logger.info("Application shutting down")
    try:
        from app.core.camera_manager import get_camera_manager
        camera_manager = await get_camera_manager()
        await camera_manager.shutdown()
        logger.info("Camera manager shutdown complete")
    except Exception as e:
        logger.exception(f"Error during shutdown: {str(e)}")
    logger.info("Application shutdown complete")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "CCTV Monitoring System API"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    logging.info(f"Starting server on port {settings.PORT}")
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=settings.PORT, 
        reload=settings.DEBUG,
        log_level="info"
    )