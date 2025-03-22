#!/usr/bin/env python3
import cv2
import time
import argparse
import sys
import threading
import requests

def test_rtsp_stream(url, max_frames=100):
    """Test direct RTSP connection"""
    print(f"Connecting to RTSP stream: {url}")
    
    try:
        # Open connection with a 10-second timeout
        cap = cv2.VideoCapture(url)
        
        if not cap.isOpened():
            print("Failed to open RTSP stream!")
            return False
        
        print("Connection opened successfully")
        
        # Get stream properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        print(f"Stream properties: {width}x{height} @ {fps} FPS")
        
        # Try to read frames
        frames_read = 0
        start_time = time.time()
        
        window_name = "RTSP Test"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, min(width, 800), min(height, 600))
        
        while frames_read < max_frames:
            ret, frame = cap.read()
            
            if not ret:
                print(f"Failed to read frame after reading {frames_read} frames")
                break
            
            frames_read += 1
            
            # Show frame
            cv2.imshow(window_name, frame)
            
            # Check for quit key
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Quit requested by user")
                break
            
            # Print progress
            if frames_read % 10 == 0:
                elapsed = time.time() - start_time
                actual_fps = frames_read / elapsed
                print(f"Read {frames_read} frames in {elapsed:.2f}s ({actual_fps:.2f} FPS)")
        
        # Clean up
        cap.release()
        cv2.destroyAllWindows()
        
        # Final stats
        elapsed = time.time() - start_time
        actual_fps = frames_read / elapsed if elapsed > 0 else 0
        
        print("\nRTSP Test Results:")
        print(f"Frames read: {frames_read}")
        print(f"Time elapsed: {elapsed:.2f} seconds")
        print(f"Actual FPS: {actual_fps:.2f}")
        
        return frames_read > 0
        
    except Exception as e:
        print(f"Error testing RTSP stream: {e}")
        cv2.destroyAllWindows()
        return False

def get_rtsp_url_from_api(server_url, camera_id):
    """Get RTSP URL from the API"""
    try:
        response = requests.get(f"{server_url}/api/cameras/{camera_id}")
        if response.status_code == 200:
            camera_data = response.json()
            return camera_data.get("rtsp_url")
        else:
            print(f"Failed to get camera info: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error getting camera info: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test RTSP stream directly')
    parser.add_argument('--url', type=str, help='RTSP URL to test')
    parser.add_argument('--camera-id', type=int, help='Camera ID (to get RTSP URL from API)')
    parser.add_argument('--server', type=str, default='http://localhost:8000', 
                        help='API server URL (default: http://localhost:8000)')
    parser.add_argument('--frames', type=int, default=100, 
                        help='Maximum number of frames to read (default: 100)')
    
    args = parser.parse_args()
    
    # Either URL or camera ID must be provided
    if not args.url and not args.camera_id:
        print("Error: Either --url or --camera-id must be provided")
        parser.print_help()
        sys.exit(1)
    
    # Get RTSP URL from API if camera ID is provided
    rtsp_url = args.url
    if not rtsp_url and args.camera_id:
        rtsp_url = get_rtsp_url_from_api(args.server, args.camera_id)
        if not rtsp_url:
            print("Failed to get RTSP URL from API")
            sys.exit(1)
    
    print("RTSP Stream Test Tool")
    print("--------------------")
    print(f"RTSP URL: {rtsp_url}")
    print(f"Max frames: {args.frames}")
    print("Press 'q' to quit")
    
    try:
        success = test_rtsp_stream(rtsp_url, args.frames)
        if success:
            print("\nRTSP test completed successfully!")
            sys.exit(0)
        else:
            print("\nRTSP test failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("Test stopped by user")
        sys.exit(0)