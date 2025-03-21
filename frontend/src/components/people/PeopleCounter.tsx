// src/components/people/PeopleCounter.tsx
import React, { useState } from 'react';
import { ArrowUp, ArrowDown, Users, RotateCcw, Sliders } from 'lucide-react';
import Card from '../common/Card';
import Button from '../common/Button';
import { useToast } from '../../context/ToastContext';
import { resetPeopleCounter, setLinePosition } from '../../api/peopleCount';
import { useApi } from '../../hooks/useApi';

interface PeopleCounterProps {
  cameraId: number;
  entryCount: number;
  exitCount: number;
  currentCount: number;
  onReset?: () => void;
}

const PeopleCounter: React.FC<PeopleCounterProps> = ({
  cameraId,
  entryCount,
  exitCount,
  currentCount,
  onReset,
}) => {
  const [linePosition, setLinePositionValue] = useState(0.5);
  const [isPositionAdjustOpen, setIsPositionAdjustOpen] = useState(false);
  const { showToast } = useToast();

  const { execute: executeReset, isLoading: isResetting } = useApi(resetPeopleCounter, {
    onSuccess: () => {
      showToast('People counter reset successfully', 'success');
      if (onReset) onReset();
    },
  });

  const { execute: executeSetLinePosition, isLoading: isSettingLine } = useApi(
    (position: number) => setLinePosition(cameraId, position),
    {
      onSuccess: () => {
        showToast('Line position updated', 'success');
      },
    }
  );

  const handleReset = async () => {
    if (window.confirm('Are you sure you want to reset the people counter?')) {
      await executeReset(cameraId);
    }
  };

  const handleSetLinePosition = async () => {
    await executeSetLinePosition(linePosition);
    setIsPositionAdjustOpen(false);
  };

  return (
    <Card className="h-full">
      <div className="flex flex-col h-full">
        <div className="mb-4 text-center">
          <h3 className="text-xl font-semibold text-gray-800">People Counter</h3>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="text-center">
            <div className="flex justify-center mb-2">
              <div className="bg-green-100 p-2 rounded-full">
                <ArrowDown className="text-green-600" size={24} />
              </div>
            </div>
            <p className="text-sm text-gray-600">Entries</p>
            <p className="text-2xl font-bold text-green-600">{entryCount}</p>
          </div>

          <div className="text-center">
            <div className="flex justify-center mb-2">
              <div className="bg-blue-100 p-2 rounded-full">
                <Users className="text-blue-600" size={24} />
              </div>
            </div>
            <p className="text-sm text-gray-600">Current</p>
            <p className="text-2xl font-bold text-blue-600">{currentCount}</p>
          </div>

          <div className="text-center">
            <div className="flex justify-center mb-2">
              <div className="bg-red-100 p-2 rounded-full">
                <ArrowUp className="text-red-600" size={24} />
              </div>
            </div>
            <p className="text-sm text-gray-600">Exits</p>
            <p className="text-2xl font-bold text-red-600">{exitCount}</p>
          </div>
        </div>

        <div className="mt-auto">
          <div className="flex space-x-2">
            <Button
              variant="warning"
              size="sm"
              onClick={handleReset}
              isLoading={isResetting}
              icon={<RotateCcw size={16} />}
              className="flex-1"
            >
              Reset Counter
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsPositionAdjustOpen(!isPositionAdjustOpen)}
              icon={<Sliders size={16} />}
              className="flex-1"
            >
              Adjust Line
            </Button>
          </div>

          {isPositionAdjustOpen && (
            <div className="mt-4 p-3 bg-gray-50 rounded-md">
              <p className="text-sm text-gray-600 mb-2">Virtual Line Position</p>
              <div className="flex items-center space-x-2">
                <input
                  type="range"
                  min="0.1"
                  max="0.9"
                  step="0.05"
                  value={linePosition}
                  onChange={(e) => setLinePositionValue(parseFloat(e.target.value))}
                  className="flex-1"
                />
                <span className="text-sm bg-gray-200 px-2 py-1 rounded">
                  {Math.round(linePosition * 100)}%
                </span>
              </div>
              <div className="flex justify-end mt-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSetLinePosition}
                  isLoading={isSettingLine}
                >
                  Apply
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

export default PeopleCounter;