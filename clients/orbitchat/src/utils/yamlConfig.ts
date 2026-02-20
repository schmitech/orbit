/**
 * YAML Configuration Schema & Flatten Utility
 *
 * Defines the nested shape of orbitchat.yaml and provides a function
 * to flatten it into the flat RuntimeConfig shape.
 */

import type { RuntimeConfig, NavLink } from './runtimeConfig';

/** Shape of orbitchat.yaml */
export interface OrbitChatYamlConfig {
  application?: {
    name?: string;
    description?: string;
    inputPlaceholder?: string;
    settingsAboutMsg?: string;
    locale?: string;
  };
  api?: {
    url?: string;
    defaultAdapter?: string;
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

/**
 * Flatten a nested YAML config object into the flat RuntimeConfig shape.
 * Only keys present in the YAML are included (sparse overlay).
 */
export function flattenYamlConfig(yaml: OrbitChatYamlConfig): Partial<RuntimeConfig> {
  const flat: Partial<RuntimeConfig> = {};

  if (yaml.application) {
    const a = yaml.application;
    if (a.name !== undefined) flat.applicationName = a.name;
    if (a.description !== undefined) flat.applicationDescription = a.description;
    if (a.inputPlaceholder !== undefined) flat.defaultInputPlaceholder = a.inputPlaceholder;
    if (a.settingsAboutMsg !== undefined) flat.settingsAboutMsg = a.settingsAboutMsg;
    if (a.locale !== undefined) flat.locale = a.locale;
  }

  if (yaml.api) {
    const a = yaml.api;
    if (a.url !== undefined) flat.apiUrl = a.url;
    if (a.defaultAdapter !== undefined) flat.defaultKey = a.defaultAdapter;
  }

  if (yaml.debug) {
    if (yaml.debug.consoleDebug !== undefined) flat.consoleDebug = yaml.debug.consoleDebug;
  }

  if (yaml.features) {
    const f = yaml.features;
    if (f.enableUpload !== undefined) flat.enableUploadButton = f.enableUpload;
    if (f.enableAudioOutput !== undefined) flat.enableAudioOutput = f.enableAudioOutput;
    if (f.enableAudioInput !== undefined) flat.enableAudioInput = f.enableAudioInput;
    if (f.enableFeedbackButtons !== undefined) flat.enableFeedbackButtons = f.enableFeedbackButtons;
    if (f.enableConversationThreads !== undefined) flat.enableConversationThreads = f.enableConversationThreads;
    if (f.enableAutocomplete !== undefined) flat.enableAutocomplete = f.enableAutocomplete;
  }

  if (yaml.voice) {
    if (yaml.voice.silenceTimeoutMs !== undefined) flat.voiceSilenceTimeoutMs = yaml.voice.silenceTimeoutMs;
    if (yaml.voice.recognitionLanguage !== undefined) flat.voiceRecognitionLanguage = yaml.voice.recognitionLanguage;
  }

  if (yaml.github) {
    const g = yaml.github;
    if (g.showStats !== undefined) flat.showGitHubStats = g.showStats;
    if (g.owner !== undefined) flat.githubOwner = g.owner;
    if (g.repo !== undefined) flat.githubRepo = g.repo;
  }

  if (yaml.outOfServiceMessage !== undefined) flat.outOfServiceMessage = yaml.outOfServiceMessage;

  if (yaml.limits) {
    const l = yaml.limits;
    if (l.files) {
      if (l.files.perConversation !== undefined) flat.maxFilesPerConversation = l.files.perConversation;
      if (l.files.maxSizeMB !== undefined) flat.maxFileSizeMB = l.files.maxSizeMB;
      if (l.files.totalFiles !== undefined) flat.maxTotalFiles = l.files.totalFiles;
    }
    if (l.conversations) {
      if (l.conversations.maxConversations !== undefined) flat.maxConversations = l.conversations.maxConversations;
      if (l.conversations.messagesPerConversation !== undefined) flat.maxMessagesPerConversation = l.conversations.messagesPerConversation;
      if (l.conversations.messagesPerThread !== undefined) flat.maxMessagesPerThread = l.conversations.messagesPerThread;
      if (l.conversations.totalMessages !== undefined) flat.maxTotalMessages = l.conversations.totalMessages;
    }
    if (l.messages) {
      if (l.messages.maxLength !== undefined) flat.maxMessageLength = l.messages.maxLength;
    }
  }

  if (yaml.guestLimits) {
    const g = yaml.guestLimits;
    if (g.files) {
      if (g.files.perConversation !== undefined) flat.guestMaxFilesPerConversation = g.files.perConversation;
      if (g.files.maxSizeMB !== undefined) flat.guestMaxFileSizeMB = g.files.maxSizeMB;
      if (g.files.totalFiles !== undefined) flat.guestMaxTotalFiles = g.files.totalFiles;
    }
    if (g.conversations) {
      if (g.conversations.maxConversations !== undefined) flat.guestMaxConversations = g.conversations.maxConversations;
      if (g.conversations.messagesPerConversation !== undefined) flat.guestMaxMessagesPerConversation = g.conversations.messagesPerConversation;
      if (g.conversations.messagesPerThread !== undefined) flat.guestMaxMessagesPerThread = g.conversations.messagesPerThread;
      if (g.conversations.totalMessages !== undefined) flat.guestMaxTotalMessages = g.conversations.totalMessages;
    }
    if (g.messages) {
      if (g.messages.maxLength !== undefined) flat.guestMaxMessageLength = g.messages.maxLength;
    }
    // guestLimits.rateLimit is enforced server-side; no client runtime fields to map.
  }

  if (yaml.auth) {
    if (yaml.auth.enabled !== undefined) flat.enableAuth = yaml.auth.enabled;
  }

  if (yaml.header) {
    const h = yaml.header;
    if (h.enabled !== undefined) flat.enableHeader = h.enabled;
    if (h.logoUrl !== undefined) flat.headerLogoUrl = h.logoUrl;
    if (h.brandName !== undefined) flat.headerBrandName = h.brandName;
    if (h.bgColor !== undefined) flat.headerBgColor = h.bgColor;
    if (h.textColor !== undefined) flat.headerTextColor = h.textColor;
    if (h.showBorder !== undefined) flat.headerShowBorder = h.showBorder;
    if (h.navLinks !== undefined) flat.headerNavLinks = h.navLinks;
  }

  if (yaml.footer) {
    const f = yaml.footer;
    if (f.enabled !== undefined) flat.enableFooter = f.enabled;
    if (f.text !== undefined) flat.footerText = f.text;
    if (f.bgColor !== undefined) flat.footerBgColor = f.bgColor;
    if (f.textColor !== undefined) flat.footerTextColor = f.textColor;
    if (f.showBorder !== undefined) flat.footerShowBorder = f.showBorder;
    if (f.layout !== undefined) flat.footerLayout = f.layout;
    if (f.align !== undefined) flat.footerAlign = f.align;
    if (f.topPadding !== undefined) flat.footerTopPadding = f.topPadding;
    if (f.navLinks !== undefined) flat.footerNavLinks = f.navLinks;
  }

  if (yaml.adapters !== undefined) {
    flat.adapters = yaml.adapters;
  }

  return flat;
}
