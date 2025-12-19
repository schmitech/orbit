/**
 * Global Error Handler Middleware
 */

import type { Request, Response, NextFunction } from 'express';
import { getLogger } from '../utils/logger.js';

/**
 * Global error handler middleware
 * Must be the last middleware in the chain
 */
export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  const logger = getLogger();

  // Log the error
  logger.error(
    {
      err,
      method: req.method,
      url: req.url,
      adapter: req.headers['x-adapter-name'],
    },
    'Unhandled error'
  );

  // Don't expose internal errors in production
  const isProduction = process.env.NODE_ENV === 'production';
  const message = isProduction ? 'Internal server error' : err.message;

  // Send error response
  if (!res.headersSent) {
    res.status(500).json({
      error: 'Internal server error',
      message,
      ...(isProduction ? {} : { stack: err.stack }),
    });
  }
}

/**
 * Not found handler for unmatched routes
 */
export function notFoundHandler(req: Request, res: Response): void {
  res.status(404).json({
    error: 'Not found',
    message: `Cannot ${req.method} ${req.url}`,
  });
}
