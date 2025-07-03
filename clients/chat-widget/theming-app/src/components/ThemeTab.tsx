import React, { useState } from 'react';
import type { CustomColors, ExpandedSections } from '../types/widget.types';
import { themes } from '../constants/themes';
import { ColorPicker } from './ColorPicker';
import { SectionToggle } from './SectionToggle';
import { ChevronDown } from 'lucide-react';

interface ThemeTabProps {
  selectedTheme: string;
  customColors: CustomColors;
  expandedSections: ExpandedSections;
  onApplyTheme: (themeName: keyof typeof themes) => void;
  onUpdateColor: (colorKey: keyof CustomColors, value: string) => void;
  onToggleSection: (section: keyof ExpandedSections) => void;
}

// Icon categories for better UX
const iconCategories = {
  'Chat & Communication': [
    'MessageSquare', 'MessageCircle', 'MessageCircleMore', 'MessageSquareText', 
    'MessageSquareDots', 'Send', 'Reply'
  ],
  'Help & Info': [
    'HelpCircle', 'Info', 'Lightbulb', 'Sparkles'
  ],
  'AI & Technology': [
    'Bot', 'Brain', 'Cpu', 'Chip', 'Zap', 'Target'
  ],
  'People & Users': [
    'User', 'Users', 'UserCheck', 'UserPlus', 'UserMinus'
  ],
  'Search & Discovery': [
    'Search', 'Filter'
  ]
};

// Simple SVG icon component for preview
const IconPreview: React.FC<{ iconName: string; className?: string }> = ({ iconName, className = "w-5 h-5" }) => {
  const iconPaths: Record<string, string> = {
    'MessageSquare': 'M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1',
    'MessageCircle': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    'MessageCircleMore': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M12 12h.01 M16 12h.01 M8 12h.01',
    'MessageSquareText': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M13 8H7 M17 12H7',
    'MessageSquareDots': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M12 11h.01 M16 11h.01 M8 11h.01',
    'Send': 'M22 3L12 13l-10-10z',
    'Reply': 'M9 17l-4-4 4-4 M20 18v-2a4 4 0 0 0-4-4H4',
    'HelpCircle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3 M12 17h.01',
    'Info': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 16v-4 M12 8h.01',
    'Lightbulb': 'M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5 M9 18h6 M10 22h4',
    'Sparkles': 'M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.582a.5.5 0 0 1 0 .962L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z',
    'Bot': 'M12 8V4H8 M4 8h16v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8z M2 14h2 M20 14h2 M15 13v2 M9 13v2',
    'Brain': 'M12 4.5a2.5 2.5 0 0 0-4.96-.46 2.5 2.5 0 0 0-1.98 3 2.5 2.5 0 0 0-1.32 4.24 3 3 0 0 0 .34 5.58 2.5 2.5 0 0 0 2.96 3.08A2.5 2.5 0 0 0 9.5 22c1.05 0 2.05-.25 2.96-.73A2.5 2.5 0 0 0 16.5 22c1.05 0 2.05-.25 2.96-.73a2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 12 4.5z',
    'Cpu': 'M4 4h16v16H4z M9 9h6v6H9z M9 1v2 M15 1v2 M9 21v2 M15 21v2 M1 9h2 M1 15h2 M21 9h2 M21 15h2',
    'Chip': 'M6 6h12v12H6z M4 10v4 M20 10v4 M10 4h4 M10 20h4',
    'Zap': 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    'Target': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 18c3.314 0 6-2.686 6-6s-2.686-6-6-6-6 2.686-6 6 2.686 6 6 6z M12 14c1.105 0 2-.895 2-2s-.895-2-2-2-2 .895-2 2 .895 2 2 2z',
    'User': 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2 M12 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z',
    'Users': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
    'UserCheck': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z M16 11l2 2 4-4',
    'UserPlus': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z M20 8v6 M23 11h-6',
    'UserMinus': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z M23 11h-6',
    'Search': 'M11 19c4.418 0 8-3.582 8-8s-3.582-8-8-8-8 3.582-8 8 3.582 8 8 8z M21 21l-4.35-4.35',
    'Filter': 'M22 3H2l8 9.46V19l4 2v-8.54L22 3z'
  };

  const path = iconPaths[iconName] || iconPaths['MessageSquare'];
  
  return (
    <svg 
      className={className} 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    >
      {path.split(' M ').map((pathPart, index) => (
        <path key={index} d={index === 0 ? pathPart : `M ${pathPart}`} />
      ))}
    </svg>
  );
};

const IconDropdown: React.FC<{
  value: string;
  onChange: (value: string) => void;
}> = ({ value, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 border border-gray-300 rounded-md bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
      >
        <div className="flex items-center space-x-2">
          <IconPreview iconName={value} className="w-5 h-5 text-gray-600" />
          <span className="text-sm text-gray-700">{value}</span>
        </div>
        <ChevronDown className={`w-4 h-4 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-52 overflow-hidden">
          {/* Icons List */}
          <div className="max-h-40 overflow-y-auto">
            {Object.entries(iconCategories).map(([category, icons]) => (
              <div key={category}>
                <div className="px-3 py-2 bg-gray-50 border-b border-gray-200">
                  <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider">{category}</h4>
                </div>
                <div className="p-2">
                  {icons.map((icon) => (
                    <button
                      key={icon}
                      onClick={() => {
                        onChange(icon);
                        setIsOpen(false);
                      }}
                      className={`w-full flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-gray-100 transition-colors ${
                        value === icon ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700'
                      }`}
                    >
                      <IconPreview iconName={icon} className="w-4 h-4" />
                      <span className="text-sm font-medium">{icon}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

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
              { key: 'primary', label: 'Primary Color (Header & Minimized Button)' },
              { key: 'secondary', label: 'Secondary Color (Send Button)' },
              { key: 'background', label: 'Background Color' }
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

        {/* Text Colors */}
        <SectionToggle
          title="Text Colors"
          isExpanded={expandedSections.textColors}
          onToggle={() => onToggleSection('textColors')}
        >
          <div className="space-y-3">
            {[
              { key: 'textPrimary', label: 'Primary Text Color' },
              { key: 'textSecondary', label: 'Secondary Text Color' },
              { key: 'textInverse', label: 'Inverse Text Color' }
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
              { key: 'userBubble', label: 'User Bubble Color' },
              { key: 'userText', label: 'User Text Color' },
              { key: 'assistantBubble', label: 'Assistant Bubble Color' }
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

        {/* Input Field */}
        <SectionToggle
          title="Input Field"
          isExpanded={expandedSections.inputField}
          onToggle={() => onToggleSection('inputField')}
        >
          <div className="space-y-3">
            {[
              { key: 'inputBackground', label: 'Input Background Color' },
              { key: 'inputBorder', label: 'Input Border Color' }
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

        {/* Suggested Questions */}
        <SectionToggle
          title="Suggested Questions"
          isExpanded={expandedSections.suggestedQuestions}
          onToggle={() => onToggleSection('suggestedQuestions')}
        >
          <div className="space-y-3">
            {[
              { key: 'suggestedBackground', label: 'Background Color' },
              { key: 'suggestedHoverBackground', label: 'Hover Background Color' },
              { key: 'suggestedText', label: 'Text Color' }
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

        {/* Icon Selection */}
        <SectionToggle
          title="Icon Selection"
          isExpanded={expandedSections.iconSelection}
          onToggle={() => onToggleSection('iconSelection')}
        >
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Chat Button Icon</label>
              <IconDropdown
                value={customColors.iconName}
                onChange={(value) => onUpdateColor('iconName', value)}
              />
            </div>
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="flex items-center space-x-2 mb-2">
                <IconPreview iconName={customColors.iconName} className="w-6 h-6 text-indigo-600" />
                <span className="text-sm font-medium text-gray-700">Preview: {customColors.iconName}</span>
              </div>
              <p className="text-xs text-gray-600">
                This icon will appear on the chat button. Choose from categorized icons or search for a specific one.
              </p>
            </div>
          </div>
        </SectionToggle>

        {/* Chat Button */}
        <SectionToggle
          title="Chat Button"
          isExpanded={expandedSections.chatButton}
          onToggle={() => onToggleSection('chatButton')}
        >
          <div className="space-y-3">
            {[
              { key: 'chatButtonBg', label: 'Background Color' },
              { key: 'chatButtonHover', label: 'Hover Background Color' },
              { key: 'iconColor', label: 'Icon Color' },
              { key: 'iconBorderColor', label: 'Icon Border Color' },
              { key: 'buttonBorderColor', label: 'Button Border Color' }
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