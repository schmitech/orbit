/**
 * CORS Middleware Configuration
 */

import cors, { CorsOptions } from 'cors';
import type { CorsConfig } from '../config/types.js';
import { getLogger } from '../utils/logger.js';

/**
 * Create CORS middleware with configuration
 */
export function createCorsMiddleware(config: CorsConfig) {
  const logger = getLogger();

  const corsOptions: CorsOptions = {
    origin: (origin, callback) => {
      // Allow requests with no origin (e.g., mobile apps, curl)
      if (!origin) {
        callback(null, true);
        return;
      }

      // Allow all origins if '*' is configured
      if (config.allowedOrigins.includes('*')) {
        callback(null, true);
        return;
      }

      // Check if origin is in the allowed list
      if (config.allowedOrigins.includes(origin)) {
        callback(null, true);
        return;
      }

      logger.warn({ origin }, 'CORS request from unauthorized origin');
      callback(new Error('Not allowed by CORS'));
    },
    credentials: config.allowCredentials,
    methods: config.allowedMethods,
    allowedHeaders: config.allowedHeaders,
    exposedHeaders: config.exposeHeaders,
    maxAge: config.maxAge,
    preflightContinue: false,
    optionsSuccessStatus: 204,
  };

  return cors(corsOptions);
}
