/**
 * Runtime Configuration Utility
 *
 * Reads configuration from a single merged object built at startup:
 *  - Vite plugin injects defaults + orbitchat.yaml via import.meta.env.__ORBITCHAT_CONFIG (dev/build)
 *  - CLI injects window.ORBIT_CHAT_CONFIG (production server)
 *  - Secrets come from VITE_AUTH_* env vars
 */

export const DEFAULT_API_URL = 'http://localhost:3000';
const DEFAULT_HEADER_LOGO_LIGHT = '/orbit-logo-light.png';
const DEFAULT_HEADER_LOGO_DARK = '/orbit-logo-dark.png';

export interface NavLink {
  label: string;
  url: string;
}

export interface RuntimeConfig {
  application: {
    name: string;
    description: string;
    inputPlaceholder: string;
    settingsAboutMsg: string;
    locale: string;
  };
  debug: {
    consoleDebug: boolean;
  };
  features: {
    enableUpload: boolean;
    enableAudioOutput: boolean;
    enableAudioInput: boolean;
    enableFeedbackButtons: boolean;
    enableConversationThreads: boolean;
    enableAutocomplete: boolean;
  };
  voice: {
    silenceTimeoutMs: number;
    recognitionLanguage: string;
  };
  github: {
    showStats: boolean;
    owner: string;
    repo: string;
  };
  outOfServiceMessage: string | null;
  limits: {
    files: {
      perConversation: number;
      maxSizeMB: number;
      totalFiles: number | null;
    };
    conversations: {
      maxConversations: number | null;
      messagesPerConversation: number | null;
      messagesPerThread: number | null;
      totalMessages: number | null;
    };
    messages: {
      maxLength: number;
    };
  };
  guestLimits: {
    files: {
      perConversation: number;
      maxSizeMB: number;
      totalFiles: number | null;
    };
    conversations: {
      maxConversations: number | null;
      messagesPerConversation: number | null;
      messagesPerThread: number | null;
      totalMessages: number | null;
    };
    messages: {
      maxLength: number;
    };
  };
  auth: {
    enabled: boolean;
    domain: string;
    clientId: string;
    audience: string;
  };
  header: {
    enabled: boolean;
    logoUrl: string;
    logoUrlLight: string;
    logoUrlDark: string;
    brandName: string;
    bgColor: string;
    textColor: string;
    showBorder: boolean;
    navLinks: NavLink[];
  };
  footer: {
    enabled: boolean;
    text: string;
    bgColor: string;
    textColor: string;
    showBorder: boolean;
    layout: 'stacked' | 'inline';
    align: 'left' | 'center';
    topPadding: 'normal' | 'large';
    navLinks: NavLink[];
  };
  adapters: Array<{
    id: string;
    name: string;
    apiUrl?: string;
    description?: string;
    notes?: string;
  }>;
}

declare global {
  interface Window {
    ORBIT_CHAT_CONFIG?: Partial<RuntimeConfig>;
  }
}

/** Default values — single source of truth for the entire app */
export const DEFAULTS: RuntimeConfig = {
  application: {
    name: 'ORBIT Chat',
    description: "Explore ideas with ORBIT's AI copilots, share context, and build together.",
    inputPlaceholder: 'Message ORBIT...',
    settingsAboutMsg: 'ORBIT Chat',
    locale: 'en-US',
  },
  debug: {
    consoleDebug: false,
  },
  features: {
    enableUpload: false,
    enableAudioOutput: false,
    enableAudioInput: false,
    enableFeedbackButtons: false,
    enableConversationThreads: true,
    enableAutocomplete: false,
  },
  voice: {
    silenceTimeoutMs: 4000,
    recognitionLanguage: '',
  },
  github: {
    showStats: true,
    owner: 'schmitech',
    repo: 'orbit',
  },
  outOfServiceMessage: null,
  limits: {
    files: {
      perConversation: 5,
      maxSizeMB: 50,
      totalFiles: 100,
    },
    conversations: {
      maxConversations: 10,
      messagesPerConversation: 1000,
      messagesPerThread: 1000,
      totalMessages: 10000,
    },
    messages: {
      maxLength: 1000,
    },
  },
  guestLimits: {
    files: {
      perConversation: 1,
      maxSizeMB: 10,
      totalFiles: 2,
    },
    conversations: {
      maxConversations: 1,
      messagesPerConversation: 10,
      messagesPerThread: 10,
      totalMessages: 10,
    },
    messages: {
      maxLength: 500,
    },
  },
  auth: {
    enabled: false,
    domain: '',
    clientId: '',
    audience: '',
  },
  header: {
    enabled: false,
    logoUrl: '',
    logoUrlLight: '',
    logoUrlDark: '',
    brandName: '',
    bgColor: '',
    textColor: '',
    showBorder: true,
    navLinks: [],
  },
  footer: {
    enabled: false,
    text: '',
    bgColor: '',
    textColor: '',
    showBorder: false,
    layout: 'stacked',
    align: 'center',
    topPadding: 'large',
    navLinks: [],
  },
  adapters: [],
};

function isObject(item: unknown): item is Record<string, unknown> {
  return typeof item === 'object' && item !== null && !Array.isArray(item);
}

/** Recursive deep merge of source into target */
function deepMerge<T extends Record<string, unknown>>(target: T, source: Record<string, unknown>): T {
  if (!isObject(target) || !isObject(source)) {
    return source as T;
  }

  const output = { ...target } as Record<string, unknown>;
  Object.keys(source).forEach(key => {
    const targetValue = output[key];
    const sourceValue = source[key];

    if (isObject(targetValue) && isObject(sourceValue)) {
      output[key] = deepMerge(targetValue as Record<string, unknown>, sourceValue);
    } else if (sourceValue !== undefined) {
      output[key] = sourceValue;
    }
  });

  return output as T;
}

function normalizeOutOfServiceMessage(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const lowered = trimmed.toLowerCase();
  if (lowered === 'false' || lowered === '0' || lowered === 'off' || lowered === 'disabled') return null;
  return trimmed;
}

/**
 * Build the runtime config by merging sources.
 *
 * Priority (highest wins):
 *  1. window.ORBIT_CHAT_CONFIG  (injected by orbitchat CLI at runtime)
 *  2. import.meta.env.__ORBITCHAT_CONFIG  (injected by Vite plugin at build/dev time)
 *  3. DEFAULTS
 *
 * Auth secrets always overlay from VITE_AUTH_* env vars.
 */
function buildRuntimeConfig(): RuntimeConfig {
  // Config injected by the Vite plugin (dev + build)
  const viteConfig = (import.meta.env as Record<string, unknown>).__ORBITCHAT_CONFIG || {};

  // Config injected by the CLI server at runtime
  const injected = (typeof window !== 'undefined' && window.ORBIT_CHAT_CONFIG) || {};

  // Merge: DEFAULTS < viteConfig < injected
  let merged = deepMerge(DEFAULTS, viteConfig);
  merged = deepMerge(merged, injected);

  // Overlay auth secrets from VITE_AUTH_* env vars (always available from .env)
  if (import.meta.env.VITE_AUTH_DOMAIN) merged.auth.domain = import.meta.env.VITE_AUTH_DOMAIN;
  if (import.meta.env.VITE_AUTH_CLIENT_ID) merged.auth.clientId = import.meta.env.VITE_AUTH_CLIENT_ID;
  if (import.meta.env.VITE_AUTH_AUDIENCE) merged.auth.audience = import.meta.env.VITE_AUTH_AUDIENCE;

  // Normalize outOfServiceMessage
  merged.outOfServiceMessage = normalizeOutOfServiceMessage(merged.outOfServiceMessage);

  if (merged.auth.enabled && !merged.header.enabled) {
    console.warn('[runtimeConfig] Auth is enabled but header is disabled. Auth UI is expected to be shown from the header, so enable header.enabled to expose sign-in controls.');
  }

  return merged;
}

export const runtimeConfig: RuntimeConfig = buildRuntimeConfig();

// --- Getter functions (thin pass-throughs) ---

/**
 * Get the global API URL fallback.
 * Priority: first adapter's URL, then DEFAULT_API_URL.
 */
export function getApiUrl(): string {
  const adapters = runtimeConfig.adapters;
  if (Array.isArray(adapters) && adapters.length > 0) {
    const firstUrl = adapters[0].apiUrl?.trim();
    if (firstUrl) return firstUrl;
  }
  return DEFAULT_API_URL;
}

export function resolveApiUrl(url?: string | null): string {
  const trimmed = url?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : getApiUrl();
}

/**
 * Get the global default adapter key fallback.
 */
export function getDefaultKey(): string {
  const adapters = runtimeConfig.adapters;
  if (Array.isArray(adapters) && adapters.length > 0) {
    return adapters[0].id;
  }
  return 'default-key';
}

export function getApplicationName(): string {
  return runtimeConfig.application.name;
}

export function getApplicationDescription(): string {
  return runtimeConfig.application.description;
}

export function getDefaultInputPlaceholder(): string {
  return runtimeConfig.application.inputPlaceholder;
}

export function getConsoleDebug(): boolean {
  return runtimeConfig.debug.consoleDebug;
}

export function getLocale(): string {
  return runtimeConfig.application.locale;
}

export function getEnableUploadButton(): boolean {
  return runtimeConfig.features.enableUpload;
}

export function getEnableAudioOutput(): boolean {
  return runtimeConfig.features.enableAudioOutput;
}

export function getEnableAudioInput(): boolean {
  return runtimeConfig.features.enableAudioInput;
}

export function getEnableFeedbackButtons(): boolean {
  return runtimeConfig.features.enableFeedbackButtons;
}

export function getEnableConversationThreads(): boolean {
  return runtimeConfig.features.enableConversationThreads;
}

export function getEnableAutocomplete(): boolean {
  return runtimeConfig.features.enableAutocomplete;
}

export function getVoiceSilenceTimeoutMs(): number {
  return Math.max(1000, runtimeConfig.voice.silenceTimeoutMs);
}

export function getVoiceRecognitionLanguage(): string {
  return runtimeConfig.voice.recognitionLanguage;
}

/**
 * Resolve the default adapter id.
 * Picks the first adapter in the configured adapters list.
 */
export function getDefaultAdapterName(): string | null {
  const adapters = runtimeConfig.adapters;
  if (Array.isArray(adapters) && adapters.length > 0) {
    for (const adapter of adapters) {
      const id = typeof adapter?.id === 'string' ? adapter.id.trim() : '';
      if (id) return id;
    }
  }
  return null;
}

export function getShowGitHubStats(): boolean {
  return runtimeConfig.github.showStats;
}

export function getGitHubOwner(): string {
  return runtimeConfig.github.owner;
}

export function getGitHubRepo(): string {
  return runtimeConfig.github.repo;
}

export function getOutOfServiceMessage(): string | null {
  return runtimeConfig.outOfServiceMessage;
}

export function getSettingsAboutMsg(): string {
  return runtimeConfig.application.settingsAboutMsg;
}

export function getEnableAuth(): boolean {
  return runtimeConfig.auth.enabled;
}

export function getIsAuthConfigured(): boolean {
  return Boolean(runtimeConfig.auth.enabled && runtimeConfig.auth.domain && runtimeConfig.auth.clientId);
}

export function getAuthDomain(): string {
  return runtimeConfig.auth.domain;
}

export function getAuthClientId(): string {
  return runtimeConfig.auth.clientId;
}

export function getAuthAudience(): string {
  return runtimeConfig.auth.audience;
}

export function getEnableHeader(): boolean {
  return runtimeConfig.header.enabled;
}

export function getHeaderLogoUrl(): string {
  return runtimeConfig.header.logoUrl;
}

export function getHeaderLogoUrlLight(): string {
  const configured = runtimeConfig.header.logoUrlLight?.trim();
  return configured || DEFAULT_HEADER_LOGO_LIGHT;
}

export function getHeaderLogoUrlDark(): string {
  const configured = runtimeConfig.header.logoUrlDark?.trim();
  return configured || DEFAULT_HEADER_LOGO_DARK;
}

export function getHeaderBrandName(): string {
  return runtimeConfig.header.brandName;
}

export function getHeaderBgColor(): string {
  return runtimeConfig.header.bgColor;
}

export function getHeaderTextColor(): string {
  return runtimeConfig.header.textColor;
}

export function getHeaderShowBorder(): boolean {
  return runtimeConfig.header.showBorder;
}

export function getHeaderNavLinks(): NavLink[] {
  const raw = runtimeConfig.header.navLinks;
  if (Array.isArray(raw)) return raw;
  // Fallback: parse if a JSON string was injected (legacy compat)
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

export function getEnableFooter(): boolean {
  return runtimeConfig.footer.enabled;
}

export function getFooterText(): string {
  return runtimeConfig.footer.text;
}

export function getFooterBgColor(): string {
  return runtimeConfig.footer.bgColor;
}

export function getFooterTextColor(): string {
  return runtimeConfig.footer.textColor;
}

export function getFooterShowBorder(): boolean {
  return runtimeConfig.footer.showBorder;
}

export function getFooterLayout(): 'stacked' | 'inline' {
  return runtimeConfig.footer.layout === 'inline' ? 'inline' : 'stacked';
}

export function getFooterAlign(): 'left' | 'center' {
  return runtimeConfig.footer.align === 'left' ? 'left' : 'center';
}

export function getFooterTopPadding(): 'normal' | 'large' {
  return runtimeConfig.footer.topPadding === 'normal' ? 'normal' : 'large';
}

export function getFooterNavLinks(): NavLink[] {
  const raw = runtimeConfig.footer.navLinks;
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}
