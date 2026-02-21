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

const baseConfig = {
  // File Upload Limits
  maxFilesPerConversation: runtimeConfig.limits.files.perConversation,
  maxFileSizeMB: runtimeConfig.limits.files.maxSizeMB,
  maxTotalFiles: runtimeConfig.limits.files.totalFiles,

  // Conversation Limits
  maxConversations: runtimeConfig.limits.conversations.maxConversations,
  maxMessagesPerConversation: runtimeConfig.limits.conversations.maxMessagesPerConversation,
  maxMessagesPerThread: runtimeConfig.limits.conversations.maxMessagesPerThread,
  maxTotalMessages: runtimeConfig.limits.conversations.totalMessages,

  // Message Limits
  maxMessageLength: runtimeConfig.limits.messages.maxLength,
};

function getGuestLimit(prop: string) {
  const g = runtimeConfig.guestLimits;
  switch (prop) {
    case 'maxConversations': return g.conversations.maxConversations;
    case 'maxMessagesPerConversation': return g.conversations.messagesPerConversation;
    case 'maxMessagesPerThread': return g.conversations.messagesPerThread;
    case 'maxTotalMessages': return g.conversations.totalMessages;
    case 'maxFilesPerConversation': return g.files.perConversation;
    case 'maxTotalFiles': return g.files.totalFiles;
    case 'maxMessageLength': return g.messages.maxLength;
    case 'maxFileSizeMB': return g.files.maxSizeMB;
    default: return undefined;
  }
}

/**
 * Application configuration with all limits.
 * When auth is enabled and user is a guest, limit keys automatically
 * return the guest-tier values. Zero call-site changes required.
 */
export const AppConfig = new Proxy(baseConfig, {
  get(target, prop: string) {
    if (getIsAuthConfigured() && !getIsAuthenticated()) {
      const guestValue = getGuestLimit(prop);
      if (guestValue !== undefined) return guestValue;
    }
    return target[prop as keyof typeof target];
  },
});
