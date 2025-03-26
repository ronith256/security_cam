// src/components/notifications/NotificationTriggerForm.tsx
import React, { useState, useEffect } from 'react';
import { Save, X, Play } from 'lucide-react';
import Button from '../common/Button';
import { 
  NotificationTrigger, 
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

interface NotificationTriggerFormProps {
  initialValues?: NotificationTrigger;
  onSubmit: (data: NotificationTriggerCreate) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

const NotificationTriggerForm: React.FC<NotificationTriggerFormProps> = ({
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting
}) => {
  const { showToast } = useToast();

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

  // Validation errors
  const [errors, setErrors] = useState<Record<string, string>>({});
  
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
    (id: number, testData: any) => testTrigger(id, testData),
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
          subject_template: 'Alert: {{condition_type}} triggered on {{camera_name}}',
          body_template: 'A {{condition_type}} condition was triggered on camera {{camera_name}} at {{timestamp}}.',
          include_snapshot: true 
        };
        break;
      case NotificationType.TELEGRAM:
        notificationConfig = { 
          chat_ids: [''],
          message_template: 'Alert: {{condition_type}} triggered on {{camera_name}} at {{timestamp}}',
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

  // Handle recipients array change
  const handleRecipientsChange = (index: number, value: string) => {
    const recipients = [...(formData.notification_config.recipients || [''])];
    recipients[index] = value;
    
    handleNotificationConfigChange('recipients', recipients);
  };

  // Add recipient field
  const addRecipient = () => {
    const recipients = [...(formData.notification_config.recipients || [''])];
    recipients.push('');
    
    handleNotificationConfigChange('recipients', recipients);
  };

  // Remove recipient field
  const removeRecipient = (index: number) => {
    const recipients = [...(formData.notification_config.recipients || [''])];
    recipients.splice(index, 1);
    
    handleNotificationConfigChange('recipients', recipients);
  };

  // Handle chat IDs array change
  const handleChatIdsChange = (index: number, value: string) => {
    const chatIds = [...(formData.notification_config.chat_ids || [''])];
    chatIds[index] = value;
    
    handleNotificationConfigChange('chat_ids', chatIds);
  };

  // Add chat ID field
  const addChatId = () => {
    const chatIds = [...(formData.notification_config.chat_ids || [''])];
    chatIds.push('');
    
    handleNotificationConfigChange('chat_ids', chatIds);
  };

  // Remove chat ID field
  const removeChatId = (index: number) => {
    const chatIds = [...(formData.notification_config.chat_ids || [''])];
    chatIds.splice(index, 1);
    
    handleNotificationConfigChange('chat_ids', chatIds);
  };

  // Validate form data
  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};
    
    // Required fields
    if (!formData.name) {
      newErrors.name = 'Name is required';
    }
    
    // Condition-specific validation
    if (formData.condition_type === TriggerConditionType.OCCUPANCY_ABOVE || 
        formData.condition_type === TriggerConditionType.OCCUPANCY_BELOW) {
      if (!formData.condition_params.threshold) {
        newErrors.threshold = 'Threshold is required';
      } else if (formData.condition_params.threshold <= 0) {
        newErrors.threshold = 'Threshold must be greater than 0';
      }
    } else if (formData.condition_type === TriggerConditionType.SPECIFIC_FACE) {
      if (!formData.condition_params.person_id) {
        newErrors.person_id = 'Person is required';
      }
    } else if (formData.condition_type === TriggerConditionType.TEMPLATE_MATCHED) {
      if (!formData.condition_params.template_id) {
        newErrors.template_id = 'Template is required';
      }
    }
    
    // Time restriction validation
    if (formData.time_restriction !== TimeRestrictedTrigger.ALWAYS) {
      if (!formData.time_start) {
        newErrors.time_start = 'Start time is required';
      }
      if (!formData.time_end) {
        newErrors.time_end = 'End time is required';
      }
    }
    
    // Notification config validation
    if (formData.notification_type === NotificationType.EMAIL) {
      if (!formData.notification_config.recipients || formData.notification_config.recipients.length === 0) {
        newErrors.recipients = 'At least one recipient is required';
      } else if (formData.notification_config.recipients.some(email => !email)) {
        newErrors.recipients = 'All email addresses must be filled';
      }
    } else if (formData.notification_type === NotificationType.TELEGRAM) {
      if (!formData.notification_config.chat_ids || formData.notification_config.chat_ids.length === 0) {
        newErrors.chat_ids = 'At least one chat ID is required';
      } else if (formData.notification_config.chat_ids.some(id => !id)) {
        newErrors.chat_ids = 'All chat IDs must be filled';
      }
    } else if (formData.notification_type === NotificationType.WEBHOOK) {
      if (!formData.notification_config.url) {
        newErrors.webhook_url = 'Webhook URL is required';
      }
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validateForm()) {
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
      event_data: {}
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

  // Render condition params form fields
  const renderConditionParams = () => {
    switch (formData.condition_type) {
      case TriggerConditionType.OCCUPANCY_ABOVE:
      case TriggerConditionType.OCCUPANCY_BELOW:
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Occupancy Threshold
            </label>
            <input
              type="number"
              value={formData.condition_params.threshold || 0}
              onChange={(e) => handleConditionParamChange('threshold', parseInt(e.target.value))}
              className={`w-full px-3 py-2 border rounded-md ${
                errors.threshold ? 'border-red-500' : 'border-gray-300'
              }`}
              min="1"
            />
            {errors.threshold && <p className="mt-1 text-sm text-red-500">{errors.threshold}</p>}
            <p className="mt-1 text-sm text-gray-500">
              Trigger when the number of people is {formData.condition_type === TriggerConditionType.OCCUPANCY_ABOVE ? 'above' : 'below'} this threshold
            </p>
          </div>
        );
      
      case TriggerConditionType.SPECIFIC_FACE:
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Person
            </label>
            <select
              value={formData.condition_params.person_id || ''}
              onChange={(e) => handleConditionParamChange('person_id', parseInt(e.target.value))}
              className={`w-full px-3 py-2 border rounded-md ${
                errors.person_id ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Select a person</option>
              {persons?.map(person => (
                <option key={person.id} value={person.id}>{person.name}</option>
              ))}
            </select>
            {errors.person_id && <p className="mt-1 text-sm text-red-500">{errors.person_id}</p>}
            
            <div className="mt-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Confidence Threshold
              </label>
              <div className="flex items-center space-x-2">
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={formData.condition_params.confidence_threshold || 0.6}
                  onChange={(e) => handleConditionParamChange('confidence_threshold', parseFloat(e.target.value))}
                  className="w-full"
                />
                <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
                  {((formData.condition_params.confidence_threshold || 0.6) * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        );
      
      case TriggerConditionType.UNREGISTERED_FACE:
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Confidence Threshold
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={formData.condition_params.confidence_threshold || 0.6}
                onChange={(e) => handleConditionParamChange('confidence_threshold', parseFloat(e.target.value))}
                className="w-full"
              />
              <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
                {((formData.condition_params.confidence_threshold || 0.6) * 100).toFixed(0)}%
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Minimum confidence level required to consider a face as unrecognized
            </p>
          </div>
        );
      
      case TriggerConditionType.TEMPLATE_MATCHED:
        return (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Template
            </label>
            <select
              value={formData.condition_params.template_id || ''}
              onChange={(e) => handleConditionParamChange('template_id', parseInt(e.target.value))}
              className={`w-full px-3 py-2 border rounded-md ${
                errors.template_id ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Select a template</option>
              {templates?.map(template => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </select>
            {errors.template_id && <p className="mt-1 text-sm text-red-500">{errors.template_id}</p>}
            
            <div className="mt-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Confidence Threshold
              </label>
              <div className="flex items-center space-x-2">
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={formData.condition_params.confidence_threshold || 0.7}
                  onChange={(e) => handleConditionParamChange('confidence_threshold', parseFloat(e.target.value))}
                  className="w-full"
                />
                <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
                  {((formData.condition_params.confidence_threshold || 0.7) * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        );
      
      case TriggerConditionType.TIME_RANGE:
        return (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Start Time
              </label>
              <input
                type="time"
                value={formData.condition_params.start_time || ''}
                onChange={(e) => handleConditionParamChange('start_time', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                End Time
              </label>
              <input
                type="time"
                value={formData.condition_params.end_time || ''}
                onChange={(e) => handleConditionParamChange('end_time', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
        );
      
      default:
        return null;
    }
  };

  // Render notification config form fields
  const renderNotificationConfig = () => {
    switch (formData.notification_type) {
      case NotificationType.EMAIL:
        return (
          <div>
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email Recipients
              </label>
              {formData.notification_config.recipients?.map((email, index) => (
                <div key={index} className="flex items-center mb-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => handleRecipientsChange(index, e.target.value)}
                    className={`flex-grow px-3 py-2 border ${
                      errors.recipients ? 'border-red-500' : 'border-gray-300'
                    } rounded-md mr-2`}
                    placeholder="email@example.com"
                  />
                  <button
                    type="button"
                    onClick={() => removeRecipient(index)}
                    className="text-red-500 hover:text-red-700"
                    disabled={formData.notification_config.recipients.length === 1}
                  >
                    <X size={18} />
                  </button>
                </div>
              ))}
              {errors.recipients && <p className="mt-0 mb-2 text-sm text-red-500">{errors.recipients}</p>}
              <button
                type="button"
                onClick={addRecipient}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                + Add another recipient
              </button>
            </div>
            
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email Subject Template
              </label>
              <input
                type="text"
                value={formData.notification_config.subject_template || ''}
                onChange={(e) => handleNotificationConfigChange('subject_template', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
                placeholder="Alert: {{condition_type}} triggered on {{camera_name}}"
              />
              <p className="mt-1 text-xs text-gray-500">
                Available variables: {{condition_type}}, {{camera_name}}, {{timestamp}}
              </p>
            </div>
            
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email Body Template
              </label>
              <textarea
                value={formData.notification_config.body_template || ''}
                onChange={(e) => handleNotificationConfigChange('body_template', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
                rows={3}
                placeholder="A {{condition_type}} condition was triggered on camera {{camera_name}} at {{timestamp}}."
              />
              <p className="mt-1 text-xs text-gray-500">
                Available variables: {{condition_type}}, {{camera_name}}, {{timestamp}}, {{trigger_name}}
              </p>
            </div>
            
            <div className="flex items-center">
              <input
                type="checkbox"
                id="include_snapshot"
                checked={formData.notification_config.include_snapshot}
                onChange={(e) => handleNotificationConfigChange('include_snapshot', e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="include_snapshot" className="ml-2 text-sm text-gray-700">
                Include snapshot image in email
              </label>
            </div>
          </div>
        );
      
      case NotificationType.TELEGRAM:
        return (
          <div>
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Telegram Chat IDs
              </label>
              {formData.notification_config.chat_ids?.map((chatId, index) => (
                <div key={index} className="flex items-center mb-2">
                  <input
                    type="text"
                    value={chatId}
                    onChange={(e) => handleChatIdsChange(index, e.target.value)}
                    className={`flex-grow px-3 py-2 border ${
                      errors.chat_ids ? 'border-red-500' : 'border-gray-300'
                    } rounded-md mr-2`}
                    placeholder="123456789"
                  />
                  <button
                    type="button"
                    onClick={() => removeChatId(index)}
                    className="text-red-500 hover:text-red-700"
                    disabled={formData.notification_config.chat_ids.length === 1}
                  >
                    <X size={18} />
                  </button>
                </div>
              ))}
              {errors.chat_ids && <p className="mt-0 mb-2 text-sm text-red-500">{errors.chat_ids}</p>}
              <button
                type="button"
                onClick={addChatId}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                + Add another chat ID
              </button>
            </div>
            
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Message Template
              </label>
              <textarea
                value={formData.notification_config.message_template || ''}
                onChange={(e) => handleNotificationConfigChange('message_template', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
                rows={3}
                placeholder="Alert: {{condition_type}} triggered on {{camera_name}} at {{timestamp}}"
              />
              <p className="mt-1 text-xs text-gray-500">
                Available variables: {{condition_type}}, {{camera_name}}, {{timestamp}}, {{trigger_name}}
              </p>
            </div>
            
            <div className="flex items-center">
              <input
                type="checkbox"
                id="include_snapshot_telegram"
                checked={formData.notification_config.include_snapshot}
                onChange={(e) => handleNotificationConfigChange('include_snapshot', e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="include_snapshot_telegram" className="ml-2 text-sm text-gray-700">
                Include snapshot image in message
              </label>
            </div>
          </div>
        );
      
      case NotificationType.WEBHOOK:
        return (
          <div>
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Webhook URL
              </label>
              <input
                type="url"
                value={formData.notification_config.url || ''}
                onChange={(e) => handleNotificationConfigChange('url', e.target.value)}
                className={`w-full px-3 py-2 border ${
                  errors.webhook_url ? 'border-red-500' : 'border-gray-300'
                } rounded-md`}
                placeholder="https://example.com/webhook"
              />
              {errors.webhook_url && <p className="mt-1 text-sm text-red-500">{errors.webhook_url}</p>}
            </div>
            
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Headers (JSON)
              </label>
              <textarea
                value={JSON.stringify(formData.notification_config.headers || {}, null, 2)}
                onChange={(e) => {
                  try {
                    const headers = JSON.parse(e.target.value);
                    handleNotificationConfigChange('headers', headers);
                  } catch (error) {
                    // Don't update if invalid JSON
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
                rows={3}
                placeholder='{ "Authorization": "Bearer token", "Content-Type": "application/json" }'
              />
            </div>
            
            <div className="flex items-center">
              <input
                type="checkbox"
                id="include_snapshot_webhook"
                checked={formData.notification_config.include_snapshot}
                onChange={(e) => handleNotificationConfigChange('include_snapshot', e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              <label htmlFor="include_snapshot_webhook" className="ml-2 text-sm text-gray-700">
                Include snapshot (base64 encoded) in request
              </label>
            </div>
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
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
              value={formData.description}
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
          {renderConditionParams()}
          
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
          {renderNotificationConfig()}
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