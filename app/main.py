from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
import logging
from app.config import settings
from app.database import init_db, get_db
from app.api import cameras, templates, people_counting, face_recognition, settings as app_settings
from app.api import notifications, hls
from app.models.camera import Camera
from app.utils.logging_config import setup_logging
from app.services.notification_service import get_notification_service
from starlette.responses import FileResponse

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
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(hls.router, prefix="/api/hls", tags=["hls"])

# Mount static files for storing images, templates, snapshots, etc.
# Add CORS headers for static files
class StaticFilesCORS(StaticFiles):
    """Custom StaticFiles class that adds CORS headers"""
    async def __call__(self, scope, receive, send):
        """Add CORS headers to static file responses"""
        # Add CORS headers to the response
        async def wrapped_send(message):
            if message['type'] == 'http.response.start':
                # Add CORS headers
                headers = list(message.get('headers', []))
                headers.append((b'Access-Control-Allow-Origin', b'*'))
                headers.append((b'Access-Control-Allow-Methods', b'GET, HEAD, OPTIONS'))
                headers.append((b'Access-Control-Allow-Headers', b'*'))
                message['headers'] = headers
            await send(message)
            
        await super().__call__(scope, receive, wrapped_send)

# Mount custom static files middleware with CORS support
app.mount("/static", StaticFilesCORS(directory="static"), name="static")

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
        
        # Initialize notification service
        logger.info("Initializing notification service")
        notification_service = await get_notification_service()
        
        # Start HLS cleanup task
        logger.info("Starting HLS session cleanup task")
        from app.api.hls import start_cleanup_task
        await start_cleanup_task()
        
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