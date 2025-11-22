#!/usr/bin/env node
/**
 * ORBIT Chat CLI
 * 
 * Serves the chat-app as a standalone application with runtime configuration.
 * Configuration can be provided via CLI arguments, config file, or environment variables.
 */

import http from 'http';
import fs from 'fs';
import path from 'path';
import { homedir } from 'os';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

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
  maxFilesPerConversation: 5,
  maxFileSizeMB: 50,
  maxTotalFiles: 100,
  maxConversations: 10,
  maxMessagesPerConversation: 1000,
  maxTotalMessages: 10000,
  maxMessageLength: 1000,
};

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
      case '--default-key':
        config.defaultKey = args[++i];
        break;
      case '--use-local-api':
        config.useLocalApi = args[++i] === 'true';
        break;
      case '--local-api-path':
        config.localApiPath = args[++i];
        break;
      case '--console-debug':
        config.consoleDebug = args[++i] === 'true';
        break;
      case '--enable-upload':
        config.enableUploadButton = args[++i] === 'true';
        break;
      case '--enable-audio':
        config.enableAudioOutput = args[++i] === 'true';
        break;
      case '--enable-feedback':
        config.enableFeedbackButtons = args[++i] === 'true';
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
          configKey === 'enableFeedbackButtons') {
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
 */
function injectConfig(html, config) {
  const configScript = `
    <script>
      window.ORBIT_CHAT_CONFIG = ${JSON.stringify(config, null, 2)};
    </script>
  `;
  
  // Replace the placeholder script tag
  return html.replace(
    /<script id="orbit-chat-config" type="application\/json">[\s\S]*?<\/script>/,
    configScript
  );
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
 * Create HTTP server to serve the built app
 */
function createServer(distPath, config) {
  return http.createServer((req, res) => {
    let filePath = path.join(distPath, req.url === '/' ? 'index.html' : req.url);
    
    // Security: prevent directory traversal
    filePath = path.normalize(filePath);
    if (!filePath.startsWith(distPath)) {
      res.writeHead(403);
      res.end('Forbidden');
      return;
    }

    // Check if file exists
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      // For SPA routing, serve index.html for non-file requests
      if (!path.extname(filePath)) {
        filePath = path.join(distPath, 'index.html');
      } else {
        res.writeHead(404);
        res.end('Not Found');
        return;
      }
    }

    // Read and serve file
    try {
      let content = fs.readFileSync(filePath);
      
      // Inject configuration into HTML files
      if (path.extname(filePath) === '.html') {
        content = Buffer.from(injectConfig(content.toString(), config));
      }

      const mimeType = getMimeType(filePath);
      res.writeHead(200, { 'Content-Type': mimeType });
      res.end(content);
    } catch (error) {
      res.writeHead(500);
      res.end('Internal Server Error');
    }
  });
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
  --use-local-api BOOLEAN          Use local API build (default: false)
  --local-api-path PATH            Path to local API
  --console-debug BOOLEAN          Enable console debug (default: false)
  --enable-upload BOOLEAN          Enable upload button (default: false)
  --enable-audio BOOLEAN           Enable audio button (default: false)
  --enable-feedback BOOLEAN        Enable feedback buttons (default: false)
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
  orbitchat --config /path/to/config.json
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
  const server = createServer(distPath, config);
  
  server.listen(serverConfig.port, serverConfig.host, () => {
    const url = `http://${serverConfig.host}:${serverConfig.port}`;
    console.log(`\n🚀 ORBIT Chat App is running at ${url}\n`);
    console.log('Configuration:');
    console.log(`  API URL: ${config.apiUrl}`);
    console.log(`  Default Key: ${config.defaultKey}`);
    console.log(`  Port: ${serverConfig.port}`);
    console.log(`  Host: ${serverConfig.host}\n`);
    
    if (serverConfig.open) {
      openBrowser(url);
    }
  });

  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\n\nShutting down server...');
    server.close(() => {
      console.log('Server closed.');
      process.exit(0);
    });
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
