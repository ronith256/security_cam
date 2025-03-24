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
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate
from aiortc.contrib.media import MediaRecorder, MediaBlackhole
from av import VideoFrame
import av
import fractions
import uuid

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("webrtc_test.log"),
    ],
)
logger = logging.getLogger("webrtc_test")

# Frame queue for communication between asyncio and streamlit threads
frame_queue = queue.Queue(maxsize=10)
log_queue = queue.Queue(maxsize=100)
stats_queue = queue.Queue(maxsize=5)

class FrameCounter:
    def __init__(self):
        self.frame_count = 0
        self.start_time = time.time()
    
    def increment(self):
        self.frame_count += 1
    
    def get_fps(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.frame_count / elapsed
        return 0
    
    def reset(self):
        self.frame_count = 0
        self.start_time = time.time()

class VideoReceiver:
    def __init__(self, api_base_url, camera_id, log_callback=None):
        self.api_base_url = api_base_url
        self.camera_id = camera_id
        self.pc = None
        self.recorder = MediaBlackhole()
        self.counter = FrameCounter()
        self.log_callback = log_callback
        self.is_connected = False
        self.track_task = None
        self.connection_task = None
        self.ice_candidates = []
        self.session = None
        
    def log(self, message, level="info"):
        if self.log_callback:
            self.log_callback(message, level)
        
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "debug":
            logger.debug(message)
    
    async def connect(self):
        self.log("Creating peer connection")
        self.pc = RTCPeerConnection()
        
        # Set up track handler
        @self.pc.on("track")
        async def on_track(track):
            self.log(f"Received track: {track.kind}")
            if track.kind == "video":
                self.counter.reset()
                self.track_task = asyncio.create_task(self.process_track(track))
                
            # Add track to recorder
            self.recorder.addTrack(track)
            await self.recorder.start()
        
        # Set up ICE candidate handler
        @self.pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                self.log(f"Generated ICE candidate", "debug")
                await self.send_ice_candidate(candidate)
        
        # Set up connection state change handler
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            self.log(f"Connection state changed to: {self.pc.connectionState}")
            if self.pc.connectionState == "connected":
                self.is_connected = True
                self.log("WebRTC connected successfully!")
            elif self.pc.connectionState in ["failed", "closed", "disconnected"]:
                self.is_connected = False
                self.log(f"WebRTC connection {self.pc.connectionState}", "warning")
        
        # Create offer
        self.log("Creating offer")
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        
        # Send offer to server
        self.log(f"Sending offer to server for camera {self.camera_id}")
        
        # Create session if not exists
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        try:
            response = await self.session.post(
                f"{self.api_base_url}/webrtc/offer",
                json={
                    "cameraId": self.camera_id,
                    "sdp": self.pc.localDescription.sdp
                }
            )
            
            if response.status != 200:
                error_text = await response.text()
                self.log(f"Server returned error: {response.status} - {error_text}", "error")
                return False
            
            answer_data = await response.json()
            self.log("Received answer from server")
            
            # Set remote description
            answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
            await self.pc.setRemoteDescription(answer)
            
            # Send any queued ICE candidates
            if self.ice_candidates:
                for candidate in self.ice_candidates:
                    await self.send_ice_candidate(candidate)
                self.ice_candidates = []
            
            return True
        except Exception as e:
            self.log(f"Error connecting to server: {str(e)}", "error")
            return False
    
    async def send_ice_candidate(self, candidate):
        """Send ICE candidate to the server"""
        if not self.pc or not self.pc.localDescription:
            # Queue the candidate for later
            self.ice_candidates.append(candidate)
            return
        
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
                
            await self.session.post(
                f"{self.api_base_url}/webrtc/ice-candidate",
                json={
                    "cameraId": self.camera_id,
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                }
            )
        except Exception as e:
            self.log(f"Error sending ICE candidate: {str(e)}", "error")
    
    async def process_track(self, track):
        """Process incoming video frames"""
        self.log("Starting track processing")
        try:
            while True:
                try:
                    frame = await track.recv()
                    self.counter.increment()
                    
                    # Convert to numpy array
                    img = frame.to_ndarray(format="bgr24")
                    
                    # Add timestamp and stats
                    fps = self.counter.get_fps()
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    cv2.putText(
                        img, 
                        f"FPS: {fps:.1f} | Frame: {self.counter.frame_count} | {timestamp}", 
                        (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        1, 
                        (0, 255, 0), 
                        2
                    )
                    
                    # Update stats every 30 frames
                    if self.counter.frame_count % 30 == 0:
                        stats = {
                            "fps": fps,
                            "frame_count": self.counter.frame_count,
                            "ice_connection_state": self.pc.iceConnectionState,
                            "connection_state": self.pc.connectionState,
                            "timestamp": timestamp
                        }
                        try:
                            # Non-blocking put
                            stats_queue.put_nowait(stats)
                        except queue.Full:
                            # Queue is full, remove oldest item
                            try:
                                stats_queue.get_nowait()
                                stats_queue.put_nowait(stats)
                            except (queue.Empty, queue.Full):
                                pass
                    
                    # Put frame in queue for Streamlit to display
                    try:
                        # Non-blocking put
                        frame_queue.put_nowait(img)
                    except queue.Full:
                        # Queue is full, remove oldest item
                        try:
                            frame_queue.get_nowait()
                            frame_queue.put_nowait(img)
                        except (queue.Empty, queue.Full):
                            pass
                            
                except Exception as e:
                    self.log(f"Error receiving frame: {str(e)}", "error")
                    break
                
        except asyncio.CancelledError:
            self.log("Track processing cancelled", "warning")
        except Exception as e:
            self.log(f"Track processing error: {str(e)}", "error")
        finally:
            self.log("Track processing stopped")
    
    async def close(self):
        """Close the connection and release resources"""
        self.log("Closing WebRTC connection")
        self.is_connected = False
        
        # Cancel track task if running
        if self.track_task and not self.track_task.done():
            self.track_task.cancel()
            try:
                await self.track_task
            except asyncio.CancelledError:
                pass
        
        # Stop recorder
        if self.recorder:
            await self.recorder.stop()
        
        # Close peer connection
        if self.pc:
            await self.pc.close()
            self.pc = None
        
        # Close session
        if self.session:
            await self.session.close()
            self.session = None
        
        self.log("WebRTC connection closed")

class SnapshotReceiver:
    def __init__(self, ws_base_url, camera_id, log_callback=None):
        self.ws_base_url = ws_base_url
        self.camera_id = camera_id
        self.log_callback = log_callback
        self.websocket = None
        self.counter = FrameCounter()
        self.is_connected = False
        self.ws_task = None
    
    def log(self, message, level="info"):
        if self.log_callback:
            self.log_callback(message, level)
        
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "debug":
            logger.debug(message)
    
    async def connect(self):
        """Connect to the WebSocket snapshot endpoint"""
        import websockets
        
        self.log(f"Connecting to WebSocket at {self.ws_base_url}/webrtc/snapshot/{self.camera_id}")
        
        try:
            self.websocket = await websockets.connect(f"{self.ws_base_url}/webrtc/snapshot/{self.camera_id}")
            self.is_connected = True
            self.counter.reset()
            
            # Send initial ping
            await self.websocket.send(json.dumps({"type": "ping"}))
            
            # Start processing task
            self.ws_task = asyncio.create_task(self.process_messages())
            
            self.log("WebSocket connected successfully")
            return True
        except Exception as e:
            self.log(f"Error connecting to WebSocket: {str(e)}", "error")
            self.is_connected = False
            return False
    
    async def process_messages(self):
        """Process incoming WebSocket messages"""
        import websockets
        
        try:
            while self.is_connected and self.websocket:
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(self.websocket.recv(), 1.0)
                    data = json.loads(message)
                    
                    if data["type"] == "snapshot":
                        # Got a snapshot
                        self.counter.increment()
                        
                        # Update stats every 5 frames
                        if self.counter.frame_count % 5 == 0:
                            fps = self.counter.get_fps()
                            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                            stats = {
                                "fps": fps,
                                "frame_count": self.counter.frame_count,
                                "connection_type": "WebSocket Snapshot",
                                "timestamp": timestamp
                            }
                            try:
                                stats_queue.put_nowait(stats)
                            except queue.Full:
                                try:
                                    stats_queue.get_nowait()
                                    stats_queue.put_nowait(stats)
                                except (queue.Empty, queue.Full):
                                    pass
                        
                        # Decode base64 image
                        img_data = base64.b64decode(data["data"])
                        nparr = np.frombuffer(img_data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        # Add timestamp and stats
                        fps = self.counter.get_fps()
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        cv2.putText(
                            img, 
                            f"FPS: {fps:.1f} | Frame: {self.counter.frame_count} | {timestamp}", 
                            (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 
                            1, 
                            (0, 255, 0), 
                            2
                        )
                        
                        # Put frame in queue for Streamlit to display
                        try:
                            frame_queue.put_nowait(img)
                        except queue.Full:
                            try:
                                frame_queue.get_nowait()
                                frame_queue.put_nowait(img)
                            except (queue.Empty, queue.Full):
                                pass
                    
                    elif data["type"] == "pong":
                        self.log("Received pong", "debug")
                    
                    elif data["type"] == "info":
                        self.log(f"Info from server: {data.get('message', '')}")
                
                except asyncio.TimeoutError:
                    # Send ping on timeout
                    if self.websocket:
                        try:
                            await self.websocket.send(json.dumps({"type": "ping"}))
                        except:
                            self.log("WebSocket connection lost", "error")
                            break
                except websockets.exceptions.ConnectionClosed:
                    self.log("WebSocket connection closed", "warning")
                    break
                except Exception as e:
                    self.log(f"Error processing WebSocket message: {str(e)}", "error")
        
        except asyncio.CancelledError:
            self.log("WebSocket task cancelled", "warning")
        except Exception as e:
            self.log(f"WebSocket processing error: {str(e)}", "error")
        finally:
            self.is_connected = False
            self.log("WebSocket processing stopped")
    
    async def close(self):
        """Close the WebSocket connection"""
        self.log("Closing WebSocket connection")
        self.is_connected = False
        
        # Cancel task if running
        if self.ws_task and not self.ws_task.done():
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        self.log("WebSocket connection closed")

async def get_cameras(api_base_url):
    """Get list of available cameras from the API"""
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(f"{api_base_url}/cameras")
            
            if response.status != 200:
                return []
            
            data = await response.json()
            return data
    except Exception as e:
        logger.error(f"Error getting cameras: {str(e)}")
        return []

async def test_camera_connection(api_base_url, camera_id):
    """Test the direct connection to a camera"""
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(f"{api_base_url}/cameras/{camera_id}/test")
            
            if response.status != 200:
                return None
            
            data = await response.json()
            return data
    except Exception as e:
        logger.error(f"Error testing camera: {str(e)}")
        return None

def add_to_log_queue(message, level="info"):
    """Add a message to the log queue for display in the UI"""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message
        }
        log_queue.put_nowait(log_entry)
    except queue.Full:
        try:
            log_queue.get_nowait()
            log_queue.put_nowait(log_entry)
        except (queue.Empty, queue.Full):
            pass

async def clean_queues():
    """Utility to clean all queues"""
    # Clean frame queue
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            break
    
    # Clean log queue
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break
    
    # Clean stats queue
    while not stats_queue.empty():
        try:
            stats_queue.get_nowait()
        except queue.Empty:
            break

async def background_tasks(api_url, camera_id, connection_mode):
    """Run background tasks for WebRTC or WebSocket connections"""
    logger.info(f"Starting background tasks for camera {camera_id} in {connection_mode} mode")
    
    # Clean queues
    await clean_queues()
    
    # Add initial logs
    add_to_log_queue(f"Starting {connection_mode} connection to camera {camera_id}")
    add_to_log_queue(f"Server URL: {api_url}")
    
    # Test camera connection
    add_to_log_queue("Testing camera connection...")
    connection_info = await test_camera_connection(api_url, camera_id)
    
    if connection_info:
        add_to_log_queue("Camera connection test successful")
        
        if connection_info['tests']['connection']['success']:
            add_to_log_queue("Camera is connected to the server")
        else:
            add_to_log_queue("Camera is not connected to the server", "warning")
            
        if connection_info['tests']['frame']['success']:
            add_to_log_queue("Camera is providing frames")
        else:
            add_to_log_queue("Camera is not providing frames", "warning")
    else:
        add_to_log_queue("Camera connection test failed", "error")
    
    # Initialize WebRTC or WebSocket connection
    if connection_mode == "WebRTC":
        receiver = VideoReceiver(api_url, camera_id, add_to_log_queue)
        
        try:
            # Connect
            connection_successful = await receiver.connect()
            
            if connection_successful:
                add_to_log_queue("WebRTC connection established, waiting for video...")
                
                # Wait for 30 seconds or until connection is closed
                timeout = 600  # 10 minutes
                start_time = time.time()
                
                while receiver.is_connected and time.time() - start_time < timeout:
                    await asyncio.sleep(1)
                
                if time.time() - start_time >= timeout:
                    add_to_log_queue("Connection timeout reached", "warning")
            else:
                add_to_log_queue("Failed to establish WebRTC connection", "error")
        
        except Exception as e:
            add_to_log_queue(f"Error in WebRTC connection: {str(e)}", "error")
        
        finally:
            # Cleanup
            await receiver.close()
            add_to_log_queue("WebRTC connection closed")
    
    elif connection_mode == "Snapshot":
        # Convert HTTP to WebSocket URL
        ws_url = api_url.replace("http", "ws")
        
        receiver = SnapshotReceiver(ws_url, camera_id, add_to_log_queue)
        
        try:
            # Connect
            connection_successful = await receiver.connect()
            
            if connection_successful:
                add_to_log_queue("WebSocket connection established, waiting for snapshots...")
                
                # Wait for 30 seconds or until connection is closed
                timeout = 600  # 10 minutes
                start_time = time.time()
                
                while receiver.is_connected and time.time() - start_time < timeout:
                    await asyncio.sleep(1)
                
                if time.time() - start_time >= timeout:
                    add_to_log_queue("Connection timeout reached", "warning")
            else:
                add_to_log_queue("Failed to establish WebSocket connection", "error")
        
        except Exception as e:
            add_to_log_queue(f"Error in WebSocket connection: {str(e)}", "error")
        
        finally:
            # Cleanup
            await receiver.close()
            add_to_log_queue("WebSocket connection closed")
    
    logger.info("Background tasks completed")

def run_async(coroutine):
    """Utility function to run coroutines in the streamlit app"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coroutine)

def main():
    st.set_page_config(
        page_title="WebRTC Test App",
        page_icon="🎥",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    st.title("WebRTC Test App")
    st.markdown("""
    This app helps you test WebRTC and WebSocket snapshot connections to your CCTV monitoring system.
    """)
    
    # Sidebar config
    st.sidebar.header("Configuration")
    
    # URL input
    api_url = st.sidebar.text_input(
        "Server URL",
        value="http://localhost:8000/api",
        help="The base URL of your API server"
    )
    
    # Connection mode
    connection_mode = st.sidebar.radio(
        "Connection Mode",
        ["WebRTC", "Snapshot"],
        help="Choose the connection method"
    )
    
    # Get camera list
    if st.sidebar.button("Refresh Camera List"):
        with st.sidebar.status("Getting cameras..."):
            cameras = run_async(get_cameras(api_url))
            
            if cameras:
                st.session_state['cameras'] = cameras
                st.sidebar.success(f"Found {len(cameras)} cameras")
            else:
                st.sidebar.error("No cameras found or error connecting to server")
                st.session_state['cameras'] = []
    
    # Camera selection
    camera_options = {}
    if 'cameras' in st.session_state and st.session_state['cameras']:
        for camera in st.session_state['cameras']:
            camera_options[f"{camera['id']}: {camera['name']}"] = camera['id']
    
    selected_camera = st.sidebar.selectbox(
        "Select Camera",
        list(camera_options.keys()) if camera_options else ["No cameras available"],
        help="Select a camera to connect to"
    )
    
    camera_id = camera_options.get(selected_camera) if camera_options else None
    
    # Connection button
    connection_status = st.sidebar.empty()
    if camera_id and st.sidebar.button(f"Connect ({connection_mode})"):
        # Start background tasks
        connection_status.info("Connecting...")
        if 'task' in st.session_state:
            st.warning("Already connected. Disconnect first.")
        else:
            st.session_state['task'] = threading.Thread(
                target=lambda: run_async(
                    background_tasks(api_url, camera_id, connection_mode)
                ),
                daemon=True
            )
            st.session_state['task'].start()
            st.session_state['connected'] = True
    
    # Disconnect button
    if 'connected' in st.session_state and st.session_state['connected']:
        if st.sidebar.button("Disconnect"):
            if 'task' in st.session_state:
                st.session_state['connected'] = False
                if st.session_state['task'].is_alive():
                    # Just let it finish on its own
                    connection_status.warning("Disconnecting...")
                    # In a real app, we'd have a way to signal the task to stop
                else:
                    connection_status.info("Disconnected")
                    st.session_state.pop('task', None)
                    st.session_state.pop('connected', None)
                    
    # Save logs button
    if st.sidebar.button("Save Logs"):
        # Save logs to file
        logs_path = Path("webrtc_test_logs")
        logs_path.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        log_file = logs_path / f"webrtc_test_{timestamp}.log"
        
        with open(log_file, "w") as f:
            # Add all items in the log queue
            logs = []
            while not log_queue.empty():
                try:
                    logs.append(log_queue.get_nowait())
                except queue.Empty:
                    break
            
            for log in logs:
                f.write(f"[{log['timestamp']}] [{log['level'].upper()}] {log['message']}\n")
                # Put log back in queue
                try:
                    log_queue.put_nowait(log)
                except queue.Full:
                    pass
        
        st.sidebar.success(f"Logs saved to {log_file}")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    # Video display
    with col1:
        st.header("Video Stream")
        video_placeholder = st.empty()
        
        # Stats below video
        stats_placeholder = st.empty()
    
    # Logs display
    with col2:
        st.header("Logs")
        logs_placeholder = st.empty()
    
    # Main loop for updating UI
    while True:
        # Update video if frame available
        try:
            frame = frame_queue.get_nowait()
            if frame is not None:
                # Encode frame as JPEG
                _, buffer = cv2.imencode('.jpg', frame)
                img_bytes = buffer.tobytes()
                
                # Display frame
                video_placeholder.image(img_bytes, channels="BGR", use_column_width=True)
        except queue.Empty:
            pass
        
        # Update logs
        logs = []
        updated_logs = False
        
        # Get all available logs
        while not log_queue.empty():
            try:
                log = log_queue.get_nowait()
                logs.append(log)
                updated_logs = True
            except queue.Empty:
                break
        
        # Display logs if updated
        if updated_logs:
            # Format logs with color coding
            log_html = "<div style='height: 400px; overflow-y: scroll;'>"
            for log in logs[::-1]:  # Reverse to show newest first
                level = log['level'].upper()
                color = {
                    "INFO": "white",
                    "ERROR": "red",
                    "WARNING": "orange",
                    "DEBUG": "gray"
                }.get(level, "white")
                
                log_html += f"<div style='margin-bottom: 5px;'>"
                log_html += f"<span style='color: #888; font-size: 12px;'>{log['timestamp']}</span> "
                log_html += f"<span style='color: {color}; font-weight: bold;'>[{level}]</span> "
                log_html += f"<span>{log['message']}</span>"
                log_html += "</div>"
            
            log_html += "</div>"
            logs_placeholder.markdown(log_html, unsafe_allow_html=True)
            
            # Put logs back in queue
            for log in logs:
                try:
                    log_queue.put_nowait(log)
                except queue.Full:
                    # If queue is full, remove oldest item and try again
                    try:
                        log_queue.get_nowait()
                        log_queue.put_nowait(log)
                    except (queue.Empty, queue.Full):
                        pass
        
        # Update stats
        try:
            stats = stats_queue.get_nowait()
            if stats:
                # Create stats table
                stats_md = "### Stream Statistics\n"
                stats_md += "| Metric | Value |\n"
                stats_md += "|--------|-------|\n"
                
                for key, value in stats.items():
                    if key == "fps":
                        value = f"{value:.2f}"
                    stats_md += f"| {key} | {value} |\n"
                
                stats_placeholder.markdown(stats_md)
        except queue.Empty:
            pass
        
        # Brief pause
        time.sleep(0.033)  # ~30 FPS refresh rate

if __name__ == "__main__":
    main()