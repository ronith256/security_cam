import asyncio
import logging
import os
import subprocess
import time
import sys
from typing import Dict, Optional, List, Tuple
import uuid
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import asyncio

from app.database import get_db
from app.models.camera import Camera
from app.config import settings

# Configure logger
logger = logging.getLogger(__name__)

# Create a specific logger for FFmpeg output
ffmpeg_logger = logging.getLogger("ffmpeg")
ffmpeg_logger.setLevel(logging.DEBUG)

# Create ffmpeg logs directory if it doesn't exist
FFMPEG_LOGS_DIR = "logs/ffmpeg"
os.makedirs(FFMPEG_LOGS_DIR, exist_ok=True)

# Add a file handler for FFmpeg logs
ffmpeg_handler = logging.FileHandler(os.path.join(FFMPEG_LOGS_DIR, "ffmpeg.log"))
ffmpeg_handler.setLevel(logging.DEBUG)
ffmpeg_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ffmpeg_handler.setFormatter(ffmpeg_formatter)
ffmpeg_logger.addHandler(ffmpeg_handler)

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
        session_dir = os.path.join(settings.HLS_DIR, session_id)
        access_file = os.path.join(settings.HLS_DIR, f"{session_id}.access")
        
        # Remove segment directory if it exists
        if os.path.exists(session_dir):
            for file in os.listdir(session_dir):
                os.remove(os.path.join(session_dir, file))
            os.rmdir(session_dir)
            
        # Remove access file if it exists
        if os.path.exists(access_file):
            os.remove(access_file)
    except Exception as e:
        logger.error(f"Error cleaning up HLS files: {str(e)}")


async def read_ffmpeg_output(process, session_id):
    """Read and log FFmpeg's stdout and stderr output"""
    log_file_path = os.path.join(FFMPEG_LOGS_DIR, f"{session_id}.log")
    
    with open(log_file_path, 'w') as log_file:
        # Write header info
        log_file.write(f"=== FFmpeg Output for Session {session_id} ===\n")
        log_file.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        log_file.flush()
        
        # Create async file readers
        async def read_stream(stream, prefix):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                
                # Log to both the session-specific log file and the FFmpeg logger
                log_file.write(f"[{prefix}] {decoded_line}\n")
                log_file.flush()
                
                ffmpeg_logger.debug(f"[{session_id}] {prefix}: {decoded_line}")
        
        # Create tasks to read stdout and stderr
        stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))
        
        # Wait for both tasks to complete
        await asyncio.gather(stdout_task, stderr_task)
        
        # Add a completion message
        completion_msg = f"\nProcess exited with return code: {process.returncode}\n"
        log_file.write(completion_msg)
        ffmpeg_logger.info(f"[{session_id}] {completion_msg}")


async def start_hls_stream(camera_id: int, rtsp_url: str, session_id: str) -> bool:
    """Start an HLS stream using FFmpeg to convert RTSP to HLS"""
    try:
        # Create output directory if it doesn't exist
        output_dir = settings.HLS_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a dedicated directory for this session
        session_dir = os.path.join(output_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        
        # Define playlist path inside the session directory
        playlist_path = os.path.join(session_dir, "index.m3u8")
        
        # Debug log for file paths
        logger.info(f"HLS directory: {session_dir}")
        logger.info(f"Playlist path: {playlist_path}")
        logger.info(f"FFmpeg log will be in: {os.path.join(FFMPEG_LOGS_DIR, f'{session_id}.log')}")
        
        # Access controls for HLS (optional)
        access_file = os.path.join(output_dir, f"{session_id}.access")
        with open(access_file, 'w') as f:
            f.write(session_id)
        
        # Improved FFmpeg command with more explicit transcoding options
        command = [
            settings.FFMPEG_PATH,
            '-loglevel', 'debug',         # Show detailed logs for debugging
            '-rtsp_transport', 'tcp',     # Use TCP for RTSP (more reliable)
            '-i', rtsp_url,               # Input RTSP URL
            '-c:v', 'libx264',            # Re-encode with H.264 instead of copy
            '-profile:v', 'baseline',     # Use baseline profile for compatibility
            '-level', '3.0',              # H.264 level
            '-preset', 'ultrafast',       # Fast encoding
            '-tune', 'zerolatency',       # Minimize latency
            '-r', '15',                   # Output frame rate
            '-g', '30',                   # GOP size 
            '-sc_threshold', '0',         # Disable scene detection
            '-b:v', '1000k',              # Video bitrate
            '-bufsize', '1500k',          # Buffer size
            '-maxrate', '1500k',          # Max bitrate
            '-an',                        # No audio
            '-f', 'hls',                  # HLS output format
            '-hls_time', '2',             # Segment length in seconds
            '-hls_list_size', '3',        # Number of segments in playlist
            '-hls_flags', 'delete_segments+append_list',
            '-hls_segment_type', 'mpegts', # Use MPEG-TS segment type
            '-hls_segment_filename', f"{session_dir}/%d.ts",  # Segment filename pattern
            playlist_path                 # Output playlist path
        ]
        
        # Log the exact command for debugging
        full_command = " ".join(command)
        logger.info(f"Starting FFmpeg with command: {full_command}")
        
        # Start FFmpeg process with pipe for stdout and stderr
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # Unbuffered
            text=False  # Binary mode
        )
        
        # Start a task to read FFmpeg output
        asyncio.create_task(read_ffmpeg_output(process, session_id))
        
        # Store process
        active_processes[session_id] = process
        
        # Store session information
        hls_sessions[session_id] = {
            "camera_id": camera_id,
            "start_time": time.time(),
            "last_activity": time.time(),
            "playlist_path": playlist_path,
            "hls_url": f"/static/hls/{session_id}/index.m3u8",  # Updated URL path
            "rtsp_url": rtsp_url
        }
        
        # Add to active camera streams
        active_camera_streams[camera_id] = session_id
        
        # Add to camera connections
        if camera_id not in camera_connections:
            camera_connections[camera_id] = []
        camera_connections[camera_id].append(session_id)
        
        # Wait a bit for FFmpeg to start
        await asyncio.sleep(5)  # Increased wait time to 5 seconds
            
        # Check if playlist file was created (with retries)
        retry_count = 0
        max_retries = 5
        while not os.path.exists(playlist_path) and retry_count < max_retries:
            await asyncio.sleep(1)
            retry_count += 1
            logger.info(f"Waiting for playlist file to be created (attempt {retry_count}/{max_retries})")
        
        if not os.path.exists(playlist_path):
            logger.error(f"HLS playlist file was not created: {playlist_path}")
            await cleanup_process(session_id)
            return False
            
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
        "url": f"{settings.API_URL}/static/hls/{session_id}/index.m3u8",
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


# Debug endpoint to get FFmpeg logs for a session
@router.get("/logs/{session_id}")
async def get_ffmpeg_logs(session_id: str):
    """Get FFmpeg logs for a specific session"""
    log_path = os.path.join(FFMPEG_LOGS_DIR, f"{session_id}.log")
    
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Logs not found for this session")
    
    try:
        with open(log_path, 'r') as f:
            logs = f.read()
        
        return {"session_id": session_id, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading logs: {str(e)}")


# Start background task to clean up expired sessions
async def start_cleanup_task():
    """Start the background task to clean up expired sessions"""
