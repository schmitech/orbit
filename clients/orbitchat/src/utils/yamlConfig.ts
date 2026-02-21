/**
 * YAML Configuration Schema
 *
 * Defines the nested shape of orbitchat.yaml.
 */

import type { NavLink } from './runtimeConfig';

/** Shape of orbitchat.yaml */
export interface OrbitChatYamlConfig {
  application?: {
    name?: string;
    description?: string;
    inputPlaceholder?: string;
    settingsAboutMsg?: string;
    locale?: string;
  };
  debug?: {
    consoleDebug?: boolean;
  };
  features?: {
    enableUpload?: boolean;
    enableAudioOutput?: boolean;
    enableAudioInput?: boolean;
    enableFeedbackButtons?: boolean;
    enableConversationThreads?: boolean;
    enableAutocomplete?: boolean;
  };
  voice?: {
    silenceTimeoutMs?: number;
    recognitionLanguage?: string;
  };
  github?: {
    showStats?: boolean;
    owner?: string;
    repo?: string;
  };
  outOfServiceMessage?: string | null;
  limits?: {
    files?: {
      perConversation?: number;
      maxSizeMB?: number;
      totalFiles?: number;
    };
    conversations?: {
      maxConversations?: number;
      messagesPerConversation?: number;
      messagesPerThread?: number;
      totalMessages?: number;
    };
    messages?: {
      maxLength?: number;
    };
  };
  guestLimits?: {
    files?: {
      perConversation?: number;
      maxSizeMB?: number;
      totalFiles?: number;
    };
    conversations?: {
      maxConversations?: number;
      messagesPerConversation?: number;
      messagesPerThread?: number;
      totalMessages?: number;
    };
    messages?: {
      maxLength?: number;
    };
    rateLimit?: {
      enabled?: boolean;
      windowMs?: number;
      maxRequests?: number;
      chat?: {
        windowMs?: number;
        maxRequests?: number;
      };
    };
  };
  auth?: {
    enabled?: boolean;
  };
  header?: {
    enabled?: boolean;
    logoUrl?: string;
    logoUrlLight?: string;
    logoUrlDark?: string;
    brandName?: string;
    bgColor?: string;
    textColor?: string;
    showBorder?: boolean;
    navLinks?: NavLink[];
  };
  footer?: {
    enabled?: boolean;
    text?: string;
    bgColor?: string;
    textColor?: string;
    showBorder?: boolean;
    layout?: 'stacked' | 'inline';
    align?: 'left' | 'center';
    topPadding?: 'normal' | 'large';
    navLinks?: NavLink[];
  };
  adapters?: Array<{
    name: string;
    apiUrl?: string;
    description?: string;
    notes?: string;
  }>;
}
