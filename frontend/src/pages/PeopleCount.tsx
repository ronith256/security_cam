// src/pages/PeopleCount.tsx
import React, { useState, useEffect } from 'react';
import PageHeader from '../components/common/PageHeader';
import Card from '../components/common/Card';
import { useApi } from '../hooks/useApi';
import { fetchCameras } from '../api/cameras';
import { getCurrentOccupancy } from '../api/peopleCount';
import { OccupancyResponse } from '../types/event';
import PeopleCounter from '../components/people/PeopleCounter';
import OccupancyChart from '../components/people/OccupancyChart';
import TrafficStats from '../components/people/TrafficStats';
import Loader from '../components/common/Loader';
import { AlertCircle } from 'lucide-react';

const PeopleCount: React.FC = () => {
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  
  const { execute: loadCameras, data: cameras, isLoading: isLoadingCameras } = useApi(fetchCameras);
  
  const { execute: loadOccupancy, data: occupancy, isLoading: isLoadingOccupancy } = useApi(getCurrentOccupancy);

  useEffect(() => {
    loadCameras();
    loadOccupancy();
    
    const intervalId = setInterval(() => {
      loadOccupancy();
    }, 30000); // Refresh every 30 seconds
    
    return () => clearInterval(intervalId);
  }, [loadCameras, loadOccupancy]);

  useEffect(() => {
    // Set initial selected camera
    if (cameras && cameras.length > 0 && !selectedCameraId) {
      // Find a camera with people counting enabled
      const countingCamera = cameras.find(cam => cam.count_people && cam.enabled);
      setSelectedCameraId(countingCamera?.id || cameras[0].id);
    }
  }, [cameras, selectedCameraId]);

  const handleCameraChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedCameraId(parseInt(e.target.value));
  };

  const getSelectedCameraData = (): OccupancyResponse | undefined => {
    if (!occupancy || !selectedCameraId) return undefined;
    return occupancy.find(item => item.camera_id === selectedCameraId);
  };

  const selectedCameraData = getSelectedCameraData();
  const totalOccupancy = occupancy ? occupancy.reduce((sum, item) => sum + item.current_count, 0) : 0;

  const isLoading = isLoadingCameras || isLoadingOccupancy;
  const error = null; // Add error handling as needed

  return (
    <div>
      <PageHeader
        title="People Counting"
        subtitle="Monitor and analyze room occupancy"
      />

      {isLoading && !cameras ? (
        <div className="flex justify-center my-12">
          <Loader text="Loading data..." />
        </div>
      ) : error ? (
        <div className="bg-red-50 p-4 rounded-md flex items-start my-6">
          <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
          <div>
            <h3 className="text-red-800 font-medium">Error loading data</h3>
            <p className="text-red-700 text-sm">{error}</p>
          </div>
        </div>
      ) : (
        <>
          <div className="mb-6">
            <Card>
              <div className="flex flex-col md:flex-row md:items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-blue-600">{totalOccupancy}</h2>
                  <p className="text-gray-600">Total People in All Rooms</p>
                </div>
                <div className="mt-4 md:mt-0">
                  <label htmlFor="cameraSelect" className="block text-sm font-medium text-gray-700 mb-1">
                    Select Camera
                  </label>
                  <select
                    id="cameraSelect"
                    value={selectedCameraId || ''}
                    onChange={handleCameraChange}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  >
                    {cameras?.map(camera => (
                      <option 
                        key={camera.id} 
                        value={camera.id}
                        disabled={!camera.count_people || !camera.enabled}
                      >
                        {camera.name} {!camera.count_people && '(People Counting Disabled)'}
                        {!camera.enabled && '(Camera Disabled)'}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </Card>
          </div>

          {selectedCameraId && selectedCameraData && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <PeopleCounter
                cameraId={selectedCameraId}
                entryCount={0} // You'll need to implement this
                exitCount={0}  // You'll need to implement this
                currentCount={selectedCameraData.current_count}
                onReset={loadOccupancy}
              />
              <div className="lg:col-span-2">
                <OccupancyChart cameraId={selectedCameraId} />
              </div>
            </div>
          )}

          {selectedCameraId && (
            <div className="mt-6">
              <TrafficStats cameraId={selectedCameraId} />
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default PeopleCount;
