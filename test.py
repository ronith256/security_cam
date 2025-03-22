#!/usr/bin/env python3
import asyncio
import websockets
import json
import base64
import cv2
import numpy as np
import time
import argparse
import sys
import requests
import threading

def print_diagnostic_info(args):
    """Print diagnostic information about the camera"""
    try:
        # Get camera test info
        print(f"\nFetching camera test information...")
        response = requests.get(f"{args.http_server}/api/cameras/{args.camera_id}/test")
        if response.status_code == 200:
            test_info = response.json()
            print("\n=== Camera Diagnostic Information ===")
            print(f"Camera ID: {test_info['camera_id']}")
            print(f"Name: {test_info['camera_name']}")
            print(f"RTSP URL: {test_info['rtsp_url']}")
            print(f"Enabled: {test_info['camera_enabled']}")
            
            print("\nTest Results:")
            tests = test_info['tests']
            print(f"In Manager: {tests['in_manager']}")
            
            print(f"Connection: {tests['connection']['success']}")
            if tests['connection']['error']:
                print(f"  Error: {tests['connection']['error']}")
            
            print(f"Frame: {tests['frame']['success']}")
            if tests['frame']['error']:
                print(f"  Error: {tests['frame']['error']}")
            if tests['frame']['info']:
                info = tests['frame']['info']
                print(f"  Shape: {info.get('shape')}")
                print(f"  Age: {info.get('age', 'N/A')} seconds")
                print(f"  JPEG Size: {info.get('jpeg_size', 'N/A')} bytes")
            
            if 'processor_info' in test_info and test_info['processor_info']:
                proc = test_info['processor_info']
                print("\nProcessor Info:")
                print(f"  Connected: {proc['connected']}")
                print(f"  Processing: {proc['processing']}")
                print(f"  FPS: {proc['fps']}")
            
            print("\nCamera is", "ready for streaming" if tests['frame']['success'] else "not ready for streaming")
        else:
            print(f"Error getting camera test information: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error getting diagnostic information: {e}")

async def test_webrtc_stream(args):
    """Test WebRTC streaming by connecting to the WebSocket endpoint"""
    uri = f"{args.ws_server}/api/webrtc/ws/{args.camera_id}"
    print(f"\nConnecting to {uri}...")
    
    # Print diagnostic info before connecting
    if args.http_server:
        threading.Thread(target=print_diagnostic_info, args=(args,)).start()
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket!")
            
            # Keep the connection alive
            frame_count = 0
            start_time = time.time()
            last_ping_time = time.time()
            last_message_time = time.time()
            window_name = f"Camera {args.camera_id} Stream"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 800, 600)
            
            # Add info to window
            info_img = np.zeros((100, 800, 3), np.uint8)
            cv2.putText(info_img, f"Waiting for frames from camera {args.camera_id}...", 
                      (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow(window_name, info_img)
            cv2.waitKey(1)
            
            try:
                while True:
                    # Send ping every 30 seconds
                    current_time = time.time()
                    if current_time - last_ping_time > 30:
                        print("Sending ping...")
                        await websocket.send(json.dumps({"type": "ping"}))
                        last_ping_time = current_time
                    
                    # Get the next message with a timeout
                    try:
                        # Check if we've gone too long without a message
                        if current_time - last_message_time > 60:
                            print("No messages received for 60 seconds. Connection may be stalled.")
                            print("Press 'q' to quit or wait for reconnection...")
                            
                        message = await asyncio.wait_for(websocket.recv(), timeout=5)
                        last_message_time = time.time()
                        
                        try:
                            data = json.loads(message)
                            
                            if data.get("type") == "frame":
                                # Decode the base64 frame
                                frame_data = base64.b64decode(data.get("data", ""))
                                
                                # Convert to OpenCV format
                                nparr = np.frombuffer(frame_data, np.uint8)
                                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                
                                if img is not None:
                                    # Display the frame
                                    cv2.imshow(window_name, img)
                                    
                                    # Press q to quit
                                    key = cv2.waitKey(1) & 0xFF
                                    if key == ord('q'):
                                        print("Quitting...")
                                        break
                                    elif key == ord('s'):
                                        # Save snapshot
                                        snapshot_name = f"camera_{args.camera_id}_snapshot_{int(time.time())}.jpg"
                                        cv2.imwrite(snapshot_name, img)
                                        print(f"Snapshot saved as {snapshot_name}")
                                    
                                    frame_count += 1
                                    if frame_count % 30 == 0:
                                        elapsed = time.time() - start_time
                                        fps = frame_count / elapsed
                                        print(f"Received {frame_count} frames, {fps:.2f} FPS")
                            elif data.get("type") == "pong":
                                print("Received pong from server")
                            elif data.get("type") == "info":
                                print(f"Info from server: {data.get('message', '')}")
                            else:
                                print(f"Received unknown message type: {data.get('type')}")
                        except json.JSONDecodeError:
                            print(f"Received non-JSON message: {message[:100]}...")
                        except Exception as e:
                            print(f"Error processing message: {e}")
                    except asyncio.TimeoutError:
                        print("No frames received for 5 seconds. Still waiting...")
                        
                        # Update info window to show waiting status
                        elapsed = time.time() - start_time
                        info_img = np.zeros((100, 800, 3), np.uint8)
                        cv2.putText(info_img, f"Waiting for frames from camera {args.camera_id}... ({elapsed:.1f}s)", 
                                  (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                        cv2.imshow(window_name, info_img)
                        cv2.waitKey(1)
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed unexpectedly")
                        break
            finally:
                cv2.destroyAllWindows()
                print("WebSocket connection closed")
    
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"Connection failed: {e}")
    except asyncio.TimeoutError:
        print("Timeout waiting for frames")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test WebRTC streaming from the CCTV server')
    parser.add_argument('camera_id', type=int, help='ID of the camera to stream')
    parser.add_argument('--ws-server', type=str, default='ws://localhost:8000',
                        help='WebSocket server URL (default: ws://localhost:8000)')
    parser.add_argument('--http-server', type=str, default='http://localhost:8000',
                        help='HTTP server URL for diagnostics (default: http://localhost:8000)')
    
    args = parser.parse_args()
    
    print("WebRTC Stream Test Tool")
    print("----------------------")
    print(f"Camera ID: {args.camera_id}")
    print(f"WebSocket URL: {args.ws_server}")
    print(f"HTTP URL: {args.http_server}")
    print("Press 'q' to quit")
    print("Press 's' to save a snapshot")
    
    try:
        asyncio.run(test_webrtc_stream(args))
    except KeyboardInterrupt:
        print("Test stopped by user")
        sys.exit(0)