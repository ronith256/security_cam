// src/components/notifications/NotificationTriggerList.tsx
import React, { useState, useEffect } from 'react';
import { 
  Edit, 
  Trash2, 
  ToggleLeft, 
  ToggleRight, 
  Calendar,
  Activity, 
  AlertTriangle, 
  CheckCircle,
  User,
  Users,
  Clock,
  Image
} from 'lucide-react';
import { 
  NotificationTrigger, 
  TriggerConditionType,
  NotificationType,
  TimeRestrictedTrigger
} from '../../types/notification';
import Card from '../common/Card';
import Button from '../common/Button';
import Loader from '../common/Loader';
import { useApi } from '../../hooks/useApi';
import { fetchTriggers, toggleTrigger, deleteTrigger } from '../../api/notifications';
import { useToast } from '../../context/ToastContext';

interface NotificationTriggerListProps {
  onEdit: (trigger: NotificationTrigger) => void;
  filterActive?: boolean;
}

const NotificationTriggerList: React.FC<NotificationTriggerListProps> = ({ 
  onEdit,
  filterActive
}) => {
  const [triggers, setTriggers] = useState<NotificationTrigger[]>([]);
  const { showToast } = useToast();
  
  // Load triggers
  const { 
    execute: loadTriggers, 
    isLoading, 
    error 
  } = useApi(
    () => fetchTriggers(filterActive),
    {
      onSuccess: (data) => {
        setTriggers(data);
      }
    }
  );
  
  // Toggle active status
  const { execute: executeToggle } = useApi(
    (id: number, active: boolean) => toggleTrigger(id, active),
    {
      onSuccess: () => {
        showToast('Trigger status updated', 'success');
        loadTriggers();
      }
    }
  );
  
  // Delete trigger
  const { execute: executeDelete } = useApi(
    (id: number) => deleteTrigger(id),
    {
      onSuccess: () => {
        showToast('Trigger deleted successfully', 'success');
        loadTriggers();
      }
    }
  );

  // Load triggers on mount
  useEffect(() => {
    loadTriggers();
  }, [loadTriggers, filterActive]);

  const handleToggleActive = async (id: number, currentStatus: boolean) => {
    await executeToggle(id, !currentStatus);
  };

  const handleDelete = async (id: number, name: string) => {
    if (window.confirm(`Are you sure you want to delete trigger "${name}"?`)) {
      await executeDelete(id);
    }
  };

  // Get icon for condition type
  const getConditionIcon = (type: TriggerConditionType) => {
    switch (type) {
      case TriggerConditionType.OCCUPANCY_ABOVE:
        return <Users className="text-blue-600" />;
      case TriggerConditionType.OCCUPANCY_BELOW:
        return <Users className="text-amber-600" />;
      case TriggerConditionType.UNREGISTERED_FACE:
        return <User className="text-orange-600" />;
      case TriggerConditionType.SPECIFIC_FACE:
        return <User className="text-green-600" />;
      case TriggerConditionType.TEMPLATE_MATCHED:
        return <Image className="text-purple-600" />;
      case TriggerConditionType.TIME_RANGE:
        return <Clock className="text-cyan-600" />;
      default:
        return <Activity className="text-gray-600" />;
    }
  };

  // Get icon for notification type
  const getNotificationIcon = (type: NotificationType) => {
    switch (type) {
      case NotificationType.EMAIL:
        return <i className="fas fa-envelope text-gray-700"></i>;
      case NotificationType.TELEGRAM:
        return <i className="fab fa-telegram text-blue-500"></i>;
      case NotificationType.WEBHOOK:
        return <i className="fas fa-code text-gray-700"></i>;
      default:
        return null;
    }
  };

  // Get user-friendly condition description
  const getConditionDescription = (trigger: NotificationTrigger): string => {
    const { condition_type, condition_params } = trigger;
    
    switch (condition_type) {
      case TriggerConditionType.OCCUPANCY_ABOVE:
        return `Occupancy above ${condition_params.threshold} people`;
      case TriggerConditionType.OCCUPANCY_BELOW:
        return `Occupancy below ${condition_params.threshold} people`;
      case TriggerConditionType.UNREGISTERED_FACE:
        return 'Unregistered face detected';
      case TriggerConditionType.SPECIFIC_FACE:
        return `Specific person detected (ID: ${condition_params.person_id})`;
      case TriggerConditionType.TEMPLATE_MATCHED:
        return `Template matched (ID: ${condition_params.template_id})`;
      case TriggerConditionType.TIME_RANGE:
        return `Time-based alert: ${condition_params.start_time} to ${condition_params.end_time}`;
      default:
        return 'Unknown condition';
    }
  };

  // Get user-friendly notification description
  const getNotificationDescription = (trigger: NotificationTrigger): string => {
    const { notification_type, notification_config } = trigger;
    
    switch (notification_type) {
      case NotificationType.EMAIL:
        return `Email to ${notification_config.recipients?.length} recipient(s)`;
      case NotificationType.TELEGRAM:
        return `Telegram to ${notification_config.chat_ids?.length} chat(s)`;
      case NotificationType.WEBHOOK:
        return `Webhook to ${notification_config.url}`;
      default:
        return 'Unknown notification method';
    }
  };

  // Get user-friendly time restriction description
  const getTimeRestrictionDescription = (trigger: NotificationTrigger): string | null => {
    const { time_restriction, time_start, time_end } = trigger;
    
    if (time_restriction === TimeRestrictedTrigger.ALWAYS) {
      return null;
    }
    
    const timeRange = `${time_start} to ${time_end}`;
    
    if (time_restriction === TimeRestrictedTrigger.ONLY_DURING) {
      return `Only active during: ${timeRange}`;
    } else {
      return `Not active during: ${timeRange}`;
    }
  };

  if (isLoading && triggers.length === 0) {
    return <Loader text="Loading notification triggers..." />;
  }

  if (error && triggers.length === 0) {
    return (
      <div className="bg-red-50 p-4 rounded-md flex items-start">
        <AlertTriangle className="text-red-500 mr-2 mt-0.5" size={20} />
        <div>
          <h3 className="text-red-800 font-medium">Error loading triggers</h3>
          <p className="text-red-700 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  if (triggers.length === 0) {
    return (
      <div className="bg-gray-50 p-6 rounded-md text-center">
        <p className="text-gray-600">No notification triggers found.</p>
        <p className="text-gray-500 text-sm mt-1">
          Create a trigger to get notifications when events occur.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {triggers.map((trigger) => (
        <Card
          key={trigger.id}
          title={trigger.name}
          subtitle={trigger.description || 'No description'}
          className={`h-full border-l-4 ${trigger.active ? 'border-l-green-500' : 'border-l-gray-300'}`}
        >
          <div className="flex flex-col h-full">
            <div className="mb-4 flex items-center">
              <div className="p-2 rounded-full bg-gray-100 mr-3">
                {getConditionIcon(trigger.condition_type)}
              </div>
              <div>
                <p className="font-medium">{getConditionDescription(trigger)}</p>
                <p className="text-sm text-gray-600">
                  {getNotificationDescription(trigger)}
                </p>
              </div>
            </div>
            
            {trigger.camera_id && (
              <p className="text-sm text-gray-600 mb-2">
                <span className="font-medium">Camera:</span> ID {trigger.camera_id}
              </p>
            )}
            
            {trigger.cooldown_period > 0 && (
              <p className="text-sm text-gray-600 mb-2">
                <span className="font-medium">Cooldown:</span> {trigger.cooldown_period} seconds
              </p>
            )}
            
            {getTimeRestrictionDescription(trigger) && (
              <p className="text-sm text-gray-600 mb-2">
                <Calendar size={14} className="inline mr-1" />
                {getTimeRestrictionDescription(trigger)}
              </p>
            )}
            
            {trigger.last_triggered && (
              <p className="text-sm text-gray-600 mb-2">
                <span className="font-medium">Last triggered:</span> {new Date(trigger.last_triggered).toLocaleString()}
              </p>
            )}
            
            <div className="flex items-center text-sm text-gray-600 mb-2">
              <span className={`px-2 py-0.5 rounded ${trigger.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                {trigger.active ? (
                  <><CheckCircle size={14} className="inline mr-1" /> Active</>
                ) : (
                  <>Inactive</>
                )}
              </span>
              <span className="text-xs text-gray-500 ml-auto">
                Created: {new Date(trigger.created_at).toLocaleDateString()}
              </span>
            </div>
            
            <div className="flex space-x-2 mt-auto">
              <Button
                variant={trigger.active ? 'warning' : 'success'}
                size="sm"
                onClick={() => handleToggleActive(trigger.id, trigger.active)}
                icon={trigger.active ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
              >
                {trigger.active ? 'Disable' : 'Enable'}
              </Button>
              
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onEdit(trigger)}
                icon={<Edit size={16} />}
              >
                Edit
              </Button>
              
              <Button
                variant="danger"
                size="sm"
                onClick={() => handleDelete(trigger.id, trigger.name)}
                icon={<Trash2 size={16} />}
              >
                Delete
              </Button>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};

export default NotificationTriggerList;