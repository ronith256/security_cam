// src/components/people/TrafficStats.tsx
import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import Card from '../common/Card';
import { useApi } from '../../hooks/useApi';
import { getEntriesExits } from '../../api/peopleCount';
import { EntryExitResponse } from '../../types/event';
import Loader from '../common/Loader';
import { AlertCircle } from 'lucide-react';
import Button from '../common/Button';

interface TrafficStatsProps {
  cameraId: number;
  hours?: number;
}

const TrafficStats: React.FC<TrafficStatsProps> = ({ cameraId, hours = 24 }) => {
  const [timeRange, setTimeRange] = useState(hours);
  
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - timeRange * 60 * 60 * 1000);

  const { execute: fetchTraffic, data, isLoading, error } = useApi(
    () => getEntriesExits(
      cameraId,
      startDate.toISOString(),
      endDate.toISOString()
    ),
    {
      showErrorToast: true,
    }
  );

  useEffect(() => {
    fetchTraffic();
  }, [fetchTraffic, timeRange]);

  const formatData = (data: EntryExitResponse | null) => {
    if (!data) return [];
    
    return [
      {
        name: 'Entries',
        value: data.entry_count,
        fill: '#22C55E', // Green
      },
      {
        name: 'Exits',
        value: data.exit_count,
        fill: '#EF4444', // Red
      },
      {
        name: 'Current',
        value: data.current_occupancy,
        fill: '#3B82F6', // Blue
      },
    ];
  };

  const changeTimeRange = (hours: number) => {
    setTimeRange(hours);
  };

  return (
    <Card
      title="Traffic Statistics"
      subtitle={data ? `${data.camera_name} - Last ${timeRange} hours` : 'Loading...'}
      className="h-full flex flex-col"
    >
      <div className="flex mb-4 space-x-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Time Range</label>
          <div className="flex space-x-1">
            <Button
              size="sm"
              variant={timeRange === 6 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(6)}
            >
              6h
            </Button>
            <Button
              size="sm"
              variant={timeRange === 12 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(12)}
            >
              12h
            </Button>
            <Button
              size="sm"
              variant={timeRange === 24 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(24)}
            >
              24h
            </Button>
            <Button
              size="sm"
              variant={timeRange === 72 ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeTimeRange(72)}
            >
              3d
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-grow" style={{ minHeight: '300px' }}>
        {isLoading && !data && (
          <div className="h-full flex items-center justify-center">
            <Loader text="Loading traffic data..." />
          </div>
        )}

        {error && !data && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-red-500">
              <AlertCircle size={32} className="mx-auto mb-2" />
              <p>Failed to load traffic data</p>
            </div>
          </div>
        )}

        {data && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={formatData(data)} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip formatter={(value) => [`${value} people`, '']} />
              <Legend />
              <Bar dataKey="value" name="Count" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {data && (
        <div className="mt-4 grid grid-cols-3 gap-4 text-center">
          <div className="p-3 bg-green-50 rounded-md">
            <p className="text-sm text-gray-600">Entry Rate</p>
            <p className="text-xl font-bold text-green-600">
              {(data.entry_count / (timeRange || 1)).toFixed(2)}/hr
            </p>
          </div>
          
          <div className="p-3 bg-red-50 rounded-md">
            <p className="text-sm text-gray-600">Exit Rate</p>
            <p className="text-xl font-bold text-red-600">
              {(data.exit_count / (timeRange || 1)).toFixed(2)}/hr
            </p>
          </div>
          
          <div className="p-3 bg-blue-50 rounded-md">
            <p className="text-sm text-gray-600">Turnover</p>
            <p className="text-xl font-bold text-blue-600">
              {data.entry_count + data.exit_count} total
            </p>
          </div>
        </div>
      )}
    </Card>
  );
};

export default TrafficStats;