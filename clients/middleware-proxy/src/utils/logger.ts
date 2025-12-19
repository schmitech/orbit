/**
 * Logger Utility using Pino
 */

import { pino, Logger } from 'pino';
import type { LoggingConfig } from '../config/types.js';

let logger: Logger;

/**
 * Initialize the logger with configuration
 */
export function initLogger(config: LoggingConfig): Logger {
  const transport = config.format === 'pretty'
    ? {
        target: 'pino-pretty',
        options: {
          colorize: true,
          translateTime: 'SYS:standard',
          ignore: 'pid,hostname',
        },
      }
    : undefined;

  logger = pino({
    level: config.level,
    transport,
    base: {
      service: 'middleware-proxy',
    },
  });

  return logger;
}

/**
 * Get the logger instance
 */
export function getLogger(): Logger {
  if (!logger) {
    // Create a default logger if not initialized
    logger = pino({ level: 'info' });
  }
  return logger;
}

export type { Logger };
