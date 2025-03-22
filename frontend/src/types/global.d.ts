// Add this to your src/types/global.d.ts file

interface WebSocketWithPing extends WebSocket {
    pingInterval?: NodeJS.Timeout;
  }