/**
 * Graceful Shutdown Handler
 */

import type { Server } from 'http';
import { getLogger } from './logger.js';

const SHUTDOWN_TIMEOUT = 30000; // 30 seconds

/**
 * Setup graceful shutdown handlers for SIGTERM and SIGINT
 */
export function setupGracefulShutdown(server: Server): void {
  const logger = getLogger();
  const signals: NodeJS.Signals[] = ['SIGTERM', 'SIGINT'];
  let isShuttingDown = false;

  for (const signal of signals) {
    process.on(signal, () => {
      if (isShuttingDown) {
        logger.warn(`Received ${signal} during shutdown, forcing exit...`);
        process.exit(1);
      }

      isShuttingDown = true;
      logger.info(`Received ${signal}, shutting down gracefully...`);

      // Stop accepting new connections
      server.close((err) => {
        if (err) {
          logger.error({ err }, 'Error during server close');
          process.exit(1);
        }
        logger.info('HTTP server closed');
        process.exit(0);
      });

      // Force exit after timeout
      setTimeout(() => {
        logger.error('Forced shutdown after timeout');
        process.exit(1);
      }, SHUTDOWN_TIMEOUT);
    });
  }
}
