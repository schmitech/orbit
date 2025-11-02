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
  'Chat & Messaging': [
    'MessageSquare', 'MessageCircle', 'MessageCircleMore', 'MessageSquareText', 
    'MessageSquareDots', 'Send', 'Mail', 'Phone'
  ],
  'Help & Support': [
    'HelpCircle', 'Info', 'Lightbulb', 'Headphones', 'LifeBuoy'
  ],
  'AI & Bot': [
    'Bot', 'Brain', 'Sparkles', 'Zap', 'Cpu2'
  ],
  'People & Service': [
    'User', 'Users', 'UserRound', 'Smile', 'Heart'
  ],
  'Business Types': [
    'PawPrint', 'Dog', 'Cat', 'Bird', 'Fish', // Animal shelter
    'ShoppingCart', 'ShoppingBag', 'Store', // Retail
    'Stethoscope', 'Pill', 'Hospital', // Healthcare
    'GraduationCap', 'BookOpen', 'Library', // Education
    'Utensils', 'Coffee', 'Pizza', // Food & Restaurant
    'Briefcase', 'Building', 'Building2', // Business
    'Plane', 'Hotel', 'MapPin', // Travel
    'DollarSign', 'CreditCard', 'Wallet', // Finance
    'Gavel', 'Scale', // Legal
    'Hammer', 'Wrench', 'HardHat', // Construction
    'Palette', 'PaintBrush', 'Camera' // Creative
  ],
  'General': [
    'Star', 'Bell', 'Settings', 'Home', 'Play'
  ]
};

// Simple SVG icon component for preview
const IconPreview: React.FC<{ iconName: string; className?: string }> = ({ iconName, className = "w-5 h-5" }) => {
  const iconPaths: Record<string, string> = {
    // Chat & Messaging
    'MessageSquare': 'M14 9a2 2 0 0 1-2 2H6l-4 4V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2z M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1',
    'MessageCircle': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    'MessageCircleMore': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M12 12h.01 M16 12h.01 M8 12h.01',
    'MessageSquareText': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M13 8H7 M17 12H7',
    'MessageSquareDots': 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M12 11h.01 M16 11h.01 M8 11h.01',
    'Send': 'M22 2 11 13 M22 2l-7 20-4-9-9-4 20-7z',
    'Mail': 'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z M22 6l-10 7L2 6',
    'Phone': 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z',
    
    // Help & Support
    'HelpCircle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3 M12 17h.01',
    'Info': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 16v-4 M12 8h.01',
    'Lightbulb': 'M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5 M9 18h6 M10 22h4',
    'Headphones': 'M3 12v7a3 3 0 0 0 3 3h3v-8H6a3 3 0 0 0-3 3z M21 12v7a3 3 0 0 1-3 3h-3v-8h3a3 3 0 0 1 3 3z M3 12a9 9 0 0 1 18 0',
    'LifeBuoy': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 8c2.209 0 4 1.791 4 4s-1.791 4-4 4-4-1.791-4-4 1.791-4 4-4z M4.93 4.93l4.24 4.24 M14.83 14.83l4.24 4.24 M14.83 9.17l4.24-4.24 M9.17 14.83l-4.24 4.24',
    
    // AI & Bot
    'Bot': 'M12 8V4H8 M4 8h16v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8z M2 14h2 M20 14h2 M15 13v2 M9 13v2',
    'Brain': 'M12 4.5a2.5 2.5 0 0 0-4.96-.46 2.5 2.5 0 0 0-1.98 3 2.5 2.5 0 0 0-1.32 4.24 3 3 0 0 0 .34 5.58 2.5 2.5 0 0 0 2.96 3.08A2.5 2.5 0 0 0 9.5 22c1.05 0 2.05-.25 2.96-.73A2.5 2.5 0 0 0 16.5 22c1.05 0 2.05-.25 2.96-.73a2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 12 4.5z',
    'Sparkles': 'M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.582a.5.5 0 0 1 0 .962L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z',
    'Zap': 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    'Cpu2': 'M4 4h16v16H4z M9 9h6v6H9z M9 1v6 M15 1v6 M9 17v6 M15 17v6 M1 9h6 M17 9h6 M1 15h6 M17 15h6',
    
    // People & Service
    'User': 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2 M12 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z',
    'Users': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
    'UserRound': 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    'Smile': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M8 14s1.5 2 4 2 4-2 4-2 M9 9h.01 M15 9h.01',
    'Heart': 'M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z',
    
    // General
    'Star': 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
    'Bell': 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0',
    'Settings': 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    'Home': 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10',
    'Play': 'M5 3l14 9-14 9z'
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
        <h3 className="text-sm font-medium text-gray-900 mb-4">Theme Collection</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {Object.entries(themes).map(([key, theme]) => (
            <button
              key={key}
              onClick={() => onApplyTheme(key as keyof typeof themes)}
              className={`relative group overflow-hidden rounded-xl transition-all duration-300 ${
                selectedTheme === key
                  ? 'ring-2 ring-indigo-500 ring-offset-2 shadow-lg transform scale-105'
                  : 'hover:shadow-xl hover:transform hover:scale-105'
              }`}
            >
              <div 
                className="h-32 w-full relative border border-gray-200"
                style={{ 
                  background: theme.colors.inputBackground || theme.colors.questionsBackground
                }}
              >
                {/* Chat Header */}
                <div 
                  className="absolute top-0 left-0 right-0 h-8 flex items-center px-3 shadow-sm"
                  style={{ background: theme.colors.primary }}
                >
                  <div className="flex items-center space-x-2">
                    <div className="w-2 h-2 rounded-full bg-white/30"></div>
                    <div 
                      className="text-[10px] font-medium"
                      style={{ color: theme.colors.textInverse || '#ffffff' }}
                    >
                      Chat Support
                    </div>
                  </div>
                </div>
                
                {/* Chat Messages Preview */}
                <div className="absolute top-10 left-2 right-2 space-y-2">
                  {/* Assistant Message */}
                  <div className="flex items-start space-x-1">
                    <div 
                      className="rounded-lg px-2 py-1 max-w-[70%]"
                      style={{ 
                        background: theme.colors.assistantBubble || '#f3f4f6',
                      }}
                    >
                      <div 
                        className="text-[9px] leading-tight"
                        style={{ color: theme.colors.assistantText || theme.colors.textPrimary }}
                      >
                        Hello! How can I help?
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Input Area */}
                <div 
                  className="absolute bottom-0 left-0 right-0 h-7 border-t flex items-center px-2"
                  style={{ 
                    borderColor: theme.colors.secondary,
                    background: theme.colors.inputBackground || theme.colors.questionsBackground
                  }}
                >
                  <div className="flex-1 flex items-center">
                    <div 
                      className="text-[8px]"
                      style={{ color: theme.colors.textSecondary }}
                    >
                      Type a message...
                    </div>
                  </div>
                  <div 
                    className="w-4 h-4 rounded flex items-center justify-center"
                    style={{ background: theme.colors.secondary }}
                  >
                    <svg className="w-2 h-2 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                    </svg>
                  </div>
                </div>
              </div>
              <div className="p-3 bg-white border-t border-gray-100">
                <span className="text-sm font-semibold text-gray-800 block">{theme.name}</span>
                <span className="text-xs text-gray-500 mt-1 block">
                  {key === 'nebula' && 'Deep blue with soft accents'}
                  {key === 'ocean' && 'Sky blue with gentle tones'}
                  {key === 'sage' && 'Forest green with natural feel'}
                  {key === 'twilight' && 'Dark teal with subtle highlights'}
                  {key === 'lavender' && 'Soft purple with gentle warmth'}
                  {key === 'midnight' && 'Dark blue with vibrant accents'}
                  {key === 'obsidian' && 'Professional slate gray'}
                  {key === 'carbon' && 'Pure black with clean lines'}
                  {key === 'sapphire' && 'Bright cyan with fresh energy'}
                  {!['nebula', 'ocean', 'sage', 'twilight', 'lavender', 'midnight', 'obsidian', 'carbon', 'sapphire'].includes(key) && 'Custom theme'}
                </span>
              </div>
              {selectedTheme === key && (
                <div className="absolute top-2 right-2 bg-indigo-500 text-white rounded-full p-1 shadow-md">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
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
              { key: 'primary', label: 'Header & Minimized Button Background' },
              { key: 'secondary', label: 'Input Border & Send Button' },
              { key: 'questionsBackground', label: 'Suggested Questions Background' },
              { key: 'inputBackground', label: 'Chat Window Background' },
              { key: 'highlightedBackground', label: 'Suggested Questions Highlighted Background' }
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
              { key: 'textInverse', label: 'Header' },
              { key: 'textPrimary', label: 'Title' },
              { key: 'textSecondary', label: 'Description' },
              { key: 'suggestedText', label: 'Suggested Questions' }
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
              { key: 'userBubble', label: 'User Bubble Background' },
              { key: 'userText', label: 'User Text Color' },
              { key: 'assistantBubble', label: 'Assistant Bubble Background' },
              { key: 'assistantText', label: 'Assistant Text Color' }
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
