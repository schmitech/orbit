/**
 * Adapters Route
 *
 * GET /api/adapters - List available adapters (names only, no keys)
 */

import { Router, Request, Response } from 'express';
import type { AdapterConfig } from '../config/types.js';

/**
 * Create adapters router
 */
export function createAdaptersRouter(adapters: AdapterConfig[]): Router {
  const router = Router();

  /**
   * GET /api/adapters
   * Returns list of available adapter names
   * Note: Only exposes names, never API keys or URLs
   */
  router.get('/adapters', (_req: Request, res: Response) => {
    const adapterList = adapters.map(adapter => ({
      name: adapter.name,
    }));

    res.json({
      adapters: adapterList,
    });
  });

  return router;
}
