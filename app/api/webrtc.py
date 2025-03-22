# app/api/webrtc.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import json
import asyncio
import cv2
import base64
import logging
from typing import Dict, Any, List, Set
import os
import uuid
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate
from aiortc.contrib.media import MediaBlackhole, MediaRelay
from av import VideoFrame
import fractions
import numpy as np
import threading
import time
from datetime import datetime

from app.core.camera_manager import get_camera_manager
from app.database import get_db
from app.models.camera import Camera
from app.config import settings

logger = logging.getLogger(__name__)

# Relay for sharing a single webcam feed
relay = MediaRelay()

# In-memory storage for peer connections and video tracks
pcs = set()
camera_tracks = {}  # Map of camera_id to VideoStreamTrack

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
        
        # Start frame capture thread
        self._start_capture_thread()
    
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
                capture_interval = 1/30  # 30 fps max
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
            jpeg_frame = await camera_manager.get_jpeg_frame(self.camera_id, self.high_quality)
            
            if jpeg_frame:
                # Convert JPEG to numpy array
                nparr = np.frombuffer(jpeg_frame, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                # Add timestamp overlay
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(
                    img,
                    timestamp,
                    (10, img.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    1
                )
                
                return img
        except Exception as e:
            logger.error(f"Error getting frame for camera {self.camera_id}: {str(e)}")
        
        return None
    
    async def recv(self):
        """Return a frame of video"""
        frame = None
        with self._lock:
            frame = self._current_frame
        
        if frame is None:
            # If no frame yet, return blank frame (black image)
            pts, time_base = await self.next_timestamp()
            width, height = 640, 480
            frame = np.zeros((height, width, 3), np.uint8)
        else:
            pts, time_base = await self.next_timestamp()
        
        # Convert from OpenCV BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Create VideoFrame
        video_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        
        self._frame_counter += 1
        return video_frame
    
    async def next_timestamp(self):
        """Calculate the timestamp for the next frame"""
        if hasattr(self, "_timestamp"):
            self._timestamp += 1
        else:
            self._timestamp = 0
        
        return self._timestamp, fractions.Fraction(1, 30)  # 30 fps
    
    def stop(self):
        """Stop the track"""
        self._running = False
        super().stop()

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
    
    async def create_peer_connection(self, camera_id: int):
        """Create a new RTCPeerConnection"""
        pc = RTCPeerConnection()
        
        # Keep track of this peer connection
        if camera_id not in self.peer_connections:
            self.peer_connections[camera_id] = []
        self.peer_connections[camera_id].append(pc)
        
        # Create/get video track for this camera if needed
        if camera_id not in self.camera_tracks:
            self.camera_tracks[camera_id] = RTSPVideoStreamTrack(camera_id, high_quality=True)
        
        # Add track to peer connection
        pc.addTrack(relay.subscribe(self.camera_tracks[camera_id]))
        
        # Handle ICE connection state
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state for camera {camera_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed" or pc.iceConnectionState == "closed":
                await self.close_peer_connection(pc, camera_id)
        
        # Handle connection state
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state for camera {camera_id}: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await self.close_peer_connection(pc, camera_id)
        
        return pc
    
    async def close_peer_connection(self, pc, camera_id: int):
        """Close a peer connection and clean up resources"""
        # Close the connection
        await pc.close()
        
        # Remove from tracking
        if camera_id in self.peer_connections and pc in self.peer_connections[camera_id]:
            self.peer_connections[camera_id].remove(pc)
        
        # If no more connections for this camera, clean up track
        if camera_id in self.peer_connections and not self.peer_connections[camera_id]:
            if camera_id in self.camera_tracks:
                self.camera_tracks[camera_id].stop()
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
        
        try:
            while camera_id in self.snapshot_connections and self.snapshot_connections[camera_id]:
                # Get a snapshot from the camera
                jpeg_frame = await camera_manager.get_jpeg_frame(camera_id, high_quality=False)
                
                if jpeg_frame:
                    # Encode to base64
                    encoded_frame = base64.b64encode(jpeg_frame).decode('utf-8')
                    
                    # Create snapshot message
                    message = json.dumps({
                        "type": "snapshot",
                        "timestamp": time.time(),
                        "data": encoded_frame
                    })
                    
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

# Create singleton instance
webrtc_manager = WebRTCManager()

# Create router
router = APIRouter()

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
        raise HTTPException(status_code=400, detail="Missing cameraId or sdp")
    
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
        raise HTTPException(status_code=500, detail="Database error")
    
    if not camera_enabled:
        raise HTTPException(status_code=404, detail="Camera not found or disabled")
    
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
        raise HTTPException(status_code=400, detail="Missing parameters")
    
    # Find peer connection for this camera
    if camera_id in webrtc_manager.peer_connections:
        # Add ICE candidate to all peer connections for this camera
        for pc in webrtc_manager.peer_connections[camera_id]:
            # Create ICE candidate - the first parameter is the candidate string, not a named parameter
            ice_candidate = RTCIceCandidate(candidate, sdpMid, sdpMLineIndex)
            await pc.addIceCandidate(ice_candidate)
    
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
        raise HTTPException(status_code=500, detail="Database error")
    
    if not camera_enabled:
        raise HTTPException(status_code=404, detail="Camera not found or disabled")
    
    # Take template snapshot
    camera_manager = await get_camera_manager()
    jpeg_data = await camera_manager.take_template_snapshot(camera_id)
    
    if not jpeg_data:
        raise HTTPException(status_code=500, detail="Failed to take template snapshot")
    
    return {
        "success": True,
        "message": f"Template updated for camera {camera_id}"
    }