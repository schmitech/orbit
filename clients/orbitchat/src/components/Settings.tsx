import { useRef, useState } from 'react';
import { X, Monitor, Sun, Moon, Palette, Volume2, Trash2, AlertTriangle } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import { useSettings } from '../contexts/SettingsContext';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { clearTokenGetter } from '../auth/tokenStore';
import { setAuthenticatedUserId, setIsAuthenticated } from '../auth/authState';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { PACKAGE_VERSION } from '../utils/version';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

const AUTH_STORAGE_KEY_PATTERNS = [
  '@@auth0spajs@@',
  'a0.spajs',
  'auth0',
  'com.auth0',
];

function isAuthStorageKey(key: string): boolean {
  const normalized = key.toLowerCase();
  return AUTH_STORAGE_KEY_PATTERNS.some(pattern => normalized.includes(pattern.toLowerCase()));
}

function removeAuthStorageKeys(storage: Storage): void {
  const keysToRemove: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key && isAuthStorageKey(key)) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach(key => storage.removeItem(key));
}

function clearStorage(storage: Storage): void {
  try {
    removeAuthStorageKeys(storage);
    storage.clear();
  } catch (error) {
    console.warn('[Settings] Failed to clear browser storage during reset.', error);
  }
}

function clearSameOriginCookies(): void {
  if (typeof document === 'undefined' || !document.cookie) return;

  const cookieDomains = new Set<string | undefined>([undefined]);
  const hostname = window.location.hostname;
  const canUseDomain = hostname && hostname !== 'localhost' && !/^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname);
  if (canUseDomain) {
    cookieDomains.add(hostname);
    cookieDomains.add(`.${hostname}`);
  }

  document.cookie.split(';').forEach((cookie) => {
    const eqPos = cookie.indexOf('=');
    const cookieName = (eqPos > -1 ? cookie.slice(0, eqPos) : cookie).trim();
    if (!cookieName) return;

    cookieDomains.forEach((domain) => {
      const domainPart = domain ? `;domain=${domain}` : '';
      document.cookie = `${cookieName}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/${domainPart}`;
    });
  });
}

function clearBrowserAuthArtifacts(): void {
  clearStorage(localStorage);
  clearStorage(sessionStorage);
  clearSameOriginCookies();
}

export function Settings({ isOpen, onClose }: SettingsProps) {
  const { theme, updateTheme } = useTheme();
  const { settings, updateSettings } = useSettings();
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const resetDialogRef = useRef<HTMLDivElement>(null);

  const handleThemeChange = (mode: 'light' | 'dark' | 'system') => {
    updateTheme({ mode });
  };

  const handleSoundEffectsToggle = () => {
    updateSettings({ soundEnabled: !settings.soundEnabled });
  };

  const openResetDialog = () => {
    setShowResetConfirm(true);
  };

  const closeResetDialog = () => {
    setShowResetConfirm(false);
  };

  const handleResetApplication = () => {
    closeResetDialog();

    // Reset in-memory auth/login state first so UI doesn't retain stale auth state.
    clearTokenGetter();
    setIsAuthenticated(false);
    setAuthenticatedUserId(null);
    useLoginPromptStore.getState().closeLoginPrompt();

    // Clear all persisted app data plus Auth0/Auth SPA cache and same-origin cookies.
    clearBrowserAuthArtifacts();

    window.location.reload();
  };

  useFocusTrap(dialogRef, { enabled: isOpen && !showResetConfirm, onEscape: onClose });
  useFocusTrap(resetDialogRef, { enabled: showResetConfirm, onEscape: closeResetDialog });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center overflow-y-auto bg-black/50 p-0 md:p-4">
      <button
        type="button"
        onClick={onClose}
        aria-label="Close settings overlay"
        className="absolute inset-0"
      />
      <div
        onClick={(event) => event.stopPropagation()}
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        tabIndex={-1}
        className="relative flex h-[100dvh] w-full max-w-none flex-col overflow-hidden bg-white shadow-2xl dark:bg-[#1a1b1e] md:h-auto md:max-h-[90vh] md:max-w-md md:rounded-2xl"
      >
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between border-b border-gray-200 px-6 pb-4 pt-[max(env(safe-area-inset-top),1rem)] dark:border-[#2d2f39] md:p-6">
          <h2 id="settings-title" className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Settings
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-[#25262f] rounded-lg transition-colors"
            aria-label="Close settings"
          >
            <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 space-y-6 overflow-y-auto px-6 pb-[max(env(safe-area-inset-bottom),1.25rem)] pt-6 md:p-6">
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
                        : 'border-gray-200 dark:border-[#2d2f39] hover:border-gray-300 dark:hover:border-[#43465a] text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="text-sm font-medium">{label}</span>
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
                role="switch"
                aria-checked={settings.soundEnabled}
                aria-label="Toggle sound effects"
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  settings.soundEnabled ? 'bg-blue-600' : 'bg-gray-200 dark:bg-[#3c3f4a]'
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
          <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-[#2d2f39]">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <Trash2 className="w-5 h-5" />
              Data Management
            </h3>
            
            <div className="space-y-3">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Clear all application data including conversations, and personalized settings.
              </p>
              <button
                onClick={openResetDialog}
                className="w-full px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                Reset Application
              </button>
            </div>
          </div>

          <p className="pt-2 text-center text-xs text-gray-400 dark:text-[#858999]">
            v{PACKAGE_VERSION}
          </p>

        </div>
        {showResetConfirm && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div
              ref={resetDialogRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby="reset-dialog-title"
              tabIndex={-1}
              className="max-h-[calc(100dvh-2rem)] w-full max-w-sm overflow-y-auto rounded-2xl border border-red-100 bg-white p-6 shadow-2xl dark:border-red-800/60 dark:bg-[#111113]"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/40">
                  <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                </div>
                <div className="space-y-1.5">
                  <p id="reset-dialog-title" className="text-base font-semibold text-gray-900 dark:text-gray-100">
                    Reset application data?
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    This removes everything stored on this device and reloads the app.
                  </p>
                </div>
              </div>

              <div className="mt-4 flex gap-2 pt-2">
                <button
                  onClick={closeResetDialog}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-[#2d2f39] rounded-lg hover:bg-gray-50 dark:hover:bg-[#1a1b1e] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleResetApplication}
                  className="flex-1 px-4 py-2 text-sm font-semibold rounded-lg transition-colors bg-red-600 text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
                >
                  Reset
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
