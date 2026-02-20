/**
 * Application Configuration Utility
 *
 * Centralized configuration that reads from runtime configuration with defaults.
 * Handles parsing, validation, and unlimited values (0 = unlimited).
 *
 * Config sources (highest priority wins):
 * 1. window.ORBIT_CHAT_CONFIG (injected by CLI at runtime)
 * 2. import.meta.env.__ORBITCHAT_CONFIG (injected by Vite plugin from orbitchat.yaml)
 * 3. Default values
 *
 * When enableAuth is true and the user is not authenticated, the Proxy
 * transparently returns guest-tier limits instead of the normal values.
 */

import { runtimeConfig } from './runtimeConfig';
import { getIsAuthConfigured } from './runtimeConfig';
import { getIsAuthenticated } from '../auth/authState';

/**
 * Maps each normal limit key to its guest-limit counterpart in runtimeConfig.
 */
const GUEST_LIMIT_MAP: Record<string, keyof typeof runtimeConfig> = {
  maxConversations: 'guestMaxConversations',
  maxMessagesPerConversation: 'guestMaxMessagesPerConversation',
  maxTotalMessages: 'guestMaxTotalMessages',
  maxMessagesPerThread: 'guestMaxMessagesPerThread',
  maxFilesPerConversation: 'guestMaxFilesPerConversation',
  maxTotalFiles: 'guestMaxTotalFiles',
  maxMessageLength: 'guestMaxMessageLength',
  maxFileSizeMB: 'guestMaxFileSizeMB',
};

const baseConfig = {
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
};

/**
 * Application configuration with all limits.
 * When auth is enabled and user is a guest, limit keys automatically
 * return the guest-tier values. Zero call-site changes required.
 */
export const AppConfig = new Proxy(baseConfig, {
  get(target, prop: string) {
    if (prop in GUEST_LIMIT_MAP && getIsAuthConfigured() && !getIsAuthenticated()) {
      return runtimeConfig[GUEST_LIMIT_MAP[prop]];
    }
    return target[prop as keyof typeof target];
  },
});
