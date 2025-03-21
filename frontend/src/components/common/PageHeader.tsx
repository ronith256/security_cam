// src/components/common/PageHeader.tsx
import React from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, actions }) => {
  return (
    <div className="mb-6 flex justify-between items-center">
      <div>
        <h1 className="text-3xl font-bold text-gray-800">{title}</h1>
        {subtitle && <p className="mt-1 text-gray-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center space-x-2">{actions}</div>}
    </div>
  );
};

export default PageHeader;