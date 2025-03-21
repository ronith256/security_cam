// src/components/cameras/CameraStats.tsx
import React from 'react';
import { Users, UserCheck, LayoutTemplate, Settings } from 'lucide-react';
import Card from '../common/Card';
import { CameraStatus } from '../../types/camera';

interface CameraStatsProps {
  status: CameraStatus;
}

const CameraStats: React.FC<CameraStatsProps> = ({ status }) => {
  const { detection_results, current_occupancy, fps } = status;

  const peopleDetections = detection_results.people?.length || 0;
  const faceDetections = detection_results.faces?.length || 0;
  const templateMatches = detection_results.templates?.length || 0;
  const entryCount = detection_results.people_counting?.entries || 0;
  const exitCount = detection_results.people_counting?.exits || 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card className="flex items-center">
        <div className="mr-4 bg-blue-100 p-3 rounded-full">
          <Users className="text-blue-600" size={24} />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Current Occupancy</h3>
          <p className="text-2xl font-bold text-blue-600">{current_occupancy}</p>
          <p className="text-sm text-gray-500">
            {entryCount} entries, {exitCount} exits
          </p>
        </div>
      </Card>

      <Card className="flex items-center">
        <div className="mr-4 bg-green-100 p-3 rounded-full">
          <UserCheck className="text-green-600" size={24} />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Detections</h3>
          <p className="text-2xl font-bold text-green-600">{peopleDetections}</p>
          <p className="text-sm text-gray-500">
            {faceDetections} face recognitions
          </p>
        </div>
      </Card>

      <Card className="flex items-center">
        <div className="mr-4 bg-purple-100 p-3 rounded-full">
          <LayoutTemplate className="text-purple-600" size={24} />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Template Matches</h3>
          <p className="text-2xl font-bold text-purple-600">{templateMatches}</p>
          <p className="text-sm text-gray-500">Active matches</p>
        </div>
      </Card>

      <Card className="flex items-center">
        <div className="mr-4 bg-orange-100 p-3 rounded-full">
          <Settings className="text-orange-600" size={24} />
        </div>
        <div>
          <h3 className="text-lg font-semibold">Processing</h3>
          <p className="text-2xl font-bold text-orange-600">{fps.toFixed(1)} FPS</p>
          <p className="text-sm text-gray-500">Current processing rate</p>
        </div>
      </Card>
    </div>
  );
};

export default CameraStats;