// src/components/cameras/CameraStream.tsx
import React, { memo } from 'react';
import WebRTCStream from './WebRTCStream';

interface CameraStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
  onConnectionChange?: (connected: boolean) => void;
}

// Using memo to prevent unnecessary renders
const CameraStream: React.FC<CameraStreamProps> = memo(({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
  onConnectionChange
}) => {
  // This is now a wrapper that uses WebRTCStream underneath
  // This helps maintain backward compatibility with components that use CameraStream
  return (
    <WebRTCStream
      cameraId={cameraId}
      showControls={showControls}
      height={height}
      width={width}
      onConnectionChange={onConnectionChange}
    />
  );
});

CameraStream.displayName = 'CameraStream';

export default CameraStream;