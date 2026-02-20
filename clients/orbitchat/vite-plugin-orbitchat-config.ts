/**
 * Vite Plugin: OrbitChat Config
 *
 * Reads orbitchat.yaml from CWD, flattens it into RuntimeConfig shape,
 * and injects it via `define()` as `import.meta.env.__ORBITCHAT_CONFIG`.
 *
 * Also handles the adapter proxy middleware for dev mode (previously in vite-plugin-adapters.ts).
 */

import type { Plugin } from 'vite';
import { loadEnv } from 'vite';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { createProxyMiddleware } from 'http-proxy-middleware';
import rateLimit from 'express-rate-limit';
import type { Options } from 'http-proxy-middleware';
import type { IncomingMessage, ServerResponse, ClientRequest } from 'http';

// ---- Inline flatten logic (Node-side, can't import .ts from src/) ----

interface NavLink {
  label: string;
  url: string;
}

interface AdapterEntry {
  name: string;
  apiKey?: string;
  apiUrl?: string;
  description?: string;
  summary?: string;
  notes?: string;
}

interface AdapterConfig {
  apiKey: string;
  apiUrl: string;
  description?: string;
  notes?: string;
  model?: string;
}

// Minimal YAML shape (mirrors OrbitChatYamlConfig in src/utils/yamlConfig.ts)
interface YamlConfig {
  application?: { name?: string; description?: string; inputPlaceholder?: string; settingsAboutMsg?: string; locale?: string };
  api?: { url?: string; defaultAdapter?: string };
  debug?: { consoleDebug?: boolean };
  features?: { enableUpload?: boolean; enableAudioOutput?: boolean; enableAudioInput?: boolean; enableFeedbackButtons?: boolean; enableConversationThreads?: boolean; enableAutocomplete?: boolean };
  voice?: { silenceTimeoutMs?: number; recognitionLanguage?: string };
  github?: { showStats?: boolean; owner?: string; repo?: string };
  outOfServiceMessage?: string | null;
  limits?: { files?: { perConversation?: number; maxSizeMB?: number; totalFiles?: number }; conversations?: { maxConversations?: number; messagesPerConversation?: number; messagesPerThread?: number; totalMessages?: number }; messages?: { maxLength?: number } };
  guestLimits?: { files?: { perConversation?: number; maxSizeMB?: number; totalFiles?: number }; conversations?: { maxConversations?: number; messagesPerConversation?: number; messagesPerThread?: number; totalMessages?: number }; messages?: { maxLength?: number }; rateLimit?: { enabled?: boolean; windowMs?: number; maxRequests?: number; chat?: { windowMs?: number; maxRequests?: number } } };
  auth?: { enabled?: boolean };
  header?: { enabled?: boolean; logoUrl?: string; brandName?: string; bgColor?: string; textColor?: string; showBorder?: boolean; navLinks?: NavLink[] };
  footer?: { enabled?: boolean; text?: string; bgColor?: string; textColor?: string; showBorder?: boolean; layout?: 'stacked' | 'inline'; align?: 'left' | 'center'; topPadding?: 'normal' | 'large'; navLinks?: NavLink[] };
  adapters?: Array<{ name: string; apiUrl?: string; description?: string; notes?: string }>;
}

function flattenYaml(y: YamlConfig): Record<string, unknown> {
  const f: Record<string, unknown> = {};
  if (y.application) {
    const a = y.application;
    if (a.name !== undefined) f.applicationName = a.name;
    if (a.description !== undefined) f.applicationDescription = a.description;
    if (a.inputPlaceholder !== undefined) f.defaultInputPlaceholder = a.inputPlaceholder;
    if (a.settingsAboutMsg !== undefined) f.settingsAboutMsg = a.settingsAboutMsg;
    if (a.locale !== undefined) f.locale = a.locale;
  }
  if (y.api) {
    if (y.api.url !== undefined) f.apiUrl = y.api.url;
    if (y.api.defaultAdapter !== undefined) f.defaultKey = y.api.defaultAdapter;
  }
  if (y.debug) {
    if (y.debug.consoleDebug !== undefined) f.consoleDebug = y.debug.consoleDebug;
  }
  if (y.features) {
    const fe = y.features;
    if (fe.enableUpload !== undefined) f.enableUploadButton = fe.enableUpload;
    if (fe.enableAudioOutput !== undefined) f.enableAudioOutput = fe.enableAudioOutput;
    if (fe.enableAudioInput !== undefined) f.enableAudioInput = fe.enableAudioInput;
    if (fe.enableFeedbackButtons !== undefined) f.enableFeedbackButtons = fe.enableFeedbackButtons;
    if (fe.enableConversationThreads !== undefined) f.enableConversationThreads = fe.enableConversationThreads;
    if (fe.enableAutocomplete !== undefined) f.enableAutocomplete = fe.enableAutocomplete;
  }
  if (y.voice) {
    if (y.voice.silenceTimeoutMs !== undefined) f.voiceSilenceTimeoutMs = y.voice.silenceTimeoutMs;
    if (y.voice.recognitionLanguage !== undefined) f.voiceRecognitionLanguage = y.voice.recognitionLanguage;
  }
  if (y.github) {
    if (y.github.showStats !== undefined) f.showGitHubStats = y.github.showStats;
    if (y.github.owner !== undefined) f.githubOwner = y.github.owner;
    if (y.github.repo !== undefined) f.githubRepo = y.github.repo;
  }
  if (y.outOfServiceMessage !== undefined) f.outOfServiceMessage = y.outOfServiceMessage;
  if (y.limits) {
    const l = y.limits;
    if (l.files) {
      if (l.files.perConversation !== undefined) f.maxFilesPerConversation = l.files.perConversation;
      if (l.files.maxSizeMB !== undefined) f.maxFileSizeMB = l.files.maxSizeMB;
      if (l.files.totalFiles !== undefined) f.maxTotalFiles = l.files.totalFiles;
    }
    if (l.conversations) {
      if (l.conversations.maxConversations !== undefined) f.maxConversations = l.conversations.maxConversations;
      if (l.conversations.messagesPerConversation !== undefined) f.maxMessagesPerConversation = l.conversations.messagesPerConversation;
      if (l.conversations.messagesPerThread !== undefined) f.maxMessagesPerThread = l.conversations.messagesPerThread;
      if (l.conversations.totalMessages !== undefined) f.maxTotalMessages = l.conversations.totalMessages;
    }
    if (l.messages) {
      if (l.messages.maxLength !== undefined) f.maxMessageLength = l.messages.maxLength;
    }
  }
  if (y.guestLimits) {
    const g = y.guestLimits;
    if (g.files) {
      if (g.files.perConversation !== undefined) f.guestMaxFilesPerConversation = g.files.perConversation;
      if (g.files.maxSizeMB !== undefined) f.guestMaxFileSizeMB = g.files.maxSizeMB;
      if (g.files.totalFiles !== undefined) f.guestMaxTotalFiles = g.files.totalFiles;
    }
    if (g.conversations) {
      if (g.conversations.maxConversations !== undefined) f.guestMaxConversations = g.conversations.maxConversations;
      if (g.conversations.messagesPerConversation !== undefined) f.guestMaxMessagesPerConversation = g.conversations.messagesPerConversation;
      if (g.conversations.messagesPerThread !== undefined) f.guestMaxMessagesPerThread = g.conversations.messagesPerThread;
      if (g.conversations.totalMessages !== undefined) f.guestMaxTotalMessages = g.conversations.totalMessages;
    }
    if (g.messages) {
      if (g.messages.maxLength !== undefined) f.guestMaxMessageLength = g.messages.maxLength;
    }
  }
  if (y.auth) {
    if (y.auth.enabled !== undefined) f.enableAuth = y.auth.enabled;
  }
  if (y.header) {
    const h = y.header;
    if (h.enabled !== undefined) f.enableHeader = h.enabled;
    if (h.logoUrl !== undefined) f.headerLogoUrl = h.logoUrl;
    if (h.brandName !== undefined) f.headerBrandName = h.brandName;
    if (h.bgColor !== undefined) f.headerBgColor = h.bgColor;
    if (h.textColor !== undefined) f.headerTextColor = h.textColor;
    if (h.showBorder !== undefined) f.headerShowBorder = h.showBorder;
    if (h.navLinks !== undefined) f.headerNavLinks = h.navLinks;
  }
  if (y.footer) {
    const ft = y.footer;
    if (ft.enabled !== undefined) f.enableFooter = ft.enabled;
    if (ft.text !== undefined) f.footerText = ft.text;
    if (ft.bgColor !== undefined) f.footerBgColor = ft.bgColor;
    if (ft.textColor !== undefined) f.footerTextColor = ft.textColor;
    if (ft.showBorder !== undefined) f.footerShowBorder = ft.showBorder;
    if (ft.layout !== undefined) f.footerLayout = ft.layout;
    if (ft.align !== undefined) f.footerAlign = ft.align;
    if (ft.topPadding !== undefined) f.footerTopPadding = ft.topPadding;
    if (ft.navLinks !== undefined) f.footerNavLinks = ft.navLinks;
  }
  if (y.adapters !== undefined) {
    // Strip apiKey from adapter entries before sending to the browser
    f.adapters = y.adapters.map(a => ({
      name: a.name,
      ...(a.apiUrl ? { apiUrl: a.apiUrl } : {}),
      ...(a.description ? { description: a.description } : {}),
      ...(a.notes ? { notes: a.notes } : {}),
    }));
  }
  return f;
}

// ---- YAML file loading ----

function loadYamlFile(configPath: string): YamlConfig | null {
  try {
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf8');
      const parsed = yaml.load(content);
      if (parsed && typeof parsed === 'object') {
        return parsed as YamlConfig;
      }
    }
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.error(`[orbitchat-config] Failed to parse ${configPath}: ${msg}`);
  }
  return null;
}

// ---- Adapter proxy helpers ----

function loadAdaptersFromEnvAndYaml(yamlAdapters: YamlConfig['adapters'], env: Record<string, string>): Record<string, AdapterConfig> | null {
  // Parse VITE_ADAPTERS env var for secrets (apiKey)
  const envAdaptersRaw = env.VITE_ADAPTERS || process.env.VITE_ADAPTERS;
  let envAdapters: AdapterEntry[] = [];
  if (envAdaptersRaw) {
    try {
      const parsed = JSON.parse(envAdaptersRaw);
      if (Array.isArray(parsed)) envAdapters = parsed;
    } catch { /* ignore */ }
  }

  // Build adapter map: YAML metadata + env secrets
  const adapters: Record<string, AdapterConfig> = {};

  // Start with env adapters (they have apiKey)
  for (const entry of envAdapters) {
    if (entry.name && typeof entry.name === 'string') {
      adapters[entry.name] = {
        apiKey: entry.apiKey || 'default-key',
        apiUrl: entry.apiUrl || 'http://localhost:3000',
        description: entry.description || entry.summary,
        notes: entry.notes,
      };
    }
  }

  // Overlay YAML adapter metadata (description, notes, apiUrl) but NOT apiKey
  if (yamlAdapters) {
    for (const ya of yamlAdapters) {
      if (!ya.name) continue;
      if (adapters[ya.name]) {
        // Merge YAML metadata into existing env adapter
        if (ya.description) adapters[ya.name].description = ya.description;
        if (ya.notes) adapters[ya.name].notes = ya.notes;
        if (ya.apiUrl) adapters[ya.name].apiUrl = ya.apiUrl;
      }
      // Don't create adapters from YAML alone — they need apiKey from env
    }
  }

  return Object.keys(adapters).length > 0 ? adapters : null;
}

// ---- Plugin ----

export function orbitchatConfigPlugin(): Plugin {
  const yamlPath = path.join(process.cwd(), 'orbitchat.yaml');
  let yamlConfig: YamlConfig | null = null;
  let adaptersCache: Record<string, AdapterConfig> | null = null;
  let resolvedEnv: Record<string, string> = {};

  return {
    name: 'orbitchat-config',

    config(_, { mode }) {
      resolvedEnv = loadEnv(mode, process.cwd(), '');

      // Load YAML config
      yamlConfig = loadYamlFile(yamlPath);
      if (yamlConfig) {
        console.log(`[orbitchat-config] Loaded config from ${yamlPath}`);
      }

      // Flatten YAML into RuntimeConfig shape
      const flatConfig = yamlConfig ? flattenYaml(yamlConfig) : {};

      return {
        define: {
          'import.meta.env.__ORBITCHAT_CONFIG': JSON.stringify(flatConfig),
        },
      };
    },

    configureServer(server) {
      if (server.httpServer?.setMaxListeners) {
        server.httpServer.setMaxListeners(0);
      }

      // Load adapters (YAML metadata + env secrets)
      adaptersCache = loadAdaptersFromEnvAndYaml(yamlConfig?.adapters, resolvedEnv);

      // Watch orbitchat.yaml for changes
      if (fs.existsSync(yamlPath)) {
        server.watcher.add(yamlPath);
        server.watcher.on('change', (changedPath) => {
          if (path.resolve(changedPath) === path.resolve(yamlPath)) {
            console.log('[orbitchat-config] orbitchat.yaml changed, restarting...');
            server.restart();
          }
        });
      }

      // Guest rate limiting (server-only, never sent to browser). Skips authenticated requests.
      const rlConfig = yamlConfig?.guestLimits?.rateLimit;
      if (rlConfig && rlConfig.enabled !== false) {
        const windowMs = rlConfig.windowMs || 60000;
        const maxRequests = rlConfig.maxRequests || 30;
        const chatWindowMs = rlConfig.chat?.windowMs || 60000;
        const chatMaxRequests = rlConfig.chat?.maxRequests || 10;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- connect's IncomingMessage lacks .ip; express adds it at runtime
        const keyGenerator = (req: IncomingMessage) => (req as Record<string, any>).ip || req.socket?.remoteAddress || 'unknown';

        const apiLimiter = rateLimit({
          windowMs,
          max: maxRequests,
          keyGenerator,
          standardHeaders: 'draft-7',
          legacyHeaders: false,
          validate: { default: true, keyGeneratorIpFallback: false },
          skip: (req) => req.method === 'OPTIONS' || (req.url ?? '').startsWith('/adapters'),
          handler: (_req, res) => {
            const retryAfterMs = windowMs;
            (res as ServerResponse).writeHead(429, { 'Content-Type': 'application/json' });
            (res as ServerResponse).end(JSON.stringify({
              error: 'Too many requests',
              message: `Rate limit exceeded. Try again in ${Math.ceil(retryAfterMs / 1000)} seconds.`,
              retryAfterMs,
            }));
          },
        });

        const chatLimiter = rateLimit({
          windowMs: chatWindowMs,
          max: chatMaxRequests,
          keyGenerator,
          standardHeaders: 'draft-7',
          legacyHeaders: false,
          validate: { default: true, keyGeneratorIpFallback: false },
          handler: (_req, res) => {
            const retryAfterMs = chatWindowMs;
            (res as ServerResponse).writeHead(429, { 'Content-Type': 'application/json' });
            (res as ServerResponse).end(JSON.stringify({
              error: 'Too many requests',
              message: `Chat rate limit exceeded. Try again in ${Math.ceil(retryAfterMs / 1000)} seconds.`,
              retryAfterMs,
            }));
          },
        });

        // Skip authenticated requests (they have their own ORBIT-side limits)
        server.middlewares.use('/api', (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.headers.authorization) return next();
          // eslint-disable-next-line @typescript-eslint/no-explicit-any -- express-rate-limit middleware is compatible with connect
          (apiLimiter as any)(req, res, next);
        });
        server.middlewares.use('/api', (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.headers.authorization) return next();
          if (req.method === 'POST' && (/\/chat/i.test(req.url || '') || /\/stream/i.test(req.url || ''))) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any -- express-rate-limit middleware is compatible with connect
            return (chatLimiter as any)(req, res, next);
          }
          next();
        });

        console.log(`[orbitchat-config] Guest rate limiting enabled (${maxRequests} req/${windowMs / 1000}s, chat: ${chatMaxRequests} req/${chatWindowMs / 1000}s)`);
      }

      // Fetch model info from ORBIT backend for each adapter (lazy, short-lived cache).
      let modelsLastFetchedAt = 0;
      let modelsFetchInFlight: Promise<void> | null = null;
      const MODELS_CACHE_TTL_MS = 30000;
      async function fetchAdapterModels(adapterMap: Record<string, AdapterConfig>, force = false) {
        const now = Date.now();
        if (!force && (now - modelsLastFetchedAt) < MODELS_CACHE_TTL_MS) return;
        if (modelsFetchInFlight) return modelsFetchInFlight;

        modelsFetchInFlight = (async () => {
          const fetches = Object.entries(adapterMap).map(async ([, adapter]) => {
          if (!adapter.apiUrl || !adapter.apiKey) return;
          try {
            const url = `${adapter.apiUrl.replace(/\/+$/, '')}/admin/adapters/info`;
            const resp = await fetch(url, {
              headers: { 'X-API-Key': adapter.apiKey },
              signal: AbortSignal.timeout(5000),
            });
            if (resp.ok) {
              const info = await resp.json() as { model?: string };
              adapter.model = typeof info.model === 'string' ? info.model.trim() || undefined : undefined;
            }
          } catch {
            // Silently ignore — model will be omitted
          }
          });
          await Promise.all(fetches);
          modelsLastFetchedAt = Date.now();
        })().finally(() => {
          modelsFetchInFlight = null;
        });

        return modelsFetchInFlight;
      }

      // Serve /api/adapters endpoint
      server.middlewares.use('/api/adapters', (req, res, next) => {
        if (req.method !== 'GET') return next();

        const currentAdapters = adaptersCache || loadAdaptersFromEnvAndYaml(yamlConfig?.adapters, resolvedEnv);
        if (!currentAdapters) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'No adapters configured. Set VITE_ADAPTERS env var or add adapters to orbitchat.yaml.' }));
          return;
        }

        const cacheControlHeader = typeof req.headers['cache-control'] === 'string' ? req.headers['cache-control'] : '';
        const forceRefresh = req.url?.includes('refresh=1') || cacheControlHeader.includes('no-cache');

        fetchAdapterModels(currentAdapters, forceRefresh).then(() => {
          const adapterList = Object.keys(currentAdapters).map(name => ({
            name,
            description: currentAdapters[name]?.description,
            notes: currentAdapters[name]?.notes,
            model: currentAdapters[name]?.model || null,
          }));

          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ adapters: adapterList }));
        }).catch(() => {
          const adapterList = Object.keys(currentAdapters).map(name => ({
            name,
            description: currentAdapters[name]?.description,
            notes: currentAdapters[name]?.notes,
            model: currentAdapters[name]?.model || null,
          }));
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ adapters: adapterList }));
        });
      });

      // Proxy /api/* requests
      server.middlewares.use('/api', (req, res, next) => {
        if (req.url?.startsWith('/adapters')) return next();

        const adapterName = req.headers['x-adapter-name'] as string;
        if (!adapterName) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'X-Adapter-Name header is required' }));
          return;
        }

        const currentAdapters = adaptersCache || loadAdaptersFromEnvAndYaml(yamlConfig?.adapters, resolvedEnv);
        if (!currentAdapters) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'No adapters configured' }));
          return;
        }

        const adapter = currentAdapters[adapterName];
        if (!adapter) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: `Adapter '${adapterName}' not found` }));
          return;
        }

        const proxyOptions: Options = {
          target: adapter.apiUrl,
          changeOrigin: true,
          pathRewrite: (reqPath: string) => {
            if (reqPath.startsWith('/files') || reqPath.startsWith('/threads')) {
              return '/api' + reqPath;
            }
            return reqPath;
          },
          headers: {
            'X-API-Key': adapter.apiKey,
          },
          selfHandleResponse: false,
          ws: false,
          on: {
            proxyReq: (proxyReq: ClientRequest, proxyReqIncoming: IncomingMessage) => {
              proxyReq.removeHeader('x-adapter-name');
              proxyReq.setHeader('X-API-Key', adapter.apiKey);
              const headersToPreserve = ['content-type', 'x-session-id', 'x-thread-id', 'accept', 'content-length'];
              headersToPreserve.forEach(header => {
                const value = proxyReqIncoming.headers[header];
                if (value) {
                  if (typeof value === 'string') {
                    proxyReq.setHeader(header, value);
                  } else if (Array.isArray(value) && value.length > 0) {
                    proxyReq.setHeader(header, value[0]);
                  }
                }
              });
              Object.keys(proxyReqIncoming.headers).forEach(key => {
                const lowerKey = key.toLowerCase();
                if (!['x-adapter-name', 'host', 'connection', 'transfer-encoding'].includes(lowerKey)) {
                  const value = proxyReqIncoming.headers[key];
                  if (value) {
                    if (typeof value === 'string' && !headersToPreserve.includes(lowerKey)) {
                      proxyReq.setHeader(key, value);
                    } else if (Array.isArray(value) && value.length > 0 && !headersToPreserve.includes(lowerKey)) {
                      proxyReq.setHeader(key, value[0]);
                    }
                  }
                }
              });
            },
            proxyRes: (proxyRes: IncomingMessage) => {
              if (proxyRes.headers) {
                proxyRes.headers['access-control-allow-origin'] = '*';
                proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
                proxyRes.headers['access-control-allow-headers'] = 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';
              }
            },
            error: (err, _req, res) => {
              console.error('[Vite Proxy] Proxy error:', err);
              if ('headersSent' in res && !res.headersSent) {
                (res as ServerResponse).writeHead(500, { 'Content-Type': 'application/json' });
                (res as ServerResponse).end(JSON.stringify({ error: 'Proxy error', message: err.message }));
              }
            },
          },
        };

        const proxy = createProxyMiddleware(proxyOptions);
        proxy(req, res, next);
      });
    },
  };
}
