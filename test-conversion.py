import os
import subprocess
import time
import argparse
import platform
import sys
import asyncio

def check_ffmpeg():
    """Check if FFmpeg is installed and available in PATH"""
    try:
        # Run ffmpeg -version and capture output
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        
        if result.returncode == 0:
            # Extract version
            version_line = result.stdout.split('\n')[0]
            print(f"✅ FFmpeg found: {version_line}")
            return True
        else:
            print("❌ FFmpeg command returned an error:")
            print(result.stderr)
            return False
            
    except FileNotFoundError:
        print("❌ FFmpeg not found in PATH")
        
        # Suggest installation commands based on OS
        system = platform.system()
        if system == "Windows":
            print("\nInstallation suggestions for Windows:")
            print("1. Download from https://ffmpeg.org/download.html")
            print("2. Or use Chocolatey: choco install ffmpeg")
        elif system == "Darwin":  # macOS
            print("\nInstallation suggestions for macOS:")
            print("1. Using Homebrew: brew install ffmpeg")
        elif system == "Linux":
            # Get distribution info
            try:
                import distro
                dist = distro.id()
            except ImportError:
                dist = ""
                
            print("\nInstallation suggestions for Linux:")
            if dist in ["ubuntu", "debian"]:
                print("sudo apt update && sudo apt install ffmpeg")
            elif dist in ["fedora", "rhel", "centos"]:
                print("sudo dnf install ffmpeg")
            else:
                print("Please install ffmpeg using your distribution's package manager")
                
        return False

async def test_rtsp_to_hls(rtsp_url, output_dir="hls_test"):
    """Test converting an RTSP stream to HLS using FFmpeg asynchronously"""
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a unique test directory
    test_id = f"test_{int(time.time())}"
    test_dir = os.path.join(output_dir, test_id)
    os.makedirs(test_dir, exist_ok=True)
    
    # Paths for HLS files
    playlist_path = os.path.join(test_dir, "index.m3u8")
    
    print(f"Starting FFmpeg to convert RTSP to HLS...")
    print(f"RTSP URL: {rtsp_url}")
    print(f"Output directory: {test_dir}")
    print(f"Playlist path: {playlist_path}")
    
    # FFmpeg command
    command = [
        'ffmpeg',
        '-loglevel', 'debug',
        # '-rtsp_transport', 'tcp',
        '-i', rtsp_url,
        
        '-vsync', '0',       # Disable video sync
        '-copyts',          # Copy timestamps from input to output
        '-hls_segment_type', 'mpegts',
        '-movflags', 'frag_keyframe+empty_moov',
        '-an',
        # '-hls_flags', 'delete_segments+append_list'
        '-f', 'hls',         # HLS format
        '-hls_time', '2',    # Segment duration
        '-hls_list_size', '3',
        f'{test_dir}/index.m3u8'
    ]
    
    # Start FFmpeg process asynchronously
    # stdout=None, stderr=None routes output to terminal
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=None, 
        stderr=None
    )
    
    print(f"FFmpeg process started asynchronously with PID {process.pid}")
    # Return process and playlist path immediately
    return process, playlist_path

def play_hls_cv2(playlist_path):
    """Play HLS stream using cv2."""
    print(f"Playing HLS stream with cv2: {playlist_path}")
    
    try:
        import cv2
    except ImportError:
        print("❌ cv2 (opencv-python) not found. Please install it with: pip install opencv-python")
        return

    if not os.path.exists(playlist_path):
        print(f"❌ Playlist file not found: {playlist_path}. Waiting for FFmpeg to create it.")
        return

    try:
        # Open the HLS stream
        cap = cv2.VideoCapture(playlist_path)
        
        if not cap.isOpened():
            print(f"❌ Could not open HLS stream with cv2: {playlist_path}")
            return
        
        print("✅ HLS stream opened with cv2. Press 'q' to quit.")
        # Read and display frames
        while True:
            ret, frame = cap.read()
            if not ret:
                print("End of stream or error.")
                break
            
            cv2.imshow("HLS Stream", frame)
            
            # Break the loop if 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        # Release resources
        cap.release()
        cv2.destroyAllWindows()
        
    except Exception as e:
        print(f"❌ An error occurred while playing the HLS stream with cv2: {e}")
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()


async def main():
    """Main function to run the test"""
    parser = argparse.ArgumentParser(description="Test RTSP to HLS conversion with FFmpeg")
    parser.add_argument("--rtsp", required=True, help="RTSP URL to test")
    parser.add_argument("--output", default="hls_test", help="Output directory for HLS files")
    
    args = parser.parse_args()
    
    print("=== FFmpeg RTSP to HLS Test ===\n")
    
    if not check_ffmpeg():
        return 1
        
    print("\n--- Starting RTSP to HLS Conversion (Async) ---\n")
    
    process, playlist_path = await test_rtsp_to_hls(args.rtsp, args.output)
    
    if process:
        print(f"\nConversion process running in background (PID: {process.pid}).")
        print("Waiting 5 seconds for playlist generation...")
        await asyncio.sleep(5) # Give FFmpeg some time to generate the initial playlist
        
        # Attempt to play the HLS stream
        play_hls_cv2(playlist_path)
        
        # Optionally wait for the process to finish if needed, 
        # but for background task, we might just let it run.
        # await process.wait() 
        # print(f"FFmpeg process {process.pid} finished.")
        
        print("\nScript finished, but FFmpeg might still be running in the background.")
        return 0
    else:
        print("\n❌ Failed to start FFmpeg process.")
        return 1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
