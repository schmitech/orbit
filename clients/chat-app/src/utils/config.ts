/**
 * Application Configuration Utility
 * 
 * Centralized configuration that reads from runtime configuration with defaults.
 * Handles parsing, validation, and unlimited values (0 = unlimited).
 * 
 * This module now uses runtimeConfig which reads from:
 * 1. window.ORBIT_CHAT_CONFIG (injected by CLI)
 * 2. window.CHATBOT_* (legacy window variables)
 * 3. import.meta.env.VITE_* (build-time env vars, for development)
 * 4. Default values
 */

import { runtimeConfig } from './runtimeConfig';

/**
 * Application configuration with all limits
 * All values are read from runtimeConfig
 */
export const AppConfig = {
  // File Upload Limits
  maxFilesPerConversation: runtimeConfig.maxFilesPerConversation,
  maxFileSizeMB: runtimeConfig.maxFileSizeMB,
  maxTotalFiles: runtimeConfig.maxTotalFiles,
  
  // Conversation Limits
  maxConversations: runtimeConfig.maxConversations,
  maxMessagesPerConversation: runtimeConfig.maxMessagesPerConversation,
  maxMessagesPerThread: runtimeConfig.maxMessagesPerThread,
  maxTotalMessages: runtimeConfig.maxTotalMessages,
  
  // Message Limits
  maxMessageLength: runtimeConfig.maxMessageLength,
} as const;
