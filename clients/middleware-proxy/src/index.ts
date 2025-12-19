/**
 * Middleware Proxy - Main Entry Point
 *
 * Standalone middleware proxy for ORBIT chat applications.
 * Hides API keys and provides rate limiting for chat-app, chat-widget, and other clients.
 */

// Load .env file before anything else
import 'dotenv/config';

import { loadConfig } from './config/index.js';
import { initLogger, getLogger } from './utils/logger.js';
import { setupGracefulShutdown } from './utils/shutdown.js';
import { createServer } from './server.js';

/**
 * Start the middleware proxy server
 */
export async function startServer(): Promise<void> {
  try {
    // Load and validate configuration
    const config = loadConfig();

    // Initialize logger
    initLogger(config.logging);
    const logger = getLogger();

    // Create Express server
    const app = createServer(config);

    // Start listening
    const server = app.listen(config.server.port, config.server.host, () => {
      logger.info(
        {
          port: config.server.port,
          host: config.server.host,
          adapters: config.adapters.length,
        },
        `Middleware proxy is running at http://${config.server.host}:${config.server.port}`
      );

      // Log available adapters
      logger.info(
        { adapters: config.adapters.map(a => a.name) },
        'Available adapters'
      );
    });

    // Setup graceful shutdown
    setupGracefulShutdown(server);

  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Export for programmatic use
export { loadConfig } from './config/index.js';
export { createServer } from './server.js';
export { initLogger, getLogger } from './utils/logger.js';
export type { ProxyConfig, AdapterConfig, CorsConfig, RateLimitConfig, LoggingConfig, ServerConfig } from './config/types.js';
