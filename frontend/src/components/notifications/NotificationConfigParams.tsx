// src/components/notifications/NotificationConfigParams.tsx
import React from 'react';
import { X } from 'lucide-react';
import { NotificationType } from '../../types/notification';
import { NotificationConfigProps } from './types/notificationFormTypes';

const NotificationConfigParams: React.FC<NotificationConfigProps> = ({
  notificationType,
  notificationConfig,
  onChange,
  errors,
  isSubmitting
}) => {
  // Email-specific handlers
  const handleRecipientsChange = (index: number, value: string) => {
    const recipients = [...(notificationConfig.recipients || [''])];
    recipients[index] = value;
    onChange('recipients', recipients);
  };

  const addRecipient = () => {
    const recipients = [...(notificationConfig.recipients || [''])];
    recipients.push('');
    onChange('recipients', recipients);
  };

  const removeRecipient = (index: number) => {
    const recipients = [...(notificationConfig.recipients || [''])];
    recipients.splice(index, 1);
    onChange('recipients', recipients);
  };

  // Telegram-specific handlers
  const handleChatIdsChange = (index: number, value: string) => {
    const chatIds = [...(notificationConfig.chat_ids || [''])];
    chatIds[index] = value;
    onChange('chat_ids', chatIds);
  };

  const addChatId = () => {
    const chatIds = [...(notificationConfig.chat_ids || [''])];
    chatIds.push('');
    onChange('chat_ids', chatIds);
  };

  const removeChatId = (index: number) => {
    const chatIds = [...(notificationConfig.chat_ids || [''])];
    chatIds.splice(index, 1);
    onChange('chat_ids', chatIds);
  };

  switch (notificationType) {
    case NotificationType.EMAIL:
      return (
        <div>
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email Recipients
            </label>
            {notificationConfig.recipients?.map((email: string, index: number) => (
              <div key={index} className="flex items-center mb-2">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => handleRecipientsChange(index, e.target.value)}
                  className={`flex-grow px-3 py-2 border ${
                    errors.recipients ? 'border-red-500' : 'border-gray-300'
                  } rounded-md mr-2`}
                  placeholder="email@example.com"
                  disabled={isSubmitting}
                />
                <button
                  type="button"
                  onClick={() => removeRecipient(index)}
                  className="text-red-500 hover:text-red-700"
                  disabled={notificationConfig.recipients.length <= 1 || isSubmitting}
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
              disabled={isSubmitting}
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
              value={notificationConfig.subject_template || ''}
              onChange={(e) => onChange('subject_template', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="Alert: {{condition_type}} triggered on {{camera_name}}"
              disabled={isSubmitting}
            />
            <p className="mt-1 text-xs text-gray-500">
              Available variables: {`{{condition_type}}, {{camera_name}}, {{timestamp}}`}
            </p>
          </div>
          
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email Body Template
            </label>
            <textarea
              value={notificationConfig.body_template || ''}
              onChange={(e) => onChange('body_template', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows={3}
              placeholder="A {{condition_type}} condition was triggered on camera {{camera_name}} at {{timestamp}}."
              disabled={isSubmitting}
            />
            <p className="mt-1 text-xs text-gray-500">
              Available variables: {`{{condition_type}}, {{camera_name}}, {{timestamp}}, {{trigger_name}}`}
            </p>
          </div>
          
          <div className="flex items-center">
            <input
              type="checkbox"
              id="include_snapshot"
              checked={notificationConfig.include_snapshot}
              onChange={(e) => onChange('include_snapshot', e.target.checked)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
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
            {notificationConfig.chat_ids?.map((chatId: string, index: number) => (
              <div key={index} className="flex items-center mb-2">
                <input
                  type="text"
                  value={chatId}
                  onChange={(e) => handleChatIdsChange(index, e.target.value)}
                  className={`flex-grow px-3 py-2 border ${
                    errors.chat_ids ? 'border-red-500' : 'border-gray-300'
                  } rounded-md mr-2`}
                  placeholder="123456789"
                  disabled={isSubmitting}
                />
                <button
                  type="button"
                  onClick={() => removeChatId(index)}
                  className="text-red-500 hover:text-red-700"
                  disabled={notificationConfig.chat_ids.length <= 1 || isSubmitting}
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
              disabled={isSubmitting}
            >
              + Add another chat ID
            </button>
          </div>
          
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Message Template
            </label>
            <textarea
              value={notificationConfig.message_template || ''}
              onChange={(e) => onChange('message_template', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              rows={3}
              placeholder="Alert: {{condition_type}} triggered on {{camera_name}} at {{timestamp}}"
              disabled={isSubmitting}
            />
            <p className="mt-1 text-xs text-gray-500">
              Available variables: {`{{condition_type}}, {{camera_name}}, {{timestamp}}, {{trigger_name}}`}
            </p>
          </div>
          
          <div className="flex items-center">
            <input
              type="checkbox"
              id="include_snapshot_telegram"
              checked={notificationConfig.include_snapshot}
              onChange={(e) => onChange('include_snapshot', e.target.checked)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
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
              value={notificationConfig.url || ''}
              onChange={(e) => onChange('url', e.target.value)}
              className={`w-full px-3 py-2 border ${
                errors.webhook_url ? 'border-red-500' : 'border-gray-300'
              } rounded-md`}
              placeholder="https://example.com/webhook"
              disabled={isSubmitting}
            />
            {errors.webhook_url && <p className="mt-1 text-sm text-red-500">{errors.webhook_url}</p>}
          </div>
          
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Headers (JSON)
            </label>
            <textarea
              value={JSON.stringify(notificationConfig.headers || {}, null, 2)}
              onChange={(e) => {
                try {
                  const headers = JSON.parse(e.target.value);
                  onChange('headers', headers);
                } catch (error) {
                  // Don't update if invalid JSON
                }
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
              rows={3}
              placeholder='{ "Authorization": "Bearer token", "Content-Type": "application/json" }'
              disabled={isSubmitting}
            />
          </div>
          
          <div className="flex items-center">
            <input
              type="checkbox"
              id="include_snapshot_webhook"
              checked={notificationConfig.include_snapshot}
              onChange={(e) => onChange('include_snapshot', e.target.checked)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              disabled={isSubmitting}
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

export default NotificationConfigParams;