// src/components/notifications/NotificationConditionParams.tsx
import React from "react";
import { TriggerConditionType } from "../../types/notification";
import { ConditionParamsProps } from "./types/notificationFormTypes";

const NotificationConditionParams: React.FC<ConditionParamsProps> = ({
  conditionType,
  conditionParams,
  onChange,
  errors,
  persons,
  templates,
  isSubmitting,
}) => {
  switch (conditionType) {
    case TriggerConditionType.OCCUPANCY_ABOVE:
    case TriggerConditionType.OCCUPANCY_BELOW:
      return (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Occupancy Threshold
          </label>
          <input
            type="number"
            value={conditionParams.threshold || 0}
            onChange={(e) => onChange("threshold", parseInt(e.target.value))}
            className={`w-full px-3 py-2 border rounded-md ${
              errors.threshold ? "border-red-500" : "border-gray-300"
            }`}
            min="1"
            disabled={isSubmitting}
          />
          {errors.threshold && (
            <p className="mt-1 text-sm text-red-500">{errors.threshold}</p>
          )}
          <p className="mt-1 text-sm text-gray-500">
            Trigger when the number of people is{" "}
            {conditionType === TriggerConditionType.OCCUPANCY_ABOVE
              ? "above"
              : "below"}{" "}
            this threshold
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
            value={conditionParams.person_id || ""}
            onChange={(e) =>
              onChange(
                "person_id",
                e.target.value ? parseInt(e.target.value) : undefined
              )
            }
            className={`w-full px-3 py-2 border rounded-md ${
              errors.person_id ? "border-red-500" : "border-gray-300"
            }`}
            disabled={isSubmitting}
          >
            <option value="">Select a person</option>
            {persons?.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
          {errors.person_id && (
            <p className="mt-1 text-sm text-red-500">{errors.person_id}</p>
          )}

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
                value={conditionParams.confidence_threshold || 0.6}
                onChange={(e) =>
                  onChange("confidence_threshold", parseFloat(e.target.value))
                }
                className="w-full"
                disabled={isSubmitting}
              />
              <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
                {((conditionParams.confidence_threshold || 0.6) * 100).toFixed(
                  0
                )}
                %
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
              value={conditionParams.confidence_threshold || 0.6}
              onChange={(e) =>
                onChange("confidence_threshold", parseFloat(e.target.value))
              }
              className="w-full"
              disabled={isSubmitting}
            />
            <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
              {((conditionParams.confidence_threshold || 0.6) * 100).toFixed(0)}
              %
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
            value={conditionParams.template_id || ""}
            onChange={(e) =>
              onChange(
                "template_id",
                e.target.value ? parseInt(e.target.value) : undefined
              )
            }
            className={`w-full px-3 py-2 border rounded-md ${
              errors.template_id ? "border-red-500" : "border-gray-300"
            }`}
            disabled={isSubmitting}
          >
            <option value="">Select a template</option>
            {templates?.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
          {errors.template_id && (
            <p className="mt-1 text-sm text-red-500">{errors.template_id}</p>
          )}

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
                value={conditionParams.confidence_threshold || 0.7}
                onChange={(e) =>
                  onChange("confidence_threshold", parseFloat(e.target.value))
                }
                className="w-full"
                disabled={isSubmitting}
              />
              <span className="text-sm font-medium bg-gray-100 px-2 py-1 rounded-md w-16 text-center">
                {((conditionParams.confidence_threshold || 0.7) * 100).toFixed(
                  0
                )}
                %
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
              value={conditionParams.start_time || ""}
              onChange={(e) => onChange("start_time", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              disabled={isSubmitting}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              End Time
            </label>
            <input
              type="time"
              value={conditionParams.end_time || ""}
              onChange={(e) => onChange("end_time", e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md"
              disabled={isSubmitting}
            />
          </div>
        </div>
      );

    default:
      return null;
  }
};

export default NotificationConditionParams;
