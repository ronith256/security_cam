// src/pages/Dashboard.tsx
import React, { useState, useEffect } from "react";
import { Plus, ArrowRight, Camera, Users, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "../components/common/PageHeader";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import CameraList from "../components/cameras/CameraList";
import { fetchCameras } from "../api/cameras";
import { getCurrentOccupancy } from "../api/peopleCount";
import { useApi } from "../hooks/useApi";

const Dashboard: React.FC = () => {
  const [totalOccupancy, setTotalOccupancy] = useState(0);

  const { execute: loadCameras, data: cameras } = useApi(fetchCameras);

  const { execute: loadOccupancy } = useApi(getCurrentOccupancy, {
    onSuccess: (data) => {
      const total = data.reduce((sum, item) => sum + item.current_count, 0);
      setTotalOccupancy(total);
    },
  });

  useEffect(() => {
    // Load data initially
    loadCameras();
    loadOccupancy();

    // Set up interval for periodic updates
    const interval = setInterval(() => {
      loadOccupancy();
    }, 60000); // Update occupancy once per minute, not continuously

    return () => clearInterval(interval);
  }, []);

  const activeCameras =
    cameras?.filter((camera) => camera.enabled)?.length || 0;
  const totalCameras = cameras?.length || 0;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="CCTV Monitoring System Overview"
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card className="bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <div className="flex items-center">
            <div className="p-3 bg-white bg-opacity-30 rounded-full mr-4">
              <Camera className="text-white" size={24} />
            </div>
            <div>
              <h3 className="text-xl font-bold">Cameras</h3>
              <p className="text-3xl font-bold">
                {activeCameras} / {totalCameras}
              </p>
              <p className="text-sm opacity-80">Active Cameras</p>
            </div>
          </div>
          <div className="mt-6">
            <Link to="/cameras">
              <Button
                variant="secondary"
                className="bg-white bg-opacity-20 hover:bg-opacity-30 text-white border-none"
                icon={<ArrowRight size={16} />}
              >
                View Cameras
              </Button>
            </Link>
          </div>
        </Card>

        <Card className="bg-gradient-to-r from-green-500 to-green-600 text-white">
          <div className="flex items-center">
            <div className="p-3 bg-white bg-opacity-30 rounded-full mr-4">
              <Users className="text-white" size={24} />
            </div>
            <div>
              <h3 className="text-xl font-bold">Occupancy</h3>
              <p className="text-3xl font-bold">{totalOccupancy}</p>
              <p className="text-sm opacity-80">Total People in Rooms</p>
            </div>
          </div>
          <div className="mt-6">
            <Link to="/people-count">
              <Button
                variant="secondary"
                className="bg-white bg-opacity-20 hover:bg-opacity-30 text-white border-none"
                icon={<ArrowRight size={16} />}
              >
                View Occupancy
              </Button>
            </Link>
          </div>
        </Card>

        <Card className="bg-gradient-to-r from-purple-500 to-purple-600 text-white">
          <div className="flex items-center">
            <div className="p-3 bg-white bg-opacity-30 rounded-full mr-4">
              <UserPlus className="text-white" size={24} />
            </div>
            <div>
              <h3 className="text-xl font-bold">Face Recognition</h3>
              <p className="text-sm opacity-80 mt-2">
                Register and track people by face
              </p>
            </div>
          </div>
          <div className="mt-6">
            <Link to="/face-recognition">
              <Button
                variant="secondary"
                className="bg-white bg-opacity-20 hover:bg-opacity-30 text-white border-none"
                icon={<ArrowRight size={16} />}
              >
                Manage Faces
              </Button>
            </Link>
          </div>
        </Card>
      </div>

      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Active Cameras</h2>
          <Link to="/cameras/new">
            <Button variant="primary" icon={<Plus size={16} />}>
              Add Camera
            </Button>
          </Link>
        </div>
        <CameraList filter={(camera) => camera.enabled} />
      </div>
    </div>
  );
};

export default Dashboard;
