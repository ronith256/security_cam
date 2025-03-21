from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db
from app.api import cameras, templates, people_counting, face_recognition, settings as app_settings

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

# Mount static files for storing images, templates, etc.
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    """Initialize database and load AI models on startup"""
    await init_db()
    # Initialize camera manager
    from app.core.camera_manager import get_camera_manager
    camera_manager = await get_camera_manager()
    await camera_manager.initialize()
    
    # Load AI models
    from app.utils.model_loader import load_models
    await load_models()

@app.on_event("shutdown")
async def shutdown_event():
    """Release resources on shutdown"""
    from app.core.camera_manager import get_camera_manager
    camera_manager = await get_camera_manager()
    await camera_manager.shutdown()

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "CCTV Monitoring System API"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)