/**
 * Health Check Routes
 *
 * GET /health - Basic health check
 * GET /ready - Readiness check with adapter status
 */

import { Router, Request, Response } from 'express';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import type { AdapterConfig } from '../config/types.js';

const startTime = Date.now();

// Read version from package.json at runtime
let version = '1.0.0';
try {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  const packagePath = join(__dirname, '../../package.json');
  const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
  version = packageJson.version || '1.0.0';
} catch {
  // Use default version if package.json can't be read
}

/**
 * Create health check router
 */
export function createHealthRouter(adapters: AdapterConfig[]): Router {
  const router = Router();

  /**
   * GET /health
   * Basic health check - returns 200 if server is running
   */
  router.get('/health', (_req: Request, res: Response) => {
    res.json({
      status: 'healthy',
      version,
      uptime: Math.floor((Date.now() - startTime) / 1000),
      timestamp: new Date().toISOString(),
    });
  });

  /**
   * GET /ready
   * Readiness check - returns 200 if server is ready to accept traffic
   */
  router.get('/ready', (_req: Request, res: Response) => {
    const adapterCount = adapters.length;
    const isReady = adapterCount > 0;

    if (!isReady) {
      res.status(503).json({
        status: 'not ready',
        reason: 'No adapters configured',
        adapters: {
          loaded: 0,
          healthy: 0,
        },
      });
      return;
    }

    res.json({
      status: 'ready',
      adapters: {
        loaded: adapterCount,
        healthy: adapterCount, // All loaded adapters are considered healthy
      },
    });
  });

  return router;
}
