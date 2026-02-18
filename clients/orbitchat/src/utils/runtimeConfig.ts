/**
 * Runtime Configuration Utility
 * 
 * Reads configuration from multiple sources in priority order:
 * 1. window.ORBIT_CHAT_CONFIG (injected by CLI)
 * 2. window.CHATBOT_* (legacy window variables)
 * 3. import.meta.env.VITE_* (build-time env vars, for development)
 * 4. Default values
 */

export const DEFAULT_API_URL = 'http://localhost:3000';

export interface RuntimeConfig {
  // API Configuration
  apiUrl: string;
  defaultKey: string;
  applicationName: string;
  applicationDescription: string;
  defaultInputPlaceholder: string;
  useLocalApi: boolean;
  localApiPath?: string;
  consoleDebug: boolean;

  // Feature Flags
  enableUploadButton: boolean;
  enableAudioOutput: boolean;
  enableAudioInput: boolean;
  enableFeedbackButtons: boolean;
  enableConversationThreads: boolean;
  enableAutocomplete: boolean;
  voiceSilenceTimeoutMs: number;
  voiceRecognitionLanguage: string;
  showGitHubStats: boolean;
  outOfServiceMessage: string | null;

  // GitHub Configuration
  githubOwner: string;
  githubRepo: string;

  // Adapters (for middleware mode, fallback when adapters.yaml is not available)
  adapters?: Array<{
    name: string;
    apiUrl: string;
  }>;

  // File Upload Limits
  maxFilesPerConversation: number;
  maxFileSizeMB: number;
  maxTotalFiles: number | null; // null = unlimited

  // Conversation Limits
  maxConversations: number | null; // null = unlimited
  maxMessagesPerConversation: number | null; // null = unlimited
  maxMessagesPerThread: number | null; // null = unlimited
  maxTotalMessages: number | null; // null = unlimited

  // Message Limits
  maxMessageLength: number;
}

declare global {
  interface Window {
    ORBIT_CHAT_CONFIG?: Partial<RuntimeConfig>;
    CHATBOT_API_URL?: string;
    CHATBOT_API_KEY?: string;
  }
}

// Type guard for window.ORBIT_CHAT_CONFIG
function isRuntimeConfig(obj: unknown): obj is Partial<RuntimeConfig> {
  return typeof obj === 'object' && obj !== null;
}

/**
 * Map config keys to VITE_* environment variable names
 */
const envKeyMap: Record<keyof RuntimeConfig, string> = {
  apiUrl: 'VITE_API_URL',
  defaultKey: 'VITE_DEFAULT_KEY',
  applicationName: 'VITE_APPLICATION_NAME',
  applicationDescription: 'VITE_APPLICATION_DESCRIPTION',
  defaultInputPlaceholder: 'VITE_DEFAULT_INPUT_PLACEHOLDER',
  useLocalApi: 'VITE_USE_LOCAL_API',
  localApiPath: 'VITE_LOCAL_API_PATH',
  consoleDebug: 'VITE_CONSOLE_DEBUG',
  enableUploadButton: 'VITE_ENABLE_UPLOAD',
  enableAudioOutput: 'VITE_ENABLE_AUDIO_OUTPUT',
  enableAudioInput: 'VITE_ENABLE_AUDIO_INPUT',
  enableFeedbackButtons: 'VITE_ENABLE_FEEDBACK',
  enableConversationThreads: 'VITE_ENABLE_CONVERSATION_THREADS',
  enableAutocomplete: 'VITE_ENABLE_AUTOCOMPLETE',
  voiceSilenceTimeoutMs: 'VITE_VOICE_SILENCE_TIMEOUT_MS',
  voiceRecognitionLanguage: 'VITE_VOICE_RECOGNITION_LANG',
  showGitHubStats: 'VITE_SHOW_GITHUB_STATS',
  outOfServiceMessage: 'VITE_OUT_OF_SERVICE_MESSAGE',
  githubOwner: 'VITE_GITHUB_OWNER',
  githubRepo: 'VITE_GITHUB_REPO',
  adapters: 'VITE_ADAPTERS',
  maxFilesPerConversation: 'VITE_MAX_FILES_PER_CONVERSATION',
  maxFileSizeMB: 'VITE_MAX_FILE_SIZE_MB',
  maxTotalFiles: 'VITE_MAX_TOTAL_FILES',
  maxConversations: 'VITE_MAX_CONVERSATIONS',
  maxMessagesPerConversation: 'VITE_MAX_MESSAGES_PER_CONVERSATION',
  maxMessagesPerThread: 'VITE_MAX_MESSAGES_PER_THREAD',
  maxTotalMessages: 'VITE_MAX_TOTAL_MESSAGES',
  maxMessageLength: 'VITE_MAX_MESSAGE_LENGTH',
};

function getFirstConfiguredAdapterName(): string | null {
  const normalizeAdapterName = (candidate: unknown): string | null => {
    if (!candidate || typeof candidate !== 'object') {
      return null;
    }
    const adapter = candidate as { name?: unknown };
    if (typeof adapter.name !== 'string') {
      return null;
    }
    const trimmed = adapter.name.trim();
    return trimmed.length > 0 ? trimmed : null;
  };

  if (typeof window !== 'undefined') {
    const runtimeAdapters = window.ORBIT_CHAT_CONFIG?.adapters;
    if (Array.isArray(runtimeAdapters)) {
      for (const adapter of runtimeAdapters) {
        const normalized = normalizeAdapterName(adapter);
        if (normalized) {
          return normalized;
        }
      }
    }
  }

  const envAdapters = import.meta.env.VITE_ADAPTERS;
  if (envAdapters) {
    try {
      const parsed = JSON.parse(envAdapters);
      if (Array.isArray(parsed)) {
        for (const adapter of parsed) {
          const normalized = normalizeAdapterName(adapter);
          if (normalized) {
            return normalized;
          }
        }
      }
    } catch {
      // Ignore parse errors - fallback remains null
    }
  }

  return null;
}

/**
 * Check if window.ORBIT_CHAT_CONFIG has been injected by CLI
 * This is set by the orbitchat CLI when serving the app
 */
function hasCliConfig(): boolean {
  return typeof window !== 'undefined' && isRuntimeConfig(window.ORBIT_CHAT_CONFIG);
}

/**
 * Get a configuration value from multiple sources
 *
 * Priority order:
 * 1. window.ORBIT_CHAT_CONFIG (injected by CLI at runtime - HIGHEST priority)
 * 2. window.CHATBOT_* (legacy window variables)
 * 3. import.meta.env.VITE_* (build-time env vars - ONLY used if no CLI config exists)
 * 4. Default values
 *
 * Note: GitHub-related config (showGitHubStats, githubOwner, githubRepo) is only
 * configurable via build-time env vars for developers who fork the repo.
 *
 * IMPORTANT: When CLI config is present, we ONLY use CLI values and defaults.
 * Build-time env vars are ignored to ensure CLI arguments always take precedence.
 */
function getConfigValue<T>(
  key: keyof RuntimeConfig,
  defaultValue: T,
  type: 'string' | 'boolean' | 'number' | 'numberOrNull' = 'string'
): T {
  // GitHub config is only configurable via build-time env vars (for forkers)
  const isGitHubConfig = key === 'showGitHubStats' || key === 'githubOwner' || key === 'githubRepo';

  // Check if CLI config exists - if so, we prioritize it completely over env vars
  const cliConfigExists = hasCliConfig();

  if (!isGitHubConfig) {
    // Check window.ORBIT_CHAT_CONFIG first (injected by CLI)
    if (cliConfigExists) {
      const value = window.ORBIT_CHAT_CONFIG?.[key];
      if (value !== undefined && value !== null) {
        return value as T;
      }
      // If CLI config exists but this key is not set, fall through to defaults
      // Do NOT check env vars - CLI config takes complete precedence
      return defaultValue;
    }

    // Check legacy window.CHATBOT_* variables
    if (typeof window !== 'undefined') {
      switch (key) {
        case 'apiUrl':
          if (window.CHATBOT_API_URL) {
            return window.CHATBOT_API_URL as T;
          }
          break;
        case 'defaultKey':
          if (window.CHATBOT_API_KEY) {
            return window.CHATBOT_API_KEY as T;
          }
          break;
      }
    }
  }

  // Check import.meta.env.VITE_* (build-time, for development and forkers)
  // ONLY used when no CLI config is present
  const envKey = envKeyMap[key];
  const envRecord = import.meta.env as Record<string, string | undefined>;
  const envValue = envKey ? envRecord[envKey] : undefined;

  if (envValue !== undefined && envValue !== null && envValue !== '') {
    if (type === 'boolean') {
      return (envValue === 'true') as T;
    } else if (type === 'number' || type === 'numberOrNull') {
      const parsed = parseInt(envValue, 10);
      if (!isNaN(parsed)) {
        if (type === 'numberOrNull' && parsed === 0) {
          return null as T;
        }
        return parsed as T;
      }
    } else {
      return envValue as T;
    }
  }

  // Return default value
  return defaultValue;
}

/**
 * Parse a number or null (0 = unlimited)
 */
function parseLimit(envValue: string | undefined, defaultValue: number): number | null {
  if (envValue === undefined || envValue === '') {
    return defaultValue === 0 ? null : defaultValue;
  }
  
  const parsed = parseInt(envValue, 10);
  if (isNaN(parsed) || parsed < 0) {
    return defaultValue === 0 ? null : defaultValue;
  }
  
  if (parsed === 0) {
    return null; // 0 means unlimited
  }
  
  return parsed;
}

/**
 * Parse a required number (cannot be unlimited)
 */
function parseRequiredLimit(envValue: string | undefined, defaultValue: number): number {
  if (envValue === undefined || envValue === '') {
    return defaultValue;
  }
  
  const parsed = parseInt(envValue, 10);
  if (isNaN(parsed) || parsed < 0) {
    return defaultValue;
  }
  
  return parsed;
}

function normalizeOutOfServiceMessage(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const lowered = trimmed.toLowerCase();
  if (lowered === 'false' || lowered === '0' || lowered === 'off' || lowered === 'disabled') {
    return null;
  }

  return trimmed;
}

/**
 * Runtime configuration object
 * All values are resolved at runtime from the sources above
 */
export const runtimeConfig: RuntimeConfig = {
  // API Configuration
  apiUrl: getConfigValue('apiUrl', DEFAULT_API_URL, 'string'),
  defaultKey: getConfigValue('defaultKey', 'default-key', 'string'),
  applicationName: getConfigValue('applicationName', 'ORBIT Chat', 'string'),
  applicationDescription: getConfigValue(
    'applicationDescription',
    "Explore ideas with ORBIT's AI copilots, share context, and build together.",
    'string'
  ),
  defaultInputPlaceholder: getConfigValue('defaultInputPlaceholder', 'Message ORBIT...', 'string'),
  useLocalApi: getConfigValue('useLocalApi', false, 'boolean'),
  localApiPath: getConfigValue('localApiPath', undefined, 'string'),
  consoleDebug: getConfigValue('consoleDebug', false, 'boolean'),
  
  // Feature Flags
  enableUploadButton: getConfigValue('enableUploadButton', false, 'boolean'),
  enableAudioOutput: getConfigValue('enableAudioOutput', false, 'boolean'),
  enableAudioInput: getConfigValue('enableAudioInput', false, 'boolean'),
  enableFeedbackButtons: getConfigValue('enableFeedbackButtons', false, 'boolean'),
  enableConversationThreads: getConfigValue('enableConversationThreads', true, 'boolean'),
  enableAutocomplete: getConfigValue('enableAutocomplete', false, 'boolean'),
  voiceSilenceTimeoutMs: getConfigValue('voiceSilenceTimeoutMs', 4000, 'number'),
  voiceRecognitionLanguage: getConfigValue('voiceRecognitionLanguage', '', 'string'),
  showGitHubStats: getConfigValue('showGitHubStats', true, 'boolean'),
  outOfServiceMessage: (() => {
    const val = getConfigValue('outOfServiceMessage', '', 'string') as string;
    return normalizeOutOfServiceMessage(val);
  })(),
  
  // GitHub Configuration
  githubOwner: getConfigValue('githubOwner', 'schmitech', 'string'),
  githubRepo: getConfigValue('githubRepo', 'orbit', 'string'),
  
  // File Upload Limits
  maxFilesPerConversation: (() => {
    const val = getConfigValue('maxFilesPerConversation', '5', 'string') as string;
    return parseRequiredLimit(val, 5);
  })(),
  maxFileSizeMB: (() => {
    const val = getConfigValue('maxFileSizeMB', '50', 'string') as string;
    return parseRequiredLimit(val, 50);
  })(),
  maxTotalFiles: (() => {
    const val = getConfigValue('maxTotalFiles', '100', 'string') as string;
    return parseLimit(val, 100);
  })(),
  
  // Conversation Limits
  maxConversations: (() => {
    const val = getConfigValue('maxConversations', '10', 'string') as string;
    return parseLimit(val, 10);
  })(),
  maxMessagesPerConversation: (() => {
    const val = getConfigValue('maxMessagesPerConversation', '1000', 'string') as string;
    return parseLimit(val, 1000);
  })(),
  maxMessagesPerThread: (() => {
    const val = getConfigValue('maxMessagesPerThread', '1000', 'string') as string;
    return parseLimit(val, 1000);
  })(),
  maxTotalMessages: (() => {
    const val = getConfigValue('maxTotalMessages', '10000', 'string') as string;
    return parseLimit(val, 10000);
  })(),
  
  // Message Limits
  maxMessageLength: (() => {
    const val = getConfigValue('maxMessageLength', '1000', 'string') as string;
    return parseRequiredLimit(val, 1000);
  })(),
};

/**
 * Helper functions to get specific config values
 * These read dynamically to ensure they always get the latest runtime config
 */
export function getApiUrl(): string {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  const value = getConfigValue('apiUrl', DEFAULT_API_URL, 'string');  
  return value;
}

export function resolveApiUrl(url?: string | null): string {
  const trimmed = url?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : getApiUrl();
}

export function getDefaultKey(): string {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('defaultKey', 'default-key', 'string');
}

export function getApplicationName(): string {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('applicationName', 'ORBIT Chat', 'string');
}

export function getApplicationDescription(): string {
  return getConfigValue(
    'applicationDescription',
    "Explore ideas with ORBIT's AI copilots, share context, and build together.",
    'string'
  );
}

export function getDefaultInputPlaceholder(): string {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('defaultInputPlaceholder', 'Message ORBIT...', 'string');
}

export function getUseLocalApi(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('useLocalApi', false, 'boolean');
}

export function getLocalApiPath(): string | undefined {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('localApiPath', undefined, 'string');
}

export function getConsoleDebug(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('consoleDebug', false, 'boolean');
}

export function getEnableUploadButton(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableUploadButton', false, 'boolean');
}

export function getEnableAudioOutput(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableAudioOutput', false, 'boolean');
}

export function getEnableAudioInput(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableAudioInput', false, 'boolean');
}

export function getEnableFeedbackButtons(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableFeedbackButtons', false, 'boolean');
}

export function getEnableConversationThreads(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableConversationThreads', true, 'boolean');
}

export function getEnableAutocomplete(): boolean {
  // Read dynamically to ensure we get the latest window.ORBIT_CHAT_CONFIG
  return getConfigValue('enableAutocomplete', false, 'boolean');
}

export function getVoiceSilenceTimeoutMs(): number {
  const value = getConfigValue('voiceSilenceTimeoutMs', 4000, 'number');
  return Math.max(1000, value);
}

export function getVoiceRecognitionLanguage(): string {
  return getConfigValue('voiceRecognitionLanguage', '', 'string');
}

/**
 * Helper to resolve the default adapter name.
 * Falls back to null when no default adapter is configured.
 */
export function getDefaultAdapterName(): string | null {
  const adapterName = getDefaultKey()?.trim();
  if (adapterName && adapterName !== 'default-key') {
    return adapterName;
  }

  const fallbackAdapter = getFirstConfiguredAdapterName();
  if (fallbackAdapter) {
    return fallbackAdapter;
  }

  return adapterName && adapterName.length > 0 ? adapterName : null;
}

export function getShowGitHubStats(): boolean {
  return runtimeConfig.showGitHubStats;
}

export function getGitHubOwner(): string {
  return runtimeConfig.githubOwner;
}

export function getGitHubRepo(): string {
  return runtimeConfig.githubRepo;
}

export function getOutOfServiceMessage(): string | null {
  const value = getConfigValue('outOfServiceMessage', '', 'string') as string;
  return normalizeOutOfServiceMessage(value);
}
