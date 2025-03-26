// src/components/notifications/NotificationEventList.tsx
import React, { useState, useEffect } from 'react';
import { 
  Calendar, 
  Camera, 
  Clock, 
  CheckCircle, 
  XCircle, 
  AlertTriangle, 
  ChevronDown, 
  ChevronUp,
  ExternalLink
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { NotificationEvent, TriggerConditionType } from '../../types/notification';
import Card from '../common/Card';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { useApi } from '../../hooks/useApi';
import { fetchNotificationEvents } from '../../api/notifications';
import { fetchCameras } from '../../api/cameras';
import { fetchTriggers } from '../../api/notifications';

interface NotificationEventListProps {
  limit?: number;
  triggerId?: number;
  cameraId?: number;
  showFilters?: boolean;
  onViewDetails?: (event: NotificationEvent) => void;
}

const NotificationEventList: React.FC<NotificationEventListProps> = ({ 
  limit = 10,
  triggerId,
  cameraId,
  showFilters = false,
  onViewDetails
}) => {
  const [events, setEvents] = useState<NotificationEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState({
    triggerId: triggerId || undefined,
    cameraId: cameraId || undefined,
    successfulOnly: false,
    startDate: undefined as string | undefined,
    endDate: undefined as string | undefined
  });
  
  // Load events
  const { 
    execute: loadEvents, 
    isLoading, 
    error 
  } = useApi(
    () => fetchNotificationEvents({
      trigger_id: filters.triggerId,
      camera_id: filters.cameraId,
      successful_only: filters.successfulOnly,
      start_date: filters.startDate,
      end_date: filters.endDate,
      limit
    }),
    {
      onSuccess: (data) => {
        setEvents(data);
      }
    }
  );
  
  // Load cameras for filters
  const { data: cameras } = useApi(fetchCameras, {
    executeOnMount: showFilters
  });
  
  // Load triggers for filters
  const { data: triggers } = useApi(fetchTriggers, {
    executeOnMount: showFilters
  });

  // Load events on mount and when filters change
  useEffect(() => {
    loadEvents();
  }, [loadEvents, filters]);

  // Load events when props change
  useEffect(() => {
    setFilters(prev => ({
      ...prev,
      triggerId: triggerId || undefined,
      cameraId: cameraId || undefined
    }));
  }, [triggerId, cameraId]);

  const toggleExpand = (id: number) => {
    setExpandedEvents(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const formatTimestamp = (timestamp: string): string => {
    return new Date(timestamp).toLocaleString();
  };

  const getCameraName = (id: number): string => {
    if (!cameras) return `Camera ${id}`;
    const camera = cameras.find(c => c.id === id);
    return camera ? camera.name : `Camera ${id}`;
  };

  const getTriggerName = (id: number): string => {
    if (!triggers) return `Trigger ${id}`;
    const trigger = triggers.find(t => t.id === id);
    return trigger ? trigger.name : `Trigger ${id}`;
  };

  const getTriggerConditionType = (id: number): TriggerConditionType | undefined => {
    if (!triggers) return undefined;
    const trigger = triggers.find(t => t.id === id);
    return trigger?.condition_type;
  };

  const handleFilterChange = (name: string, value: any) => {
    setFilters(prev => ({
      ...prev,
      [name]: value
    }));
  };

  if (isLoading && events.length === 0) {
    return <Loader text="Loading notification events..." />;
  }

  if (error && events.length === 0) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertTriangle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading events</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="bg-gray-50 p-6 rounded-md text-center">
        <p className="text-gray-600">No notification events found.</p>
        <p className="text-gray-500 text-sm mt-1">
          Events will appear here when notifications are triggered.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {showFilters && (
        <Card className="mb-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Filter Events</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Trigger
              </label>
              <select
                value={filters.triggerId || ''}
                onChange={(e) => handleFilterChange('triggerId', e.target.value ? parseInt(e.target.value) : undefined)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="">All Triggers</option>
                {triggers?.map(trigger => (
                  <option key={trigger.id} value={trigger.id}>
                    {trigger.name}
                  </option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Camera
              </label>
              <select
                value={filters.cameraId || ''}
                onChange={(e) => handleFilterChange('cameraId', e.target.value ? parseInt(e.target.value) : undefined)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="">All Cameras</option>
                {cameras?.map(camera => (
                  <option key={camera.id} value={camera.id}>
                    {camera.name}
                  </option>
                ))}
              </select>
            </div>
            
            <div className="flex items-end">
              <div className="flex items-center h-10">
                <input
                  type="checkbox"
                  id="successfulOnly"
                  checked={filters.successfulOnly}
                  onChange={(e) => handleFilterChange('successfulOnly', e.target.checked)}
                  className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                />
                <label htmlFor="successfulOnly" className="ml-2 text-sm text-gray-700">
                  Successful notifications only
                </label>
              </div>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Start Date
              </label>
              <input
                type="datetime-local"
                value={filters.startDate || ''}
                onChange={(e) => handleFilterChange('startDate', e.target.value || undefined)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                End Date
              </label>
              <input
                type="datetime-local"
                value={filters.endDate || ''}
                onChange={(e) => handleFilterChange('endDate', e.target.value || undefined)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
          
          <div className="mt-4 flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setFilters({
                  triggerId: undefined,
                  cameraId: undefined,
                  successfulOnly: false,
                  startDate: undefined,
                  endDate: undefined
                });
              }}
            >
              Clear Filters
            </Button>
          </div>
        </Card>
      )}
      
      <div className="space-y-4">
        {events.map((event) => {
          const isExpanded = expandedEvents.has(event.id);
          const conditionType = getTriggerConditionType(event.trigger_id);
          
          return (
            <div
              key={event.id}
              className={`border rounded-md overflow-hidden ${
                event.sent_successfully 
                  ? 'border-green-200 bg-green-50' 
                  : 'border-red-200 bg-red-50'
              }`}
            >
              <div 
                className="p-4 cursor-pointer flex items-center"
                onClick={() => toggleExpand(event.id)}
              >
                <div className="mr-3">
                  {event.sent_successfully ? (
                    <CheckCircle className="text-green-500" size={24} />
                  ) : (
                    <XCircle className="text-red-500" size={24} />
                  )}
                </div>
                
                <div className="flex-grow">
                  <h3 className="font-medium text-gray-900">
                    {getTriggerName(event.trigger_id)}
                  </h3>
                  <div className="flex flex-wrap text-sm text-gray-600 mt-1">
                    <span className="flex items-center mr-4">
                      <Camera size={14} className="mr-1" />
                      {getCameraName(event.camera_id)}
                    </span>
                    <span className="flex items-center mr-4">
                      <Clock size={14} className="mr-1" />
                      {formatTimestamp(event.timestamp)}
                    </span>
                    {conditionType && (
                      <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs">
                        {conditionType}
                      </span>
                    )}
                  </div>
                </div>
                
                <div>
                  {isExpanded ? (
                    <ChevronUp size={20} className="text-gray-500" />
                  ) : (
                    <ChevronDown size={20} className="text-gray-500" />
                  )}
                </div>
              </div>
              
              {isExpanded && (
                <div className="border-t px-4 py-3 bg-white">
                  <h4 className="font-medium text-sm mb-2">Event Data:</h4>
                  <pre className="bg-gray-50 p-2 rounded-md text-xs overflow-x-auto">
                    {JSON.stringify(event.event_data, null, 2)}
                  </pre>
                  
                  {event.delivery_error && (
                    <div className="mt-3">
                      <h4 className="font-medium text-sm mb-1 text-red-700">Error:</h4>
                      <p className="text-sm text-red-600">{event.delivery_error}</p>
                    </div>
                  )}
                  
                  {event.snapshot_path && (
                    <div className="mt-3">
                      <h4 className="font-medium text-sm mb-2">Snapshot:</h4>
                      <img 
                        src={`/api/${event.snapshot_path}`} 
                        alt="Event snapshot" 
                        className="max-h-48 rounded-md border"
                      />
                    </div>
                  )}
                  
                  <div className="mt-3 flex justify-end">
                    {onViewDetails && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => onViewDetails(event)}
                        icon={<ExternalLink size={14} />}
                      >
                        View Details
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default NotificationEventList;