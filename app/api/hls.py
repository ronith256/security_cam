import asyncio
import logging
import os
import subprocess
import time
from typing import Dict, Optional, List
import uuid
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.camera import Camera
from app.config import settings

# Configure logger
logger = logging.getLogger(__name__)

router = APIRouter()

# Store active FFmpeg processes
active_processes: Dict[str, subprocess.Popen] = {}

# Store HLS sessions
hls_sessions: Dict[str, Dict] = {}

# Store camera connections
camera_connections: Dict[int, List[str]] = {}

# Store active cameras to avoid duplicate ffmpeg processes
# Maps camera_id to session_id
active_camera_streams: Dict[int, str] = {}

# Session housekeeping task
async def cleanup_expired_sessions():
    """Periodic task to clean up expired HLS sessions"""
    while True:
        try:
            current_time = time.time()
            expired_sessions = []
            
            # Find expired sessions
            for session_id, session_data in hls_sessions.items():
                # If session is older than TTL and hasn't had activity
                if current_time - session_data.get("last_activity", 0) > settings.HLS_TTL:
                    expired_sessions.append(session_id)
            
            # Clean up expired sessions
            for session_id in expired_sessions:
                await cleanup_process(session_id)
                logger.info(f"Cleaned up expired session {session_id}")
                
        except Exception as e:
            logger.error(f"Error in session cleanup: {str(e)}")
        
        # Run every minute
        await asyncio.sleep(60)


async def cleanup_process(session_id: str):
    """Clean up FFmpeg process for a session"""
    if session_id in active_processes:
        process = active_processes[session_id]
        try:
            # Send SIGTERM signal to gracefully terminate
            process.terminate()
            # Wait up to 3 seconds for termination
            try:
                await asyncio.sleep(3)
                # Check if process is still running
                if process.poll() is None:
                    # Force kill if still running
                    process.kill()
            except Exception as e:
                logger.error(f"Error killing process: {str(e)}")
                
            logger.info(f"Terminated FFmpeg process for session {session_id}")
        except Exception as e:
            logger.error(f"Error terminating FFmpeg process: {str(e)}")
        finally:
            # Remove from active processes
            del active_processes[session_id]
            
    # Clean up session data
    if session_id in hls_sessions:
        # Clean up camera association
        camera_id = hls_sessions[session_id].get("camera_id")
        if camera_id and camera_id in active_camera_streams and active_camera_streams[camera_id] == session_id:
            del active_camera_streams[camera_id]
        
        del hls_sessions[session_id]
        
    # Remove from camera connections
    for camera_id in list(camera_connections.keys()):
        if session_id in camera_connections[camera_id]:
            camera_connections[camera_id].remove(session_id)
            # If no more connections for this camera, clean up the entry
            if not camera_connections[camera_id]:
                del camera_connections[camera_id]
    
    # Clean up HLS files if they exist
    try:
        hls_dir = os.path.join(settings.HLS_DIR, session_id)
        hls_file = os.path.join(settings.HLS_DIR, f"{session_id}.m3u8")
        access_file = os.path.join(settings.HLS_DIR, f"{session_id}.access")
        
        # Remove segment directory if it exists
        if os.path.exists(hls_dir):
            for file in os.listdir(hls_dir):
                os.remove(os.path.join(hls_dir, file))
            os.rmdir(hls_dir)
            
        # Remove playlist file if it exists
        if os.path.exists(hls_file):
            os.remove(hls_file)
            
        # Remove access file if it exists
        if os.path.exists(access_file):
            os.remove(access_file)
    except Exception as e:
        logger.error(f"Error cleaning up HLS files: {str(e)}")


async def start_hls_stream(camera_id: int, rtsp_url: str, session_id: str) -> bool:
    """Start an HLS stream using FFmpeg to convert RTSP to HLS"""
    try:
        # Create output directory if it doesn't exist
        output_dir = settings.HLS_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        # Define unique output paths for this session
        hls_path = os.path.join(output_dir, f"{session_id}.m3u8")
        hls_dir = os.path.join(output_dir, session_id)
        os.makedirs(hls_dir, exist_ok=True)
        
        # Debug log for file paths
        logger.info(f"HLS path: {hls_path}")
        logger.info(f"HLS directory: {hls_dir}")
        logger.info(f"Directory exists: {os.path.exists(hls_dir)}")
        
        # Access controls for HLS
        access_file = os.path.join(output_dir, f"{session_id}.access")
        with open(access_file, 'w') as f:
            f.write(session_id)
        
        # FFmpeg command to convert RTSP to HLS
        # Use hardware acceleration if available (this will fall back to software encoding if hardware not available)
        command = [
            settings.FFMPEG_PATH,
            "-y",                             # Overwrite output files without asking
            "-loglevel", "warning",          # Show warnings and errors for better debugging
            "-rtsp_transport", "tcp",         # Use TCP for RTSP (more reliable)
            "-i", rtsp_url,                   # Input RTSP URL
            "-c:v", "libx264",                # Use H.264 video codec
            "-preset", "ultrafast",           # Use ultrafast preset for low latency
            "-tune", "zerolatency",           # Tune for minimal latency
            "-bufsize", settings.FFMPEG_BUFFER_SIZE,  # Buffer size
            "-c:a", "aac",                    # Audio codec (if any)
            "-ac", "2",                       # Two audio channels
            "-ar", "44100",                   # Audio sample rate
            "-f", "hls",                      # HLS output format
            "-hls_time", str(settings.HLS_SEGMENT_TIME),  # Segment length in seconds
            "-hls_list_size", str(settings.HLS_LIST_SIZE),  # Number of segments to keep in playlist
            "-hls_flags", "delete_segments+independent_segments+discont_start",
            "-hls_segment_type", "mpegts",    # Use MPEG-TS segment type
            "-start_number", "0",             # Start segment numbering at 0
            "-hls_segment_filename", f"{hls_dir}/%d.ts",  # Segment file pattern
            hls_path                          # Output path
        ]
        
        # Start FFmpeg process
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )
        
        # Store process
        active_processes[session_id] = process
        
        # Store session information
        hls_sessions[session_id] = {
            "camera_id": camera_id,
            "start_time": time.time(),
            "last_activity": time.time(),
            "hls_path": hls_path,
            "hls_url": f"/static/hls/{session_id}.m3u8",
            "rtsp_url": rtsp_url
        }
        
        # Add to active camera streams
        active_camera_streams[camera_id] = session_id
        
        # Add to camera connections
        if camera_id not in camera_connections:
            camera_connections[camera_id] = []
        camera_connections[camera_id].append(session_id)
        
        # Wait a bit for FFmpeg to start
        await asyncio.sleep(2)
        
        # Check if process is still running
        if process.poll() is not None:
            # Process terminated
            stderr = process.stderr.read().decode() if process.stderr else "No error output"
            logger.error(f"FFmpeg process terminated: {stderr}")
            await cleanup_process(session_id)
            return False
            
        # Verify HLS files were created
        if not os.path.exists(hls_path):
            logger.error(f"HLS playlist file was not created: {hls_path}")
            # Don't immediately clean up - wait for potential delayed file creation
            
        logger.info(f"Started HLS stream for camera {camera_id} with session {session_id}")
        return True
        
    except Exception as e:
        logger.exception(f"Error starting HLS stream: {str(e)}")
        await cleanup_process(session_id)
        return False


class StreamResponse(BaseModel):
    """Response model for stream start/status"""
    session_id: str
    url: str
    camera_id: int
    start_time: float


@router.post("/start/{camera_id}", response_model=StreamResponse)
async def start_stream(
    camera_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Start an HLS stream for a camera"""
    # Check if camera exists
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Check if this camera already has an active stream
    if camera_id in active_camera_streams:
        session_id = active_camera_streams[camera_id]
        if session_id in hls_sessions:
            # Update last activity
            hls_sessions[session_id]["last_activity"] = time.time()
            session = hls_sessions[session_id]
            
            # Return existing stream URL
            logger.info(f"Reusing existing HLS stream for camera {camera_id}: {session_id}")
            return {
                "session_id": session_id,
                "url": f"{settings.API_URL}{session['hls_url']}",
                "camera_id": camera_id,
                "start_time": session["start_time"]
            }
    
    # Generate session ID for new stream
    session_id = str(uuid.uuid4())
    
    # Start HLS stream
    success = await start_hls_stream(camera_id, camera.rtsp_url, session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start stream")
    
    # Return stream information
    return {
        "session_id": session_id,
        "url": f"{settings.API_URL}/static/hls/{session_id}.m3u8",
        "camera_id": camera_id,
        "start_time": time.time()
    }


@router.post("/keepalive/{session_id}")
async def keepalive(session_id: str):
    """Keep an HLS stream alive"""
    if session_id not in hls_sessions:
        raise HTTPException(status_code=404, detail="Stream session not found")
    
    # Update last activity time
    hls_sessions[session_id]["last_activity"] = time.time()
    
    return {"status": "ok"}


@router.delete("/stop/{session_id}")
async def stop_stream(session_id: str):
    """Stop an HLS stream"""
    if session_id not in hls_sessions:
        raise HTTPException(status_code=404, detail="Stream session not found")
    
    # Clean up the session
    await cleanup_process(session_id)
    
    return {"status": "stopped"}


@router.get("/status/{session_id}", response_model=StreamResponse)
async def stream_status(session_id: str):
    """Get status of an HLS stream"""
    if session_id not in hls_sessions:
        raise HTTPException(status_code=404, detail="Stream session not found")
    
    session = hls_sessions[session_id]
    
    # Update last activity time
    session["last_activity"] = time.time()
    
    return {
        "session_id": session_id,
        "url": f"{settings.API_URL}{session['hls_url']}",
        "camera_id": session["camera_id"],
        "start_time": session["start_time"]
    }


# Start background task to clean up expired sessions
async def start_cleanup_task():
    """Start the background task to clean up expired sessions"""
    asyncio.create_task(cleanup_expired_sessions()) 