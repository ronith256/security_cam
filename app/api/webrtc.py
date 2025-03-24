from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Optional, List, Any
import json
import cv2
import numpy as np
import asyncio
import base64
import logging
import time
import uuid
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaBlackhole, MediaRelay
from av import VideoFrame

from app.database import get_db
from app.models.camera import Camera
from app.core.camera_manager import get_camera_manager
from app.models.settings import Settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Global state
pcs: Dict[str, RTCPeerConnection] = {}
relays: Dict[str, MediaRelay] = {}
active_websockets: Dict[int, List[WebSocket]] = {}

class CameraVideoStreamTrack(MediaStreamTrack):
    """Video stream track that reads from camera processor"""
    kind = "video"
    
    def __init__(self, camera_id: int):
        super().__init__()
        self.camera_id = camera_id
        self.camera_manager = None
        self.frame_count = 0
        self.start_time = time.time()
        self.last_frame_time = 0
        self.frame_interval = 1.0 / 30  # Default to 30fps
        self.pts = 0
        self.stopped = False
    
    async def get_camera_manager(self):
        """Get or initialize camera manager"""
        if self.camera_manager is None:
            self.camera_manager = await get_camera_manager()
        return self.camera_manager
    
    async def recv(self):
        """Get the next frame"""
        if self.stopped:
            return None
        
        try:
            # Get camera manager
            camera_manager = await self.get_camera_manager()
            if not camera_manager:
                raise Exception("Camera manager not available")
            
            # Get processor for this camera
            processor = camera_manager.cameras.get(self.camera_id)
            if not processor:
                raise Exception("Camera not found")
            
            # Throttle frame rate
            current_time = time.time()
            elapsed = current_time - self.last_frame_time
            if elapsed < self.frame_interval:
                await asyncio.sleep(max(0, self.frame_interval - elapsed))
            
            # Get latest frame
            frame_data = processor.get_latest_frame()
            if frame_data is None:
                # If no frame available, create blank frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                frame_time = current_time
            else:
                frame, frame_time = frame_data
            
            # Convert to video frame
            video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
            video_frame.pts = self.pts
            video_frame.time_base = 1/30  # 30fps
            
            # Update timing
            self.pts += 1
            self.frame_count += 1
            self.last_frame_time = current_time
            
            # Calculate FPS every 30 frames
            if self.frame_count % 30 == 0:
                elapsed = current_time - self.start_time
                fps = self.frame_count / elapsed if elapsed > 0 else 0
                logger.debug(f"Streaming camera {self.camera_id} at {fps:.2f} FPS")
            
            return video_frame
            
        except Exception as e:
            logger.exception(f"Error getting frame for camera {self.camera_id}: {str(e)}")
            self.stopped = True
            return None
    
    def stop(self):
        """Stop the track"""
        self.stopped = True
        super().stop()

async def create_peer_connection(camera_id: int) -> RTCPeerConnection:
    """Create and configure a peer connection"""
    # Create peer connection with STUN server configuration
    config = RTCConfiguration([
        RTCIceServer(urls=["stun:stun.l.google.com:19302"])
    ])
    pc = RTCPeerConnection(configuration=config)
    
    # Create video track
    video = CameraVideoStreamTrack(camera_id)
    
    # Add track to peer connection
    pc.addTrack(video)
    
    # Store for cleanup
    pc_id = str(uuid.uuid4())
    pcs[pc_id] = pc
    
    # Handle connection state changes
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state for {pc_id}: {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            await cleanup_peer_connection(pc_id)
    
    return pc, pc_id

async def cleanup_peer_connection(pc_id: str):
    """Cleanup peer connection resources"""
    try:
        if pc_id in pcs:
            pc = pcs[pc_id]
            
            # Close all transceivers
            for transceiver in pc.getTransceivers():
                if transceiver.sender:
                    await transceiver.sender.stop()
                if transceiver.receiver:
                    await transceiver.receiver.stop()
            
            # Close peer connection
            await pc.close()
            
            # Remove from tracking
            del pcs[pc_id]
            
            logger.info(f"Cleaned up peer connection {pc_id}")
    except Exception as e:
        logger.exception(f"Error cleaning up peer connection {pc_id}: {str(e)}")

@router.post("/offer")
async def webrtc_offer(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle WebRTC offer from client"""
    try:
        data = await request.json()
        camera_id = data["cameraId"]
        offer = RTCSessionDescription(sdp=data["sdp"], type="offer")
        
        # Check if camera exists
        camera = await db.get(Camera, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # Create peer connection
        pc, pc_id = await create_peer_connection(camera_id)
        
        # Set remote description
        await pc.setRemoteDescription(offer)
        
        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }
        
    except Exception as e:
        logger.exception(f"Error handling WebRTC offer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ice-candidate")
async def webrtc_ice_candidate(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle ICE candidate from client"""
    try:
        data = await request.json()
        camera_id = data["cameraId"]
        
        # Check if camera exists
        camera = await db.get(Camera, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # Find corresponding peer connection
        pc = None
        for pc_id, candidate_pc in pcs.items():
            if any(sender.track.camera_id == camera_id for sender in candidate_pc.getSenders()):
                pc = candidate_pc
                break
        
        if pc is None:
            raise HTTPException(status_code=404, detail="Peer connection not found")
        
        # Add ICE candidate
        candidate = data["candidate"]
        sdp_mid = data["sdpMid"]
        sdp_m_line_index = data["sdpMLineIndex"]
        
        await pc.addIceCandidate({
            "candidate": candidate,
            "sdpMid": sdp_mid,
            "sdpMLineIndex": sdp_m_line_index
        })
        
        return {"message": "ICE candidate added"}
        
    except Exception as e:
        logger.exception(f"Error handling ICE candidate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/snapshot/{camera_id}")
async def snapshot_endpoint(
    websocket: WebSocket,
    camera_id: int,
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint for snapshot mode"""
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
        
        # Get processor
        processor = camera_manager.cameras.get(camera_id)
        if not processor:
            await websocket.close(code=4006, reason="Camera processor not found")
            return
        
        # Get snapshot interval from settings
        snapshot_interval = 1.0  # Default 1 second
        try:
            query = select(Settings).where(Settings.key == "idle_snapshot_interval")
            result = await db.execute(query)
            setting = result.scalar_one_or_none()
            if setting:
                snapshot_interval = float(setting.value)
        except Exception as e:
            logger.warning(f"Error getting snapshot interval: {str(e)}")
        
        last_snapshot_time = 0
        ping_timeout = 30  # 30 seconds timeout for ping
        last_ping_time = time.time()
        
        while True:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=ping_timeout
                )
                
                # Parse message
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
                        frame_data = processor.get_latest_frame()
                        if frame_data:
                            frame, timestamp = frame_data
                            
                            # Convert to JPEG
                            _, buffer = cv2.imencode('.jpg', frame)
                            base64_image = base64.b64encode(buffer).decode('utf-8')
                            
                            # Send snapshot
                            await websocket.send_json({
                                "type": "snapshot",
                                "timestamp": timestamp,
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
                break
                
            except Exception as e:
                logger.exception(f"Error in snapshot websocket: {str(e)}")
                break
    
    finally:
        # Cleanup
        if camera_id in active_websockets:
            try:
                active_websockets[camera_id].remove(websocket)
                if not active_websockets[camera_id]:
                    del active_websockets[camera_id]
            except ValueError:
                pass
        
        try:
            await websocket.close()
        except:
            pass

@router.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown"""
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