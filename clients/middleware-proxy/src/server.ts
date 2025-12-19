/**
 * Express Server Setup
 *
 * Creates and configures the Express application with all middleware and routes
 */

import express, { Express } from 'express';
import type { ProxyConfig } from './config/types.js';
import { createCorsMiddleware } from './middleware/cors.js';
import { createRequestLogger } from './middleware/requestLogger.js';
import { errorHandler, notFoundHandler } from './middleware/errorHandler.js';
import { createHealthRouter } from './routes/health.js';
import { createAdaptersRouter } from './routes/adapters.js';
import { createProxyRouter } from './routes/proxy.js';
import { getLogger } from './utils/logger.js';

/**
 * Create and configure the Express application
 */
export function createServer(config: ProxyConfig): Express {
  const app = express();
  const logger = getLogger();

  // Trust proxy for correct IP detection behind load balancers
  app.set('trust proxy', true);

  // CORS middleware - must be first
  app.use(createCorsMiddleware(config.cors));

  // Request logging
  app.use(createRequestLogger(config.logging));

  // Health check routes (before other middleware to keep them lightweight)
  app.use(createHealthRouter(config.adapters));

  // API routes - Proxy routes MUST be before body parsers to preserve request stream
  app.use('/api/proxy', createProxyRouter(config.adapters, config.rateLimit));

  // Adapters endpoint
  app.use('/api', createAdaptersRouter(config.adapters));

  // Body parsers - after proxy routes to preserve request body stream for streaming uploads
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  // Not found handler for unmatched routes
  app.use(notFoundHandler);

  // Global error handler - must be last
  app.use(errorHandler);

  logger.info(
    {
      adapters: config.adapters.map(a => a.name),
      cors: config.cors.allowedOrigins,
      rateLimit: {
        windowMs: config.rateLimit.windowMs,
        maxRequests: config.rateLimit.maxRequests,
      },
    },
    'Server configured'
  );

  return app;
}
