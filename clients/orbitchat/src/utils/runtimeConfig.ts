/**
 * Runtime Configuration Utility
 *
 * Reads configuration from a single merged object built at startup:
 *  - Vite plugin injects defaults + orbitchat.yaml via import.meta.env.__ORBITCHAT_CONFIG (dev/build)
 *  - CLI injects window.ORBIT_CHAT_CONFIG (production server)
 *  - Secrets come from VITE_AUTH_* env vars
 */

export const DEFAULT_API_URL = 'http://localhost:3000';

export interface NavLink {
  label: string;
  url: string;
}

export interface RuntimeConfig {
  // API Configuration
  apiUrl: string;
  defaultKey: string;
  applicationName: string;
  applicationDescription: string;
  defaultInputPlaceholder: string;
  consoleDebug: boolean;
  locale: string;

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

  // Adapters (for middleware mode)
  adapters?: Array<{
    name: string;
    apiUrl?: string;
    description?: string;
    notes?: string;
  }>;

  // File Upload Limits
  maxFilesPerConversation: number;
  maxFileSizeMB: number;
  maxTotalFiles: number | null;

  // Conversation Limits
  maxConversations: number | null;
  maxMessagesPerConversation: number | null;
  maxMessagesPerThread: number | null;
  maxTotalMessages: number | null;

  // Message Limits
  maxMessageLength: number;

  // Guest Limits (used when enableAuth=true and user is not authenticated)
  guestMaxConversations: number | null;
  guestMaxMessagesPerConversation: number | null;
  guestMaxTotalMessages: number | null;
  guestMaxMessagesPerThread: number | null;
  guestMaxFilesPerConversation: number;
  guestMaxTotalFiles: number | null;
  guestMaxMessageLength: number;
  guestMaxFileSizeMB: number;

  // Settings Page
  settingsAboutMsg: string;

  // Auth Configuration
  enableAuth: boolean;
  authDomain: string;
  authClientId: string;
  authAudience: string;

  // Header Configuration
  enableHeader: boolean;
  headerLogoUrl: string;
  headerBrandName: string;
  headerBgColor: string;
  headerTextColor: string;
  headerShowBorder: boolean;
  headerNavLinks: NavLink[];

  // Footer Configuration
  enableFooter: boolean;
  footerText: string;
  footerBgColor: string;
  footerTextColor: string;
  footerShowBorder: boolean;
  footerLayout: 'stacked' | 'inline';
  footerAlign: 'left' | 'center';
  footerTopPadding: 'normal' | 'large';
  footerNavLinks: NavLink[];
}

declare global {
  interface Window {
    ORBIT_CHAT_CONFIG?: Partial<RuntimeConfig>;
  }
}

/** Default values — single source of truth for the entire app */
export const DEFAULTS: RuntimeConfig = {
  apiUrl: 'http://localhost:3000',
  defaultKey: 'default-key',
  applicationName: 'ORBIT Chat',
  applicationDescription: "Explore ideas with ORBIT's AI copilots, share context, and build together.",
  defaultInputPlaceholder: 'Message ORBIT...',
  consoleDebug: false,
  locale: 'en-US',

  enableUploadButton: false,
  enableAudioOutput: false,
  enableAudioInput: false,
  enableFeedbackButtons: false,
  enableConversationThreads: true,
  enableAutocomplete: false,
  voiceSilenceTimeoutMs: 4000,
  voiceRecognitionLanguage: '',
  showGitHubStats: true,
  outOfServiceMessage: null,

  githubOwner: 'schmitech',
  githubRepo: 'orbit',

  maxFilesPerConversation: 5,
  maxFileSizeMB: 50,
  maxTotalFiles: 100,
  maxConversations: 10,
  maxMessagesPerConversation: 1000,
  maxMessagesPerThread: 1000,
  maxTotalMessages: 10000,
  maxMessageLength: 1000,

  guestMaxConversations: 1,
  guestMaxMessagesPerConversation: 10,
  guestMaxTotalMessages: 10,
  guestMaxMessagesPerThread: 10,
  guestMaxFilesPerConversation: 1,
  guestMaxTotalFiles: 2,
  guestMaxMessageLength: 500,
  guestMaxFileSizeMB: 10,

  settingsAboutMsg: 'ORBIT Chat',

  enableAuth: false,
  authDomain: '',
  authClientId: '',
  authAudience: '',

  enableHeader: false,
  headerLogoUrl: '',
  headerBrandName: '',
  headerBgColor: '',
  headerTextColor: '',
  headerShowBorder: true,
  headerNavLinks: [],

  enableFooter: false,
  footerText: '',
  footerBgColor: '',
  footerTextColor: '',
  footerShowBorder: false,
  footerLayout: 'stacked',
  footerAlign: 'center',
  footerTopPadding: 'large',
  footerNavLinks: [],
};

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
  const viteConfig: Partial<RuntimeConfig> =
    (import.meta.env as Record<string, unknown>).__ORBITCHAT_CONFIG as Partial<RuntimeConfig> ?? {};

  // Config injected by the CLI server at runtime
  const injected: Partial<RuntimeConfig> =
    (typeof window !== 'undefined' && window.ORBIT_CHAT_CONFIG) || {};

  // Auth secrets from VITE_AUTH_* env vars (always available from .env)
  const secrets: Partial<RuntimeConfig> = {};
  const authDomain = import.meta.env.VITE_AUTH_DOMAIN;
  const authClientId = import.meta.env.VITE_AUTH_CLIENT_ID;
  const authAudience = import.meta.env.VITE_AUTH_AUDIENCE;
  if (authDomain) secrets.authDomain = authDomain;
  if (authClientId) secrets.authClientId = authClientId;
  if (authAudience) secrets.authAudience = authAudience;

  const merged = { ...DEFAULTS, ...viteConfig, ...injected, ...secrets };

  // Normalize outOfServiceMessage
  merged.outOfServiceMessage = normalizeOutOfServiceMessage(merged.outOfServiceMessage);

  return merged;
}

export const runtimeConfig: RuntimeConfig = buildRuntimeConfig();

// --- Getter functions (thin pass-throughs) ---

export function getApiUrl(): string {
  return runtimeConfig.apiUrl;
}

export function resolveApiUrl(url?: string | null): string {
  const trimmed = url?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : getApiUrl();
}

export function getDefaultKey(): string {
  return runtimeConfig.defaultKey;
}

export function getApplicationName(): string {
  return runtimeConfig.applicationName;
}

export function getApplicationDescription(): string {
  return runtimeConfig.applicationDescription;
}

export function getDefaultInputPlaceholder(): string {
  return runtimeConfig.defaultInputPlaceholder;
}

export function getConsoleDebug(): boolean {
  return runtimeConfig.consoleDebug;
}

export function getLocale(): string {
  return runtimeConfig.locale;
}

export function getEnableUploadButton(): boolean {
  return runtimeConfig.enableUploadButton;
}

export function getEnableAudioOutput(): boolean {
  return runtimeConfig.enableAudioOutput;
}

export function getEnableAudioInput(): boolean {
  return runtimeConfig.enableAudioInput;
}

export function getEnableFeedbackButtons(): boolean {
  return runtimeConfig.enableFeedbackButtons;
}

export function getEnableConversationThreads(): boolean {
  return runtimeConfig.enableConversationThreads;
}

export function getEnableAutocomplete(): boolean {
  return runtimeConfig.enableAutocomplete;
}

export function getVoiceSilenceTimeoutMs(): number {
  return Math.max(1000, runtimeConfig.voiceSilenceTimeoutMs);
}

export function getVoiceRecognitionLanguage(): string {
  return runtimeConfig.voiceRecognitionLanguage;
}

/**
 * Resolve the default adapter name.
 * Falls back to the first adapter in the adapters list when the key is the placeholder.
 */
export function getDefaultAdapterName(): string | null {
  const adapterName = runtimeConfig.defaultKey?.trim();
  if (adapterName && adapterName !== 'default-key') {
    return adapterName;
  }

  // Try first configured adapter
  const adapters = runtimeConfig.adapters;
  if (Array.isArray(adapters)) {
    for (const adapter of adapters) {
      const name = typeof adapter?.name === 'string' ? adapter.name.trim() : '';
      if (name) return name;
    }
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
  return runtimeConfig.outOfServiceMessage;
}

export function getSettingsAboutMsg(): string {
  return runtimeConfig.settingsAboutMsg;
}

export function getEnableAuth(): boolean {
  return runtimeConfig.enableAuth;
}

export function getIsAuthConfigured(): boolean {
  return Boolean(runtimeConfig.enableAuth && runtimeConfig.authDomain && runtimeConfig.authClientId);
}

export function getAuthDomain(): string {
  return runtimeConfig.authDomain;
}

export function getAuthClientId(): string {
  return runtimeConfig.authClientId;
}

export function getAuthAudience(): string {
  return runtimeConfig.authAudience;
}

export function getEnableHeader(): boolean {
  return runtimeConfig.enableHeader;
}

export function getHeaderLogoUrl(): string {
  return runtimeConfig.headerLogoUrl;
}

export function getHeaderBrandName(): string {
  return runtimeConfig.headerBrandName;
}

export function getHeaderBgColor(): string {
  return runtimeConfig.headerBgColor;
}

export function getHeaderTextColor(): string {
  return runtimeConfig.headerTextColor;
}

export function getHeaderShowBorder(): boolean {
  return runtimeConfig.headerShowBorder;
}

export function getHeaderNavLinks(): NavLink[] {
  const raw = runtimeConfig.headerNavLinks;
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
  return runtimeConfig.enableFooter;
}

export function getFooterText(): string {
  return runtimeConfig.footerText;
}

export function getFooterBgColor(): string {
  return runtimeConfig.footerBgColor;
}

export function getFooterTextColor(): string {
  return runtimeConfig.footerTextColor;
}

export function getFooterShowBorder(): boolean {
  return runtimeConfig.footerShowBorder;
}

export function getFooterLayout(): 'stacked' | 'inline' {
  return runtimeConfig.footerLayout === 'inline' ? 'inline' : 'stacked';
}

export function getFooterAlign(): 'left' | 'center' {
  return runtimeConfig.footerAlign === 'left' ? 'left' : 'center';
}

export function getFooterTopPadding(): 'normal' | 'large' {
  return runtimeConfig.footerTopPadding === 'normal' ? 'normal' : 'large';
}

export function getFooterNavLinks(): NavLink[] {
  const raw = runtimeConfig.footerNavLinks;
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
