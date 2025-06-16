import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface SectionToggleProps {
  title: string;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  className?: string;
}

export const SectionToggle: React.FC<SectionToggleProps> = ({
  title,
  isExpanded,
  onToggle,
  children,
  className = ""
}) => {
  return (
    <div className={`border border-gray-200 rounded-lg ${className}`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50"
      >
        <span className="font-medium text-gray-900">{title}</span>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-gray-500" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-500" />
        )}
      </button>
      {isExpanded && (
        <div className="p-4 pt-0">
          {children}
        </div>
      )}
    </div>
  );
};