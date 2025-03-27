// src/components/notifications/NotificationTriggerForm.tsx
import React, { useState, useEffect } from 'react';
import { Save, X, Play } from 'lucide-react';
import Button from '../common/Button';
import { 
  NotificationTriggerCreate, 
  TriggerConditionType,
  TimeRestrictedTrigger,
  NotificationType
} from '../../types/notification';
import { fetchCameras } from '../../api/cameras';
import { fetchPersons } from '../../api/faceRecognition';
import { fetchTemplates } from '../../api/templates';
import { useApi } from '../../hooks/useApi';
import { testTrigger } from '../../api/notifications';
import { useToast } from '../../context/ToastContext';
import { NotificationTriggerFormProps, TestEventData } from './types/notificationFormTypes';
import { useNotificationFormValidation } from './hooks/useNotificationFormValidation';
import NotificationConditionParams from './NotificationConditionParams';
import NotificationConfigParams from './NotificationConfigParams';

const NotificationTriggerForm: React.FC<NotificationTriggerFormProps> = ({
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting
}) => {
  const { showToast } = useToast();
  const { errors, validateForm } = useNotificationFormValidation();

  // Form data state
  const [formData, setFormData] = useState<NotificationTriggerCreate>({
    name: '',
    description: '',
    active: true,
    condition_type: TriggerConditionType.OCCUPANCY_ABOVE,
    condition_params: { threshold: 10 },
    time_restriction: TimeRestrictedTrigger.ALWAYS,
    time_start: '08:00',
    time_end: '18:00',
    camera_id: undefined,
    cooldown_period: 300, // 5 minutes
    notification_type: NotificationType.EMAIL,
    notification_config: { 
      recipients: [''],
      include_snapshot: true
    }
  });
  
  // Testing state
  const [isTesting, setIsTesting] = useState(false);

  // Load initial values if provided
  useEffect(() => {
    if (initialValues) {
      setFormData({
        ...initialValues,
        // Remove properties not part of Create type
        id: undefined,
        created_at: undefined,
        updated_at: undefined,
        last_triggered: undefined
      } as NotificationTriggerCreate);
    }
  }, [initialValues]);

  // Load cameras
  const { execute: loadCameras, data: cameras } = useApi(fetchCameras);
  
  // Load persons for face recognition triggers
  const { execute: loadPersons, data: persons } = useApi(fetchPersons);
  
  // Load templates for template matching
  const { execute: loadTemplates, data: templates } = useApi(fetchTemplates);
  
  // Test trigger API
  const { execute: executeTriggerTest } = useApi(
    (id: number, testData: {camera_id: number, event_data: TestEventData}) => testTrigger(id, testData),
    {
      onSuccess: () => {
        showToast('Test notification sent successfully', 'success');
        setIsTesting(false);
      },
      onError: (error) => {
        showToast(`Test failed: ${error.message}`, 'error');
        setIsTesting(false);
      }
    }
  );

  // Load data on component mount
  useEffect(() => {
    loadCameras();
    
    if ([TriggerConditionType.SPECIFIC_FACE, TriggerConditionType.UNREGISTERED_FACE]
        .includes(formData.condition_type)) {
      loadPersons();
    }
    
    if (formData.condition_type === TriggerConditionType.TEMPLATE_MATCHED) {
      loadTemplates();
    }
  }, [formData.condition_type, loadCameras, loadPersons, loadTemplates]);

  // Handle form field changes
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  // Handle checkbox changes
  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    
    setFormData(prev => ({
      ...prev,
      [name]: checked
    }));
  };

  // Handle condition type change
  const handleConditionTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as TriggerConditionType;
    
    // Set default condition params based on type
    let conditionParams = {};
    
    switch (value) {
      case TriggerConditionType.OCCUPANCY_ABOVE:
      case TriggerConditionType.OCCUPANCY_BELOW:
        conditionParams = { threshold: 10 };
        break;
      case TriggerConditionType.SPECIFIC_FACE:
        conditionParams = { person_id: undefined, confidence_threshold: 0.6 };
        break;
      case TriggerConditionType.UNREGISTERED_FACE:
        conditionParams = { confidence_threshold: 0.6 };
        break;
      case TriggerConditionType.TEMPLATE_MATCHED:
        conditionParams = { template_id: undefined, confidence_threshold: 0.7 };
        break;
      case TriggerConditionType.TIME_RANGE:
        conditionParams = { start_time: '08:00', end_time: '18:00' };
        break;
    }
    
    setFormData(prev => ({
      ...prev,
      condition_type: value,
      condition_params: conditionParams
    }));
  };

  // Handle notification type change
  const handleNotificationTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as NotificationType;
    
    // Set default notification config based on type
    let notificationConfig = {};
    
    switch (value) {
      case NotificationType.EMAIL:
        notificationConfig = { 
          recipients: [''],
          subject_template: `Alert: {{condition_type}} triggered on {{camera_name}}`,
          body_template: `A {{condition_type}} condition was triggered on camera {{camera_name}} at {{timestamp}}.`,
          include_snapshot: true 
        };
        break;
      case NotificationType.TELEGRAM:
        notificationConfig = { 
          chat_ids: [''],
          message_template: `Alert: {{condition_type}} triggered on {{camera_name}} at {{timestamp}}`,
          include_snapshot: true 
        };
        break;
      case NotificationType.WEBHOOK:
        notificationConfig = { 
          url: '',
          headers: {},
          include_snapshot: false 
        };
        break;
    }
    
    setFormData(prev => ({
      ...prev,
      notification_type: value,
      notification_config: notificationConfig
    }));
  };

  // Handle condition params change
  const handleConditionParamChange = (name: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      condition_params: {
        ...prev.condition_params,
        [name]: value
      }
    }));
  };

  // Handle notification config change
  const handleNotificationConfigChange = (name: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      notification_config: {
        ...prev.notification_config,
        [name]: value
      }
    }));
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm(formData)) {
      await onSubmit(formData);
    }
  };

  // Handle test trigger
  const handleTestTrigger = async () => {
    if (!initialValues?.id) {
      showToast('Save the trigger first before testing', 'warning');
      return;
    }
    
    setIsTesting(true);
    
    const testData = {
      camera_id: formData.camera_id || 1,
      event_data: {} as TestEventData
    };
    
    // Add specific test data based on condition type
    switch (formData.condition_type) {
      case TriggerConditionType.OCCUPANCY_ABOVE:
        testData.event_data.occupancy = formData.condition_params.threshold + 1;
        break;
      case TriggerConditionType.OCCUPANCY_BELOW:
        testData.event_data.occupancy = formData.condition_params.threshold - 1;
        break;
      case TriggerConditionType.SPECIFIC_FACE:
        testData.event_data.person_id = formData.condition_params.person_id;
        testData.event_data.confidence = 0.9;
        break;
      case TriggerConditionType.UNREGISTERED_FACE:
        testData.event_data.unregistered_face = true;
        break;
      case TriggerConditionType.TEMPLATE_MATCHED:
        testData.event_data.template_id = formData.condition_params.template_id;
        testData.event_data.confidence = 0.9;
        break;
    }
    
    await executeTriggerTest(initialValues.id, testData);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6 max-h-[80vh] overflow-y-auto">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Basic information */}
        <div className="md:col-span-2">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Trigger Information</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
                Name *
              </label>
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                className={`w-full px-3 py-2 border rounded-md ${
                  errors.name ? 'border-red-500' : 'border-gray-300'
                }`}
                disabled={isSubmitting}
                placeholder="Occupancy Alert"
              />
              {errors.name && <p className="mt-1 text-sm text-red-500">{errors.name}</p>}
            </div>
            
            <div>
              <label htmlFor="camera_id" className="block text-sm font-medium text-gray-700 mb-1">
                Camera
              </label>
              <select
                id="camera_id"
                name="camera_id"
                value={formData.camera_id || ''}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
                disabled={isSubmitting}
              >
                <option value="">All Cameras</option>
                {cameras?.map(camera => (
                  <option key={camera.id} value={camera.id}>{camera.name}</option>
                ))}
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Leave blank to apply to all cameras
              </p>
            </div>
          </div>
          
          <div className="mt-3">
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="description"
              name="description"
              value={formData.description || ''}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows={2}
              disabled={isSubmitting}
              placeholder="Alert when occupancy is above threshold"
            />
          </div>
          
          <div className="mt-3 flex items-center">
            <input
              type="checkbox"
              id="active"
              name="active"
              checked={formData.active}
              onChange={handleCheckboxChange}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
            />
            <label htmlFor="active" className="ml-2 text-sm text-gray-700">
              Trigger is active
            </label>
          </div>
        </div>
        
        {/* Condition settings */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4">Trigger Condition</h3>
          
          <div className="mb-4">
            <label htmlFor="condition_type" className="block text-sm font-medium text-gray-700 mb-1">
              Condition Type
            </label>
            <select
              id="condition_type"
              value={formData.condition_type}
              onChange={handleConditionTypeChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              disabled={isSubmitting}
            >
              <option value={TriggerConditionType.OCCUPANCY_ABOVE}>Occupancy Above Threshold</option>
              <option value={TriggerConditionType.OCCUPANCY_BELOW}>Occupancy Below Threshold</option>
              <option value={TriggerConditionType.UNREGISTERED_FACE}>Unregistered Face Detected</option>
              <option value={TriggerConditionType.SPECIFIC_FACE}>Specific Person Detected</option>
              <option value={TriggerConditionType.TEMPLATE_MATCHED}>Template Matched</option>
              <option value={TriggerConditionType.TIME_RANGE}>Time Range (Scheduled Alert)</option>
            </select>
          </div>
          
          {/* Render condition-specific fields */}
          <NotificationConditionParams
            conditionType={formData.condition_type}
            conditionParams={formData.condition_params}
            onChange={handleConditionParamChange}
            errors={errors}
            persons={persons || []}
            templates={templates || []}
            isSubmitting={isSubmitting}
          />
          
          <div className="mt-4">
            <label htmlFor="cooldown_period" className="block text-sm font-medium text-gray-700 mb-1">
              Cooldown Period (seconds)
            </label>
            <input
              type="number"
              id="cooldown_period"
              name="cooldown_period"
              value={formData.cooldown_period}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              min="0"
              disabled={isSubmitting}
            />
            <p className="mt-1 text-sm text-gray-500">
              Minimum time between notifications (0 for no cooldown)
            </p>
          </div>
        </div>
        
        {/* Time restrictions */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4">Time Restrictions</h3>
          
          <div className="mb-4">
            <label htmlFor="time_restriction" className="block text-sm font-medium text-gray-700 mb-1">
              Time Restriction
            </label>
            <select
              id="time_restriction"
              name="time_restriction"
              value={formData.time_restriction}
              onChange={handleChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              disabled={isSubmitting}
            >
              <option value={TimeRestrictedTrigger.ALWAYS}>Always Active</option>
              <option value={TimeRestrictedTrigger.ONLY_DURING}>Only During Time Window</option>
              <option value={TimeRestrictedTrigger.EXCEPT_DURING}>Except During Time Window</option>
            </select>
          </div>
          
          {formData.time_restriction !== TimeRestrictedTrigger.ALWAYS && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="time_start" className="block text-sm font-medium text-gray-700 mb-1">
                  Start Time
                </label>
                <input
                  type="time"
                  id="time_start"
                  name="time_start"
                  value={formData.time_start || ''}
                  onChange={handleChange}
                  className={`w-full px-3 py-2 border rounded-md ${
                    errors.time_start ? 'border-red-500' : 'border-gray-300'
                  }`}
                  disabled={isSubmitting}
                />
                {errors.time_start && <p className="mt-1 text-sm text-red-500">{errors.time_start}</p>}
              </div>
              <div>
                <label htmlFor="time_end" className="block text-sm font-medium text-gray-700 mb-1">
                  End Time
                </label>
                <input
                  type="time"
                  id="time_end"
                  name="time_end"
                  value={formData.time_end || ''}
                  onChange={handleChange}
                  className={`w-full px-3 py-2 border rounded-md ${
                    errors.time_end ? 'border-red-500' : 'border-gray-300'
                  }`}
                  disabled={isSubmitting}
                />
                {errors.time_end && <p className="mt-1 text-sm text-red-500">{errors.time_end}</p>}
              </div>
            </div>
          )}
        </div>
        
        {/* Notification settings */}
        <div className="md:col-span-2">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Notification Settings</h3>
          
          <div className="mb-4">
            <label htmlFor="notification_type" className="block text-sm font-medium text-gray-700 mb-1">
              Notification Method
            </label>
            <select
              id="notification_type"
              value={formData.notification_type}
              onChange={handleNotificationTypeChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              disabled={isSubmitting}
            >
              <option value={NotificationType.EMAIL}>Email</option>
              <option value={NotificationType.TELEGRAM}>Telegram</option>
              <option value={NotificationType.WEBHOOK}>Webhook</option>
            </select>
          </div>
          
          {/* Render notification-specific fields */}
          <NotificationConfigParams
            notificationType={formData.notification_type}
            notificationConfig={formData.notification_config}
            onChange={handleNotificationConfigChange}
            errors={errors}
            isSubmitting={isSubmitting}
          />
        </div>
      </div>
      
      <div className="flex justify-end space-x-3">
        {initialValues?.id && (
          <Button
            type="button"
            variant="secondary"
            onClick={handleTestTrigger}
            disabled={isSubmitting || isTesting}
            icon={<Play size={16} />}
          >
            Test Trigger
          </Button>
        )}
        
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={isSubmitting}
          icon={<X size={16} />}
        >
          Cancel
        </Button>
        
        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          icon={<Save size={16} />}
        >
          {initialValues ? 'Update Trigger' : 'Create Trigger'}
        </Button>
      </div>
    </form>
  );
};

export default NotificationTriggerForm;