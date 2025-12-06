import type { Plugin } from 'vite';
import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'js-yaml';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { Options } from 'http-proxy-middleware';
import type { IncomingMessage, ServerResponse, ClientRequest } from 'http';

let adaptersCache: Record<string, { apiKey: string; apiUrl: string }> | null = null;

function loadAdaptersConfig(): Record<string, { apiKey: string; apiUrl: string }> | null {
  if (adaptersCache) {
    return adaptersCache;
  }

  // Try to load adapters.yaml from common locations
  const configPaths = [
    path.join(process.cwd(), 'adapters.yaml'),
    path.join(__dirname, 'adapters.yaml'),
    path.join(process.cwd(), '..', 'adapters.yaml'),
  ];

  for (const configPath of configPaths) {
    try {
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf8');
        const config = yaml.load(content) as { adapters?: Record<string, { apiKey: string; apiUrl: string }> };
        if (config && config.adapters) {
          adaptersCache = config.adapters;
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

          // Return adapter list without exposing API keys
          const adapterList = Object.keys(adapters).map(name => ({
            name,
            apiUrl: adapters[name].apiUrl,
          }));

          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ adapters: adapterList }));
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to load adapters';
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: message }));
        }
      });

      // Proxy /api/proxy/* requests
      server.middlewares.use('/api/proxy', (req, res, next) => {
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
          pathRewrite: {
            '^/api/proxy': '',
          },
          headers: {
            'X-API-Key': adapter.apiKey,
          },
          // Enable streaming for SSE responses
          selfHandleResponse: false,
          // Don't buffer the response - stream it directly
          buffer: false,
          onProxyReq: (proxyReq: ClientRequest, proxyReqIncoming: IncomingMessage) => {
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
          onProxyRes: (proxyRes: IncomingMessage) => {
            // Handle CORS
            if (proxyRes.headers) {
              proxyRes.headers['access-control-allow-origin'] = '*';
              proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
              proxyRes.headers['access-control-allow-headers'] = 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';
            }
          },
          onError: (err: Error, _req: IncomingMessage, res: ServerResponse) => {
            console.error('[Vite Proxy] Proxy error:', err);
            if (!res.headersSent) {
              res.writeHead(500, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: 'Proxy error', message: err.message }));
            }
          },
          ws: false,
          logLevel: 'silent',
        };

        const proxy = createProxyMiddleware(proxyOptions);

        proxy(req, res, next);
      });
    },
  };
}
