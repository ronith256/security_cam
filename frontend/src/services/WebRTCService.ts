// src/services/WebRTCService.ts
import axios from 'axios';
import { apiBaseUrl } from '../api';

export enum StreamMode {
  SNAPSHOT = 'snapshot', // Low bandwidth mode - periodic snapshots
  WEBRTC = 'webrtc',    // High quality mode - WebRTC streaming
}

export interface ConnectionOptions {
  cameraId: number;
  mode: StreamMode;
  onConnectionChange?: (connected: boolean) => void;
  onError?: (error: Error) => void;
}

export interface WebRTCState {
  isConnected: boolean;
  isLoading: boolean;
  error: Error | null;
  sessionId: string | null;
  mode: StreamMode;
}

class WebRTCService {
  private peerConnection: RTCPeerConnection | null = null;
  private videoElement: HTMLVideoElement | null = null;
  private canvasElement: HTMLCanvasElement | null = null;
  private webSocket: WebSocket | null = null;
  private pingInterval: NodeJS.Timeout | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private keepAliveInterval: NodeJS.Timeout | null = null;
  private connectionAttempts: number = 0;
  private isMounted: boolean = true;
  private sessionId: string | null = null;
  private cameraId: number | null = null;
  private isConnecting: boolean = false;
  
  // Options and callbacks
  private onConnectionChange?: (connected: boolean) => void;
  private onError?: (error: Error) => void;
  
  // State change callbacks
  private onStateChange?: (state: WebRTCState) => void;
  
  constructor() {
    console.log('WebRTCService initialized');
  }
  
  /**
   * Initialize the service with HTML elements
   */
  public init(
    videoElement: HTMLVideoElement | null, 
    canvasElement: HTMLCanvasElement | null,
    onStateChange?: (state: WebRTCState) => void
  ) {
    console.log('WebRTCService.init called', { videoElement, canvasElement });
    this.videoElement = videoElement;
    this.canvasElement = canvasElement;
    this.onStateChange = onStateChange;
    this.isMounted = true;
    
    // Report initial state
    this.notifyStateChange();
    
    return this;
  }
  
  /**
   * Update state and notify listeners
   */
  private notifyStateChange(partial: Partial<WebRTCState> = {}) {
    if (!this.onStateChange || !this.isMounted) return;
    
    const state: WebRTCState = {
      isConnected: partial.isConnected ?? false,
      isLoading: partial.isLoading ?? false,
      error: partial.error ?? null,
      sessionId: this.sessionId,
      mode: partial.mode ?? StreamMode.WEBRTC,
    };
    
    console.log('WebRTCService state update:', state);
    this.onStateChange(state);
  }
  
  /**
   * Notify of connection change
   */
  private notifyConnectionChange(connected: boolean) {
    console.log('WebRTCService connection change:', connected);
    if (this.onConnectionChange && this.isMounted) {
      this.onConnectionChange(connected);
    }
  }
  
  /**
   * Connect to the camera
   */
  public async connect(options: ConnectionOptions): Promise<void> {
    console.log('WebRTCService.connect called with options:', options);
    
    // Save options
    this.cameraId = options.cameraId;
    this.onConnectionChange = options.onConnectionChange;
    this.onError = options.onError;
    
    // Clean up any existing connections
    this.cleanup();
    
    // Reset connection state
    this.connectionAttempts = 0;
    this.notifyStateChange({ 
      isConnected: false, 
      isLoading: true, 
      error: null,
      mode: options.mode 
    });
    
    console.log(`Initializing camera stream for camera ${options.cameraId} in ${options.mode} mode`);
    
    // Connect based on mode
    if (options.mode === StreamMode.WEBRTC) {
      try {
        await this.connectWebRTC();
      } catch (error) {
        console.error('Error in connect WebRTC:', error);
        this.handleError(error as Error);
      }
    } else {
      try {
        this.connectWebSocket();
      } catch (error) {
        console.error('Error in connect WebSocket:', error);
        this.handleError(error as Error);
      }
    }
  }
  
  /**
   * Handle errors
   */
  private handleError(error: Error) {
    console.error('WebRTC error:', error);
    
    if (!this.isMounted) return;
    
    this.notifyStateChange({ 
      isConnected: false, 
      isLoading: false, 
      error 
    });
    
    this.notifyConnectionChange(false);
    
    if (this.onError) {
      this.onError(error);
    }
    
    // Attempt reconnection with exponential backoff
    if (this.isMounted && this.connectionAttempts < 5) {
      this.connectionAttempts++;
      const delay = Math.min(1000 * Math.pow(2, this.connectionAttempts), 30000);
      console.log(`Connection failed. Will attempt reconnection in ${delay}ms (attempt ${this.connectionAttempts})`);
      
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
      }
      
      this.reconnectTimeout = setTimeout(() => {
        if (this.isMounted && this.cameraId) {
          this.reconnectTimeout = null;
          this.connect({
            cameraId: this.cameraId,
            mode: this.onStateChange ? 
              StreamMode.WEBRTC : 
              StreamMode.WEBRTC,
            onConnectionChange: this.onConnectionChange,
            onError: this.onError
          });
        }
      }, delay);
    }
  }
  
  /**
   * Connect using WebRTC
   */
  private async connectWebRTC(): Promise<void> {
    if (this.isConnecting || !this.isMounted) {
      console.log("Already connecting or not mounted, skipping WebRTC connection");
      return;
    }
    
    this.isConnecting = true;
    this.notifyStateChange({ isLoading: true, error: null });
    
    try {
      console.log(`Setting up WebRTC connection for camera ${this.cameraId}`);
      
      // Clean up any existing connection
      if (this.peerConnection) {
        try {
          this.peerConnection.close();
        } catch (e) {
          console.error('Error closing existing peer connection:', e);
        }
        this.peerConnection = null;
      }
      
      // Create a new peer connection
      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' }
        ]
      });
      console.log("Created new RTCPeerConnection with STUN servers");
      this.peerConnection = pc;
      
      // Create a data channel to keep the connection alive
      this.dataChannel = pc.createDataChannel('keepalive');
      console.log("Created data channel for keepalive");
      
      this.dataChannel.onopen = () => {
        console.log('Data channel opened - connection should be more stable');
        
        // Set up keepalive pings
        if (this.keepAliveInterval) {
          clearInterval(this.keepAliveInterval);
        }
        
        this.keepAliveInterval = setInterval(() => {
          if (this.dataChannel && this.dataChannel.readyState === 'open') {
            try {
              this.dataChannel.send(JSON.stringify({ 
                type: 'ping', 
                timestamp: Date.now() 
              }));
            } catch (e) {
              console.error('Error sending ping through data channel:', e);
            }
          } else if (this.keepAliveInterval) {
            clearInterval(this.keepAliveInterval);
            this.keepAliveInterval = null;
          }
        }, 5000);
      };
      
      // Handle ICE candidates
      pc.onicecandidate = async (event) => {
        console.log('ICE candidate event:', event.candidate);
        if (event.candidate && this.sessionId) {
          try {
            console.log(`Sending ICE candidate to ${apiBaseUrl}/webrtc/icecandidate/${this.sessionId}`);
            await axios.post(`${apiBaseUrl}/webrtc/icecandidate/${this.sessionId}`, {
              candidate: event.candidate.candidate,
              sdpMid: event.candidate.sdpMid, 
              sdpMLineIndex: event.candidate.sdpMLineIndex
            });
          } catch (err) {
            console.error('Error sending ICE candidate:', err);
          }
        }
      };
      
      // Handle connection state changes
      pc.onconnectionstatechange = () => {
        console.log(`WebRTC connection state: ${pc.connectionState}`);
        
        if (pc.connectionState === 'connected') {
          this.isConnecting = false;
          this.connectionAttempts = 0;
          this.notifyStateChange({ isConnected: true, isLoading: false });
          this.notifyConnectionChange(true);
        } 
        else if (pc.connectionState === 'failed' || 
                 pc.connectionState === 'disconnected' || 
                 pc.connectionState === 'closed') {
          this.isConnecting = false;
          this.notifyStateChange({ isConnected: false });
          this.notifyConnectionChange(false);
          
          // Automatic reconnection is handled by handleError
          this.handleError(new Error(`WebRTC connection ${pc.connectionState}`));
        }
      };
      
      // Handle track events for incoming video
      pc.ontrack = (event) => {
        console.log('Track received:', event.track.kind);
        if (this.videoElement && event.streams && event.streams[0]) {
          console.log('Setting video element srcObject');
          this.videoElement.srcObject = event.streams[0];
        }
      };
      
      // Create offer
      console.log('Creating offer for WebRTC');
      const offer = await pc.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: false
      });
      
      console.log('Setting local description:', offer);
      await pc.setLocalDescription(offer);
      
      // Send offer to server
      console.log(`Sending WebRTC offer to ${apiBaseUrl}/webrtc/offer`);
      const response = await axios.post(`${apiBaseUrl}/webrtc/offer`, {
        cameraId: this.cameraId,
        sdp: offer.sdp
      });
      
      console.log('Received response from offer:', response.data);
      
      // Store session ID
      this.sessionId = response.data.session_id;
      
      // Process the SDP answer
      const answerSDP = response.data.sdp;
      const answerType = response.data.type;
      
      // Set remote description
      const remoteDesc = new RTCSessionDescription({
        sdp: answerSDP,
        type: answerType as RTCSdpType
      });
      
      console.log('Setting remote description:', remoteDesc);
      await pc.setRemoteDescription(remoteDesc);
      
      console.log('WebRTC connection established with session ID:', this.sessionId);
      
    } catch (err) {
      console.error('Error in connectWebRTC:', err);
      this.isConnecting = false;
      throw err;
    }
  }
  
  /**
   * Connect using WebSocket (snapshot mode)
   */
  private connectWebSocket(): void {
    if (this.isConnecting || !this.isMounted || !this.cameraId) {
      console.log("Already connecting or not mounted or no camera ID, skipping WebSocket connection");
      return;
    }
    
    this.isConnecting = true;
    this.notifyStateChange({ isLoading: true, error: null });
    
    // Clean up existing connection
    if (this.webSocket) {
      if (this.pingInterval) {
        clearInterval(this.pingInterval);
        this.pingInterval = null;
      }
      
      if (this.webSocket.readyState !== WebSocket.CLOSED && 
          this.webSocket.readyState !== WebSocket.CLOSING) {
        try {
          this.webSocket.close();
        } catch (err) {
          console.error('Error closing WebSocket:', err);
        }
      }
      this.webSocket = null;
    }
    
    try {
      // Construct WebSocket URL for snapshots
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = apiBaseUrl.replace(/^https?:\/\//, '').replace(/\/api$/, '');
      const wsUrl = `${protocol}//${host}/api/webrtc/snapshot/${this.cameraId}`;
      
      console.log(`Connecting to WebSocket for snapshots: ${wsUrl}`);
      
      const ws = new WebSocket(wsUrl);
      this.webSocket = ws;
      
      ws.onopen = () => {
        if (!this.isMounted) {
          ws.close();
          return;
        }
        
        console.log(`WebSocket connected for camera ${this.cameraId} snapshots`);
        this.isConnecting = false;
        this.connectionAttempts = 0;
        this.notifyStateChange({ isConnected: true, isLoading: false });
        this.notifyConnectionChange(true);
        
        // Set up ping interval
        this.pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch (err) {
              console.error('Error sending ping:', err);
            }
          } else if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
          }
        }, 30000);
        
        // Send initial ping to get first snapshot
        try {
          ws.send(JSON.stringify({ type: 'ping' }));
        } catch (err) {
          console.error('Error sending initial ping:', err);
        }
      };
      
      ws.onmessage = (event) => {
        if (!this.isMounted) return;
        
        try {
          const message = JSON.parse(event.data);
          
          if (message.type === 'snapshot') {
            // Render the snapshot on canvas
            this.renderSnapshot(message.data);
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };
      
      ws.onerror = (event) => {
        if (!this.isMounted) return;
        
        console.error('WebSocket error:', event);
        this.isConnecting = false;
        this.handleError(new Error('Failed to connect to snapshot stream'));
      };
      
      ws.onclose = (event) => {
        if (!this.isMounted) return;
        
        console.log('WebSocket closed:', event.code, event.reason);
        this.isConnecting = false;
        this.notifyStateChange({ isConnected: false });
        this.notifyConnectionChange(false);
        
        // Clean up ping interval
        if (this.pingInterval) {
          clearInterval(this.pingInterval);
          this.pingInterval = null;
        }
        
        // Handle unexpected closures
        if (event.code !== 1000 && event.code !== 1001) {
          this.handleError(new Error(`WebSocket closed: ${event.code}`));
        }
      };
      
    } catch (err) {
      console.error('Error in connectWebSocket:', err);
      this.isConnecting = false;
      throw err;
    }
  }
  
  /**
   * Render a snapshot on the canvas
   */
  private renderSnapshot(base64Data: string): void {
    if (!this.isMounted || !this.canvasElement) return;
    
    const ctx = this.canvasElement.getContext('2d');
    if (!ctx) return;
    
    const img = new Image();
    img.onload = () => {
      // Adjust canvas size if needed
      if (this.canvasElement!.width !== img.width || 
          this.canvasElement!.height !== img.height) {
        this.canvasElement!.width = img.width;
        this.canvasElement!.height = img.height;
      }
      
      // Draw the image
      ctx.drawImage(img, 0, 0);
    };
    
    img.src = 'data:image/jpeg;base64,' + base64Data;
  }
  
  /**
   * Take a template snapshot
   */
  public async takeTemplateSnapshot(): Promise<void> {
    if (!this.cameraId) {
      throw new Error('No camera ID set');
    }
    
    try {
      this.notifyStateChange({ isLoading: true });
      
      await axios.post(`${apiBaseUrl}/webrtc/template/${this.cameraId}`);
      
      this.notifyStateChange({ isLoading: false });
      return;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to take template snapshot');
      this.notifyStateChange({ isLoading: false, error });
      throw error;
    }
  }
  
  /**
   * Toggle stream mode
   */
  public async toggleMode(): Promise<void> {
    if (!this.cameraId) return;
    
    const currentMode = this.onStateChange ? StreamMode.WEBRTC : StreamMode.WEBRTC;
    const newMode = currentMode === StreamMode.WEBRTC ? 
                    StreamMode.SNAPSHOT : 
                    StreamMode.WEBRTC;
    
    // Clean up existing connection
    this.cleanup();
    
    // Connect with new mode
    await this.connect({
      cameraId: this.cameraId,
      mode: newMode,
      onConnectionChange: this.onConnectionChange,
      onError: this.onError
    });
  }
  
  /**
   * Clean up resources
   */
  public cleanup(): void {
    console.log('Cleaning up WebRTC resources');
    
    // Clear timeouts and intervals
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
    
    if (this.keepAliveInterval) {
      clearInterval(this.keepAliveInterval);
      this.keepAliveInterval = null;
    }
    
    // Close WebSocket
    if (this.webSocket) {
      if (this.webSocket.readyState !== WebSocket.CLOSED && 
          this.webSocket.readyState !== WebSocket.CLOSING) {
        try {
          console.log('Closing WebSocket connection');
          this.webSocket.close();
        } catch (err) {
          console.error('Error closing WebSocket:', err);
        }
      }
      this.webSocket = null;
    }
    
    // Close data channel
    if (this.dataChannel) {
      try {
        this.dataChannel.close();
      } catch (err) {
        console.error('Error closing data channel:', err);
      }
      this.dataChannel = null;
    }
    
    // Close peer connection
    if (this.peerConnection) {
      try {
        this.peerConnection.close();
      } catch (err) {
        console.error('Error closing peer connection:', err);
      }
      this.peerConnection = null;
    }
    
    // Stop video tracks
    if (this.videoElement && this.videoElement.srcObject) {
      try {
        const mediaStream = this.videoElement.srcObject as MediaStream;
        if (mediaStream) {
          mediaStream.getTracks().forEach(track => track.stop());
        }
        this.videoElement.srcObject = null;
      } catch (err) {
        console.error('Error stopping video tracks:', err);
      }
    }
    
    // Close session on backend - with delay
    if (this.sessionId) {
      const sessionId = this.sessionId;
      this.sessionId = null;
      
      // Use timeout to ensure we close the connection properly on the client side first
      setTimeout(() => {
        try {
          console.log(`Closing WebRTC session ${sessionId} on backend`);
          axios.delete(`${apiBaseUrl}/webrtc/session/${sessionId}`)
            .catch(err => console.error('Error closing WebRTC session:', err));
        } catch (err) {
          console.error('Error closing WebRTC session:', err);
        }
      }, 300);
    }
    
    // Reset state
    this.isConnecting = false;
    this.connectionAttempts = 0;
  }
  
  /**
   * Destroy the service
   */
  public destroy(): void {
    console.log('Destroying WebRTC service');
    this.isMounted = false;
    this.cleanup();
    
    // Reset references
    this.videoElement = null;
    this.canvasElement = null;
    this.onStateChange = undefined;
    this.onConnectionChange = undefined;
    this.onError = undefined;
    this.cameraId = null;
  }

  /**
   * Get a singleton instance
   */
  public static getInstance(): WebRTCService {
    if (!WebRTCService.instance) {
      WebRTCService.instance = new WebRTCService();
    }
    return WebRTCService.instance;
  }

  private static instance: WebRTCService | null = null;
}

export default WebRTCService;