import streamlit as st
import asyncio
import json
import aiohttp
import logging
import cv2
import numpy as np
import base64
import time
import os
import threading
import queue
from pathlib import Path
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaBlackhole
from av import VideoFrame
import av
import uuid
import websockets
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cctv_test.log")
    ]
)
logger = logging.getLogger("cctv_test")

# Queues for inter-thread communication
frame_queue = queue.Queue(maxsize=30)  # 1 second buffer at 30fps
log_queue = queue.Queue(maxsize=100)
stats_queue = queue.Queue(maxsize=5)

class VideoReceiver:
    """Handles WebRTC video stream reception"""
    def __init__(self, api_base_url: str, camera_id: int, on_log=None):
        self.api_base_url = api_base_url
        self.camera_id = camera_id
        self.on_log = on_log
        self.pc = None
        self.recorder = None
        self.connected = False
        self.track_task = None
        self.session = None
        self.start_time = time.time()
        self.frame_count = 0

    def log(self, message: str, level: str = "info"):
        """Log a message both to logger and through callback"""
        if self.on_log:
            self.on_log(message, level)
        getattr(logger, level)(message)

    async def connect(self) -> bool:
        """Establish WebRTC connection"""
        try:
            # Create peer connection with STUN server
            config = RTCConfiguration([
                RTCIceServer(urls=["stun:stun.l.google.com:19302"])
            ])
            self.pc = RTCPeerConnection(configuration=config)
            self.recorder = MediaBlackhole()

            @self.pc.on("track")
            async def on_track(track):
                self.log(f"Received {track.kind} track")
                if track.kind == "video":
                    self.track_task = asyncio.create_task(self.process_track(track))
                self.recorder.addTrack(track)
                await self.recorder.start()

            @self.pc.on("connectionstatechange")
            async def on_connectionstatechange():
                self.log(f"Connection state changed to: {self.pc.connectionState}")
                if self.pc.connectionState == "connected":
                    self.connected = True
                elif self.pc.connectionState in ["failed", "closed", "disconnected"]:
                    self.connected = False

            # Create and send offer
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)

            self.session = aiohttp.ClientSession()
            async with self.session.post(
                f"{self.api_base_url}/webrtc/offer",
                json={
                    "cameraId": self.camera_id,
                    "sdp": self.pc.localDescription.sdp
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.log(f"Server error: {error_text}", "error")
                    return False

                data = await response.json()
                answer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
                await self.pc.setRemoteDescription(answer)
                return True

        except Exception as e:
            self.log(f"Connection error: {str(e)}", "error")
            return False

    async def process_track(self, track):
        """Process incoming video frames"""
        try:
            while True:
                frame = await track.recv()
                self.frame_count += 1
                
                # Convert to numpy array
                img = frame.to_ndarray(format="bgr24")
                
                # Add stats overlay
                fps = self.frame_count / (time.time() - self.start_time)
                cv2.putText(
                    img,
                    f"FPS: {fps:.1f} | WebRTC | {time.strftime('%H:%M:%S')}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 0),
                    2
                )

                # Update stats
                if self.frame_count % 30 == 0:
                    try:
                        stats_queue.put_nowait({
                            "mode": "WebRTC",
                            "fps": fps,
                            "frames": self.frame_count,
                            "connection_state": self.pc.connectionState,
                            "ice_state": self.pc.iceConnectionState
                        })
                    except queue.Full:
                        pass

                # Queue frame for display
                try:
                    frame_queue.put_nowait(img)
                except queue.Full:
                    # Skip frame if queue is full
                    pass

        except Exception as e:
            self.log(f"Track processing error: {str(e)}", "error")

    async def close(self):
        """Close connection and cleanup"""
        self.connected = False
        
        if self.track_task:
            self.track_task.cancel()
            try:
                await self.track_task
            except asyncio.CancelledError:
                pass

        if self.recorder:
            await self.recorder.stop()

        if self.pc:
            await self.pc.close()
            self.pc = None

        if self.session:
            await self.session.close()
            self.session = None

class SnapshotReceiver:
    """Handles WebSocket snapshot mode"""
    def __init__(self, ws_base_url: str, camera_id: int, on_log=None):
        self.ws_base_url = ws_base_url
        self.camera_id = camera_id
        self.on_log = on_log
        self.websocket = None
        self.connected = False
        self.ws_task = None
        self.start_time = time.time()
        self.frame_count = 0

    def log(self, message: str, level: str = "info"):
        """Log a message both to logger and through callback"""
        if self.on_log:
            self.on_log(message, level)
        getattr(logger, level)(message)

    async def connect(self) -> bool:
        """Establish WebSocket connection"""
        try:
            self.websocket = await websockets.connect(
                f"{self.ws_base_url}/webrtc/snapshot/{self.camera_id}"
            )
            self.connected = True
            
            # Start processing
            self.ws_task = asyncio.create_task(self.process_messages())
            return True

        except Exception as e:
            self.log(f"Connection error: {str(e)}", "error")
            return False

    async def process_messages(self):
        """Process incoming WebSocket messages"""
        try:
            while self.connected:
                try:
                    # Send periodic pings
                    await self.websocket.send(json.dumps({"type": "ping"}))
                    
                    # Wait for message
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=5.0
                    )
                    data = json.loads(message)

                    if data["type"] == "snapshot":
                        self.frame_count += 1
                        
                        # Decode image
                        img_data = base64.b64decode(data["data"])
                        nparr = np.frombuffer(img_data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        # Add stats overlay
                        fps = self.frame_count / (time.time() - self.start_time)
                        cv2.putText(
                            img,
                            f"FPS: {fps:.1f} | Snapshot | {time.strftime('%H:%M:%S')}",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0, 255, 0),
                            2
                        )

                        # Update stats
                        if self.frame_count % 5 == 0:
                            try:
                                stats_queue.put_nowait({
                                    "mode": "Snapshot",
                                    "fps": fps,
                                    "frames": self.frame_count,
                                    "last_frame": time.strftime("%H:%M:%S")
                                })
                            except queue.Full:
                                pass

                        # Queue frame for display
                        try:
                            frame_queue.put_nowait(img)
                        except queue.Full:
                            pass

                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    self.log("Connection closed", "warning")
                    break
                except Exception as e:
                    self.log(f"Message processing error: {str(e)}", "error")
                    break

        except asyncio.CancelledError:
            pass
        finally:
            self.connected = False

    async def close(self):
        """Close connection and cleanup"""
        self.connected = False
        
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

def log_message(message: str, level: str = "info"):
    """Add message to log queue"""
    try:
        log_queue.put_nowait({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message
        })
    except queue.Full:
        pass

async def get_cameras(api_url: str) -> list:
    """Get list of available cameras"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{api_url}/cameras") as response:
                if response.status == 200:
                    return await response.json()
    except Exception as e:
        logger.error(f"Error getting cameras: {e}")
    return []

def run_async(coro):
    """Run coroutine in current thread"""
    return asyncio.run(coro)

def main():
    st.set_page_config(
        page_title="CCTV System Test",
        page_icon="🎥",
        layout="wide"
    )

    st.title("CCTV Monitoring System Test")

    # Sidebar
    with st.sidebar:
        st.header("Configuration")
        
        # Server URL
        api_url = st.text_input(
            "Server URL",
            value="http://localhost:8000/api"
        )

        # Connection mode
        mode = st.radio(
            "Connection Mode",
            ["WebRTC", "Snapshot"]
        )

        # Camera selection
        if st.button("Refresh Cameras"):
            cameras = run_async(get_cameras(api_url))
            if cameras:
                st.session_state["cameras"] = cameras
                st.success(f"Found {len(cameras)} cameras")
            else:
                st.error("No cameras found")

        camera_options = {}
        if "cameras" in st.session_state:
            for cam in st.session_state["cameras"]:
                camera_options[f"{cam['name']} (ID: {cam['id']})"] = cam['id']

        selected_camera = st.selectbox(
            "Select Camera",
            options=list(camera_options.keys()) if camera_options else ["No cameras available"]
        )

        camera_id = camera_options.get(selected_camera) if camera_options else None

        # Connect button
        if camera_id:
            if st.button("Connect" if not st.session_state.get("connected") else "Disconnect"):
                if st.session_state.get("connected"):
                    st.session_state["connected"] = False
                    log_message("Disconnecting...")
                else:
                    st.session_state["connected"] = True
                    st.session_state["mode"] = mode
                    st.session_state["camera_id"] = camera_id
                    log_message(f"Connecting to camera {camera_id} using {mode}...")

    # Main area
    col1, col2 = st.columns([2, 1])

    # Video display
    with col1:
        st.header("Video Feed")
        video_placeholder = st.empty()
        stats_placeholder = st.empty()

    # Logs
    with col2:
        st.header("Connection Logs")
        logs_placeholder = st.empty()

    # Main loop
    while True:
        # Update video feed
        try:
            frame = frame_queue.get_nowait()
            if frame is not None:
                success, buffer = cv2.imencode(".jpg", frame)
                if success:
                    video_placeholder.image(
                        buffer.tobytes(),
                        channels="BGR",
                        use_column_width=True
                    )
        except queue.Empty:
            pass

        # Update stats
        try:
            stats = stats_queue.get_nowait()
            if stats:
                stats_md = "### Stream Statistics\n"
                stats_md += "|Metric|Value|\n|-|-|\n"
                for k, v in stats.items():
                    if isinstance(v, float):
                        v = f"{v:.2f}"
                    stats_md += f"|{k}|{v}|\n"
                stats_placeholder.markdown(stats_md)
        except queue.Empty:
            pass

        # Update logs
        logs = []
        while True:
            try:
                logs.append(log_queue.get_nowait())
            except queue.Empty:
                break

        if logs:
            logs_html = "<div style='height:400px;overflow-y:scroll'>"
            for log in logs[::-1]:
                color = {
                    "info": "white",
                    "error": "red",
                    "warning": "orange",
                    "debug": "gray"
                }.get(log["level"], "white")
                
                logs_html += f"""
                <div style='margin-bottom:5px'>
                    <span style='color:gray'>{log['timestamp']}</span>
                    <span style='color:{color}'>{log['message']}</span>
                </div>
                """
            logs_html += "</div>"
            logs_placeholder.markdown(logs_html, unsafe_allow_html=True)

        # Brief sleep to prevent CPU overuse
        time.sleep(0.033)  # ~30fps refresh

if __name__ == "__main__":
    main()