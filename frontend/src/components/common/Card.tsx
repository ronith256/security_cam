// src/components/common/Card.tsx
import React from 'react';

interface CardProps {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

const Card: React.FC<CardProps> = ({ title, subtitle, actions, children, className = '' }) => {
  return (
    <div className={`bg-white rounded-lg shadow-md overflow-hidden ${className}`}>
      {(title || actions) && (
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <div>
            {title && <h3 className="text-lg font-semibold text-gray-800">{title}</h3>}
            {subtitle && <p className="text-sm text-gray-600 mt-1">{subtitle}</p>}
          </div>
          {actions && <div>{actions}</div>}
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
};

export default Card;