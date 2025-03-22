// src/components/cameras/CameraStream.tsx
import React from 'react';
import WebRTCStream from './WebRTCStream';

interface CameraStreamProps {
  cameraId: number;
  showControls?: boolean;
  height?: string;
  width?: string;
}

const CameraStream: React.FC<CameraStreamProps> = ({
  cameraId,
  showControls = true,
  height = 'h-72',
  width = 'w-full',
}) => {
  // This is now a wrapper that uses WebRTCStream underneath
  // This helps maintain backward compatibility with components that use CameraStream
  return (
    <WebRTCStream
      cameraId={cameraId}
      showControls={showControls}
      height={height}
      width={width}
    />
  );
};

export default CameraStream;