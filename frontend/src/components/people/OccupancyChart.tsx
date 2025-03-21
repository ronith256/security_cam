// src/components/people/OccupancyChart.tsx
import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import Card from '../common/Card';
import { useApi } from '../../hooks/useApi';
import { getOccupancyHistory } from '../../api/peopleCount';
import { OccupancyHistory } from '../../types/event';
import Loader from '../common/Loader';
import { AlertCircle } from 'lucide-react';
import Button from '../common/Button';

interface OccupancyChartProps {
  cameraId: number;
  interval?: string;
  hours?: number;
}

const OccupancyChart: React.FC<OccupancyChartProps> = ({ 
  cameraId, 
  interval = '1h',
  hours = 24
}) => {
  const [timeRange, setTimeRange] = useState(hours);
  const [selectedInterval, setSelectedInterval] = useState(interval);
  
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - timeRange * 60 * 60 * 1000);

  const { execute: fetchHistory, data, isLoading, error } = useApi(
    () => getOccupancyHistory(
      cameraId,
      startDate.toISOString(),
      endDate.toISOString(),
      selectedInterval
    ),
    {
      showErrorToast: true,
    }
  );

  useEffect(() => {
    fetchHistory();
    
    const intervalId = setInterval(() => {
      fetchHistory();
    }, 5 * 60 * 1000); // Refresh every 5 minutes
    
    return () => clearInterval(intervalId);
  }, [fetchHistory, timeRange, selectedInterval]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatData = (data: OccupancyHistory | null) => {
    if (!data) return [];
    
    return data.data.map((item) => ({
      time: formatDate(item.timestamp),
      count: item.count,
      timestamp: item.timestamp,
    }));
  };

  const changeTimeRange = (hours: number) => {
    setTimeRange(hours);
  };

  const changeInterval = (interval: string) => {
    setSelectedInterval(interval);
  };

  return (
    <Card
      title="Occupancy Over Time"
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
        
        <div>
          <label className="block text-xs text-gray-500 mb-1">Interval</label>
          <div className="flex space-x-1">
            <Button
              size="sm"
              variant={selectedInterval === '15m' ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeInterval('15m')}
            >
              15m
            </Button>
            <Button
              size="sm"
              variant={selectedInterval === '1h' ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeInterval('1h')}
            >
              1h
            </Button>
            <Button
              size="sm"
              variant={selectedInterval === '3h' ? 'primary' : 'secondary'}
              className="text-xs px-2 py-1"
              onClick={() => changeInterval('3h')}
            >
              3h
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-grow" style={{ minHeight: '300px' }}>
        {isLoading && !data && (
          <div className="h-full flex items-center justify-center">
            <Loader text="Loading occupancy data..." />
          </div>
        )}

        {error && !data && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-red-500">
              <AlertCircle size={32} className="mx-auto mb-2" />
              <p>Failed to load occupancy data</p>
            </div>
          </div>
        )}

        {data && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={formatData(data)} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis
                domain={[0, (dataMax: number) => Math.max(dataMax + 2, 10)]}
                allowDecimals={false}
                label={{ value: 'People', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                formatter={(value) => [`${value} people`, 'Occupancy']}
                labelFormatter={(label) => `Time: ${label}`}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="count"
                name="Occupancy"
                stroke="#3B82F6"
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
};

export default OccupancyChart;