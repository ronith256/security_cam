// src/components/faces/PersonStats.tsx
import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import Card from '../common/Card';
import { useApi } from '../../hooks/useApi';
import { getPersonStatistics } from '../../api/faceRecognition';
import Loader from '../common/Loader';
import { AlertCircle } from 'lucide-react';
import Button from '../common/Button';

interface PersonStatsProps {
  personId: number;
  days?: number;
}

const PersonStats: React.FC<PersonStatsProps> = ({ personId, days = 7 }) => {
  const [timeRange, setTimeRange] = useState(days);
  
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - timeRange * 24 * 60 * 60 * 1000);

  const { execute: fetchStats, data: stats, isLoading, error } = useApi(
    () => getPersonStatistics(
      personId,
      startDate.toISOString(),
      endDate.toISOString()
    ),
    {
      showErrorToast: true,
    }
  );

  useEffect(() => {
    fetchStats();
  }, [fetchStats, timeRange]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const changeTimeRange = (days: number) => {
    setTimeRange(days);
  };

  const chartData = [
    {
      name: 'Entries',
      value: stats?.total_entries || 0,
    },
    {
      name: 'Detections',
      value: stats?.total_detections || 0,
    },
  ];

  return (
    <Card
      title={stats ? `${stats.person_name}'s Statistics` : 'Person Statistics'}
      subtitle={`Last ${timeRange} days`}
      className="h-full flex flex-col"
    >
      <div className="flex mb-4 space-x-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Time Range</label>
          <div className="flex space-x-1">
            <Button
              size="sm"
              variant={timeRange === 1 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(1)}
            >
              1d
            </Button>
            <Button
              size="sm"
              variant={timeRange === 7 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(7)}
            >
              7d
            </Button>
            <Button
              size="sm"
              variant={timeRange === 30 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(30)}
            >
              30d
            </Button>
            <Button
              size="sm"
              variant={timeRange === 90 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(90)}
            >
              90d
            </Button>
          </div>
        </div>
      </div>

      {isLoading && !stats ? (
        <div className="flex items-center justify-center h-64">
          <Loader text="Loading statistics..." />
        </div>
      ) : error ? (
        <div className="bg-red-50 p-4 rounded-md flex items-start">
          <AlertCircle className="text-red-500 mr-2 mt-0.5" size={20} />
          <div>
            <h3 className="text-red-800 font-medium">Error loading statistics</h3>
            <p className="text-red-700 text-sm">{error.message}</p>
          </div>
        </div>
      ) : stats ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-blue-50 p-4 rounded-md text-center">
              <p className="text-sm text-gray-600">Entries</p>
              <p className="text-xl font-bold text-blue-600">{stats.total_entries}</p>
            </div>
            <div className="bg-purple-50 p-4 rounded-md text-center">
              <p className="text-sm text-gray-600">Detections</p>
              <p className="text-xl font-bold text-purple-600">{stats.total_detections}</p>
            </div>
            <div className="bg-green-50 p-4 rounded-md text-center">
              <p className="text-sm text-gray-600">First Seen</p>
              <p className="text-md font-bold text-green-600">{formatDate(stats.first_seen)}</p>
              <p className="text-xs text-gray-500">{formatTime(stats.first_seen)}</p>
            </div>
            <div className="bg-amber-50 p-4 rounded-md text-center">
              <p className="text-sm text-gray-600">Last Seen</p>
              <p className="text-md font-bold text-amber-600">{formatDate(stats.last_seen)}</p>
              <p className="text-xs text-gray-500">{formatTime(stats.last_seen)}</p>
            </div>
          </div>

          <div style={{ height: '250px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip formatter={(value) => [`${value}`, ``]} />
                <Legend />
                <Bar dataKey="value" name="Count" fill="#3B82F6" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div>
            <h3 className="font-medium text-gray-700 mb-2">Cameras where detected:</h3>
            <div className="bg-gray-50 p-4 rounded-md">
              {stats.cameras.length > 0 ? (
                <ul className="space-y-1">
                  {stats.cameras.map((camera, index) => (
                    <li key={index} className="flex items-center">
                      <span className="w-2 h-2 bg-blue-500 rounded-full mr-2"></span>
                      {camera}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-gray-500">No camera detections recorded</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
};

export default PersonStats;