import { useState, useEffect } from 'react';
import { X, Monitor, Sun, Moon, Palette, Type, Volume2, Package, Trash2, AlertTriangle } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import { useSettings } from '../contexts/SettingsContext';
import { getVersionInfo } from '../utils/version';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Settings({ isOpen, onClose }: SettingsProps) {
  const { theme, updateTheme } = useTheme();
  const { settings, updateSettings } = useSettings();
  const [versionInfo, setVersionInfo] = useState<{
    appVersion: string;
    apiVersion: string;
    isLocalApi: boolean;
  } | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  useEffect(() => {
    if (isOpen) {
      getVersionInfo().then(setVersionInfo);
    }
  }, [isOpen]);

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

  const handleSoundEffectsToggle = () => {
    updateSettings({ soundEnabled: !settings.soundEnabled });
  };

  const handleResetApplication = () => {
    // Clear all localStorage data
    localStorage.clear();
    // Reload the page to reset all state
    window.location.reload();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-600">
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
        <div className="flex-1 min-h-0 p-6 space-y-6 overflow-y-auto">
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

            {/* Sound Effects */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Volume2 className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                <div>
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Sound Effects
                  </label>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Play sounds for notifications and events
                  </p>
                </div>
              </div>
              <button 
                onClick={handleSoundEffectsToggle}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.soundEnabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    settings.soundEnabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Data Management */}
          <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-600">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Trash2 className="w-5 h-5" />
              Data Management
            </h3>
            
            <div className="space-y-2">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Clear all application data including conversations, settings, and API configurations. This action cannot be undone.
              </p>
              {!showResetConfirm ? (
                <button
                  onClick={() => setShowResetConfirm(true)}
                  className="w-full px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  Reset Application
                </button>
              ) : (
                <div className="space-y-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-red-800 dark:text-red-300 mb-1">
                        Are you sure?
                      </p>
                      <p className="text-xs text-red-700 dark:text-red-400">
                        This will delete all conversations, settings, API keys, and other stored data. The page will reload automatically.
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleResetApplication}
                      className="flex-1 px-4 py-2 text-sm font-medium text-white bg-red-600 dark:bg-red-700 rounded-lg hover:bg-red-700 dark:hover:bg-red-600 transition-colors"
                    >
                      Yes, Reset Everything
                    </button>
                    <button
                      onClick={() => setShowResetConfirm(false)}
                      className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* About */}
          <div className="space-y-2 pt-4 border-t border-gray-200 dark:border-gray-600">
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
              <Package className="w-4 h-4" />
              About
            </h3>
            <div className="space-y-1">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                AI Chat Application v{versionInfo?.appVersion || '1.0.0'}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                API Package: @schmitech/chatbot-api v{versionInfo?.apiVersion || '^0.5.3'}
                {versionInfo?.isLocalApi && (
                  <span className="ml-1 px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
                    Local
                  </span>
                )}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Built with React, TypeScript, and Tailwind CSS
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}