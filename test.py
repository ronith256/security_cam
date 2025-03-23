import asyncio
import json
import websockets
import aiohttp
import argparse
import logging
import cv2
import base64
import numpy as np
import time
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate
from aiortc.contrib.media import MediaRecorder, MediaBlackhole

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webrtc_test")

# Global variables
api_base_url = "http://localhost:8000/api"
ws_base_url = "ws://localhost:8000/api"

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
    def __init__(self, output_file=None, save_frames=False, display=False):
        self.pc = None
        self.recorder = None
        self.save_frames = save_frames
        self.display = display
        self.output_file = output_file
        self.counter = FrameCounter()
        self.frame_directory = "frames"
        
        if self.save_frames:
            import os
            os.makedirs(self.frame_directory, exist_ok=True)
    
    async def connect(self, camera_id):
        # Create peer connection
        self.pc = RTCPeerConnection()
        
        # Set up media recorder if output file is specified
        if self.output_file:
            self.recorder = MediaRecorder(self.output_file)
        else:
            # Use MediaBlackhole to consume media if we're not recording
            self.recorder = MediaBlackhole()
        
        # Set up track handlers
        @self.pc.on("track")
        async def on_track(track):
            logger.info(f"Received track: {track.kind}")
            if track.kind == "video":
                self.counter.reset()
                
                # Process each frame
                async def process_frames():
                    while True:
                        try:
                            frame = await track.recv()
                            self.counter.increment()
                            
                            # Display current FPS every second
                            if self.counter.frame_count % 30 == 0:
                                logger.info(f"Receiving at {self.counter.get_fps():.2f} FPS")
                            
                            # Save frames if requested
                            if self.save_frames:
                                # Convert to numpy array and save as JPG
                                img = frame.to_ndarray(format="bgr24")
                                filename = f"{self.frame_directory}/frame_{self.counter.frame_count:04d}.jpg"
                                cv2.imwrite(filename, img)
                            
                            # Display frames if requested
                            if self.display:
                                img = frame.to_ndarray(format="bgr24")
                                cv2.imshow("WebRTC Stream", img)
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    break
                                
                        except Exception as e:
                            logger.error(f"Error processing frame: {e}")
                            break
                
                asyncio.create_task(process_frames())
                
            # Add track to recorder
            self.recorder.addTrack(track)
            await self.recorder.start()
        
        # Create offer
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        
        # Send offer to server
        async with aiohttp.ClientSession() as session:
            logger.info(f"Sending offer to server for camera {camera_id}")
            response = await session.post(
                f"{api_base_url}/webrtc/offer",
                json={
                    "cameraId": camera_id,
                    "sdp": self.pc.localDescription.sdp
                }
            )
            
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Server returned error: {response.status} - {error_text}")
                return False
            
            answer_data = await response.json()
            logger.info("Received answer from server")
            
            # Set remote description
            answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
            await self.pc.setRemoteDescription(answer)
            
            return True
    
    async def add_ice_candidate(self, candidate, sdp_mid, sdp_m_line_index, camera_id):
        """Send ICE candidate to the server"""
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{api_base_url}/webrtc/ice-candidate",
                    json={
                        "cameraId": camera_id,
                        "candidate": candidate,
                        "sdpMid": sdp_mid,
                        "sdpMLineIndex": sdp_m_line_index
                    }
                )
        except Exception as e:
            logger.error(f"Error sending ICE candidate: {e}")
    
    async def close(self):
        """Close the connection and release resources"""
        if self.recorder:
            await self.recorder.stop()
        
        if self.pc:
            await self.pc.close()
        
        if self.display:
            cv2.destroyAllWindows()

async def test_webrtc(camera_id, duration=30, output_file=None, save_frames=False, display=False):
    """Test WebRTC connection to a camera"""
    logger.info(f"Testing WebRTC connection to camera {camera_id}")
    
    receiver = VideoReceiver(output_file, save_frames, display)
    
    try:
        # Establish connection
        success = await receiver.connect(camera_id)
        if not success:
            logger.error("Failed to establish WebRTC connection")
            return False
        
        # Register ICE candidates
        @receiver.pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                logger.debug(f"Sending ICE candidate: {candidate}")
                await receiver.add_ice_candidate(
                    candidate.candidate, 
                    candidate.sdpMid, 
                    candidate.sdpMLineIndex,
                    camera_id
                )
        
        # Keep the connection open for the specified duration
        logger.info(f"Connection established. Receiving for {duration} seconds...")
        await asyncio.sleep(duration)
        
        # Display final statistics
        logger.info(f"Test complete. Average FPS: {receiver.counter.get_fps():.2f}")
        
        return True
    except Exception as e:
        logger.error(f"Error in WebRTC test: {e}")
        return False
    finally:
        await receiver.close()

async def test_snapshot_mode(camera_id, duration=30, save_frames=False):
    """Test the WebSocket snapshot mode for a camera"""
    logger.info(f"Testing WebSocket snapshot mode for camera {camera_id}")
    
    counter = FrameCounter()
    
    try:
        # Connect to WebSocket
        ws_url = f"{ws_base_url}/webrtc/snapshot/{camera_id}"
        logger.info(f"Connecting to WebSocket at {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            logger.info("WebSocket connected.")
            
            # Set up frame directory
            if save_frames:
                import os
                frame_dir = "snapshot_frames"
                os.makedirs(frame_dir, exist_ok=True)
            
            # Send initial ping
            await websocket.send(json.dumps({"type": "ping"}))
            
            # Keep receiving for the specified duration
            end_time = time.time() + duration
            while time.time() < end_time:
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(websocket.recv(), 1.0)
                    data = json.loads(message)
                    
                    if data["type"] == "snapshot":
                        # Got a snapshot
                        counter.increment()
                        
                        # Display stats every 5 frames
                        if counter.frame_count % 5 == 0:
                            logger.info(f"Received {counter.frame_count} snapshots, {counter.get_fps():.2f} FPS")
                        
                        # Save frame if requested
                        if save_frames:
                            try:
                                # Decode base64 image
                                img_data = base64.b64decode(data["data"])
                                nparr = np.frombuffer(img_data, np.uint8)
                                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                
                                # Save to file
                                filename = f"{frame_dir}/snapshot_{counter.frame_count:04d}.jpg"
                                cv2.imwrite(filename, img)
                            except Exception as e:
                                logger.error(f"Error saving snapshot: {e}")
                    
                    elif data["type"] == "pong":
                        logger.debug("Received pong")
                    
                    elif data["type"] == "info":
                        logger.info(f"Info from server: {data.get('message', '')}")
                    
                    # Send periodic pings to keep the connection alive
                    if time.time() % 10 < 1:  # Roughly every 10 seconds
                        await websocket.send(json.dumps({"type": "ping"}))
                
                except asyncio.TimeoutError:
                    # Send ping on timeout
                    try:
                        await websocket.send(json.dumps({"type": "ping"}))
                    except:
                        logger.error("WebSocket connection lost")
                        break
                except Exception as e:
                    logger.error(f"Error receiving snapshot: {e}")
            
            # Display final statistics
            logger.info(f"Snapshot test complete. Received {counter.frame_count} snapshots.")
            logger.info(f"Average FPS: {counter.get_fps():.2f}")
            
            return counter.frame_count > 0
    
    except Exception as e:
        logger.error(f"Error in WebSocket test: {e}")
        return False

async def check_camera_status(camera_id):
    """Check the status of a camera"""
    try:
        async with aiohttp.ClientSession() as session:
            logger.info(f"Checking status for camera {camera_id}")
            response = await session.get(f"{api_base_url}/cameras/{camera_id}/status")
            
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Error getting camera status: {response.status} - {error_text}")
                return None
            
            data = await response.json()
            return data
    except Exception as e:
        logger.error(f"Error checking camera status: {e}")
        return None

async def test_camera_connection(camera_id):
    """Test the direct connection to a camera"""
    try:
        async with aiohttp.ClientSession() as session:
            logger.info(f"Testing connection for camera {camera_id}")
            response = await session.get(f"{api_base_url}/cameras/{camera_id}/test")
            
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Error testing camera: {response.status} - {error_text}")
                return None
            
            data = await response.json()
            return data
    except Exception as e:
        logger.error(f"Error testing camera: {e}")
        return None

async def list_cameras():
    """Get list of all cameras"""
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("Getting camera list")
            response = await session.get(f"{api_base_url}/cameras")
            
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Error getting camera list: {response.status} - {error_text}")
                return []
            
            data = await response.json()
            return data
    except Exception as e:
        logger.error(f"Error listing cameras: {e}")
        return []

async def main():
    parser = argparse.ArgumentParser(description="Test WebRTC implementation")
    parser.add_argument("--camera", type=int, help="Camera ID to test")
    parser.add_argument("--list", action="store_true", help="List available cameras")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="Base URL for the API")
    parser.add_argument("--output", type=str, help="Output file for recording (webrtc mode only)")
    parser.add_argument("--save-frames", action="store_true", help="Save frames to disk")
    parser.add_argument("--display", action="store_true", help="Display frames (webrtc mode only)")
    parser.add_argument("--mode", choices=["webrtc", "snapshot", "status", "all"], default="all", 
                        help="Test mode: webrtc, snapshot, status, or all")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Update global URLs
    global api_base_url, ws_base_url
    api_base_url = f"{args.url}/api"
    ws_base_url = api_base_url.replace("http", "ws")
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # List cameras if requested
    if args.list:
        cameras = await list_cameras()
        print("\nAvailable cameras:")
        for camera in cameras:
            print(f"ID: {camera['id']}, Name: {camera['name']}, Enabled: {camera['enabled']}")
            print(f"  RTSP URL: {camera['rtsp_url']}")
            print(f"  Features: " + 
                  ", ".join([feature for feature, enabled in {
                      "People Detection": camera['detect_people'],
                      "People Counting": camera['count_people'],
                      "Face Recognition": camera['recognize_faces'],
                      "Template Matching": camera['template_matching']
                  }.items() if enabled])
            )
            print()
        
        if not cameras:
            print("No cameras found.\n")
        
        if not args.camera:
            return
    
    # Ensure we have a camera ID
    if not args.camera:
        print("Please specify a camera ID with --camera.")
        return
    
    # Test camera status
    if args.mode in ["status", "all"]:
        print(f"\n--- Testing camera {args.camera} status ---")
        status = await check_camera_status(args.camera)
        if status:
            print(f"Camera active: {status['active']}")
            print(f"Current FPS: {status['fps']:.2f}")
            print(f"Current occupancy: {status['current_occupancy']}")
            
            # Check for existing detections
            if status['detection_results']:
                print("\nDetection results:")
                for key, value in status['detection_results'].items():
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} items")
                    else:
                        print(f"  {key}: {value}")
        
        # Get detailed connection info
        connection_test = await test_camera_connection(args.camera)
        if connection_test:
            print("\nConnection test results:")
            print(f"Camera in manager: {connection_test['tests']['in_manager']}")
            print(f"Connection successful: {connection_test['tests']['connection']['success']}")
            
            if connection_test['tests']['frame']['success']:
                frame_info = connection_test['tests']['frame']['info']
                print(f"Frame available: Yes, shape: {frame_info.get('shape')}")
                print(f"Frame age: {frame_info.get('age', 'N/A'):.2f} seconds")
            else:
                print(f"Frame available: No, error: {connection_test['tests']['frame']['error']}")
            
            if 'processor_info' in connection_test:
                print("\nProcessor information:")
                info = connection_test['processor_info']
                print(f"Connected: {info.get('connected', False)}")
                print(f"Processing: {info.get('processing', False)}")
                print(f"FPS: {info.get('fps', 0):.2f}")
    
    # Test WebRTC
    if args.mode in ["webrtc", "all"]:
        print(f"\n--- Testing WebRTC streaming for camera {args.camera} ---")
        webrtc_success = await test_webrtc(
            args.camera, 
            args.duration, 
            args.output, 
            args.save_frames,
            args.display
        )
        print(f"WebRTC test {'passed' if webrtc_success else 'failed'}")
    
    # Test Snapshot mode
    if args.mode in ["snapshot", "all"]:
        print(f"\n--- Testing snapshot mode for camera {args.camera} ---")
        snapshot_success = await test_snapshot_mode(
            args.camera, 
            args.duration,
            args.save_frames
        )
        print(f"Snapshot test {'passed' if snapshot_success else 'failed'}")

if __name__ == "__main__":
    asyncio.run(main())