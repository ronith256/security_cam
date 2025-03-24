from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Optional, List, Any
import logging
import base64
import asyncio
import time
import uuid
import json

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from av import VideoFrame
import fractions
import cv2
import numpy as np

from app.database import get_db
from app.models.camera import Camera
from app.core.camera_manager import get_camera_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Global variables to store peer connections and video tracks
pcs = {}
relay = MediaRelay()

# Active websockets for snapshot mode
active_websockets = {}

class CameraVideoStreamTrack(MediaStreamTrack):
    """A video stream track that captures from the camera."""
    
    kind = "video"

    def __init__(self, camera_id):
        super().__init__()
        self.camera_id = camera_id
        self.camera_manager = None
        self.frame_count = 0
        self.fps = 30
        self.frame_time = 1 / self.fps
        self.start_time = time.time()
        self.current_time = 0
        self.last_frame = None
        self.stopped = False
    
    async def get_camera_manager(self):
        """Get or initialize camera manager"""
        if self.camera_manager is None:
            self.camera_manager = await get_camera_manager()
        return self.camera_manager
    
    async def recv(self):
        """Get the next frame."""
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        video_frame = VideoFrame.from_ndarray(black_frame, format="bgr24")
        pts, time_base = self.frame_count, fractions.Fraction(1, self.fps)
        video_frame.pts = pts
        video_frame.time_base = time_base
        self.frame_count += 1
        if self.stopped:
            # If stopped, return a black frame
            return video_frame
        
        # Throttle frame rate
        self.current_time = time.time() - self.start_time
        next_frame_time = self.frame_count * self.frame_time
        wait_time = max(0, next_frame_time - self.current_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        try:
            # Get frame from camera
            camera_manager = await self.get_camera_manager()
            if not camera_manager:
                raise Exception("Camera manager not available")
            
            # Get frame
            print(f"camera id: {self.camera_id}")
            jpeg_frame = await camera_manager.get_jpeg_frame(self.camera_id)
            if jpeg_frame is None:
                return video_frame
            
            # Convert jpeg bytes to numpy array
            frame = cv2.imdecode(np.frombuffer(jpeg_frame, np.uint8), cv2.IMREAD_COLOR)
            
            # Convert to VideoFrame for WebRTC
            # Note: We need to convert BGR to RGB here
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            
            # Set timing information
            pts, time_base = self.frame_count, fractions.Fraction(1, self.fps)
            video_frame.pts = pts
            video_frame.time_base = time_base
            
            # Update counters
            self.frame_count += 1
            self.last_frame = video_frame
            
            return video_frame
            
        except Exception as e:
            logger.exception(f"Error getting frame from camera {self.camera_id}: {str(e)}")
            
            # Return last frame if available or a black frame
            if self.last_frame is not None:
                return self.last_frame
            
            # Create a black frame as fallback
            black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            video_frame = VideoFrame.from_ndarray(black_frame, format="bgr24")
            pts, time_base = self.frame_count, fractions.Fraction(1, self.fps)
            video_frame.pts = pts
            video_frame.time_base = time_base
            self.frame_count += 1
            return video_frame
    
    def stop(self):
        """Stop the track."""
        if not self.stopped:
            self.stopped = True
            super().stop()

async def cleanup_peer_connection(pc_id):
    """
    Clean up resources associated with a peer connection
    """
    if pc_id in pcs:
        pc_data = pcs[pc_id]
        pc = pc_data["pc"]
        
        # Close transceivers and stop tracks
        for transceiver in pc.getTransceivers():
            if transceiver.sender and transceiver.sender.track:
                transceiver.sender.track.stop()
            if transceiver.receiver and transceiver.receiver.track:
                transceiver.receiver.track.stop()
        
        # Close the peer connection
        await pc.close()
        
        # Remove from dictionary
        del pcs[pc_id]
        
        logger.info(f"Cleaned up peer connection {pc_id}")

@router.post("/offer")
async def webrtc_offer(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle WebRTC offer from client
    """
    try:
        # Parse request data
        data = await request.json()
        camera_id = data.get("cameraId")
        sdp = data.get("sdp")
        
        if not camera_id or not sdp:
            raise HTTPException(status_code=400, detail="Missing cameraId or SDP")
        
        # Check if camera exists in database
        camera = await db.get(Camera, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # Debug log to see what's happening
        logger.info(f"Processing WebRTC offer for camera {camera_id}")
        
        # Get camera manager
        camera_manager = await get_camera_manager()
        logger.info(f"Current cameras in manager: {list(camera_manager.cameras.keys())}")
        
        # Try to ensure camera is connected
        # If it's not in the manager, this will try to add it
        if not await camera_manager.ensure_camera_connected(camera_id):
            logger.error(f"Failed to ensure camera {camera_id} is connected")
            # Instead of raising error, try to add camera directly
            success = await camera_manager.add_camera(camera, start_processing=False)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to connect to camera")
            logger.info(f"Added camera {camera_id} to manager")
        
        # Create peer connection
        pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=[
                    RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
                    RTCIceServer(urls=["stun:stun1.l.google.com:19302"])
                ]
            )
        )
        
        # Generate a unique ID for this connection
        pc_id = str(uuid.uuid4())
        
        # Create video track
        video_track = CameraVideoStreamTrack(camera_id)
        
        # Add track to peer connection
        pc.addTrack(video_track)
        
        # Store for cleanup
        pcs[pc_id] = {"pc": pc, "camera_id": camera_id}
        
        # Handle connection state changes
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state for {pc_id}: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                await cleanup_peer_connection(pc_id)
        
        # Parse and set remote description (client's offer)
        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await pc.setRemoteDescription(offer)
        
        # Create answer with explicit direction to avoid the None error
        # The key fix:
        for transceiver in pc.getTransceivers():
            if transceiver.direction is None:
                transceiver.direction = "recvonly"
        
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Return the answer
        return {
            "type": pc.localDescription.type,
            "sdp": pc.localDescription.sdp,
            "session_id": pc_id
        }
        
    except Exception as e:
        logger.exception(f"Error handling WebRTC offer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/icecandidate/{session_id}")
async def webrtc_ice_candidate(session_id: str, request: Request):
    """
    Handle ICE candidate from client
    """
    try:
        # Check if session exists
        if session_id not in pcs:
            return JSONResponse(status_code=404, content={"error": "Session not found"})
        
        # Get peer connection
        pc = pcs[session_id]["pc"]
        
        # Parse candidate
        data = await request.json()
        
        # Add candidate
        candidate = data.get("candidate", "")
        sdp_mid = data.get("sdpMid")
        sdp_mline_index = data.get("sdpMLineIndex")
        
        # Skip empty candidates
        if not candidate:
            return {"success": True}
        
        # Add candidate to peer connection
        await pc.addIceCandidate({
            "candidate": candidate,
            "sdpMid": sdp_mid,
            "sdpMLineIndex": sdp_mline_index
        })
        
        return {"success": True}
        
    except Exception as e:
        logger.exception(f"Error handling ICE candidate: {e}")
        # Don't raise an exception for ICE candidate errors
        return {"success": False, "error": str(e)}

@router.delete("/session/{session_id}")
async def close_session(session_id: str):
    """
    Close a WebRTC session
    """
    try:
        # Check if session exists
        if session_id not in pcs:
            return {"message": "Session not found"}
        
        # Clean up
        await cleanup_peer_connection(session_id)
        
        return {"message": "Session closed"}
        
    except Exception as e:
        logger.exception(f"Error closing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/snapshot/{camera_id}")
async def snapshot_endpoint(
    websocket: WebSocket,
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for snapshot mode
    """
    try:
        # Accept connection
        await websocket.accept()
        
        # Check if camera exists
        camera = await db.get(Camera, camera_id)
        if camera is None:
            await websocket.close(code=4004, reason="Camera not found")
            return
        
        # Add to active websockets
        if camera_id not in active_websockets:
            active_websockets[camera_id] = []
        active_websockets[camera_id].append(websocket)
        
        # Get camera manager
        camera_manager = await get_camera_manager()
        
        # Ensure camera is connected
        if not await camera_manager.ensure_camera_connected(camera_id):
            await websocket.close(code=4005, reason="Camera not available")
            return
        
        # Snapshot interval
        snapshot_interval = 1.0  # 1 second default
        last_snapshot_time = 0
        ping_timeout = 30  # 30 seconds timeout
        last_ping_time = time.time()
        
        # Main loop
        while True:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=ping_timeout
                )
                
                # Parse message as JSON
                data = json.loads(message)
                message_type = data.get("type")
                
                if message_type == "ping":
                    # Update ping time and send pong
                    last_ping_time = time.time()
                    await websocket.send_json({"type": "pong"})
                    
                    # Check if it's time for a new snapshot
                    current_time = time.time()
                    if current_time - last_snapshot_time >= snapshot_interval:
                        # Get latest frame
                        jpeg_frame = await camera_manager.get_jpeg_frame(camera_id)
                        
                        if jpeg_frame:
                            # Encode as base64
                            base64_image = base64.b64encode(jpeg_frame).decode('utf-8')
                            
                            # Send snapshot
                            await websocket.send_json({
                                "type": "snapshot",
                                "timestamp": current_time,
                                "data": base64_image
                            })
                            
                            last_snapshot_time = current_time
                
            except asyncio.TimeoutError:
                # Check ping timeout
                if time.time() - last_ping_time > ping_timeout:
                    logger.warning(f"Ping timeout for camera {camera_id}")
                    break
                continue
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for camera {camera_id}")
                break
                
            except Exception as e:
                logger.exception(f"Error in snapshot websocket: {e}")
                break
    
    finally:
        # Clean up
        if camera_id in active_websockets:
            try:
                active_websockets[camera_id].remove(websocket)
                if not active_websockets[camera_id]:
                    del active_websockets[camera_id]
            except (ValueError, KeyError):
                pass
        
        try:
            await websocket.close()
        except:
            pass

@router.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup resources on shutdown
    """
    # Close all peer connections
    for pc_id in list(pcs.keys()):
        await cleanup_peer_connection(pc_id)
    
    # Close all websockets
    for camera_id in list(active_websockets.keys()):
        for ws in active_websockets[camera_id]:
            try:
                await ws.close()
            except:
                pass
        del active_websockets[camera_id]