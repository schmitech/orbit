/**
 * Application Configuration Utility
 * 
 * Centralized configuration that reads environment variables with defaults.
 * Handles parsing, validation, and unlimited values (0 = unlimited).
 */

/**
 * Parse an environment variable as an integer with a default value.
 * Returns null if the value is 0 (unlimited), otherwise returns the parsed number.
 * 
 * @param envValue - The environment variable value
 * @param defaultValue - Default value if envValue is undefined or invalid
 * @returns The parsed number, or null if unlimited (0)
 */
function parseLimit(envValue: string | undefined, defaultValue: number): number | null {
  if (envValue === undefined || envValue === '') {
    return defaultValue === 0 ? null : defaultValue;
  }
  
  const parsed = parseInt(envValue, 10);
  
  // Handle NaN or invalid values
  if (isNaN(parsed) || parsed < 0) {
    return defaultValue === 0 ? null : defaultValue;
  }
  
  // 0 means unlimited
  if (parsed === 0) {
    return null;
  }
  
  return parsed;
}

/**
 * Parse an environment variable as an integer with a default value.
 * Does not treat 0 as unlimited (for values that cannot be unlimited).
 * 
 * @param envValue - The environment variable value
 * @param defaultValue - Default value if envValue is undefined or invalid
 * @returns The parsed number
 */
function parseRequiredLimit(envValue: string | undefined, defaultValue: number): number {
  if (envValue === undefined || envValue === '') {
    return defaultValue;
  }
  
  const parsed = parseInt(envValue, 10);
  
  // Handle NaN or invalid values
  if (isNaN(parsed) || parsed < 0) {
    return defaultValue;
  }
  
  return parsed;
}

/**
 * Application configuration with all limits
 */
export const AppConfig = {
  // File Upload Limits
  maxFilesPerConversation: parseRequiredLimit(
    import.meta.env.VITE_MAX_FILES_PER_CONVERSATION,
    5
  ),
  maxFileSizeMB: parseRequiredLimit(
    import.meta.env.VITE_MAX_FILE_SIZE_MB,
    50
  ),
  maxTotalFiles: parseLimit(
    import.meta.env.VITE_MAX_TOTAL_FILES,
    100
  ),
  
  // Conversation Limits
  maxConversations: parseLimit(
    import.meta.env.VITE_MAX_CONVERSATIONS,
    10
  ),
  maxMessagesPerConversation: parseLimit(
    import.meta.env.VITE_MAX_MESSAGES_PER_CONVERSATION,
    1000
  ),
  maxTotalMessages: parseLimit(
    import.meta.env.VITE_MAX_TOTAL_MESSAGES,
    10000
  ),
  
  // Message Limits
  maxMessageLength: parseRequiredLimit(
    import.meta.env.VITE_MAX_MESSAGE_LENGTH,
    1000
  ),
} as const;

