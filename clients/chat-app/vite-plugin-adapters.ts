import type { Plugin } from 'vite';
import { loadEnv } from 'vite';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { Options } from 'http-proxy-middleware';
import type { IncomingMessage, ServerResponse, ClientRequest } from 'http';

interface AdapterConfig {
  apiKey: string;
  apiUrl: string;
  description?: string;
  notes?: string;
}

let adaptersCache: Record<string, AdapterConfig> | null = null;
let loadedEnv: Record<string, string> | null = null;

interface AdapterEntry {
  name: string;
  apiKey?: string;
  apiUrl?: string;
  description?: string;
  summary?: string;
  notes?: string;
}

function loadAdaptersFromEnv(): Record<string, AdapterConfig> | null {
  // Load env vars using Vite's loadEnv if not already loaded
  if (!loadedEnv) {
    const mode = process.env.NODE_ENV || 'development';
    loadedEnv = loadEnv(mode, process.cwd(), '');
  }

  const envValue = loadedEnv.VITE_ADAPTERS || process.env.VITE_ADAPTERS;
  if (!envValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(envValue) as AdapterEntry[];
    if (!Array.isArray(parsed)) {
      return null;
    }

    const adapters: Record<string, AdapterConfig> = {};
    for (const entry of parsed) {
      if (entry.name && typeof entry.name === 'string') {
        adapters[entry.name] = {
          apiKey: entry.apiKey || 'default-key',
          apiUrl: entry.apiUrl || 'http://localhost:3000',
          description: entry.description || entry.summary,
          notes: entry.notes,
        };
      }
    }

    if (Object.keys(adapters).length > 0) {
      console.debug('[adapters-plugin] Loaded adapters from VITE_ADAPTERS env var');
      return adapters;
    }
  } catch (error) {
    console.warn('[adapters-plugin] Failed to parse VITE_ADAPTERS:', error);
  }

  return null;
}

function loadAdaptersConfig(): Record<string, AdapterConfig> | null {
  if (adaptersCache) {
    return adaptersCache;
  }

  // First try VITE_ADAPTERS environment variable
  const envAdapters = loadAdaptersFromEnv();
  if (envAdapters) {
    adaptersCache = envAdapters;
    return adaptersCache;
  }

  // Then try to load adapters.yaml from common locations
  const configPaths = [
    path.join(process.cwd(), 'adapters.yaml'),
    path.join(__dirname, 'adapters.yaml'),
    path.join(process.cwd(), '..', 'adapters.yaml'),
  ];

  for (const configPath of configPaths) {
    try {
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf8');
        const config = yaml.load(content) as { adapters?: Record<string, AdapterConfig> };
        if (config && config.adapters) {
          const normalized: Record<string, AdapterConfig> = {};
          for (const [name, adapter] of Object.entries(config.adapters)) {
            normalized[name] = {
              apiKey: adapter.apiKey || 'default-key',
              apiUrl: adapter.apiUrl || 'http://localhost:3000',
              description: adapter.description,
              notes: adapter.notes,
            };
          }
          adaptersCache = normalized;
          console.log(`[adapters-plugin] Loaded adapters from ${configPath}`);
          return adaptersCache;
        }
      }
    } catch (error) {
      console.warn(`Failed to read adapters from ${configPath}:`, error);
    }
  }

  return null;
}

/**
 * Vite plugin to serve adapters endpoint and proxy requests during development
 * This allows the dev server to handle middleware endpoints without needing Express
 */
export function adaptersPlugin(): Plugin {
  return {
    name: 'adapters-plugin',
    configureServer(server) {
      if (server.httpServer?.setMaxListeners) {
        server.httpServer.setMaxListeners(0);
      }
      // Serve /api/adapters endpoint
      server.middlewares.use('/api/adapters', (req, res, next) => {
        if (req.method !== 'GET') {
          return next();
        }

        try {
          const adapters = loadAdaptersConfig();

          if (!adapters) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'adapters.yaml not found. Please create adapters.yaml in the project root.' }));
            return;
          }

          // Return adapter list without exposing API keys or URLs
        const adapterList = Object.keys(adapters).map(name => ({
          name,
          description: adapters[name]?.description,
          notes: adapters[name]?.notes,
        }));

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ adapters: adapterList }));
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to load adapters';
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: message }));
        }
      });

      // Proxy /api/* requests (security: no "proxy" in URL path)
      // Note: /api/adapters is handled above, this catches other /api/* routes
      server.middlewares.use('/api', (req, res, next) => {
        // Skip /api/adapters - handled by the route above
        if (req.url?.startsWith('/adapters')) {
          return next();
        }
        const adapterName = req.headers['x-adapter-name'] as string;
        
        if (!adapterName) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'X-Adapter-Name header is required' }));
          return;
        }

        const adapters = loadAdaptersConfig();
        if (!adapters) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'adapters.yaml not found' }));
          return;
        }

        const adapter = adapters[adapterName];
        if (!adapter) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: `Adapter '${adapterName}' not found` }));
          return;
        }

        // Create proxy middleware
        const proxyOptions: Options = {
          target: adapter.apiUrl,
          changeOrigin: true,
          // Restore /api prefix for backend paths that need it (files, threads)
          pathRewrite: (path: string) => {
            if (path.startsWith('/files') || path.startsWith('/threads')) {
              return '/api' + path;
            }
            return path;
          },
          headers: {
            'X-API-Key': adapter.apiKey,
          },
          // Enable streaming for SSE responses (don't self-handle, let proxy stream directly)
          selfHandleResponse: false,
          ws: false,
          on: {
            proxyReq: (proxyReq: ClientRequest, proxyReqIncoming: IncomingMessage) => {
              // Remove adapter name header
              proxyReq.removeHeader('x-adapter-name');
              // Ensure API key is set (use X-API-Key to match backend expectation)
              proxyReq.setHeader('X-API-Key', adapter.apiKey);
              
              // Preserve important headers
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
              // Copy all other headers
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
              // Handle CORS
              if (proxyRes.headers) {
                proxyRes.headers['access-control-allow-origin'] = '*';
                proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
                proxyRes.headers['access-control-allow-headers'] = 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';
              }
            },
            error: (err, _req, res) => {
              console.error('[Vite Proxy] Proxy error:', err);
              // res can be ServerResponse or Socket; only write if it's a ServerResponse
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
