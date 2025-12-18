import React from 'react';
import type { TabType } from '../types/widget.types';
import { WIDGET_CONFIG } from '../utils/widget-config';

interface Tab {
  id: TabType;
  label: string;
}

interface TabNavigationProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  className?: string;
}

export const TabNavigation: React.FC<TabNavigationProps> = ({
  activeTab,
  onTabChange,
  className = ""
}) => {
  const baseTabs: Tab[] = [
    { id: 'theme', label: 'Theme' },
    { id: 'content', label: 'Content' },
    { id: 'code', label: 'Code' }
  ];

  const promptTab: Tab = { id: 'prompt', label: 'Prompt' };
  
  const tabs: Tab[] = WIDGET_CONFIG.promptEnabled 
    ? [...baseTabs.slice(0, 2), promptTab, ...baseTabs.slice(2)]
    : baseTabs;

  return (
    <div className={`border-b border-gray-200 ${className}`}>
      <nav className="flex -mb-px">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
};