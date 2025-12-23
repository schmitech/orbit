/**
 * Proxy Routes
 *
 * /api/* - Proxy requests to ORBIT server based on X-Adapter-Name header
 */

import { Router } from 'express';
import type { AdapterConfig, RateLimitConfig } from '../config/types.js';
import { createProxyInstances, createProxyMiddlewareHandler } from '../middleware/proxy.js';
import { createRateLimiter } from '../middleware/rateLimit.js';

/**
 * Create proxy router
 */
export function createProxyRouter(
  adapters: AdapterConfig[],
  rateLimitConfig: RateLimitConfig
): Router {
  const router = Router();

  // Create proxy instances for all adapters
  const proxyInstances = createProxyInstances(adapters);

  // Apply rate limiting before proxying
  router.use(createRateLimiter(rateLimitConfig));

  // Route all requests through the proxy middleware
  router.use(createProxyMiddlewareHandler(proxyInstances));

  return router;
}
