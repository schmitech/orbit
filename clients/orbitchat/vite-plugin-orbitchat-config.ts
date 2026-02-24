/**
 * Vite Plugin: OrbitChat Config
 *
 * Reads orbitchat.yaml from CWD and injects it via `define()`
 * as `import.meta.env.__ORBITCHAT_CONFIG`.
 *
 * Also handles the adapter proxy middleware for dev mode.
 */

import type { Plugin } from 'vite';
import { loadEnv } from 'vite';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { createProxyMiddleware } from 'http-proxy-middleware';
import rateLimit from 'express-rate-limit';
import type { IncomingMessage, ServerResponse, ClientRequest } from 'http';

interface AdapterConfig {
  apiKey: string;
  apiUrl: string;
  name?: string;
  description?: string;
  notes?: string;
  model?: string;
}

interface YamlConfig {
  guestLimits?: { rateLimit?: { enabled?: boolean; windowMs?: number; maxRequests?: number; chat?: { windowMs?: number; maxRequests?: number } } };
  adapters?: Array<{ id: string; name: string; apiUrl?: string; description?: string; notes?: string; model?: string }>;
}

function loadYamlFile(configPath: string): YamlConfig | null {
  try {
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf8');
      return yaml.load(content) as YamlConfig;
    }
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    console.error(`[orbitchat-config] Failed to parse ${configPath}: ${msg}`);
  }
  return null;
}

/**
 * Build adapter map for the proxy: YAML metadata + env secrets.
 *
 * Uses VITE_ADAPTER_KEYS (JSON object: {"id": "Key"}) for secrets.
 * Adapters are keyed by their `id` field. Adapters without an `id` are skipped with a warning.
 */
function loadAdaptersForProxy(yamlAdapters: YamlConfig['adapters'], env: Record<string, string>): Record<string, AdapterConfig> | null {
  const adapters: Record<string, AdapterConfig> = {};
  const defaultApiUrl = 'http://localhost:3000';

  // 1. Start with metadata from YAML, keyed by id
  if (yamlAdapters) {
    for (const ya of yamlAdapters) {
      if (!ya.id) {
        console.warn(`[orbitchat-config] Adapter "${ya.name || '(unnamed)'}" is missing a required 'id' field — skipping.`);
        continue;
      }
      const id = ya.id;
      adapters[id] = {
        apiKey: '', // placeholder
        apiUrl: ya.apiUrl || defaultApiUrl,
        name: ya.name,
        description: ya.description,
        notes: ya.notes,
        model: ya.model,
      };
    }
  }

  // 2. Overlay secrets from VITE_ADAPTER_KEYS (keyed by adapter id)
  const envKeysRaw = env.VITE_ADAPTER_KEYS || process.env.VITE_ADAPTER_KEYS;
  if (envKeysRaw) {
    try {
      const keys = JSON.parse(envKeysRaw);
      for (const [id, value] of Object.entries(keys)) {
        if (!adapters[id]) {
          // Strict mode: only adapters explicitly declared in orbitchat.yaml are allowed.
          continue;
        }
        const isObjectValue = typeof value === 'object' && value !== null;
        const apiKey = isObjectValue
          ? String((value as { apiKey?: unknown; key?: unknown }).apiKey || (value as { apiKey?: unknown; key?: unknown }).key || '')
          : String(value);
        const apiUrl = isObjectValue ? (value as { apiUrl?: unknown }).apiUrl : undefined;
        const description = isObjectValue ? (value as { description?: unknown }).description : undefined;
        const notes = isObjectValue ? (value as { notes?: unknown }).notes : undefined;
        const model = isObjectValue ? (value as { model?: unknown }).model : undefined;
        adapters[id].apiKey = apiKey;
        if (typeof apiUrl === 'string' && apiUrl) adapters[id].apiUrl = apiUrl;
        if (typeof description === 'string') adapters[id].description = description;
        if (typeof notes === 'string') adapters[id].notes = notes;
        if (typeof model === 'string') adapters[id].model = model;
      }
    } catch { /* ignore */ }
  }

  // Filter out any adapters that ended up without an API key
  const finalAdapters: Record<string, AdapterConfig> = {};
  for (const [id, config] of Object.entries(adapters)) {
    if (config.apiKey) {
      finalAdapters[id] = config;
    }
  }

  return Object.keys(finalAdapters).length > 0 ? finalAdapters : null;
}

export function orbitchatConfigPlugin(): Plugin {
  let yamlPath = '';
  let yamlConfig: YamlConfig | null = null;
  let adaptersCache: Record<string, AdapterConfig> | null = null;
  let resolvedEnv: Record<string, string> = {};

  return {
    name: 'orbitchat-config',

    config(_, { mode }) {
      resolvedEnv = loadEnv(mode, process.cwd(), '');
      const configFile = resolvedEnv.ORBITCHAT_CONFIG || process.env.ORBITCHAT_CONFIG;
      yamlPath = configFile
        ? path.resolve(process.cwd(), configFile)
        : path.join(process.cwd(), 'orbitchat.yaml');
      yamlConfig = loadYamlFile(yamlPath);

      if (yamlConfig) {
        console.log(`[orbitchat-config] Loaded config from ${yamlPath}`);
      }

      return {
        define: {
          'import.meta.env.__ORBITCHAT_CONFIG': JSON.stringify(yamlConfig || {}),
        },
      };
    },

    configureServer(server) {
      if (server.httpServer?.setMaxListeners) {
        server.httpServer.setMaxListeners(0);
      }

      adaptersCache = loadAdaptersForProxy(yamlConfig?.adapters, resolvedEnv);

      if (fs.existsSync(yamlPath)) {
        server.watcher.add(yamlPath);
        server.watcher.on('change', (changedPath) => {
          if (path.resolve(changedPath) === path.resolve(yamlPath)) {
            console.log('[orbitchat-config] orbitchat.yaml changed, restarting...');
            server.restart();
          }
        });
      }

      // Guest rate limiting
      const rlConfig = yamlConfig?.guestLimits?.rateLimit;
      if (rlConfig && rlConfig.enabled !== false) {
        const windowMs = rlConfig.windowMs || 60000;
        const maxRequests = rlConfig.maxRequests || 30;
        const chatWindowMs = rlConfig.chat?.windowMs || 60000;
        const chatMaxRequests = rlConfig.chat?.maxRequests || 10;

        const keyGenerator = (req: IncomingMessage) => (req as IncomingMessage & { ip?: string }).ip || req.socket?.remoteAddress || 'unknown';

        const apiLimiter = rateLimit({
          windowMs, max: maxRequests, keyGenerator,
          standardHeaders: 'draft-7', legacyHeaders: false,
          validate: { keyGeneratorIpFallback: false },
          skip: (req) => req.method === 'OPTIONS' || (req.url ?? '').startsWith('/adapters'),
          handler: (_, res) => {
            (res as ServerResponse).writeHead(429, { 'Content-Type': 'application/json' });
            (res as ServerResponse).end(JSON.stringify({
              error: 'Too many requests',
              message: `Rate limit exceeded. Try again in ${Math.ceil(windowMs / 1000)} seconds.`,
              retryAfterMs: windowMs,
            }));
          },
        });

        const chatLimiter = rateLimit({
          windowMs: chatWindowMs, max: chatMaxRequests, keyGenerator,
          standardHeaders: 'draft-7', legacyHeaders: false,
          validate: { keyGeneratorIpFallback: false },
          handler: (_, res) => {
            (res as ServerResponse).writeHead(429, { 'Content-Type': 'application/json' });
            (res as ServerResponse).end(JSON.stringify({
              error: 'Too many requests',
              message: `Chat rate limit exceeded. Try again in ${Math.ceil(chatWindowMs / 1000)} seconds.`,
              retryAfterMs: chatWindowMs,
            }));
          },
        });

        server.middlewares.use('/api', (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.headers.authorization) return next();
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (apiLimiter as any)(req, res, next);
        });
        server.middlewares.use('/api', (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.headers.authorization) return next();
          if (req.method === 'POST' && (/\/chat/i.test(req.url || '') || /\/stream/i.test(req.url || ''))) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return (chatLimiter as any)(req, res, next);
          }
          next();
        });

        console.log(`[orbitchat-config] Guest rate limiting enabled (${maxRequests} req/${windowMs / 1000}s, chat: ${chatMaxRequests} req/${chatWindowMs / 1000}s)`);
      }

      // Fetch model info from adapter backends (lazy, short-lived cache).
      let modelsLastFetchedAt = 0;
      let modelsFetchInFlight: Promise<void> | null = null;
      const MODELS_CACHE_TTL_MS = 30000;

      async function fetchAdapterModels(adapterMap: Record<string, AdapterConfig>, force = false): Promise<void> {
        const now = Date.now();
        if (!force && (now - modelsLastFetchedAt) < MODELS_CACHE_TTL_MS) return;
        if (modelsFetchInFlight) return modelsFetchInFlight;

        modelsFetchInFlight = (async () => {
          const fetches = Object.values(adapterMap).map(async (adapter) => {
            if (!adapter.apiUrl || !adapter.apiKey) return;
            try {
              const url = `${adapter.apiUrl.replace(/\/+$/, '')}/admin/adapters/info`;
              const resp = await fetch(url, {
                headers: { 'X-API-Key': adapter.apiKey }
              });
              if (resp.ok) {
                const info = await resp.json() as { model?: string | null };
                adapter.model = typeof info.model === 'string' ? info.model.trim() || undefined : undefined;
              }
            } catch {
              // Ignore model lookup failures; card renders without model badge.
            }
          });
          await Promise.all(fetches);
          modelsLastFetchedAt = Date.now();
        })().finally(() => {
          modelsFetchInFlight = null;
        });

        return modelsFetchInFlight;
      }

      const buildAdapterList = (adapterMap: Record<string, AdapterConfig>) =>
        Object.keys(adapterMap).map(id => ({
          id,
          name: adapterMap[id]?.name || id,
          description: adapterMap[id]?.description,
          notes: adapterMap[id]?.notes,
          model: adapterMap[id]?.model || null,
        }));

      // Serve /api/adapters
      server.middlewares.use('/api/adapters', (req, res, next) => {
        if (req.method !== 'GET') return next();

        const currentAdapters = adaptersCache || loadAdaptersForProxy(yamlConfig?.adapters, resolvedEnv);
        if (!currentAdapters) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'No adapters configured. Set VITE_ADAPTER_KEYS in .env' }));
          return;
        }

        const cacheControlHeader = typeof req.headers['cache-control'] === 'string' ? req.headers['cache-control'] : '';
        const forceRefresh = req.url?.includes('refresh=1') || cacheControlHeader.includes('no-cache');

        fetchAdapterModels(currentAdapters, forceRefresh).then(() => {
          const adapterList = buildAdapterList(currentAdapters);
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ adapters: adapterList }));
        }).catch(() => {
          const adapterList = buildAdapterList(currentAdapters);
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ adapters: adapterList }));
        });
      });

      // Proxy /api/*
      server.middlewares.use('/api', (req, res, next) => {
        if (req.url?.startsWith('/adapters')) return next();

        const adapterName = req.headers['x-adapter-name'] as string;
        if (!adapterName) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'X-Adapter-Name header is required' }));
          return;
        }

        const currentAdapters = adaptersCache || loadAdaptersForProxy(yamlConfig?.adapters, resolvedEnv);
        const adapter = currentAdapters?.[adapterName];
        if (!adapter) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: `Adapter '${adapterName}' not found` }));
          return;
        }

        const proxy = createProxyMiddleware({
          target: adapter.apiUrl,
          changeOrigin: true,
          pathRewrite: (reqPath: string) => reqPath.startsWith('/files') || reqPath.startsWith('/threads') ? '/api' + reqPath : reqPath,
          headers: { 'X-API-Key': adapter.apiKey },
          on: {
            proxyReq: (proxyReq: ClientRequest, reqIncoming: IncomingMessage) => {
              proxyReq.removeHeader('x-adapter-name');
              proxyReq.setHeader('X-API-Key', adapter.apiKey);
              ['content-type', 'x-session-id', 'x-thread-id', 'accept', 'content-length', 'authorization'].forEach(h => {
                const val = reqIncoming.headers[h];
                if (val) proxyReq.setHeader(h, Array.isArray(val) ? val[0] : val);
              });
            },
            error: (err, _req, resProxy) => {
              console.error('[Vite Proxy] Proxy error:', err);
              if (!(resProxy as ServerResponse).headersSent) {
                (resProxy as ServerResponse).writeHead(500, { 'Content-Type': 'application/json' });
                (resProxy as ServerResponse).end(JSON.stringify({ error: 'Proxy error', message: err.message }));
              }
            },
          },
        });

        proxy(req, res, next);
      });
    },
  };
}
