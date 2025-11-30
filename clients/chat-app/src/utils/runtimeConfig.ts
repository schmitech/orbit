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

interface RuntimeConfig {
  // API Configuration
  apiUrl: string;
  defaultKey: string;
  useLocalApi: boolean;
  localApiPath?: string;
  consoleDebug: boolean;
  
  // Feature Flags
  enableUploadButton: boolean;
  enableAudioOutput: boolean;
  enableFeedbackButtons: boolean;
  enableConversationThreads: boolean;
  enableApiMiddleware: boolean;
  showGitHubStats: boolean;
  
  // GitHub Configuration
  githubOwner: string;
  githubRepo: string;
  
  // File Upload Limits
  maxFilesPerConversation: number;
  maxFileSizeMB: number;
  maxTotalFiles: number | null; // null = unlimited
  
  // Conversation Limits
  maxConversations: number | null; // null = unlimited
  maxMessagesPerConversation: number | null; // null = unlimited
  maxTotalMessages: number | null; // null = unlimited
  
  // Message Limits
  maxMessageLength: number;
}

// Type guard for window.ORBIT_CHAT_CONFIG
function isRuntimeConfig(obj: any): obj is Partial<RuntimeConfig> {
  return typeof obj === 'object' && obj !== null;
}

/**
 * Map config keys to VITE_* environment variable names
 */
const envKeyMap: Record<keyof RuntimeConfig, string> = {
  apiUrl: 'VITE_API_URL',
  defaultKey: 'VITE_DEFAULT_KEY',
  useLocalApi: 'VITE_USE_LOCAL_API',
  localApiPath: 'VITE_LOCAL_API_PATH',
  consoleDebug: 'VITE_CONSOLE_DEBUG',
  enableUploadButton: 'VITE_ENABLE_UPLOAD',
  enableAudioOutput: 'VITE_ENABLE_AUDIO_OUTPUT',
  enableFeedbackButtons: 'VITE_ENABLE_FEEDBACK',
  enableConversationThreads: 'VITE_ENABLE_CONVERSATION_THREADS',
  enableApiMiddleware: 'VITE_ENABLE_API_MIDDLEWARE',
  showGitHubStats: 'VITE_SHOW_GITHUB_STATS',
  githubOwner: 'VITE_GITHUB_OWNER',
  githubRepo: 'VITE_GITHUB_REPO',
  maxFilesPerConversation: 'VITE_MAX_FILES_PER_CONVERSATION',
  maxFileSizeMB: 'VITE_MAX_FILE_SIZE_MB',
  maxTotalFiles: 'VITE_MAX_TOTAL_FILES',
  maxConversations: 'VITE_MAX_CONVERSATIONS',
  maxMessagesPerConversation: 'VITE_MAX_MESSAGES_PER_CONVERSATION',
  maxTotalMessages: 'VITE_MAX_TOTAL_MESSAGES',
  maxMessageLength: 'VITE_MAX_MESSAGE_LENGTH',
};

/**
 * Get a configuration value from multiple sources
 * Note: GitHub-related config (showGitHubStats, githubOwner, githubRepo) is only
 * configurable via build-time env vars for developers who fork the repo.
 */
function getConfigValue<T>(
  key: keyof RuntimeConfig,
  defaultValue: T,
  type: 'string' | 'boolean' | 'number' | 'numberOrNull' = 'string'
): T {
  // GitHub config is only configurable via build-time env vars (for forkers)
  const isGitHubConfig = key === 'showGitHubStats' || key === 'githubOwner' || key === 'githubRepo';
  
  if (!isGitHubConfig) {
    // Check window.ORBIT_CHAT_CONFIG first (injected by CLI)
    if (typeof window !== 'undefined' && isRuntimeConfig((window as any).ORBIT_CHAT_CONFIG)) {
      const value = (window as any).ORBIT_CHAT_CONFIG[key];
      if (value !== undefined && value !== null) {
        return value as T;
      }
    }
    
    // Check legacy window.CHATBOT_* variables
    if (typeof window !== 'undefined') {
      const win = window as any;
      switch (key) {
        case 'apiUrl':
          if (win.CHATBOT_API_URL) return win.CHATBOT_API_URL as T;
          break;
        case 'defaultKey':
          if (win.CHATBOT_API_KEY) return win.CHATBOT_API_KEY as T;
          break;
      }
    }
  }
  
  // Check import.meta.env.VITE_* (build-time, for development and forkers)
  const envKey = envKeyMap[key];
  const envValue = envKey ? (import.meta.env as any)[envKey] : undefined;
  
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

/**
 * Runtime configuration object
 * All values are resolved at runtime from the sources above
 */
export const runtimeConfig: RuntimeConfig = {
  // API Configuration
  apiUrl: getConfigValue('apiUrl', DEFAULT_API_URL, 'string'),
  defaultKey: getConfigValue('defaultKey', 'default-key', 'string'),
  useLocalApi: getConfigValue('useLocalApi', false, 'boolean'),
  localApiPath: getConfigValue('localApiPath', undefined, 'string'),
  consoleDebug: getConfigValue('consoleDebug', false, 'boolean'),
  
  // Feature Flags
  enableUploadButton: getConfigValue('enableUploadButton', false, 'boolean'),
  enableAudioOutput: getConfigValue('enableAudioOutput', false, 'boolean'),
  enableFeedbackButtons: getConfigValue('enableFeedbackButtons', false, 'boolean'),
  enableConversationThreads: getConfigValue('enableConversationThreads', true, 'boolean'),
  enableApiMiddleware: getConfigValue('enableApiMiddleware', false, 'boolean'),
  showGitHubStats: getConfigValue('showGitHubStats', true, 'boolean'),
  
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

export function getUseLocalApi(): boolean {
  return runtimeConfig.useLocalApi;
}

export function getLocalApiPath(): string | undefined {
  return runtimeConfig.localApiPath;
}

export function getConsoleDebug(): boolean {
  return runtimeConfig.consoleDebug;
}

export function getEnableUploadButton(): boolean {
  return runtimeConfig.enableUploadButton;
}

export function getEnableAudioOutput(): boolean {
  return runtimeConfig.enableAudioOutput;
}

export function getEnableFeedbackButtons(): boolean {
  return runtimeConfig.enableFeedbackButtons;
}

export function getEnableConversationThreads(): boolean {
  return runtimeConfig.enableConversationThreads;
}

export function getEnableApiMiddleware(): boolean {
  return runtimeConfig.enableApiMiddleware;
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
