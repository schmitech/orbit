/**
 * Request Logging Middleware
 *
 * Logs incoming requests and responses
 */

import type { Request, Response, NextFunction, RequestHandler } from 'express';
import type { LoggingConfig } from '../config/types.js';
import { getLogger } from '../utils/logger.js';

/**
 * Create request logging middleware
 */
export function createRequestLogger(config: LoggingConfig): RequestHandler {
  if (!config.logRequests) {
    // Return a no-op middleware if request logging is disabled
    return (_req: Request, _res: Response, next: NextFunction) => next();
  }

  const logger = getLogger();

  return (req: Request, res: Response, next: NextFunction) => {
    // Skip health check requests
    if (req.url === '/health' || req.url === '/ready') {
      return next();
    }

    const startTime = Date.now();

    // Log when response finishes
    res.on('finish', () => {
      const duration = Date.now() - startTime;
      const logData = {
        method: req.method,
        url: req.url,
        statusCode: res.statusCode,
        duration,
        adapter: req.headers['x-adapter-name'],
        sessionId: req.headers['x-session-id'],
        origin: req.headers.origin,
        contentType: res.getHeader('content-type'),
      };

      if (res.statusCode >= 500) {
        logger.error(logData, `${req.method} ${req.url} ${res.statusCode}`);
      } else if (res.statusCode >= 400) {
        logger.warn(logData, `${req.method} ${req.url} ${res.statusCode}`);
      } else {
        logger.info(logData, `${req.method} ${req.url} ${res.statusCode}`);
      }
    });

    next();
  };
}
