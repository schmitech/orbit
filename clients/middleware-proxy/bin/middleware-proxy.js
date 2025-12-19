#!/usr/bin/env node
/**
 * Middleware Proxy CLI Entry Point
 *
 * Usage:
 *   middleware-proxy [options]
 *
 * Options:
 *   --help, -h     Show this help message
 *   --version, -v  Show version number
 *
 * Environment Variables:
 *   PORT                      Server port (default: 3001)
 *   HOST                      Server host (default: 0.0.0.0)
 *   ORBIT_ADAPTERS            JSON array of adapter configurations
 *   ALLOWED_ORIGINS           Comma-separated list of allowed CORS origins
 *   RATE_LIMIT_WINDOW_MS      Rate limit window in milliseconds
 *   RATE_LIMIT_MAX_REQUESTS   Max requests per window
 *   LOG_LEVEL                 Logging level (debug, info, warn, error)
 *   LOG_FORMAT                Log format (json, pretty)
 *   CONFIG_FILE               Path to optional config file
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Get version from package.json
function getVersion() {
  try {
    const packagePath = join(__dirname, '..', 'package.json');
    const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
    return packageJson.version || '1.0.0';
  } catch {
    return '1.0.0';
  }
}

// Print help message
function printHelp() {
  console.log(`
ORBIT Middleware Proxy

A standalone middleware proxy for ORBIT chat applications.
Hides API keys and provides rate limiting for chat-app, chat-widget, and other clients.

Usage: middleware-proxy [options]

Options:
  --help, -h     Show this help message
  --version, -v  Show version number

Environment Variables:
  PORT                      Server port (default: 3001)
  HOST                      Server host (default: 0.0.0.0)
  ORBIT_ADAPTERS            JSON array of adapter configurations
                            Example: '[{"name":"Chat","apiKey":"key1","apiUrl":"https://api.example.com"}]'
  VITE_ADAPTERS             Alternative to ORBIT_ADAPTERS (for compatibility)
  ALLOWED_ORIGINS           Comma-separated list of allowed CORS origins
                            Example: 'https://app.example.com,https://widget.example.com'
                            Use '*' for development (not recommended for production)
  RATE_LIMIT_WINDOW_MS      Rate limit window in milliseconds (default: 60000)
  RATE_LIMIT_MAX_REQUESTS   Max requests per window per adapter (default: 100)
  LOG_LEVEL                 Logging level: debug, info, warn, error (default: info)
  LOG_FORMAT                Log format: json, pretty (default: json)
  LOG_REQUESTS              Log all requests: true, false (default: true)
  CONFIG_FILE               Path to optional JSON config file

Examples:
  # Start with environment variables
  ORBIT_ADAPTERS='[{"name":"Chat","apiKey":"mykey","apiUrl":"https://orbit.example.com"}]' \\
  ALLOWED_ORIGINS='https://app.example.com' \\
  middleware-proxy

  # Start with config file
  CONFIG_FILE=/etc/middleware-proxy/config.json middleware-proxy

  # Development mode with pretty logging
  LOG_FORMAT=pretty LOG_LEVEL=debug middleware-proxy
`);
}

// Check for help or version flags
const args = process.argv.slice(2);
if (args.includes('--help') || args.includes('-h')) {
  printHelp();
  process.exit(0);
}

if (args.includes('--version') || args.includes('-v')) {
  console.log(getVersion());
  process.exit(0);
}

// Start the server
import('../dist/index.js').then(({ startServer }) => {
  startServer();
}).catch((error) => {
  console.error('Failed to start middleware proxy:', error.message);
  console.error('\nMake sure you have run "npm run build" first.');
  process.exit(1);
});
