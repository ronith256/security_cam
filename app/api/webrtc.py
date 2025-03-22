from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import json
import asyncio
import cv2
import base64
import logging
from typing import Dict, Any, List
from app.core.camera_manager import get_camera_manager
from app.database import get_db
from app.models.camera import Camera
from app.config import settings

logger = logging.getLogger(__name__)

class WebRTCManager:
    """
    Manages WebRTC connections and signaling
    """
    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, camera_id: int, websocket: WebSocket):
        """Register a new client connection for a camera"""
        await websocket.accept()
        
        async with self._lock:
            if camera_id not in self.connections:
                self.connections[camera_id] = []
            self.connections[camera_id].append(websocket)
        
        logger.info(f"WebRTC client connected for camera {camera_id}")

    async def disconnect(self, camera_id: int, websocket: WebSocket):
        """Remove a client connection"""
        async with self._lock:
            if camera_id in self.connections and websocket in self.connections[camera_id]:
                self.connections[camera_id].remove(websocket)
                if not self.connections[camera_id]:
                    del self.connections[camera_id]
        
        logger.info(f"WebRTC client disconnected from camera {camera_id}")

    async def broadcast_frame(self, camera_id: int, frame_data: bytes):
        """Broadcast a frame to all connected clients for this camera"""
        if camera_id not in self.connections:
            return
        
        # Convert frame data to base64 for WebRTC streaming
        encoded_frame = base64.b64encode(frame_data).decode('utf-8')
        message = json.dumps({
            "type": "frame",
            "data": encoded_frame
        })
        
        disconnected_clients = []
        for client in self.connections[camera_id]:
            try:
                await client.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send frame to client: {str(e)}")
                disconnected_clients.append(client)
        
        # Clean up disconnected clients
        for client in disconnected_clients:
            await self.disconnect(camera_id, client)

    async def handle_signaling(self, camera_id: int, websocket: WebSocket, data: Dict[str, Any]):
        """Handle WebRTC signaling messages"""
        # Pass the signaling message to all other clients for this camera
        message = json.dumps({
            "type": "signal",
            "data": data
        })
        
        for client in self.connections[camera_id]:
            if client != websocket:  # Don't send back to the sender
                try:
                    await client.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send signaling message: {str(e)}")

# Create singleton instance
webrtc_manager = WebRTCManager()

# Create router
router = APIRouter()

@router.websocket("/ws/{camera_id}")
async def webrtc_endpoint(websocket: WebSocket, camera_id: int):
    """WebSocket endpoint for WebRTC signaling"""
    # Check if camera exists and is enabled
    async for session in get_db():
        camera = await session.get(Camera, camera_id)
        if not camera or not camera.enabled:
            await websocket.close(code=1000, reason="Camera not found or disabled")
            return
    
    # Connect the client
    await webrtc_manager.connect(camera_id, websocket)
    
    # Start frame processing task
    camera_manager = await get_camera_manager()
    frame_task = None
    
    if camera_id in camera_manager.cameras:
        # Create a task to send frames
        frame_task = asyncio.create_task(process_frames(camera_id, camera_manager))
    
    try:
        # Handle incoming messages (signaling)
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "signal":
                await webrtc_manager.handle_signaling(camera_id, websocket, data.get("data", {}))
    except WebSocketDisconnect:
        logger.info(f"WebRTC client disconnected from camera {camera_id}")
    except Exception as e:
        logger.exception(f"Error in WebRTC connection: {str(e)}")
    finally:
        # Clean up
        await webrtc_manager.disconnect(camera_id, websocket)
        if frame_task:
            frame_task.cancel()

async def process_frames(camera_id: int, camera_manager):
    """Process and send frames for a camera"""
    try:
        while True:
            # Get the latest processed frame
            frame_data = await camera_manager.get_jpeg_frame(camera_id)
            if frame_data:
                # Broadcast the frame
                await webrtc_manager.broadcast_frame(camera_id, frame_data)
            
            # Control the frame rate
            await asyncio.sleep(1 / 30)  # 30 FPS max
    except asyncio.CancelledError:
        logger.info(f"Frame processing task for camera {camera_id} cancelled")
    except Exception as e:
        logger.exception(f"Error processing frames for camera {camera_id}: {str(e)}")

# Method to start processing frames for all active cameras on startup
async def start_webrtc_streaming():
    """Start WebRTC streaming for all active cameras"""
    camera_manager = await get_camera_manager()
    
    for camera_id in camera_manager.cameras:
        asyncio.create_task(process_frames(camera_id, camera_manager))
    
    logger.info("WebRTC streaming started for all active cameras")