// src/pages/NotificationDashboard.tsx
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Bell, List } from 'lucide-react';
import PageHeader from '../components/common/PageHeader';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import NotificationStats from '../components/notifications/NotificationStats';
import NotificationEventList from '../components/notifications/NotificationEventList';
import NotificationTriggerList from '../components/notifications/NotificationTriggerList';

const NotificationDashboard: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Notification Dashboard"
        subtitle="Overview of notification system performance and recent events"
        actions={
          <div className="flex space-x-3">
            <Link to="/notifications/triggers">
              <Button
                variant="secondary"
                icon={<Bell size={16} />}
              >
                Manage Triggers
              </Button>
            </Link>
            <Link to="/notifications/events">
              <Button
                variant="secondary"
                icon={<List size={16} />}
              >
                Event History
              </Button>
            </Link>
          </div>
        }
      />
      
      {/* Statistics */}
      <div className="mb-8">
        <NotificationStats />
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Recent Events */}
        <div>
          <Card className="mb-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-medium text-gray-900">Recent Events</h3>
              <Link to="/notifications/events">
                <Button
                  variant="link"
                  icon={<ArrowRight size={16} />}
                  className="text-sm"
                >
                  View All
                </Button>
              </Link>
            </div>
          </Card>
          
          <NotificationEventList limit={10} />
        </div>
        
        {/* Active Triggers */}
        <div>
          <Card className="mb-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-medium text-gray-900">Active Triggers</h3>
              <Link to="/notifications/triggers">
                <Button
                  variant="link"
                  icon={<ArrowRight size={16} />}
                  className="text-sm"
                >
                  Manage
                </Button>
              </Link>
            </div>
          </Card>
          
          <NotificationTriggerList 
            filterActive={true}
            onEdit={(trigger) => {
              window.location.href = `/notifications/triggers?edit=${trigger.id}`;
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default NotificationDashboard;