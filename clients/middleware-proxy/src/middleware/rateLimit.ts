/**
 * Rate Limiting Middleware
 *
 * Per-adapter rate limiting using express-rate-limit
 */

import rateLimit from 'express-rate-limit';
import type { Request, Response } from 'express';
import type { RateLimitConfig } from '../config/types.js';
import { getLogger } from '../utils/logger.js';

/**
 * Create rate limiting middleware with per-adapter limits
 */
export function createRateLimiter(config: RateLimitConfig) {
  const logger = getLogger();

  return rateLimit({
    windowMs: config.windowMs,
    max: config.maxRequests,
    standardHeaders: true, // Return rate limit info in the `RateLimit-*` headers
    legacyHeaders: false, // Disable the `X-RateLimit-*` headers

    // Rate limit per adapter name if perAdapter is true
    keyGenerator: (req: Request): string => {
      if (config.perAdapter) {
        const adapterName = req.headers['x-adapter-name'] as string;
        return adapterName || 'unknown';
      }
      // Global rate limit based on IP
      return req.ip || 'unknown';
    },

    // Custom handler for rate limit exceeded
    handler: (req: Request, res: Response) => {
      const adapterName = req.headers['x-adapter-name'] as string;
      logger.warn(
        { adapter: adapterName, ip: req.ip },
        'Rate limit exceeded'
      );

      res.status(429).json({
        error: 'Too many requests',
        message: config.perAdapter
          ? `Rate limit exceeded for adapter '${adapterName}'`
          : 'Rate limit exceeded',
        retryAfter: Math.ceil(config.windowMs / 1000),
      });
    },

    // Skip OPTIONS requests (CORS preflight)
    skip: (req: Request) => req.method === 'OPTIONS',
  });
}
