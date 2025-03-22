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
import time
import websockets

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
                        logger.info(f"Starting frame processing task for camera {camera_id}")
                        self._frame_tasks[camera_id] = asyncio.create_task(
                            self._process_frames(camera_id, camera_manager)
                        )
        
        logger.info(f"WebRTC client connected for camera {camera_id}")
        
        # Immediately send a test message to verify the connection
        try:
            test_message = json.dumps({"type": "info", "message": "WebRTC connection established"})
            await websocket.send_text(test_message)
            logger.info(f"Sent test message to new client for camera {camera_id}")
        except Exception as e:
            logger.error(f"Error sending test message: {str(e)}")

    async def _process_frames(self, camera_id: int, camera_manager):
        """Process and send frames for a camera"""
        logger.info(f"Starting frame processing for camera {camera_id}")
        frames_sent = 0
        frames_failed = 0
        start_time = time.time()
        
        try:
            while camera_id in self.active_cameras:
                # Check if we have active connections
                if camera_id not in self.connections or not self.connections[camera_id]:
                    logger.info(f"No active connections for camera {camera_id}, stopping frame processing")
                    break
                
                # Get the latest processed frame
                try:
                    frame_data = await camera_manager.get_jpeg_frame(camera_id)
                    
                    if frame_data:
                        # Reset error counter on success
                        frames_sent += 1
                        
                        # Log every 100 frames
                        if frames_sent % 100 == 0:
                            elapsed = time.time() - start_time
                            fps = frames_sent / elapsed
                            logger.info(f"WebRTC for camera {camera_id}: Sent {frames_sent} frames ({fps:.2f} FPS), failed: {frames_failed}")
                        
                        # Broadcast the frame
                        clients_before = len(self.connections.get(camera_id, []))
                        await self.broadcast_frame(camera_id, frame_data)
                        clients_after = len(self.connections.get(camera_id, []))
                        
                        if clients_before != clients_after:
                            logger.info(f"Clients changed during broadcast: {clients_before} → {clients_after}")
                    else:
                        frames_failed += 1
                        if frames_failed % 10 == 0:
                            logger.warning(f"Failed to get frame {frames_failed} times for camera {camera_id}")
                            # Add a small delay to avoid tight loop when no frames are available
                            await asyncio.sleep(0.5)
                except Exception as e:
                    logger.exception(f"Error in frame processing for camera {camera_id}: {str(e)}")
                    frames_failed += 1
                    await asyncio.sleep(0.5)  # Add delay on error
                
                # Control the frame rate
                try:
                    # 15 FPS for WebRTC stream (adjust as needed)
                    await asyncio.sleep(1 / 15)
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

    async def broadcast_frame(self, camera_id: int, frame_data: bytes):
        """Broadcast a frame to all connected clients for this camera"""
        if camera_id not in self.connections:
            return
        
        # Convert frame data to base64 for WebRTC streaming
        try:
            encoded_frame = base64.b64encode(frame_data).decode('utf-8')
            message = json.dumps({
                "type": "frame",
                "data": encoded_frame
            })
        except Exception as e:
            logger.exception(f"Error encoding frame for camera {camera_id}: {str(e)}")
            return
        
        disconnected_clients = []
        for client in self.connections.get(camera_id, []):
            try:
                await client.send_text(message)
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"WebSocket connection closed while sending frame for camera {camera_id}")
                disconnected_clients.append(client)
            except Exception as e:
                logger.warning(f"Failed to send frame to client: {str(e)}")
                disconnected_clients.append(client)
        
        # Clean up disconnected clients
        if disconnected_clients:
            logger.info(f"Removing {len(disconnected_clients)} disconnected clients for camera {camera_id}")
            async with self._lock:
                for client in disconnected_clients:
                    if camera_id in self.connections and client in self.connections[camera_id]:
                        self.connections[camera_id].remove(client)
                
                # If this was the last client, stop frame processing
                if camera_id in self.connections and not self.connections[camera_id]:
                    logger.info(f"No more clients for camera {camera_id}, cleaning up")
                    self.connections.pop(camera_id)
                    self.active_cameras.discard(camera_id)
                    
                    # Cancel frame processing task
                    if camera_id in self._frame_tasks and not self._frame_tasks[camera_id].done():
                        logger.info(f"Cancelling frame processing task for camera {camera_id}")
                        self._frame_tasks[camera_id].cancel()

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
        logger.warning(f"WebSocket connection attempt for disabled or non-existent camera {camera_id}")
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
                    logger.info(f"Adding camera {camera_id} to manager for WebRTC streaming")
                    success = await camera_manager.add_camera(camera)
                    if not success:
                        logger.error(f"Failed to connect to camera {camera_id} for WebRTC")
                        await websocket.close(code=1011, reason="Failed to connect to camera")
                        return
    except Exception as e:
        logger.error(f"Error preparing camera {camera_id} for WebRTC: {str(e)}")
        await websocket.close(code=1011, reason="Server error preparing camera")
        return
    
    # Connect the client
    logger.info(f"WebRTC WebSocket connection established for camera {camera_id}")
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
                    logger.debug(f"Ping received from client for camera {camera_id}, sent pong")
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