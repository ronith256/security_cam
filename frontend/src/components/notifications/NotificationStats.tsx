// src/components/notifications/NotificationStats.tsx
import React, { useState, useEffect } from 'react';
import { 
  PieChart, 
  Pie, 
  Cell, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer 
} from 'recharts';
import { 
  CheckCircle, 
  XCircle, 
  AlertTriangle,
  Calendar,
  Clock
} from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { useApi } from '../../hooks/useApi';
import { fetchNotificationStats } from '../../api/notifications';
import { NotificationStats as NotificationStatsType } from '../../types/notification';

interface NotificationStatsProps {
  startDate?: string;
  endDate?: string;
}

const NotificationStats: React.FC<NotificationStatsProps> = ({ 
  startDate,
  endDate 
}) => {
  const [dateRange, setDateRange] = useState({
    startDate: startDate || new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
    endDate: endDate || new Date().toISOString().slice(0, 10)
  });
  
  // Load stats
  const { 
    execute: loadStats, 
    data: stats, 
    isLoading, 
    error 
  } = useApi(
    () => fetchNotificationStats(dateRange.startDate, dateRange.endDate),
    {
      onSuccess: (data) => {
        console.log('Stats loaded:', data);
      }
    }
  );

  // Load stats on mount and when date range changes
  useEffect(() => {
    loadStats();
  }, [loadStats, dateRange]);

  // Handle date range change
  const handleDateChange = (field: 'startDate' | 'endDate', value: string) => {
    setDateRange(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Quick date range buttons
  const setQuickRange = (days: number) => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - days);
    
    setDateRange({
      startDate: start.toISOString().slice(0, 10),
      endDate: end.toISOString().slice(0, 10)
    });
  };

  // Prepare data for success/failure pie chart
  const prepareStatusData = (stats: NotificationStatsType) => [
    { name: 'Success', value: stats.success_count, color: '#22C55E' },
    { name: 'Failed', value: stats.failed_count, color: '#EF4444' }
  ];

  // Prepare data for trigger type bar chart
  const prepareTriggerData = (stats: NotificationStatsType) => {
    return stats.trigger_stats.map(trigger => ({
      name: trigger.trigger_name,
      count: trigger.event_count,
      type: trigger.condition_type
    }));
  };

  // If loading with no data yet
  if (isLoading && !stats) {
    return <Loader text="Loading notification statistics..." />;
  }

  // If there was an error
  if (error && !stats) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertTriangle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading statistics</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Date range selection */}
      <Card>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between">
          <h3 className="text-lg font-medium text-gray-900 mb-4 md:mb-0">Notification Statistics</h3>
          
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex items-center">
              <div className="mr-2">
                <label htmlFor="startDate" className="block text-sm font-medium text-gray-700">
                  Start Date
                </label>
                <input
                  type="date"
                  id="startDate"
                  value={dateRange.startDate}
                  onChange={(e) => handleDateChange('startDate', e.target.value)}
                  className="mt-1 px-3 py-1 border border-gray-300 rounded-md text-sm"
                />
              </div>
              <div>
                <label htmlFor="endDate" className="block text-sm font-medium text-gray-700">
                  End Date
                </label>
                <input
                  type="date"
                  id="endDate"
                  value={dateRange.endDate}
                  onChange={(e) => handleDateChange('endDate', e.target.value)}
                  className="mt-1 px-3 py-1 border border-gray-300 rounded-md text-sm"
                />
              </div>
            </div>
            
            <div className="flex items-center space-x-2">
              <Button size="sm" variant="secondary" onClick={() => setQuickRange(7)}>7d</Button>
              <Button size="sm" variant="secondary" onClick={() => setQuickRange(30)}>30d</Button>
              <Button size="sm" variant="secondary" onClick={() => setQuickRange(90)}>90d</Button>
            </div>
          </div>
        </div>
      </Card>
      
      {stats && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card className="bg-blue-50">
              <div className="flex items-center">
                <div className="p-3 bg-blue-100 rounded-full mr-4">
                  <Calendar className="text-blue-600" size={24} />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-800">Total Notifications</h3>
                  <p className="text-3xl font-bold text-blue-600">{stats.total_count}</p>
                </div>
              </div>
            </Card>
            
            <Card className="bg-green-50">
              <div className="flex items-center">
                <div className="p-3 bg-green-100 rounded-full mr-4">
                  <CheckCircle className="text-green-600" size={24} />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-800">Successful</h3>
                  <p className="text-3xl font-bold text-green-600">{stats.success_count}</p>
                  <p className="text-sm text-gray-600">{stats.success_rate.toFixed(1)}% success rate</p>
                </div>
              </div>
            </Card>
            
            <Card className="bg-red-50">
              <div className="flex items-center">
                <div className="p-3 bg-red-100 rounded-full mr-4">
                  <XCircle className="text-red-600" size={24} />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-800">Failed</h3>
                  <p className="text-3xl font-bold text-red-600">{stats.failed_count}</p>
                  <p className="text-sm text-gray-600">{(100 - stats.success_rate).toFixed(1)}% failure rate</p>
                </div>
              </div>
            </Card>
          </div>
          
          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Success/Failure Pie Chart */}
            <Card>
              <h3 className="text-lg font-medium text-gray-900 mb-4">Notification Status</h3>
              
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={prepareStatusData(stats)}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {prepareStatusData(stats).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </Card>
            
            {/* Trigger Type Bar Chart */}
            <Card>
              <h3 className="text-lg font-medium text-gray-900 mb-4">Notifications by Trigger</h3>
              
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={prepareTriggerData(stats)}
                    margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="count" name="Count" fill="#3B82F6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          
          {/* Date information */}
          <div className="text-sm text-gray-500 flex items-center justify-end">
            <Clock size={14} className="mr-1" />
            Showing data from {new Date(stats.start_date).toLocaleDateString()} to {new Date(stats.end_date).toLocaleDateString()}
          </div>
        </>
      )}
    </div>
  );
};

export default NotificationStats;