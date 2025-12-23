/**
 * Proxy Middleware
 *
 * Extracted and adapted from orbitchat.js (lines 315-411)
 * Handles routing API requests through adapters with API key injection
 */

import { createProxyMiddleware, Options } from 'http-proxy-middleware';
import type { RequestHandler, Request, Response, NextFunction } from 'express';
import type { AdapterConfig } from '../config/types.js';
import { getLogger } from '../utils/logger.js';

// Map of adapter name to proxy middleware
// Using RequestHandler type for compatibility with Express
type ProxyHandler = RequestHandler;
type ProxyInstances = Map<string, ProxyHandler>;

/**
 * Create proxy instances for all adapters
 * Pre-creating proxies avoids memory leaks from accumulating event listeners
 */
export function createProxyInstances(adapters: AdapterConfig[]): ProxyInstances {
  const logger = getLogger();
  const proxyInstances: ProxyInstances = new Map();

  for (const adapter of adapters) {
    if (!adapter.apiKey || !adapter.apiUrl) {
      logger.warn({ adapter: adapter.name }, 'Skipping adapter: missing apiKey or apiUrl');
      continue;
    }

    const proxyOptions: Options = {
      target: adapter.apiUrl,
      changeOrigin: true,
      // Restore /api prefix for backend paths that need it (files, threads)
      // Express mount at /api strips the prefix, so we add it back for specific paths
      pathRewrite: (path: string) => {
        if (path.startsWith('/files') || path.startsWith('/threads')) {
          return '/api' + path;
        }
        return path;
      },
      // Set headers directly for reliability
      headers: {
        'X-API-Key': adapter.apiKey,
      },
      // Critical for SSE streaming - disable response buffering
      selfHandleResponse: false,

      on: {
        proxyReq: (proxyReq, req) => {
          // Remove adapter name header (internal routing, not forwarded)
          proxyReq.removeHeader('x-adapter-name');

          // Ensure API key is set (backup to headers option above)
          proxyReq.setHeader('X-API-Key', adapter.apiKey);

          // Headers to explicitly preserve
          const headersToPreserve = [
            'content-type',
            'x-session-id',
            'x-thread-id',
            'accept',
            'content-length',
          ];

          // Preserve important headers from original request
          headersToPreserve.forEach(header => {
            const value = (req as Request).headers[header];
            if (value) {
              proxyReq.setHeader(header, value as string);
            }
          });

          // Copy all other headers except those that should not be forwarded
          const excludeHeaders = ['x-adapter-name', 'host', 'connection', 'transfer-encoding'];
          Object.keys((req as Request).headers).forEach(key => {
            const lowerKey = key.toLowerCase();
            if (!excludeHeaders.includes(lowerKey) && !headersToPreserve.includes(lowerKey)) {
              const value = (req as Request).headers[key];
              if (value) {
                proxyReq.setHeader(key, value as string);
              }
            }
          });
        },

        proxyRes: (proxyRes, _req, res) => {
          // Handle CORS headers
          proxyRes.headers['access-control-allow-origin'] = '*';
          proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
          proxyRes.headers['access-control-allow-headers'] =
            'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';

          // Critical for SSE streaming - disable buffering
          const contentType = proxyRes.headers['content-type'] || '';
          if (contentType.includes('text/event-stream')) {
            // Disable caching and buffering for SSE
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';

            // Flush response immediately
            if ((res as Response).flushHeaders) {
              (res as Response).flushHeaders();
            }
          }
        },

        error: (err, _req, res) => {
          const logger = getLogger();
          logger.error({ err }, 'Proxy error');
          const response = res as Response;
          if (!response.headersSent) {
            response.status(500).json({
              error: 'Proxy error',
              message: (err as Error).message,
            });
          }
        },
      },

      // Disable WebSocket proxying
      ws: false,
      // Reduce logging (we use our own logger)
      logger: undefined,
    };

    proxyInstances.set(adapter.name, createProxyMiddleware(proxyOptions) as unknown as ProxyHandler);
    logger.info({ adapter: adapter.name, target: adapter.apiUrl }, 'Created proxy instance');
  }

  return proxyInstances;
}

/**
 * Create the proxy routing middleware
 * Routes requests based on X-Adapter-Name header
 */
export function createProxyMiddlewareHandler(
  proxyInstances: ProxyInstances
): RequestHandler {
  const logger = getLogger();

  return (req: Request, res: Response, next: NextFunction): void => {
    const adapterName = req.headers['x-adapter-name'] as string | undefined;

    if (!adapterName) {
      res.status(400).json({
        error: 'X-Adapter-Name header is required',
      });
      return;
    }

    const proxy = proxyInstances.get(adapterName);
    if (!proxy) {
      logger.warn(
        { adapter: adapterName, available: Array.from(proxyInstances.keys()) },
        'Adapter not found'
      );
      res.status(404).json({
        error: `Adapter '${adapterName}' not found`,
      });
      return;
    }

    // Call the proxy middleware
    proxy(req, res, next);
  };
}
