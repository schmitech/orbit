#!/usr/bin/env node
/**
 * ORBIT Chat CLI
 * 
 * Serves the chat-app as a standalone application with runtime configuration.
 * Configuration can be provided via CLI arguments, config file, or environment variables.
 * 
 * When VITE_ENABLE_API_MIDDLEWARE is enabled, the server acts as a proxy to hide
 * API keys from the client by mapping adapter names to actual API keys.
 */

import express from 'express';
import fs from 'fs';
import path from 'path';
import { homedir } from 'os';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import yaml from 'js-yaml';
import { createProxyMiddleware } from 'http-proxy-middleware';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Default configuration matching env.example
// Note: GitHub stats/owner/repo are hardcoded and only configurable via build-time env vars
const DEFAULT_CONFIG = {
  apiUrl: 'http://localhost:3000',
  defaultKey: 'default-key',
  useLocalApi: false,
  localApiPath: undefined,
  consoleDebug: false,
  enableUploadButton: false,
  enableAudioOutput: false,
  enableFeedbackButtons: false,
  enableApiMiddleware: false,
  maxFilesPerConversation: 5,
  maxFileSizeMB: 50,
  maxTotalFiles: 100,
  maxConversations: 10,
  maxMessagesPerConversation: 1000,
  maxTotalMessages: 10000,
  maxMessageLength: 1000,
};

/**
 * Load adapter mappings from YAML file
 * @param {string|null} customPath - Optional custom path to adapters.yaml
 */
function loadAdaptersConfig(customPath = null) {
  const configPaths = [
    // Custom path takes priority if provided
    ...(customPath ? [customPath] : []),
    path.join(__dirname, '..', 'adapters.yaml'),
    path.join(process.cwd(), 'adapters.yaml'),
    path.join(homedir(), '.orbit-chat-app', 'adapters.yaml'),
  ];

  for (const configPath of configPaths) {
    try {
      if (fs.existsSync(configPath)) {
        const content = fs.readFileSync(configPath, 'utf8');
        const config = yaml.load(content);
        if (config && config.adapters) {
          console.log(`  Adapters config: ${configPath}`);
          return config.adapters;
        }
      }
    } catch (error) {
      console.warn(`Warning: Could not load adapters config from ${configPath}:`, error.message);
    }
  }

  return null;
}

/**
 * Parse command-line arguments
 */
function parseArgs() {
  const args = process.argv.slice(2);
  const config = { ...DEFAULT_CONFIG };
  const serverConfig = {
    port: 5173,
    host: 'localhost',
    open: false,
    configFile: null,
    adaptersConfig: null,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    switch (arg) {
      case '--api-url':
        config.apiUrl = args[++i];
        break;
      case '--api-key':
      case '--default-key':
        config.defaultKey = args[++i];
        break;
      case '--use-local-api':
        config.useLocalApi = true;
        break;
      case '--local-api-path':
        config.localApiPath = args[++i];
        break;
      case '--console-debug':
        config.consoleDebug = true;
        break;
      case '--enable-upload':
        config.enableUploadButton = true;
        break;
      case '--enable-audio':
        config.enableAudioOutput = true;
        break;
      case '--enable-feedback':
        config.enableFeedbackButtons = true;
        break;
      case '--enable-api-middleware':
        config.enableApiMiddleware = true;
        break;
      case '--max-files-per-conversation':
        config.maxFilesPerConversation = parseInt(args[++i], 10);
        break;
      case '--max-file-size-mb':
        config.maxFileSizeMB = parseInt(args[++i], 10);
        break;
      case '--max-total-files':
        config.maxTotalFiles = parseInt(args[++i], 10);
        break;
      case '--max-conversations':
        config.maxConversations = parseInt(args[++i], 10);
        break;
      case '--max-messages-per-conversation':
        config.maxMessagesPerConversation = parseInt(args[++i], 10);
        break;
      case '--max-total-messages':
        config.maxTotalMessages = parseInt(args[++i], 10);
        break;
      case '--max-message-length':
        config.maxMessageLength = parseInt(args[++i], 10);
        break;
      case '--port':
        serverConfig.port = parseInt(args[++i], 10);
        break;
      case '--host':
        serverConfig.host = args[++i];
        break;
      case '--open':
        serverConfig.open = true;
        break;
      case '--config':
        serverConfig.configFile = args[++i];
        break;
      case '--adapters-config':
        serverConfig.adaptersConfig = args[++i];
        break;
      case '--help':
      case '-h':
        // Handled in main() function
        break;
      case '--version':
      case '-v':
        // Handled in main() function
        break;
      default:
        if (arg.startsWith('--')) {
          console.error(`Unknown option: ${arg}`);
          console.error('Use --help for usage information');
          process.exit(1);
        }
    }
  }

  return { config, serverConfig };
}

/**
 * Load configuration from file
 */
function loadConfigFile(filePath) {
  try {
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf8');
      return JSON.parse(content);
    }
  } catch (error) {
    console.warn(`Warning: Could not load config file ${filePath}:`, error.message);
  }
  return null;
}

/**
 * Load configuration from environment variables
 */
function loadConfigFromEnv() {
  const envConfig = {};
  
  // Map VITE_* environment variables to config keys
  const envMap = {
    VITE_API_URL: 'apiUrl',
    VITE_DEFAULT_KEY: 'defaultKey',
    VITE_USE_LOCAL_API: 'useLocalApi',
    VITE_LOCAL_API_PATH: 'localApiPath',
    VITE_CONSOLE_DEBUG: 'consoleDebug',
    VITE_ENABLE_UPLOAD: 'enableUploadButton',
    VITE_ENABLE_AUDIO_OUTPUT: 'enableAudioOutput',
    VITE_ENABLE_FEEDBACK: 'enableFeedbackButtons',
    VITE_ENABLE_API_MIDDLEWARE: 'enableApiMiddleware',
    VITE_MAX_FILES_PER_CONVERSATION: 'maxFilesPerConversation',
    VITE_MAX_FILE_SIZE_MB: 'maxFileSizeMB',
    VITE_MAX_TOTAL_FILES: 'maxTotalFiles',
    VITE_MAX_CONVERSATIONS: 'maxConversations',
    VITE_MAX_MESSAGES_PER_CONVERSATION: 'maxMessagesPerConversation',
    VITE_MAX_TOTAL_MESSAGES: 'maxTotalMessages',
    VITE_MAX_MESSAGE_LENGTH: 'maxMessageLength',
  };

  for (const [envKey, configKey] of Object.entries(envMap)) {
    const value = process.env[envKey];
    if (value !== undefined) {
      if (configKey === 'useLocalApi' || configKey === 'consoleDebug' || 
          configKey === 'enableUploadButton' || configKey === 'enableAudioOutput' ||
          configKey === 'enableFeedbackButtons' || configKey === 'enableApiMiddleware') {
        envConfig[configKey] = value === 'true';
      } else if (configKey.includes('max') && configKey !== 'maxFileSizeMB') {
        const parsed = parseInt(value, 10);
        if (!isNaN(parsed)) {
          envConfig[configKey] = parsed;
        }
      } else {
        envConfig[configKey] = value;
      }
    }
  }

  return envConfig;
}

/**
 * Merge configurations in priority order: CLI args > config file > env vars > defaults
 * Note: GitHub stats/owner/repo are not included in runtime config - they're hardcoded
 * and only configurable via build-time env vars for developers who fork.
 */
function mergeConfig(cliConfig, serverConfig) {
  // Start with defaults
  let config = { ...DEFAULT_CONFIG };

  // Load from environment variables (excluding GitHub config)
  const envConfig = loadConfigFromEnv();
  config = { ...config, ...envConfig };

  // Load from config file (excluding GitHub config)
  const configDir = path.join(homedir(), '.orbit-chat-app');
  const defaultConfigFile = path.join(configDir, 'config.json');
  const configFile = serverConfig.configFile || defaultConfigFile;
  
  const fileConfig = loadConfigFile(configFile);
  if (fileConfig) {
    // Remove GitHub config from file config if present
    const { showGitHubStats, githubOwner, githubRepo, ...fileConfigWithoutGitHub } = fileConfig;
    config = { ...config, ...fileConfigWithoutGitHub };
  }

  // CLI arguments override everything (excluding GitHub config)
  const { showGitHubStats, githubOwner, githubRepo, ...cliConfigWithoutGitHub } = cliConfig;
  config = { ...config, ...cliConfigWithoutGitHub };

  return config;
}

/**
 * Inject configuration into HTML
 * The config script MUST be placed in <head> BEFORE the main JS module loads,
 * otherwise window.ORBIT_CHAT_CONFIG won't be available when the app initializes.
 */
function injectConfig(html, config) {
  const configScript = `<script>window.ORBIT_CHAT_CONFIG = ${JSON.stringify(config)};</script>`;

  // Remove the placeholder script tag (it's in body, too late)
  html = html.replace(
    /<script id="orbit-chat-config" type="application\/json">[\s\S]*?<\/script>/,
    '<!-- Config injected in head -->'
  );

  // Inject the config script at the START of <head>, before any other scripts
  // This ensures window.ORBIT_CHAT_CONFIG is available when the main JS bundle loads
  return html.replace(
    /<head>/i,
    '<head>\n    ' + configScript
  );
}

/**
 * Create Express server to serve the built app
 */
function createServer(distPath, config, serverConfig = {}) {
  const app = express();
  const adapters = config.enableApiMiddleware ? loadAdaptersConfig(serverConfig.adaptersConfig) : null;

  // API endpoints for middleware mode - MUST be before body parsers
  if (config.enableApiMiddleware && adapters) {
    // Endpoint to list available adapters
    app.get('/api/adapters', (req, res) => {
      const adapterList = Object.keys(adapters).map(name => ({
        name,
        apiUrl: adapters[name].apiUrl,
        // Don't expose API keys
      }));
      res.json({ adapters: adapterList });
    });

    // Proxy middleware for API requests - must be before body parsers to preserve request stream
    app.use('/api/proxy', (req, res, next) => {
      const adapterName = req.headers['x-adapter-name'];

      if (!adapterName) {
        return res.status(400).json({ error: 'X-Adapter-Name header is required' });
      }

      const adapter = adapters[adapterName];
      if (!adapter) {
        console.error(`[Proxy] Adapter '${adapterName}' not found. Available: ${Object.keys(adapters).join(', ')}`);
        return res.status(404).json({ error: `Adapter '${adapterName}' not found` });
      }

      // Validate adapter has required fields
      if (!adapter.apiKey) {
        console.error(`[Proxy] Adapter '${adapterName}' has no apiKey configured`);
        return res.status(500).json({ error: `Adapter '${adapterName}' has no apiKey configured` });
      }
      if (!adapter.apiUrl) {
        console.error(`[Proxy] Adapter '${adapterName}' has no apiUrl configured`);
        return res.status(500).json({ error: `Adapter '${adapterName}' has no apiUrl configured` });
      }

      // Create proxy middleware for this request
      const proxy = createProxyMiddleware({
        target: adapter.apiUrl,
        changeOrigin: true,
        pathRewrite: {
          '^/api/proxy': '', // Remove /api/proxy prefix
        },
        // Set headers directly - this is more reliable than onProxyReq for some cases
        headers: {
          'X-API-Key': adapter.apiKey,
        },
        onProxyReq: (proxyReq, req) => {
          // Remove adapter name header
          proxyReq.removeHeader('x-adapter-name');
          // Ensure API key is set (backup to headers option above)
          proxyReq.setHeader('X-API-Key', adapter.apiKey);
          // Preserve important headers
          const headersToPreserve = ['content-type', 'x-session-id', 'x-thread-id', 'accept', 'content-length'];
          headersToPreserve.forEach(header => {
            const value = req.headers[header];
            if (value) {
              proxyReq.setHeader(header, value);
            }
          });
          // Copy all other headers
          Object.keys(req.headers).forEach(key => {
            const lowerKey = key.toLowerCase();
            if (!['x-adapter-name', 'host', 'connection', 'transfer-encoding'].includes(lowerKey)) {
              const value = req.headers[key];
              if (value && !headersToPreserve.includes(lowerKey)) {
                proxyReq.setHeader(key, value);
              }
            }
          });
        },
        onProxyRes: (proxyRes, req, res) => {
          // Handle CORS if needed
          proxyRes.headers['access-control-allow-origin'] = '*';
          proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
          proxyRes.headers['access-control-allow-headers'] = 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';
        },
        onError: (err, req, res) => {
          console.error('Proxy error:', err);
          if (!res.headersSent) {
            res.status(500).json({ error: 'Proxy error', message: err.message });
          }
        },
        ws: false, // Disable WebSocket proxying
        logLevel: 'silent', // Reduce logging
      });

      proxy(req, res, next);
    });
  }

  // Middleware for parsing JSON - after proxy routes to preserve request body stream
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  // IMPORTANT: Handle index.html BEFORE express.static to inject runtime config
  // express.static would serve the file without config injection otherwise
  app.get(['/', '/index.html'], (req, res) => {
    try {
      const indexPath = path.join(distPath, 'index.html');
      let content = fs.readFileSync(indexPath, 'utf8');
      content = injectConfig(content, config);
      res.setHeader('Content-Type', 'text/html');
      res.send(content);
    } catch (error) {
      console.error('Error serving index.html:', error);
      res.status(500).send('Internal Server Error');
    }
  });

  // Serve static files (JS, CSS, images, etc.) - index.html is handled above
  app.use(express.static(distPath, {
    index: false, // Don't serve index.html automatically - we handle it above
  }));

  // SPA fallback - serve index.html for all non-file routes (client-side routing)
  app.get('/{*splat}', (req, res, next) => {
    // Skip API routes
    if (req.path.startsWith('/api/')) {
      return next();
    }

    // Skip requests for files with extensions (let them 404)
    if (path.extname(req.path)) {
      return res.status(404).send('Not Found');
    }

    // Serve index.html for SPA routes
    try {
      const indexPath = path.join(distPath, 'index.html');
      let content = fs.readFileSync(indexPath, 'utf8');
      content = injectConfig(content, config);
      res.setHeader('Content-Type', 'text/html');
      res.send(content);
    } catch (error) {
      console.error('Error serving index.html:', error);
      res.status(500).send('Internal Server Error');
    }
  });

  return app;
}

/**
 * Get MIME type for file extension
 */
function getMimeType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes = {
    '.html': 'text/html',
    '.js': 'application/javascript',
    '.mjs': 'application/javascript',
    '.json': 'application/json',
    '.css': 'text/css',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject',
  };
  return mimeTypes[ext] || 'application/octet-stream';
}

/**
 * Open browser
 */
function openBrowser(url) {
  const platform = process.platform;
  let command;
  
  if (platform === 'darwin') {
    command = `open "${url}"`;
  } else if (platform === 'linux') {
    command = `xdg-open "${url}"`;
  } else if (platform === 'win32') {
    command = `start "${url}"`;
  } else {
    return;
  }

  try {
    execSync(command, { stdio: 'ignore' });
  } catch (error) {
    // Ignore errors
  }
}

/**
 * Get version from package.json
 */
function getVersion() {
  try {
    const packagePath = path.join(__dirname, '..', 'package.json');
    const packageContent = fs.readFileSync(packagePath, 'utf8');
    const packageJson = JSON.parse(packageContent);
    return packageJson.version || 'unknown';
  } catch (error) {
    return 'unknown';
  }
}

/**
 * Print version
 */
function printVersion() {
  console.log(getVersion());
}

/**
 * Print help message
 */
function printHelp() {
  console.log(`
ORBIT Chat CLI

Usage: orbitchat [options]

Options:
  --api-url URL                    API URL (default: http://localhost:3000)
  --api-key KEY                    Default API key (default: default-key)
  --use-local-api                  Use local API build (default: false)
  --local-api-path PATH            Path to local API
  --console-debug                  Enable console debug (default: false)
  --enable-upload                  Enable upload button (default: false)
  --enable-audio                   Enable audio button (default: false)
  --enable-feedback                Enable feedback buttons (default: false)
  --enable-api-middleware          Enable API middleware mode (default: false)
  --adapters-config PATH           Path to adapters.yaml for middleware mode
  --max-files-per-conversation N   Max files per conversation (default: 5)
  --max-file-size-mb N             Max file size in MB (default: 50)
  --max-total-files N              Max total files (default: 100, 0 = unlimited)
  --max-conversations N            Max conversations (default: 10, 0 = unlimited)
  --max-messages-per-conversation N Max messages per conversation (default: 1000, 0 = unlimited)
  --max-total-messages N           Max total messages (default: 10000, 0 = unlimited)
  --max-message-length N           Max message length (default: 1000)
  --port PORT                      Server port (default: 5173)
  --host HOST                      Server host (default: localhost)
  --open                           Open browser automatically
  --config PATH                    Path to config file (default: ~/.orbit-chat-app/config.json)
  --help, -h                       Show this help message
  --version, -v                    Show version number

Configuration Priority:
  1. CLI arguments
  2. Config file (~/.orbit-chat-app/config.json)
  3. Environment variables (VITE_*)
  4. Default values

Examples:
  orbitchat --api-url http://localhost:3000 --port 8080
  orbitchat --api-key my-key --open
  orbitchat --enable-audio --enable-upload --console-debug
  orbitchat --config /path/to/config.json
  orbitchat --enable-api-middleware --adapters-config ./adapters.yaml
`);

}

/**
 * Main function
 */
function main() {
  // Check for version flag first
  if (process.argv.includes('--version') || process.argv.includes('-v')) {
    printVersion();
    return;
  }
  
  // Check for help flag
  if (process.argv.includes('--help') || process.argv.includes('-h')) {
    printHelp();
    return;
  }

  const { config: cliConfig, serverConfig } = parseArgs();
  const config = mergeConfig(cliConfig, serverConfig);

  // Find dist directory
  // Use __dirname which we defined at the top of the file
  const distPath = path.join(__dirname, '..', 'dist');
  
  if (!fs.existsSync(distPath)) {
    console.error('Error: dist directory not found. Please run "npm run build" first.');
    process.exit(1);
  }

  // Create and start server
  const app = createServer(distPath, config, serverConfig);

  app.listen(serverConfig.port, serverConfig.host, () => {
    const url = `http://${serverConfig.host}:${serverConfig.port}`;
    console.debug(`\n🚀 ORBIT Chat App is running at ${url}\n`);
    console.debug('Configuration:');
    console.debug(`  API URL: ${config.apiUrl}`);
    console.debug(`  Default Key: ${config.defaultKey}`);
    console.debug(`  Port: ${serverConfig.port}`);
    console.debug(`  Host: ${serverConfig.host}`);
    if (config.enableApiMiddleware) {
      console.debug(`  API Middleware: Enabled`);
      const adapters = loadAdaptersConfig(serverConfig.adaptersConfig);
      if (adapters) {
        console.debug(`  Available Adapters: ${Object.keys(adapters).join(', ')}`);
      } else {
        console.debug(`  Warning: No adapters.yaml found. Use --adapters-config to specify path.`);
      }
    }
    console.debug('');
    
    if (serverConfig.open) {
      openBrowser(url);
    }
  });

  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.debug('\n\nShutting down server...');
    process.exit(0);
  });
}

// Run if called directly (ES module equivalent of require.main === module)
// For ES modules, we check if this file is being executed directly
const isMainModule = process.argv[1] && (
  import.meta.url === `file://${process.argv[1]}` ||
  import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/')) ||
  process.argv[1].includes('orbitchat')
);

if (isMainModule) {
  main();
}

export { main, parseArgs, mergeConfig };
