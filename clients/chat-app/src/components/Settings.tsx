import React from 'react';
import { X, Monitor, Sun, Moon, Palette, Type, Volume2, Mic } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Settings({ isOpen, onClose }: SettingsProps) {
  const { theme, updateTheme, isDark } = useTheme();

  if (!isOpen) return null;

  const handleThemeChange = (mode: 'light' | 'dark' | 'system') => {
    updateTheme({ mode });
  };

  const handleFontSizeChange = (fontSize: 'small' | 'medium' | 'large') => {
    updateTheme({ fontSize });
  };

  const handleHighContrastToggle = () => {
    updateTheme({ highContrast: !theme.highContrast });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-600">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Settings
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Theme Settings */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Palette className="w-5 h-5" />
              Appearance
            </h3>

            {/* Theme Mode */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Theme
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { value: 'light', label: 'Light', icon: Sun },
                  { value: 'dark', label: 'Dark', icon: Moon },
                  { value: 'system', label: 'System', icon: Monitor }
                ].map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    onClick={() => handleThemeChange(value as 'light' | 'dark' | 'system')}
                    className={`flex flex-col items-center gap-2 p-3 rounded-lg border-2 transition-all duration-200 ${
                      theme.mode === value
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                        : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="text-sm font-medium">{label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* High Contrast */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  High Contrast
                </label>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Improve readability with enhanced contrast
                </p>
              </div>
              <button
                onClick={handleHighContrastToggle}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  theme.highContrast ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    theme.highContrast ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Font Size */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                <Type className="w-4 h-4" />
                Font Size
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { value: 'small', label: 'Small' },
                  { value: 'medium', label: 'Medium' },
                  { value: 'large', label: 'Large' }
                ].map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => handleFontSizeChange(value as 'small' | 'medium' | 'large')}
                    className={`p-2 rounded-lg border-2 transition-colors text-center ${
                      theme.fontSize === value
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                        : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
                    }`}
                  >
                    <span className={`font-medium ${
                      value === 'small' ? 'text-sm' : 
                      value === 'large' ? 'text-lg' : 'text-base'
                    }`}>
                      {label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Chat Settings */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
              Chat Preferences
            </h3>

            {/* Voice Responses */}
            <div className="flex items-center justify-between opacity-50">
              <div className="flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                <div>
                  <label className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Voice Responses
                  </label>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    Enable text-to-speech for AI responses (Coming soon)
                  </p>
                </div>
              </div>
              <button 
                disabled
                className="relative inline-flex h-6 w-11 items-center rounded-full bg-gray-200 dark:bg-gray-600 cursor-not-allowed"
              >
                <span className="inline-block h-4 w-4 transform translate-x-1 rounded-full bg-gray-300 dark:bg-gray-500" />
              </button>
            </div>

            {/* Sound Effects */}
            <div className="flex items-center justify-between opacity-50">
              <div className="flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-gray-400 dark:text-gray-500" />
                <div>
                  <label className="text-sm font-medium text-gray-500 dark:text-gray-400">
                    Sound Effects
                  </label>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    Play sounds for notifications (Coming soon)
                  </p>
                </div>
              </div>
              <button 
                disabled
                className="relative inline-flex h-6 w-11 items-center rounded-full bg-gray-200 dark:bg-gray-600 cursor-not-allowed"
              >
                <span className="inline-block h-4 w-4 transform translate-x-1 rounded-full bg-gray-300 dark:bg-gray-500" />
              </button>
            </div>
          </div>

          {/* About */}
          <div className="space-y-2 pt-4 border-t border-gray-200 dark:border-gray-600">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              About
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              AI Chat Application v1.0.0
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Built with React, TypeScript, and Tailwind CSS
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}