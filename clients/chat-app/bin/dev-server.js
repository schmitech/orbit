#!/usr/bin/env node
/**
 * Development server that runs both Express (for middleware) and Vite
 * This allows testing the API middleware feature during development
 */

import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const expressPort = 5174;
const vitePort = 5173;

// Start Express server for middleware endpoints
console.log('Starting Express middleware server on port', expressPort);
const expressServer = spawn('node', [
  path.join(__dirname, 'orbitchat.js'),
  '--port', expressPort.toString(),
  '--enable-api-middleware'
], {
  stdio: 'inherit',
  env: {
    ...process.env,
    VITE_ENABLE_API_MIDDLEWARE: 'true',
  }
});

// Start Vite dev server
console.log('Starting Vite dev server on port', vitePort);
const viteServer = spawn('npm', ['run', 'dev'], {
  stdio: 'inherit',
  env: {
    ...process.env,
    VITE_ENABLE_API_MIDDLEWARE: 'true',
    VITE_MIDDLEWARE_SERVER_URL: `http://localhost:${expressPort}`,
  }
});

// Handle cleanup
process.on('SIGINT', () => {
  console.log('\nShutting down servers...');
  expressServer.kill();
  viteServer.kill();
  process.exit(0);
});

expressServer.on('exit', (code) => {
  console.log(`Express server exited with code ${code}`);
  viteServer.kill();
  process.exit(code);
});

viteServer.on('exit', (code) => {
  console.log(`Vite server exited with code ${code}`);
  expressServer.kill();
  process.exit(code);
});

