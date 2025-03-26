// src/pages/NotificationEvents.tsx
import React, { useState } from 'react';
import { Bell, Calendar } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import NotificationEventList from '../components/notifications/NotificationEventList';
import { NotificationEvent } from '../types/notification';

const NotificationEvents: React.FC = () => {
  const [selectedEvent, setSelectedEvent] = useState<NotificationEvent | null>(null);
  
  const handleViewDetails = (event: NotificationEvent) => {
    setSelectedEvent(event);
    // Could show a detail modal here in the future
    // For now, we just log the event
    console.log('Selected event:', event);
  };

  return (
    <div>
      <PageHeader
        title="Notification Events"
        subtitle="History of triggered notification events"
        actions={
          <div className="flex space-x-3">
            <Button
              variant="secondary"
              icon={<Calendar size={16} />}
            >
              Export
            </Button>
          </div>
        }
      />
      
      <Card className="mb-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Event History</h3>
        <p className="text-gray-600 mb-4">
          This page shows the history of all notification events. You can filter the events by trigger, camera, date, and more.
        </p>
      </Card>
      
      <NotificationEventList 
        showFilters={true} 
        limit={50}
        onViewDetails={handleViewDetails} 
      />
    </div>
  );
};

export default NotificationEvents;