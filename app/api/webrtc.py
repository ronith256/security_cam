# app/api/webrtc.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, websockets
import json
import asyncio
import cv2
import base64
import logging
from typing import Dict, Any, List, Set
import os
import uuid
import gc
import time
import weakref
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate
from aiortc.contrib.media import MediaBlackhole, MediaRelay
from av import VideoFrame
import fractions
import numpy as np
import threading
from datetime import datetime

from app.core.camera_manager import get_camera_manager
from app.database import get_db
from app.models.camera import Camera
from app.config import settings

logger = logging.getLogger(__name__)

# Relay for sharing a single webcam feed (with memory management)
class ManagedMediaRelay(MediaRelay):
    def __init__(self):
        super().__init__()
        # Track when tracks were last used
        self.track_last_used = {}
        # Maximum tracks to keep in memory
        self.max_tracks = 20
        # Cleanup interval in seconds
        self.cleanup_interval = 60
        self.last_cleanup = time.time()
    
    def subscribe(self, track):
        # Perform cleanup if needed
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_tracks()
            self.last_cleanup = current_time
        
        # Track usage time
        result = super().subscribe(track)
        self.track_last_used[id(result)] = current_time
        return result
    
    def _cleanup_old_tracks(self):
        """Remove old tracks to prevent memory leaks"""
        if len(self.track_last_used) <= self.max_tracks:
            return
        
        # Sort tracks by last used time
        sorted_tracks = sorted(self.track_last_used.items(), key=lambda x: x[1])
        
        # Remove oldest tracks beyond our limit
        tracks_to_remove = sorted_tracks[:len(sorted_tracks) - self.max_tracks]
        for track_id, _ in tracks_to_remove:
            self.track_last_used.pop(track_id, None)
        
        # Force garbage collection
        gc.collect()
        logger.info(f"Cleaned up {len(tracks_to_remove)} old media tracks")

# Create managed relay instance
relay = ManagedMediaRelay()

# In-memory storage for peer connections and video tracks
pcs = set()
camera_tracks = {}  # Map of camera_id to VideoStreamTrack
pc_timestamps = {}  # Track when peer connections were created

class RTSPVideoStreamTrack(MediaStreamTrack):
    """
    A video stream track that captures from a camera processor and converts to frames.
    """
    kind = "video"
    
    def __init__(self, camera_id: int, high_quality: bool = True):
        super().__init__()
        self.camera_id = camera_id
        self.high_quality = high_quality
        self._running = True
        self._frame_counter = 0
        self._last_frame_time = 0
        self._lock = threading.Lock()
        self._current_frame = None
        
        # Add frame caching to reduce processing load
        self._cached_video_frame = None
        self._cache_expiry = 0.1  # 100ms cache validity
        self._last_cache_update = 0
        
        # Fallback frame if needed (blank frame)
        self._fallback_frame = None
        
        # Create a standard black frame as fallback
        self._create_fallback_frame()
        
        # Limit resolution based on high_quality flag
        self._frame_size = (1280, 720) if high_quality else (640, 360)
        
        # Track reference count to avoid memory leaks
        self._ref_count = 1  # Start with 1 reference
        
        # Start frame capture thread
        self._start_capture_thread()

    def _create_fallback_frame(self):
        """Create a fallback frame with a text overlay"""
        width, height = (640, 360)
        frame = np.zeros((height, width, 3), np.uint8)
        
        # Add text overlay
        font = cv2.FONT_HERSHEY_SIMPLEX
        text = f"Camera {self.camera_id} - No Stream Available"
        text_size = cv2.getTextSize(text, font, 1, 2)[0]
        text_x = (width - text_size[0]) // 2
        text_y = (height + text_size[1]) // 2
        cv2.putText(frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2)
        self._fallback_frame = frame    

    def _start_capture_thread(self):
        """Start a thread to capture frames from the camera processor"""
        thread = threading.Thread(target=self._capture_frames_loop, daemon=True)
        thread.start()
    
    def _capture_frames_loop(self):
        """Background thread to capture frames"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            while self._running:
                frame = loop.run_until_complete(self._get_frame())
                if frame is not None:
                    with self._lock:
                        self._current_frame = frame
                
                # Limit capture rate to avoid excessive CPU usage
                # Adjust based on quality - high quality gets more frames
                capture_interval = 1/30 if self.high_quality else 1/15  # 30 or 15 fps
                time.sleep(max(0, capture_interval - (time.time() - self._last_frame_time)))
                self._last_frame_time = time.time()
        except Exception as e:
            logger.exception(f"Error in capture thread for camera {self.camera_id}: {str(e)}")
        finally:
            loop.close()
    
    def _capture_frames_loop(self):
        """Background thread to capture frames"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            while self._running:
                frame = loop.run_until_complete(self._get_frame())
                if frame is not None:
                    with self._lock:
                        self._current_frame = frame
                
                # Limit capture rate to avoid excessive CPU usage
                # Adjust based on quality - high quality gets more frames
                capture_interval = 1/30 if self.high_quality else 1/15  # 30 or 15 fps
                time.sleep(max(0, capture_interval - (time.time() - self._last_frame_time)))
                self._last_frame_time = time.time()
        except Exception as e:
            logger.exception(f"Error in capture thread for camera {self.camera_id}: {str(e)}")
        finally:
            loop.close()
    
    async def _get_frame(self):
        """Get a frame from the camera processor"""
        try:
            camera_manager = await get_camera_manager()
            
            # First, make sure the camera is connected and processing
            await camera_manager.ensure_camera_connected(self.camera_id)
            
            # Then try to get a frame
            frame_data = await camera_manager.get_frame(self.camera_id)
            
            if frame_data:
                frame, timestamp = frame_data
                
                # Resize to target resolution to control memory usage
                frame = cv2.resize(frame, self._frame_size)
                
                # Add timestamp overlay
                time_stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(
                    frame,
                    time_stamp,
                    (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    1
                )
                
                return frame
            else:
                # If no frame but we have a fallback, use it
                if self._fallback_frame is not None:
                    return self._fallback_frame.copy()
        except Exception as e:
            if "No frame data available" not in str(e):  # Don't log expected message
                logger.error(f"Error getting frame for camera {self.camera_id}: {str(e)}")
        
        # Return fallback frame if available, otherwise None
        if self._fallback_frame is not None:
            return self._fallback_frame.copy()
        return None
    
    async def recv(self):
        """Return a frame of video"""
        current_time = time.time()
        
        # Check if we can use the cached frame
        if (self._cached_video_frame is not None and 
            current_time - self._last_cache_update < self._cache_expiry):
            return self._cached_video_frame.copy()
        
        # Get a new frame
        frame = None
        with self._lock:
            frame = self._current_frame
        
        if frame is None:
            # If no frame yet, return blank frame (black image)
            pts, time_base = await self.next_timestamp()
            width, height = self._frame_size
            frame = np.zeros((height, width, 3), np.uint8)
            
            # Add "No signal" text
            font = cv2.FONT_HERSHEY_SIMPLEX
            text = f"Camera {self.camera_id} - No Signal"
            text_size = cv2.getTextSize(text, font, 1, 2)[0]
            text_x = (width - text_size[0]) // 2
            text_y = (height + text_size[1]) // 2
            cv2.putText(frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2)
        else:
            pts, time_base = await self.next_timestamp()
        
        # Convert from OpenCV BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Create VideoFrame
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        
        # Update cache
        self._cached_video_frame = video_frame
        self._last_cache_update = current_time
        
        # Increment frame counter
        self._frame_counter += 1
        
        return video_frame
    
    async def next_timestamp(self):
        """Calculate the timestamp for the next frame"""
        if hasattr(self, "_timestamp"):
            self._timestamp += 1
        else:
            self._timestamp = 0
        
        # Use appropriate framerate based on quality
        framerate = 30 if self.high_quality else 15
        return self._timestamp, fractions.Fraction(1, framerate)
    
    def add_ref(self):
        """Increment reference count"""
        self._ref_count += 1
        return self
    
    def remove_ref(self):
        """Decrement reference count and stop if zero"""
        self._ref_count -= 1
        if self._ref_count <= 0:
            self.stop()
    
    def stop(self):
        """Stop the track"""
        if self._running:
            self._running = False
            self._current_frame = None
            self._cached_video_frame = None
            super().stop()
            logger.info(f"Stopped video track for camera {self.camera_id}")

# Regular cleanup task for peer connections
async def periodic_pc_cleanup():
    """Periodically clean up old peer connections to prevent memory leaks"""
    while True:
        try:
            now = time.time()
            expired_pcs = []
            
            # Find expired peer connections (older than 5 minutes with no activity)
            for pc in pcs:
                pc_id = id(pc)
                if pc_id in pc_timestamps and now - pc_timestamps[pc_id] > 300:  # 5 minutes
                    expired_pcs.append(pc)
            
            # Close expired peer connections
            for pc in expired_pcs:
                pc_id = id(pc)
                logger.info(f"Closing expired peer connection {pc_id}")
                await pc.close()
                if pc in pcs:
                    pcs.remove(pc)
                pc_timestamps.pop(pc_id, None)
            
            # Log status
            if expired_pcs:
                logger.info(f"Cleaned up {len(expired_pcs)} expired peer connections, {len(pcs)} remaining")
                
                # Force garbage collection after cleanup
                gc.collect()
        
        except Exception as e:
            logger.exception(f"Error in peer connection cleanup: {str(e)}")
        
        # Run every minute
        await asyncio.sleep(60)

class WebRTCManager:
    """
    Manages WebRTC connections and signaling
    """
    def __init__(self):
        self.peer_connections = {}  # camera_id -> [peer_connections]
        self.camera_tracks = {}     # camera_id -> RTSPVideoStreamTrack
        self.snapshot_connections = {}  # camera_id -> [websocket]
        self._lock = asyncio.Lock()
        self._snapshot_tasks = {}   # camera_id -> asyncio.Task
        
        # Memory management settings
        self.max_connections_per_camera = 5
        self.inactive_timeout = 60  # seconds
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # seconds
        
        # Start periodic cleanup
        asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodic cleanup of resources"""
        while True:
            try:
                await self._cleanup_resources()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.exception(f"Error in periodic cleanup: {str(e)}")
                await asyncio.sleep(self.cleanup_interval)
    
    async def _cleanup_resources(self):
        """Clean up inactive connections and tracks"""
        now = time.time()
        
        # Skip if we ran cleanup recently
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        self.last_cleanup = now
        
        async with self._lock:
            # Clean up peer connections by camera
            for camera_id, connections in list(self.peer_connections.items()):
                # Filter out closed connections
                active_connections = [pc for pc in connections 
                                    if pc.connectionState not in ["closed", "failed"]]
                
                if len(active_connections) == 0 and camera_id in self.camera_tracks:
                    # No active connections, stop the track
                    self.camera_tracks[camera_id].stop()
                    del self.camera_tracks[camera_id]
                    logger.info(f"Removed unused camera track for camera {camera_id}")
                
                # Update the list
                if active_connections:
                    self.peer_connections[camera_id] = active_connections
                else:
                    del self.peer_connections[camera_id]
            
            # Clean up snapshot tasks
            for camera_id, task in list(self._snapshot_tasks.items()):
                if task.done() or camera_id not in self.snapshot_connections:
                    if camera_id in self._snapshot_tasks:
                        del self._snapshot_tasks[camera_id]
        
        # Run garbage collection
        gc.collect()
        logger.info(f"Cleanup complete: {len(self.camera_tracks)} active camera tracks")
    
    async def create_peer_connection(self, camera_id: int):
        """Create a new RTCPeerConnection"""
        async with self._lock:
            # Check connection limit for this camera
            if (camera_id in self.peer_connections and 
                len(self.peer_connections[camera_id]) >= self.max_connections_per_camera):
                # Find and close the oldest connection
                if self.peer_connections[camera_id]:
                    oldest_pc = self.peer_connections[camera_id][0]
                    await oldest_pc.close()
                    self.peer_connections[camera_id].remove(oldest_pc)
                    logger.info(f"Closed oldest connection for camera {camera_id} (limit reached)")
        
        pc = RTCPeerConnection()
        pc_id = id(pc)
        pc_timestamps[pc_id] = time.time()
        
        # Keep track of this peer connection
        async with self._lock:
            if camera_id not in self.peer_connections:
                self.peer_connections[camera_id] = []
            self.peer_connections[camera_id].append(pc)
            pcs.add(pc)
        
        # Create/get video track for this camera if needed
        if camera_id not in self.camera_tracks:
            # Ensure camera is connected and processing
            camera_manager = await get_camera_manager()
            connected = await camera_manager.ensure_camera_connected(camera_id)
            
            if not connected:
                logger.warning(f"Camera {camera_id} could not be connected, but creating WebRTC track anyway")
            
            # Create the track anyway to show a "No Signal" message
            self.camera_tracks[camera_id] = RTSPVideoStreamTrack(camera_id, high_quality=True).add_ref()
        
        # Add track to peer connection
        pc.addTrack(relay.subscribe(self.camera_tracks[camera_id]))
        
        # Handle ICE connection state
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            pc_timestamps[pc_id] = time.time()  # Update timestamp on activity
            logger.info(f"ICE connection state for camera {camera_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed" or pc.iceConnectionState == "closed":
                await self.close_peer_connection(pc, camera_id)
        
        # Handle connection state
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            pc_timestamps[pc_id] = time.time()  # Update timestamp on activity
            logger.info(f"Connection state for camera {camera_id}: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await self.close_peer_connection(pc, camera_id)
        
        return pc
        
    async def close_peer_connection(self, pc, camera_id: int):
        """Close a peer connection and clean up resources"""
        # Close the connection
        await pc.close()
        
        # Remove from tracking
        async with self._lock:
            if camera_id in self.peer_connections and pc in self.peer_connections[camera_id]:
                self.peer_connections[camera_id].remove(pc)
            
            if pc in pcs:
                pcs.remove(pc)
            
            pc_id = id(pc)
            pc_timestamps.pop(pc_id, None)
            
            # If no more connections for this camera, clean up track
            if camera_id in self.peer_connections and not self.peer_connections[camera_id]:
                if camera_id in self.camera_tracks:
                    self.camera_tracks[camera_id].remove_ref()
                    del self.camera_tracks[camera_id]
    
    async def connect_snapshot(self, camera_id: int, websocket: WebSocket):
        """Register a new client connection for snapshot mode"""
        await websocket.accept()
        
        async with self._lock:
            if camera_id not in self.snapshot_connections:
                self.snapshot_connections[camera_id] = []
            self.snapshot_connections[camera_id].append(websocket)
            
            # Start snapshot task if not already running
            if camera_id not in self._snapshot_tasks or self._snapshot_tasks[camera_id].done():
                logger.info(f"Starting snapshot task for camera {camera_id}")
                self._snapshot_tasks[camera_id] = asyncio.create_task(
                    self._send_snapshots(camera_id)
                )
        
        logger.info(f"Snapshot connection established for camera {camera_id}")
        
        # Send a test message
        try:
            test_message = json.dumps({
                "type": "info", 
                "message": "Snapshot connection established"
            })
            await websocket.send_text(test_message)
        except Exception as e:
            logger.error(f"Error sending test message: {str(e)}")
    
    async def disconnect_snapshot(self, camera_id: int, websocket: WebSocket):
        """Disconnect a snapshot client"""
        async with self._lock:
            if camera_id in self.snapshot_connections:
                if websocket in self.snapshot_connections[camera_id]:
                    self.snapshot_connections[camera_id].remove(websocket)
                
                # If no more connections, cancel snapshot task
                if not self.snapshot_connections[camera_id]:
                    if camera_id in self._snapshot_tasks and not self._snapshot_tasks[camera_id].done():
                        logger.info(f"Cancelling snapshot task for camera {camera_id}")
                        self._snapshot_tasks[camera_id].cancel()
                        try:
                            await self._snapshot_tasks[camera_id]
                        except asyncio.CancelledError:
                            pass
                    
                    del self.snapshot_connections[camera_id]
                    if camera_id in self._snapshot_tasks:
                        del self._snapshot_tasks[camera_id]
    
    async def _send_snapshots(self, camera_id: int):
        """Send periodic snapshots to all connected clients"""
        camera_manager = await get_camera_manager()
        snapshot_interval = 1  # Send snapshot every second
        failed_attempts = 0
        max_failed_attempts = 5
        
        try:
            # First ensure camera is connected
            connected = await camera_manager.ensure_camera_connected(camera_id)
            if not connected:
                logger.warning(f"Camera {camera_id} could not be connected for snapshots")
                # Continue anyway to show error message
            
            # Main loop
            while camera_id in self.snapshot_connections and self.snapshot_connections[camera_id]:
                try:
                    # Get a snapshot from the camera
                    jpeg_frame = await camera_manager.get_jpeg_frame(camera_id, high_quality=False)
                    
                    if jpeg_frame:
                        # Reset failed attempts counter
                        failed_attempts = 0
                        
                        # Encode to base64
                        encoded_frame = base64.b64encode(jpeg_frame).decode('utf-8')
                        
                        # Create snapshot message
                        message = json.dumps({
                            "type": "snapshot",
                            "timestamp": time.time(),
                            "data": encoded_frame
                        })
                        
                    else:
                        # Increment failed attempts
                        failed_attempts += 1
                        logger.warning(f"No frame available for camera {camera_id}, attempt {failed_attempts}/{max_failed_attempts}")
                        
                        if failed_attempts >= max_failed_attempts:
                            # Create a "No Signal" image
                            no_signal_img = np.zeros((360, 640, 3), np.uint8)
                            font = cv2.FONT_HERSHEY_SIMPLEX
                            text = f"Camera {camera_id} - No Signal"
                            text_size = cv2.getTextSize(text, font, 1, 2)[0]
                            text_x = (640 - text_size[0]) // 2
                            text_y = (360 + text_size[1]) // 2
                            cv2.putText(no_signal_img, text, (text_x, text_y), font, 1, (255, 255, 255), 2)
                            
                            # Convert to JPEG
                            _, buffer = cv2.imencode('.jpg', no_signal_img)
                            jpeg_frame = buffer.tobytes()
                            
                            # Encode to base64
                            encoded_frame = base64.b64encode(jpeg_frame).decode('utf-8')
                            
                            # Create error message
                            message = json.dumps({
                                "type": "snapshot",
                                "timestamp": time.time(),
                                "data": encoded_frame,
                                "error": True
                            })
                            
                            # Reset counter after sending an error frame
                            failed_attempts = 0
                        else:
                            # Skip this iteration, no frame to send
                            await asyncio.sleep(snapshot_interval)
                            continue
                    
                    # Send to all connected clients
                    disconnected = []
                    for client in self.snapshot_connections.get(camera_id, []):
                        try:
                            await client.send_text(message)
                        except Exception as e:
                            logger.warning(f"Error sending snapshot to client: {str(e)}")
                            disconnected.append(client)
                    
                    # Clean up disconnected clients
                    for client in disconnected:
                        await self.disconnect_snapshot(camera_id, client)
                    
                    # Wait for next snapshot
                    await asyncio.sleep(snapshot_interval)
                    
                except asyncio.CancelledError:
                    logger.info(f"Snapshot task for camera {camera_id} cancelled")
                    raise
                except Exception as e:
                    logger.exception(f"Error in snapshot task for camera {camera_id}: {str(e)}")
                    # Brief pause to avoid flooding logs with errors
                    await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info(f"Snapshot task for camera {camera_id} cancelled")
            raise
        except Exception as e:
            logger.exception(f"Fatal error in snapshot task for camera {camera_id}: {str(e)}")


# Create singleton instance
webrtc_manager = WebRTCManager()

# Start cleanup task 
cleanup_task = None

# Create router
router = APIRouter()

@router.on_event("startup")
async def startup_event():
    """Start background tasks when router starts"""
    global cleanup_task
    cleanup_task = asyncio.create_task(periodic_pc_cleanup())

@router.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when router shuts down"""
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    # Close all peer connections
    coros = [pc.close() for pc in pcs]
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)
    pcs.clear()
    
    # Clear all tracks
    for track in camera_tracks.values():
        track.stop()
    camera_tracks.clear()

@router.websocket("/snapshot/{camera_id}")
async def snapshot_endpoint(websocket: WebSocket, camera_id: int):
    """WebSocket endpoint for snapshot mode"""
    # Check if camera exists and is enabled
    camera_enabled = False
    try:
        async for session in get_db():
            camera = await session.get(Camera, camera_id)
            if camera and camera.enabled:
                camera_enabled = True
                break
    except Exception as e:
        logger.error(f"Database error checking camera {camera_id}: {str(e)}")
        await websocket.close(code=1011, reason="Server error checking camera status")
        return
    
    if not camera_enabled:
        logger.warning(f"Snapshot connection attempt for disabled or non-existent camera {camera_id}")
        await websocket.close(code=1000, reason="Camera not found or disabled")
        return
    
    # Connect client
    await webrtc_manager.connect_snapshot(camera_id, websocket)
    
    try:
        # Keep connection alive until client disconnects
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("type") == "ping":
                    # Handle ping messages
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                continue
            except websockets.exceptions.ConnectionClosedOK:
                logger.info(f"Snapshot client disconnected normally from camera {camera_id}")
                break
            except websockets.exceptions.ConnectionClosedError:
                logger.info(f"Snapshot client connection error for camera {camera_id}")
                break
    except WebSocketDisconnect:
        logger.info(f"Snapshot client disconnected from camera {camera_id}")
    except Exception as e:
        logger.exception(f"Error in snapshot connection: {str(e)}")
    finally:
        # Clean up
        await webrtc_manager.disconnect_snapshot(camera_id, websocket)

@router.post("/offer")
async def webrtc_offer(
    request: Dict[str, Any]
):
    """Handle WebRTC offer from client"""
    camera_id = request.get("cameraId")
    sdp = request.get("sdp")
    
    if not camera_id or not sdp:
        raise HTTPException(status_code=400, detail="Missing cameraId or sdp", headers={"Access-Control-Allow-Origin": "*"})
    
    # Check if camera exists and is enabled
    camera_enabled = False
    try:
        async for session in get_db():
            camera = await session.get(Camera, camera_id)
            if camera and camera.enabled:
                camera_enabled = True
                break
    except Exception as e:
        logger.error(f"Database error checking camera {camera_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error", headers={"Access-Control-Allow-Origin": "*"})
    
    if not camera_enabled:
        raise HTTPException(status_code=404, detail="Camera not found or disabled", headers={"Access-Control-Allow-Origin": "*"})
    
    # Ensure camera is connected and processing
    camera_manager = await get_camera_manager()
    connected = await camera_manager.ensure_camera_connected(camera_id)
    
    if not connected:
        logger.warning(f"Camera {camera_id} could not be connected for WebRTC")
        # Continue anyway to allow the WebRTC connection, but warn in the log
    
    # Create peer connection
    pc = await webrtc_manager.create_peer_connection(camera_id)
    
    # Set remote description
    offer = RTCSessionDescription(sdp=sdp, type="offer")
    await pc.setRemoteDescription(offer)
    
    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }

@router.post("/ice-candidate")
async def webrtc_ice_candidate(
    request: Dict[str, Any]
):
    """Handle ICE candidate from client"""
    camera_id = request.get("cameraId")
    candidate = request.get("candidate")
    sdpMid = request.get("sdpMid")
    sdpMLineIndex = request.get("sdpMLineIndex")
    
    if not camera_id or not candidate:
        raise HTTPException(status_code=400, detail="Missing parameters", headers={"Access-Control-Allow-Origin": "*"})
    
    # Find peer connection for this camera
    if camera_id in webrtc_manager.peer_connections:
        # Add ICE candidate to all peer connections for this camera
        for pc in webrtc_manager.peer_connections[camera_id]:
            if pc.connectionState not in ["closed", "failed"]:
                try:
                    # Use the createIceCandidate method which handles the parsing internally
                    from aiortc.sdp import candidate_from_sdp
                    
                    # Mock an SDP line for the candidate
                    sdp_line = "a=" + candidate
                    ice = candidate_from_sdp(sdp_line)
                    ice.sdpMid = sdpMid
                    ice.sdpMLineIndex = sdpMLineIndex
                    
                    await pc.addIceCandidate(ice)
                except Exception as e:
                    logger.exception(f"Error adding ICE candidate: {str(e)}")
    
    return {"success": True}

@router.post("/template/{camera_id}")
async def take_template_snapshot(camera_id: int):
    """Take a snapshot to use as the template for a camera"""
    # Check if camera exists and is enabled
    camera_enabled = False
    try:
        async for session in get_db():
            camera = await session.get(Camera, camera_id)
            if camera and camera.enabled:
                camera_enabled = True
                break
    except Exception as e:
        logger.error(f"Database error checking camera {camera_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Database error", headers={"Access-Control-Allow-Origin": "*"})
    
    if not camera_enabled:
        raise HTTPException(status_code=404, detail="Camera not found or disabled", headers={"Access-Control-Allow-Origin": "*"})
    
    # Take template snapshot
    camera_manager = await get_camera_manager()
    jpeg_data = await camera_manager.take_template_snapshot(camera_id)
    
    if not jpeg_data:
        raise HTTPException(status_code=500, detail="Failed to take template snapshot", headers={"Access-Control-Allow-Origin": "*"})
    
    return {
        "success": True,
        "message": f"Template updated for camera {camera_id}"
    }
