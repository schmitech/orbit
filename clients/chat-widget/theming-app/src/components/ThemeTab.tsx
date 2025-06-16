import React from 'react';
import type { CustomColors, ExpandedSections } from '../types/widget.types';
import { themes } from '../constants/themes';
import { ColorPicker } from './ColorPicker';
import { SectionToggle } from './SectionToggle';

interface ThemeTabProps {
  selectedTheme: string;
  customColors: CustomColors;
  expandedSections: ExpandedSections;
  onApplyTheme: (themeName: keyof typeof themes) => void;
  onUpdateColor: (colorKey: keyof CustomColors, value: string) => void;
  onToggleSection: (section: keyof ExpandedSections) => void;
}

export const ThemeTab: React.FC<ThemeTabProps> = ({
  selectedTheme,
  customColors,
  expandedSections,
  onApplyTheme,
  onUpdateColor,
  onToggleSection,
}) => {
  return (
    <div className="space-y-6">
      {/* Theme Presets */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">Theme Presets</h3>
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(themes).map(([key, theme]) => (
            <button
              key={key}
              onClick={() => onApplyTheme(key as keyof typeof themes)}
              className={`relative p-3 rounded-lg border-2 transition-all ${
                selectedTheme === key
                  ? 'border-indigo-500 bg-indigo-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div 
                className="flex items-center justify-center h-8 rounded mb-2"
                style={{ 
                  background: `linear-gradient(135deg, ${theme.colors.primary} 0%, ${theme.colors.secondary} 100%)` 
                }}
              />
              <span className="text-sm font-medium text-gray-700">{theme.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Color Customization */}
      <div className="space-y-4">
        {/* Main Colors */}
        <SectionToggle
          title="Main Colors"
          isExpanded={expandedSections.mainColors}
          onToggle={() => onToggleSection('mainColors')}
        >
          <div className="space-y-3">
            {[
              { key: 'primary', label: 'Primary Color' },
              { key: 'secondary', label: 'Secondary Color' },
              { key: 'background', label: 'Background' },
              { key: 'textPrimary', label: 'Text Color' }
            ].map(({ key, label }) => (
              <ColorPicker
                key={key}
                label={label}
                value={customColors[key]}
                onChange={(value) => onUpdateColor(key as keyof CustomColors, value)}
              />
            ))}
          </div>
        </SectionToggle>

        {/* Message Bubbles */}
        <SectionToggle
          title="Message Bubbles"
          isExpanded={expandedSections.messageBubbles}
          onToggle={() => onToggleSection('messageBubbles')}
        >
          <div className="space-y-3">
            {[
              { key: 'userBubble', label: 'User Bubble' },
              { key: 'assistantBubble', label: 'Assistant Bubble' },
              { key: 'userText', label: 'User Text' }
            ].map(({ key, label }) => (
              <ColorPicker
                key={key}
                label={label}
                value={customColors[key]}
                onChange={(value) => onUpdateColor(key as keyof CustomColors, value)}
              />
            ))}
          </div>
        </SectionToggle>
      </div>
    </div>
  );
};