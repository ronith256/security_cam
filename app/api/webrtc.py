from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import json
import asyncio
import cv2
import base64
import logging
from typing import Dict, Any, List, Set
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
        self.active_cameras: Set[int] = set()
        self._lock = asyncio.Lock()
        self._frame_tasks: Dict[int, asyncio.Task] = {}

    async def connect(self, camera_id: int, websocket: WebSocket):
        """Register a new client connection for a camera"""
        await websocket.accept()
        
        async with self._lock:
            if camera_id not in self.connections:
                self.connections[camera_id] = []
            self.connections[camera_id].append(websocket)
            
            # Start frame processing if this is the first client for this camera
            if camera_id not in self.active_cameras:
                self.active_cameras.add(camera_id)
                # Start frame processing task if not already running
                if camera_id not in self._frame_tasks or self._frame_tasks[camera_id].done():
                    camera_manager = await get_camera_manager()
                    if camera_id in camera_manager.cameras:
                        self._frame_tasks[camera_id] = asyncio.create_task(
                            self._process_frames(camera_id, camera_manager)
                        )
        
        logger.info(f"WebRTC client connected for camera {camera_id}")

    async def disconnect(self, camera_id: int, websocket: WebSocket):
        """Remove a client connection"""
        async with self._lock:
            if camera_id in self.connections and websocket in self.connections[camera_id]:
                self.connections[camera_id].remove(websocket)
                
                # If this was the last client, stop frame processing
                if not self.connections[camera_id]:
                    self.connections.pop(camera_id)
                    self.active_cameras.discard(camera_id)
                    
                    # Cancel frame processing task
                    if camera_id in self._frame_tasks and not self._frame_tasks[camera_id].done():
                        self._frame_tasks[camera_id].cancel()
                        try:
                            await self._frame_tasks[camera_id]
                        except asyncio.CancelledError:
                            pass
                        self._frame_tasks.pop(camera_id)
        
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
        for client in self.connections.get(camera_id, []):
            try:
                await client.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send frame to client: {str(e)}")
                disconnected_clients.append(client)
        
        # Clean up disconnected clients
        if disconnected_clients:
            async with self._lock:
                for client in disconnected_clients:
                    if camera_id in self.connections and client in self.connections[camera_id]:
                        self.connections[camera_id].remove(client)
                
                # If this was the last client, stop frame processing
                if camera_id in self.connections and not self.connections[camera_id]:
                    self.connections.pop(camera_id)
                    self.active_cameras.discard(camera_id)
                    
                    # Cancel frame processing task
                    if camera_id in self._frame_tasks and not self._frame_tasks[camera_id].done():
                        self._frame_tasks[camera_id].cancel()

    async def handle_signaling(self, camera_id: int, websocket: WebSocket, data: Dict[str, Any]):
        """Handle WebRTC signaling messages"""
        # Pass the signaling message to all other clients for this camera
        message = json.dumps({
            "type": "signal",
            "data": data
        })
        
        for client in self.connections.get(camera_id, []):
            if client != websocket:  # Don't send back to the sender
                try:
                    await client.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send signaling message: {str(e)}")

    async def _process_frames(self, camera_id: int, camera_manager):
        """Process and send frames for a camera"""
        logger.info(f"Starting frame processing for camera {camera_id}")
        try:
            frame_count = 0
            last_log_time = asyncio.get_event_loop().time()
            
            while camera_id in self.active_cameras:
                # Check if we have active connections
                if camera_id not in self.connections or not self.connections[camera_id]:
                    break
                
                # Get the latest processed frame
                frame_data = await camera_manager.get_jpeg_frame(camera_id)
                frame_count += 1
                
                if frame_data:
                    # Broadcast the frame
                    await self.broadcast_frame(camera_id, frame_data)
                    
                    # Log FPS every 5 seconds
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_log_time >= 5:
                        fps = frame_count / (current_time - last_log_time)
                        logger.debug(f"WebRTC stream for camera {camera_id}: {fps:.2f} FPS")
                        frame_count = 0
                        last_log_time = current_time
                
                # Control the frame rate (adaptive based on camera settings)
                try:
                    # 30 FPS max - adjust if needed
                    await asyncio.sleep(1 / 30)
                except asyncio.CancelledError:
                    logger.info(f"Frame processing task for camera {camera_id} cancelled")
                    raise
        except asyncio.CancelledError:
            logger.info(f"Frame processing task for camera {camera_id} cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error processing frames for camera {camera_id}: {str(e)}")
        finally:
            logger.info(f"Stopped frame processing for camera {camera_id}")
            async with self._lock:
                self.active_cameras.discard(camera_id)
                if camera_id in self._frame_tasks:
                    self._frame_tasks.pop(camera_id)

# Create singleton instance
webrtc_manager = WebRTCManager()

# Create router
router = APIRouter()

@router.websocket("/ws/{camera_id}")
async def webrtc_endpoint(websocket: WebSocket, camera_id: int):
    """WebSocket endpoint for WebRTC signaling"""
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
        await websocket.close(code=1000, reason="Camera not found or disabled")
        return
    
    # Get camera manager - don't need to connect yet, just verify existence
    try:
        camera_manager = await get_camera_manager()
        if camera_id not in camera_manager.cameras:
            # Add camera to manager if not already present
            async for session in get_db():
                camera = await session.get(Camera, camera_id)
                if camera and camera.enabled:
                    success = await camera_manager.add_camera(camera)
                    if not success:
                        await websocket.close(code=1011, reason="Failed to connect to camera")
                        return
    except Exception as e:
        logger.error(f"Error preparing camera {camera_id}: {str(e)}")
        await websocket.close(code=1011, reason="Server error preparing camera")
        return
    
    # Connect the client
    await webrtc_manager.connect(camera_id, websocket)
    
    try:
        # Handle incoming messages (signaling)
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("type") == "signal":
                    await webrtc_manager.handle_signaling(camera_id, websocket, data.get("data", {}))
                elif data.get("type") == "ping":
                    # Handle ping messages for connection keep-alive
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from client for camera {camera_id}")
                continue
    except WebSocketDisconnect:
        logger.info(f"WebRTC client disconnected from camera {camera_id}")
    except Exception as e:
        logger.exception(f"Error in WebRTC connection: {str(e)}")
    finally:
        # Clean up
        await webrtc_manager.disconnect(camera_id, websocket)

# DO NOT start stream processing for all cameras on startup
# Instead, we'll start processing only when clients connect