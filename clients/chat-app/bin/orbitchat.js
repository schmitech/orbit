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
import { createProxyMiddleware } from 'http-proxy-middleware';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Default configuration matching env.example
// Note: GitHub stats/owner/repo are hardcoded and only configurable via build-time env vars
const DEFAULT_CONFIG = {
  apiUrl: 'http://localhost:3000',
  defaultKey: 'default-key',
  applicationName: 'ORBIT Chat',
  applicationDescription: "Explore ideas with ORBIT's AI copilots, share context, and build together.",
  defaultInputPlaceholder: 'Message ORBIT...',
  useLocalApi: false,
  localApiPath: undefined,
  consoleDebug: false,
  enableUploadButton: false,
  enableAudioOutput: false,
  enableFeedbackButtons: false,
  enableAutocomplete: false,
  enableApiMiddleware: false,
  outOfServiceMessage: null,
  maxFilesPerConversation: 5,
  maxFileSizeMB: 50,
  maxTotalFiles: 100,
  maxConversations: 10,
  maxMessagesPerConversation: 1000,
  maxMessagesPerThread: 1000,
  maxTotalMessages: 10000,
  maxMessageLength: 1000,
};

function parseAdaptersListFromEnv() {
  const envValue = process.env.ORBIT_ADAPTERS || process.env.VITE_ADAPTERS;
  if (!envValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(envValue);
    if (!Array.isArray(parsed)) {
      console.warn('Warning: ORBIT_ADAPTERS/VITE_ADAPTERS must be a JSON array');
      return [];
    }

    const adapters = [];
    for (const adapter of parsed) {
      if (!adapter.name) {
        console.warn('Warning: Each adapter must have a "name" property');
        continue;
      }
      adapters.push({
        name: adapter.name,
        apiKey: adapter.apiKey || DEFAULT_CONFIG.defaultKey,
        apiUrl: adapter.apiUrl || DEFAULT_CONFIG.apiUrl,
        description: adapter.description || adapter.summary,
        notes: adapter.notes,
      });
    }

    return adapters;
  } catch (error) {
    console.warn('Warning: Could not parse ORBIT_ADAPTERS/VITE_ADAPTERS:', error.message);
    return [];
  }
}

/**
 * Load adapter mappings from environment variable
 * Format: JSON array of adapter objects
 * Example: ORBIT_ADAPTERS='[{"name":"Simple Chat","apiKey":"key1","apiUrl":"https://api.example.com"}]'
 * @returns {object|null} - Adapters object or null if not found/invalid
 */
function loadAdaptersConfig() {
  const adapterList = parseAdaptersListFromEnv();
  if (adapterList.length === 0) {
    return null;
  }

  const adapters = {};
  for (const adapter of adapterList) {
    adapters[adapter.name] = {
      apiKey: adapter.apiKey || DEFAULT_CONFIG.defaultKey,
      apiUrl: adapter.apiUrl || DEFAULT_CONFIG.apiUrl,
      description: adapter.description,
      notes: adapter.notes,
    };
  }

  return Object.keys(adapters).length > 0 ? adapters : null;
}

function getDefaultAdapterFromEnv() {
  const adapterList = parseAdaptersListFromEnv();
  return adapterList.length > 0 ? adapterList[0].name : null;
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
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    switch (arg) {
      case '--api-url':
        config.apiUrl = args[++i];
        break;
      case '--api-key':
        config.defaultKey = args[++i];
        break;
      case '--default-adapter':
        config.defaultKey = args[++i];
        break;
      case '--default-key':
        console.warn('Warning: --default-key is deprecated. Use --default-adapter instead.');
        config.defaultKey = args[++i];
        break;
      case '--application-name':
        config.applicationName = args[++i];
        break;
      case '--application-description':
        config.applicationDescription = args[++i];
        break;
      case '--default-input-placeholder':
        config.defaultInputPlaceholder = args[++i];
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
      case '--enable-autocomplete':
        config.enableAutocomplete = true;
        break;
      case '--enable-api-middleware':
        config.enableApiMiddleware = true;
        break;
      case '--out-of-service-message':
        config.outOfServiceMessage = args[++i];
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
      case '--max-messages-per-thread':
        config.maxMessagesPerThread = parseInt(args[++i], 10);
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
    VITE_APPLICATION_NAME: 'applicationName',
    VITE_APPLICATION_DESCRIPTION: 'applicationDescription',
    VITE_DEFAULT_INPUT_PLACEHOLDER: 'defaultInputPlaceholder',
    VITE_USE_LOCAL_API: 'useLocalApi',
    VITE_LOCAL_API_PATH: 'localApiPath',
    VITE_CONSOLE_DEBUG: 'consoleDebug',
    VITE_ENABLE_UPLOAD: 'enableUploadButton',
    VITE_ENABLE_AUDIO_OUTPUT: 'enableAudioOutput',
    VITE_ENABLE_FEEDBACK: 'enableFeedbackButtons',
    VITE_ENABLE_AUTOCOMPLETE: 'enableAutocomplete',
    VITE_ENABLE_API_MIDDLEWARE: 'enableApiMiddleware',
    VITE_OUT_OF_SERVICE_MESSAGE: 'outOfServiceMessage',
    VITE_MAX_FILES_PER_CONVERSATION: 'maxFilesPerConversation',
    VITE_MAX_FILE_SIZE_MB: 'maxFileSizeMB',
    VITE_MAX_TOTAL_FILES: 'maxTotalFiles',
    VITE_MAX_CONVERSATIONS: 'maxConversations',
    VITE_MAX_MESSAGES_PER_CONVERSATION: 'maxMessagesPerConversation',
    VITE_MAX_MESSAGES_PER_THREAD: 'maxMessagesPerThread',
    VITE_MAX_TOTAL_MESSAGES: 'maxTotalMessages',
    VITE_MAX_MESSAGE_LENGTH: 'maxMessageLength',
  };

  for (const [envKey, configKey] of Object.entries(envMap)) {
    const value = process.env[envKey];
    if (value !== undefined) {
      if (configKey === 'useLocalApi' || configKey === 'consoleDebug' || 
          configKey === 'enableUploadButton' || configKey === 'enableAudioOutput' ||
          configKey === 'enableFeedbackButtons' || configKey === 'enableAutocomplete' ||
          configKey === 'enableApiMiddleware') {
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

  // Replace the title tag with the configured application name
  if (config.applicationName) {
    html = html.replace(
      /<title>.*?<\/title>/i,
      `<title>${config.applicationName}</title>`
    );
    // Also update apple-mobile-web-app-title meta tag
    html = html.replace(
      /<meta name="apple-mobile-web-app-title" content="[^"]*" \/>/i,
      `<meta name="apple-mobile-web-app-title" content="${config.applicationName}" />`
    );
  }

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
function createServer(distPath, config) {
  const app = express();
  const adapters = config.enableApiMiddleware ? loadAdaptersConfig() : null;

  // API endpoints for middleware mode - MUST be before body parsers
  if (config.enableApiMiddleware && adapters) {
    // Pre-create proxy instances for each adapter to avoid memory leaks
    // Creating proxies on every request adds event listeners that accumulate
    const proxyInstances = {};
    for (const [adapterName, adapter] of Object.entries(adapters)) {
      if (!adapter.apiKey || !adapter.apiUrl) {
        console.warn(`[Proxy] Skipping adapter '${adapterName}': missing apiKey or apiUrl`);
        continue;
      }
      proxyInstances[adapterName] = createProxyMiddleware({
        target: adapter.apiUrl,
        changeOrigin: true,
        // Restore /api prefix for backend paths that need it (files, threads)
        pathRewrite: (path) => {
          if (path.startsWith('/files') || path.startsWith('/threads')) {
            return '/api' + path;
          }
          return path;
        },
        // Set headers directly - this is more reliable than onProxyReq for some cases
        headers: {
          'X-API-Key': adapter.apiKey,
        },
        // Critical for SSE streaming - disable response buffering
        selfHandleResponse: false,
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

          // Critical for SSE streaming - disable buffering
          const contentType = proxyRes.headers['content-type'] || '';
          if (contentType.includes('text/event-stream')) {
            // Disable caching and buffering for SSE
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
            // Flush response immediately
            if (res.flushHeaders) {
              res.flushHeaders();
            }
          }
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
    }

    // Endpoint to list available adapters (only expose names, not URLs or keys)
    app.get('/api/adapters', (req, res) => {
      const adapterList = Object.keys(adapters).map(name => ({
        name,
        description: adapters[name]?.description,
        notes: adapters[name]?.notes,
      }));
      res.json({ adapters: adapterList });
    });

    // Proxy middleware for API requests - must be before body parsers to preserve request stream
    // Note: Uses /api path instead of /api/proxy for security (hides proxy nature)
    app.use('/api', (req, res, next) => {
      // Skip the /api/adapters route - it's handled separately above
      if (req.path === '/adapters') {
        return next('route');
      }
      const adapterName = req.headers['x-adapter-name'];

      if (!adapterName) {
        return res.status(400).json({ error: 'X-Adapter-Name header is required' });
      }

      const proxy = proxyInstances[adapterName];
      if (!proxy) {
        console.error(`[Proxy] Adapter '${adapterName}' not found. Available: ${Object.keys(proxyInstances).join(', ')}`);
        return res.status(404).json({ error: `Adapter '${adapterName}' not found` });
      }

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
  --default-adapter NAME           Default adapter to preselect (middleware mode)
  --api-key KEY                    Default API key (default: default-key)
  --application-name NAME          Application name shown in browser tab (default: ORBIT Chat)
  --application-description TEXT   Subtitle shown under the welcome heading
  --default-input-placeholder TEXT Message input placeholder text (default: Message ORBIT...)
  --use-local-api                  Use local API build (default: false)
  --local-api-path PATH            Path to local API
  --console-debug                  Enable console debug (default: false)
  --enable-upload                  Enable upload button (default: false)
  --enable-audio                   Enable audio button (default: false)
  --enable-feedback                Enable feedback buttons (default: false)
  --enable-autocomplete            Enable autocomplete suggestions (default: false)
  --enable-api-middleware          Enable API middleware mode (default: false)
  --out-of-service-message TEXT    Show maintenance screen blocking access
  --max-files-per-conversation N   Max files per conversation (default: 5)
  --max-file-size-mb N             Max file size in MB (default: 50)
  --max-total-files N              Max total files (default: 100, 0 = unlimited)
  --max-conversations N            Max conversations (default: 10, 0 = unlimited)
  --max-messages-per-conversation N Max messages per conversation (default: 1000, 0 = unlimited)
  --max-messages-per-thread N      Max messages per thread (default: 1000, 0 = unlimited)
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

Environment Variables for Middleware Mode:
  ORBIT_ADAPTERS or VITE_ADAPTERS   JSON array of adapter configurations
                                    Example: '[{"name":"Chat","apiKey":"key1","apiUrl":"https://api.example.com"}]'

Examples:
  orbitchat --api-url http://localhost:3000 --port 8080
  orbitchat --api-key my-key --open
  orbitchat --enable-audio --enable-upload --console-debug
  orbitchat --config /path/to/config.json
  ORBIT_ADAPTERS='[{"name":"Chat","apiKey":"mykey","apiUrl":"https://api.example.com"}]' orbitchat --enable-api-middleware
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

  if (config.enableApiMiddleware) {
    const trimmedDefaultKey = (config.defaultKey || '').trim();
    if (!trimmedDefaultKey || trimmedDefaultKey === DEFAULT_CONFIG.defaultKey) {
      const fallbackAdapter = getDefaultAdapterFromEnv();
      if (fallbackAdapter) {
        config.defaultKey = fallbackAdapter;
        console.debug(`ℹ️ Using '${fallbackAdapter}' as the default adapter (first entry from VITE_ADAPTERS).`);
      }
    }
  }

  // Find dist directory
  // Use __dirname which we defined at the top of the file
  const distPath = path.join(__dirname, '..', 'dist');
  
  if (!fs.existsSync(distPath)) {
    console.error('Error: dist directory not found. Please run "npm run build" first.');
    process.exit(1);
  }

  // Create and start server
  const app = createServer(distPath, config);

  app.listen(serverConfig.port, serverConfig.host, () => {
    const url = `http://${serverConfig.host}:${serverConfig.port}`;
    console.debug(`\n🚀 ORBIT Chat App is running at ${url}\n`);
    console.debug('Configuration:');
    console.debug(`  API URL: ${config.apiUrl}`);
    console.debug(`  Default Key/Adapter: ${config.defaultKey || '(not set)'}`);
    console.debug(`  Port: ${serverConfig.port}`);
    console.debug(`  Host: ${serverConfig.host}`);
    if (config.enableApiMiddleware) {
      console.debug(`  API Middleware: Enabled`);
      const adapters = loadAdaptersConfig();
      if (adapters) {
        console.debug(`  Available Adapters: ${Object.keys(adapters).join(', ')}`);
      } else {
        console.debug(`  Warning: No adapters configured. Set ORBIT_ADAPTERS or VITE_ADAPTERS environment variable.`);
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
