#!/usr/bin/env node
/**
 * ORBIT Chat CLI
 *
 * Serves the chat-app as a standalone application with runtime configuration.
 * Configuration is read from orbitchat.yaml (CWD by default, overridable via --config).
 * Secrets (adapter API keys) come from VITE_ADAPTERS / ORBIT_ADAPTERS env var.
 *
 * The server acts as a proxy to hide API keys from the client by mapping
 * adapter names to actual API keys.
 */

import express from 'express';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import { createProxyMiddleware } from 'http-proxy-middleware';
import yaml from 'js-yaml';
import rateLimit from 'express-rate-limit';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---- Minimal .env loader (CLI mode) ----

function parseDotEnvValue(raw) {
  const trimmed = raw.trim();
  if (!trimmed) return '';

  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }

  return trimmed;
}

function loadDotEnvFromFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const equalsIndex = trimmed.indexOf('=');
    if (equalsIndex <= 0) continue;

    const key = trimmed.slice(0, equalsIndex).trim();
    if (!key) continue;

    if (process.env[key] !== undefined) continue;

    let valueRaw = trimmed.slice(equalsIndex + 1);
    const startsWithDouble = valueRaw.startsWith('"');
    const startsWithSingle = valueRaw.startsWith("'");

    // Support simple multiline quoted values, useful for formatted JSON values.
    if (
      (startsWithDouble && !valueRaw.endsWith('"')) ||
      (startsWithSingle && !valueRaw.endsWith("'"))
    ) {
      const quote = startsWithDouble ? '"' : "'";
      while (i + 1 < lines.length) {
        i += 1;
        valueRaw += `\n${lines[i]}`;
        if (lines[i].trim().endsWith(quote)) {
          break;
        }
      }
    }

    const value = parseDotEnvValue(valueRaw);
    process.env[key] = value;
  }
}

function loadDotEnv(baseDir) {
  // Same precedence idea as Vite: .env then .env.local; do not override exported vars.
  loadDotEnvFromFile(path.join(baseDir, '.env'));
  loadDotEnvFromFile(path.join(baseDir, '.env.local'));
}

// ---- Defaults (must match DEFAULTS in src/utils/runtimeConfig.ts) ----

const DEFAULTS = {
  apiUrl: 'http://localhost:3000',
  defaultKey: 'default-key',
  applicationName: 'ORBIT Chat',
  applicationDescription: "Explore ideas with ORBIT's AI copilots, share context, and build together.",
  defaultInputPlaceholder: 'Message ORBIT...',
  consoleDebug: false,
  locale: 'en-US',
  enableUploadButton: false,
  enableAudioOutput: false,
  enableAudioInput: false,
  enableFeedbackButtons: false,
  enableConversationThreads: true,
  enableAutocomplete: false,
  voiceSilenceTimeoutMs: 4000,
  voiceRecognitionLanguage: '',
  showGitHubStats: true,
  outOfServiceMessage: null,
  githubOwner: 'schmitech',
  githubRepo: 'orbit',
  maxFilesPerConversation: 5,
  maxFileSizeMB: 50,
  maxTotalFiles: 100,
  maxConversations: 10,
  maxMessagesPerConversation: 1000,
  maxMessagesPerThread: 1000,
  maxTotalMessages: 10000,
  maxMessageLength: 1000,
  guestMaxConversations: 1,
  guestMaxMessagesPerConversation: 10,
  guestMaxTotalMessages: 10,
  guestMaxMessagesPerThread: 10,
  guestMaxFilesPerConversation: 1,
  guestMaxTotalFiles: 2,
  guestMaxMessageLength: 500,
  guestMaxFileSizeMB: 10,
  settingsAboutMsg: 'ORBIT Chat',
  enableAuth: false,
  authDomain: '',
  authClientId: '',
  authAudience: '',
  enableHeader: false,
  headerLogoUrl: '',
  headerBrandName: '',
  headerBgColor: '',
  headerTextColor: '',
  headerNavLinks: [],
  enableFooter: false,
  footerText: '',
  footerBgColor: '',
  footerTextColor: '',
  footerNavLinks: [],
};

// ---- YAML config loading ----

function flattenYamlConfig(y) {
  const f = {};
  if (y.application) {
    const a = y.application;
    if (a.name !== undefined) f.applicationName = a.name;
    if (a.description !== undefined) f.applicationDescription = a.description;
    if (a.inputPlaceholder !== undefined) f.defaultInputPlaceholder = a.inputPlaceholder;
    if (a.settingsAboutMsg !== undefined) f.settingsAboutMsg = a.settingsAboutMsg;
    if (a.locale !== undefined) f.locale = a.locale;
  }
  if (y.api) {
    if (y.api.url !== undefined) f.apiUrl = y.api.url;
    if (y.api.defaultAdapter !== undefined) f.defaultKey = y.api.defaultAdapter;
  }
  if (y.debug) {
    if (y.debug.consoleDebug !== undefined) f.consoleDebug = y.debug.consoleDebug;
  }
  if (y.features) {
    const fe = y.features;
    if (fe.enableUpload !== undefined) f.enableUploadButton = fe.enableUpload;
    if (fe.enableAudioOutput !== undefined) f.enableAudioOutput = fe.enableAudioOutput;
    if (fe.enableAudioInput !== undefined) f.enableAudioInput = fe.enableAudioInput;
    if (fe.enableFeedbackButtons !== undefined) f.enableFeedbackButtons = fe.enableFeedbackButtons;
    if (fe.enableConversationThreads !== undefined) f.enableConversationThreads = fe.enableConversationThreads;
    if (fe.enableAutocomplete !== undefined) f.enableAutocomplete = fe.enableAutocomplete;
  }
  if (y.voice) {
    if (y.voice.silenceTimeoutMs !== undefined) f.voiceSilenceTimeoutMs = y.voice.silenceTimeoutMs;
    if (y.voice.recognitionLanguage !== undefined) f.voiceRecognitionLanguage = y.voice.recognitionLanguage;
  }
  if (y.github) {
    if (y.github.showStats !== undefined) f.showGitHubStats = y.github.showStats;
    if (y.github.owner !== undefined) f.githubOwner = y.github.owner;
    if (y.github.repo !== undefined) f.githubRepo = y.github.repo;
  }
  if (y.outOfServiceMessage !== undefined) f.outOfServiceMessage = y.outOfServiceMessage;
  if (y.limits) {
    const l = y.limits;
    if (l.files) {
      if (l.files.perConversation !== undefined) f.maxFilesPerConversation = l.files.perConversation;
      if (l.files.maxSizeMB !== undefined) f.maxFileSizeMB = l.files.maxSizeMB;
      if (l.files.totalFiles !== undefined) f.maxTotalFiles = l.files.totalFiles;
    }
    if (l.conversations) {
      if (l.conversations.maxConversations !== undefined) f.maxConversations = l.conversations.maxConversations;
      if (l.conversations.messagesPerConversation !== undefined) f.maxMessagesPerConversation = l.conversations.messagesPerConversation;
      if (l.conversations.messagesPerThread !== undefined) f.maxMessagesPerThread = l.conversations.messagesPerThread;
      if (l.conversations.totalMessages !== undefined) f.maxTotalMessages = l.conversations.totalMessages;
    }
    if (l.messages) {
      if (l.messages.maxLength !== undefined) f.maxMessageLength = l.messages.maxLength;
    }
  }
  if (y.guestLimits) {
    const g = y.guestLimits;
    if (g.files) {
      if (g.files.perConversation !== undefined) f.guestMaxFilesPerConversation = g.files.perConversation;
      if (g.files.maxSizeMB !== undefined) f.guestMaxFileSizeMB = g.files.maxSizeMB;
      if (g.files.totalFiles !== undefined) f.guestMaxTotalFiles = g.files.totalFiles;
    }
    if (g.conversations) {
      if (g.conversations.maxConversations !== undefined) f.guestMaxConversations = g.conversations.maxConversations;
      if (g.conversations.messagesPerConversation !== undefined) f.guestMaxMessagesPerConversation = g.conversations.messagesPerConversation;
      if (g.conversations.messagesPerThread !== undefined) f.guestMaxMessagesPerThread = g.conversations.messagesPerThread;
      if (g.conversations.totalMessages !== undefined) f.guestMaxTotalMessages = g.conversations.totalMessages;
    }
    if (g.messages) {
      if (g.messages.maxLength !== undefined) f.guestMaxMessageLength = g.messages.maxLength;
    }
  }
  if (y.auth) {
    if (y.auth.enabled !== undefined) f.enableAuth = y.auth.enabled;
  }
  if (y.header) {
    const h = y.header;
    if (h.enabled !== undefined) f.enableHeader = h.enabled;
    if (h.logoUrl !== undefined) f.headerLogoUrl = h.logoUrl;
    if (h.brandName !== undefined) f.headerBrandName = h.brandName;
    if (h.bgColor !== undefined) f.headerBgColor = h.bgColor;
    if (h.textColor !== undefined) f.headerTextColor = h.textColor;
    if (h.navLinks !== undefined) f.headerNavLinks = h.navLinks;
  }
  if (y.footer) {
    const ft = y.footer;
    if (ft.enabled !== undefined) f.enableFooter = ft.enabled;
    if (ft.text !== undefined) f.footerText = ft.text;
    if (ft.bgColor !== undefined) f.footerBgColor = ft.bgColor;
    if (ft.textColor !== undefined) f.footerTextColor = ft.textColor;
    if (ft.navLinks !== undefined) f.footerNavLinks = ft.navLinks;
  }
  // Adapters from YAML: include metadata (name, description, notes, apiUrl) but NOT apiKey
  if (y.adapters !== undefined) {
    f.adapters = y.adapters.map(a => ({
      name: a.name,
      ...(a.apiUrl ? { apiUrl: a.apiUrl } : {}),
      ...(a.description ? { description: a.description } : {}),
      ...(a.notes ? { notes: a.notes } : {}),
    }));
  }
  return f;
}

function loadYamlConfig(configPath) {
  try {
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf8');
      const parsed = yaml.load(content);
      if (parsed && typeof parsed === 'object') {
        return parsed;
      }
    }
  } catch (error) {
    console.error(`Error: Failed to parse ${configPath}: ${error.message}`);
    process.exit(1);
  }
  return null;
}

// ---- Adapter loading (env secrets + YAML metadata) ----

function parseAdaptersFromEnv() {
  const envValue = process.env.ORBIT_ADAPTERS || process.env.VITE_ADAPTERS;
  if (!envValue) return [];

  try {
    const parsed = JSON.parse(envValue);
    if (!Array.isArray(parsed)) {
      console.warn('Warning: ORBIT_ADAPTERS/VITE_ADAPTERS must be a JSON array');
      return [];
    }
    return parsed.filter(a => a.name).map(a => ({
      name: a.name,
      apiKey: a.apiKey || DEFAULTS.defaultKey,
      apiUrl: a.apiUrl || DEFAULTS.apiUrl,
      description: a.description || a.summary,
      notes: a.notes,
    }));
  } catch (error) {
    console.warn('Warning: Could not parse ORBIT_ADAPTERS/VITE_ADAPTERS:', error.message);
    return [];
  }
}

function loadAdaptersConfig() {
  const adapterList = parseAdaptersFromEnv();
  if (adapterList.length === 0) return null;

  const adapters = {};
  for (const adapter of adapterList) {
    adapters[adapter.name] = {
      apiKey: adapter.apiKey || DEFAULTS.defaultKey,
      apiUrl: adapter.apiUrl || DEFAULTS.apiUrl,
      description: adapter.description,
      notes: adapter.notes,
    };
  }

  return Object.keys(adapters).length > 0 ? adapters : null;
}

function getDefaultAdapterFromEnv() {
  const adapterList = parseAdaptersFromEnv();
  return adapterList.length > 0 ? adapterList[0].name : null;
}

// ---- CLI arg parsing (server flags only) ----

function parseArgs() {
  const args = process.argv.slice(2);
  const serverConfig = {
    port: 5173,
    host: 'localhost',
    open: false,
    configFile: null,
    apiOnly: false,
    corsOrigin: undefined,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    switch (arg) {
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
      case '--api-only':
        serverConfig.apiOnly = true;
        break;
      case '--cors-origin':
        serverConfig.corsOrigin = args[++i];
        break;
      case '--help':
      case '-h':
      case '--version':
      case '-v':
        break;
      default:
        if (arg.startsWith('--')) {
          console.error(`Unknown option: ${arg}`);
          console.error('Use --help for usage information');
          process.exit(1);
        }
    }
  }

  return serverConfig;
}

// ---- HTML injection ----

function injectConfig(html, config) {
  const configScript = `<script>window.ORBIT_CHAT_CONFIG = ${JSON.stringify(config)};</script>`;

  // Remove the placeholder script tag
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
    html = html.replace(
      /<meta name="apple-mobile-web-app-title" content="[^"]*" \/>/i,
      `<meta name="apple-mobile-web-app-title" content="${config.applicationName}" />`
    );
  }

  // Inject the config script at the START of <head>
  return html.replace(
    /<head>/i,
    '<head>\n    ' + configScript
  );
}

// ---- Rate limiting ----

function createRateLimiters(rateLimitConfig) {
  if (!rateLimitConfig || rateLimitConfig.enabled === false) return null;

  const windowMs = rateLimitConfig.windowMs || 60000;
  const maxRequests = rateLimitConfig.maxRequests || 30;
  const chatWindowMs = rateLimitConfig.chat?.windowMs || 60000;
  const chatMaxRequests = rateLimitConfig.chat?.maxRequests || 10;

  const keyGenerator = (req) =>
    req.ip || req.headers['x-forwarded-for'] || 'unknown';

  const api = rateLimit({
    windowMs,
    max: maxRequests,
    keyGenerator,
    standardHeaders: 'draft-7',
    legacyHeaders: false,
    validate: { default: true, keyGeneratorIpFallback: false },
    skip: (req) => req.method === 'OPTIONS' || req.path === '/adapters',
    handler: (req, res) => {
      const retryAfterMs = res.getHeader('RateLimit-Reset')
        ? Number(res.getHeader('RateLimit-Reset')) * 1000
        : windowMs;
      res.status(429).json({
        error: 'Too many requests',
        message: `Rate limit exceeded. Try again in ${Math.ceil(retryAfterMs / 1000)} seconds.`,
        retryAfterMs,
      });
    },
  });

  const chat = rateLimit({
    windowMs: chatWindowMs,
    max: chatMaxRequests,
    keyGenerator,
    standardHeaders: 'draft-7',
    legacyHeaders: false,
    validate: { default: true, keyGeneratorIpFallback: false },
    handler: (req, res) => {
      const retryAfterMs = res.getHeader('RateLimit-Reset')
        ? Number(res.getHeader('RateLimit-Reset')) * 1000
        : chatWindowMs;
      res.status(429).json({
        error: 'Too many requests',
        message: `Chat rate limit exceeded. Try again in ${Math.ceil(retryAfterMs / 1000)} seconds.`,
        retryAfterMs,
      });
    },
  });

  return { api, chat };
}

// ---- Express server ----

function createServer(distPath, config, serverConfig = {}) {
  const app = express();
  const adapters = loadAdaptersConfig();
  const apiOnly = serverConfig.apiOnly || false;
  const yamlAdapterMetadata = new Map(
    Array.isArray(config.adapters)
      ? config.adapters.filter(a => a && a.name).map(a => [a.name, a])
      : []
  );

  if (apiOnly) {
    const allowedOrigin = serverConfig.corsOrigin || '*';
    app.use((req, res, next) => {
      res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name, Accept');
      res.setHeader('Access-Control-Expose-Headers', 'Content-Type');
      if (req.method === 'OPTIONS') {
        return res.sendStatus(204);
      }
      next();
    });
  }

  // Guest rate limiting — after CORS, before proxy. Skips authenticated requests.
  const limiters = createRateLimiters(serverConfig.rateLimit);
  if (limiters) {
    app.use('/api', (req, res, next) => {
      if (req.headers.authorization) return next();
      limiters.api(req, res, next);
    });
    app.use('/api', (req, res, next) => {
      if (req.headers.authorization) return next();
      if (req.method === 'POST' && (/\/chat/i.test(req.path) || /\/stream/i.test(req.path))) {
        return limiters.chat(req, res, next);
      }
      next();
    });
  }

  // API proxy endpoints - MUST be before body parsers
  if (adapters) {
    // Merge adapter metadata from YAML so UI labels/notes are consistent with dev mode.
    for (const [adapterName, adapter] of Object.entries(adapters)) {
      const metadata = yamlAdapterMetadata.get(adapterName);
      if (!metadata) continue;
      if (!adapter.description && metadata.description) {
        adapter.description = metadata.description;
      }
      if (!adapter.notes && metadata.notes) {
        adapter.notes = metadata.notes;
      }
      if (!adapter.apiUrl && metadata.apiUrl) {
        adapter.apiUrl = metadata.apiUrl;
      }
    }

    const proxyInstances = {};
    for (const [adapterName, adapter] of Object.entries(adapters)) {
      if (!adapter.apiKey || !adapter.apiUrl) {
        console.warn(`[Proxy] Skipping adapter '${adapterName}': missing apiKey or apiUrl`);
        continue;
      }
      proxyInstances[adapterName] = createProxyMiddleware({
        target: adapter.apiUrl,
        changeOrigin: true,
        pathRewrite: (path) => {
          if (path.startsWith('/files') || path.startsWith('/threads')) {
            return '/api' + path;
          }
          return path;
        },
        headers: {
          'X-API-Key': adapter.apiKey,
        },
        selfHandleResponse: false,
        onProxyReq: (proxyReq, req) => {
          proxyReq.removeHeader('x-adapter-name');
          proxyReq.setHeader('X-API-Key', adapter.apiKey);
          const headersToPreserve = ['content-type', 'x-session-id', 'x-thread-id', 'accept', 'content-length', 'authorization'];
          headersToPreserve.forEach(header => {
            const value = req.headers[header];
            if (value) {
              proxyReq.setHeader(header, value);
            }
          });
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
          proxyRes.headers['access-control-allow-origin'] = '*';
          proxyRes.headers['access-control-allow-methods'] = 'GET, POST, PUT, DELETE, OPTIONS';
          proxyRes.headers['access-control-allow-headers'] = 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name';

          const contentType = proxyRes.headers['content-type'] || '';
          if (contentType.includes('text/event-stream')) {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
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
        ws: false,
        logLevel: 'silent',
      });
    }

    app.get('/api/adapters', (req, res) => {
      const adapterList = Object.keys(adapters).map(name => ({
        name,
        description: adapters[name]?.description,
        notes: adapters[name]?.notes,
      }));
      res.json({ adapters: adapterList });
    });

    app.use('/api', (req, res, next) => {
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

  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  if (!apiOnly && distPath) {
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

    app.use(express.static(distPath, { index: false }));

    app.get('/{*splat}', (req, res, next) => {
      if (req.path.startsWith('/api/')) {
        return next();
      }
      if (path.extname(req.path)) {
        return res.status(404).send('Not Found');
      }
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
  }

  return app;
}

// ---- Utilities ----

function openBrowser(url) {
  const platform = process.platform;
  let command;
  if (platform === 'darwin') command = `open "${url}"`;
  else if (platform === 'linux') command = `xdg-open "${url}"`;
  else if (platform === 'win32') command = `start "${url}"`;
  else return;

  try { execSync(command, { stdio: 'ignore' }); } catch { /* ignore */ }
}

function getVersion() {
  try {
    const packagePath = path.join(__dirname, '..', 'package.json');
    const packageContent = fs.readFileSync(packagePath, 'utf8');
    return JSON.parse(packageContent).version || 'unknown';
  } catch { return 'unknown'; }
}

function printHelp() {
  console.log(`
ORBIT Chat CLI

Usage: orbitchat [options]

All application settings are configured in orbitchat.yaml (see orbitchat.yaml.example).
Secrets (adapter API keys) go in VITE_ADAPTERS / ORBIT_ADAPTERS env var.

Options:
  --port PORT        Server port (default: 5173)
  --host HOST        Server host (default: localhost)
  --open             Open browser automatically
  --config PATH      Path to orbitchat.yaml (default: ./orbitchat.yaml)
  --api-only         Run API proxy only (no UI serving)
  --cors-origin URL  Allowed CORS origin in api-only mode (default: *)
  --help, -h         Show this help message
  --version, -v      Show version number

Environment Variables:
  ORBIT_ADAPTERS or VITE_ADAPTERS   JSON array of adapter configurations (secrets)
    Example: '[{"name":"Chat","apiKey":"key1","apiUrl":"https://api.example.com"}]'

Examples:
  orbitchat --port 8080
  orbitchat --config /path/to/orbitchat.yaml --open
  orbitchat --api-only --cors-origin http://localhost:3001
`);
}

// ---- Main ----

function main() {
  if (process.argv.includes('--version') || process.argv.includes('-v')) {
    console.log(getVersion());
    return;
  }
  if (process.argv.includes('--help') || process.argv.includes('-h')) {
    printHelp();
    return;
  }

  const serverConfig = parseArgs();
  loadDotEnv(process.cwd());

  // Load YAML config
  const yamlPath = serverConfig.configFile || path.join(process.cwd(), 'orbitchat.yaml');
  const yamlObj = loadYamlConfig(yamlPath);
  const yamlFlat = yamlObj ? flattenYamlConfig(yamlObj) : {};

  if (yamlObj) {
    console.debug(`Loaded config from ${yamlPath}`);
  }

  // Merge: DEFAULTS < YAML config < auth secrets from env
  const config = { ...DEFAULTS, ...yamlFlat };

  // Auth secrets from env
  if (process.env.VITE_AUTH_DOMAIN) config.authDomain = process.env.VITE_AUTH_DOMAIN;
  if (process.env.VITE_AUTH_CLIENT_ID) config.authClientId = process.env.VITE_AUTH_CLIENT_ID;
  if (process.env.VITE_AUTH_AUDIENCE) config.authAudience = process.env.VITE_AUTH_AUDIENCE;

  // Default adapter fallback
  const trimmedDefaultKey = (config.defaultKey || '').trim();
  if (!trimmedDefaultKey || trimmedDefaultKey === DEFAULTS.defaultKey) {
    const fallbackAdapter = getDefaultAdapterFromEnv();
    if (fallbackAdapter) {
      config.defaultKey = fallbackAdapter;
    }
  }

  // Guest rate limiting (server-only, never sent to browser)
  if (yamlObj && yamlObj.guestLimits?.rateLimit) {
    serverConfig.rateLimit = yamlObj.guestLimits.rateLimit;
  }

  // Find dist directory
  const distPath = path.join(__dirname, '..', 'dist');

  if (!serverConfig.apiOnly && !fs.existsSync(distPath)) {
    console.error('Error: dist directory not found. Please run "npm run build" first.');
    process.exit(1);
  }

  const app = createServer(
    serverConfig.apiOnly ? null : distPath,
    config,
    serverConfig
  );

  app.listen(serverConfig.port, serverConfig.host, () => {
    const url = `http://${serverConfig.host}:${serverConfig.port}`;
    if (serverConfig.apiOnly) {
      console.debug(`\n🚀 ORBIT API Proxy is running at ${url}\n`);
    } else {
      console.debug(`\n🚀 ORBIT Chat App is running at ${url}\n`);
    }
    console.debug('Configuration:');
    console.debug(`  Mode: ${serverConfig.apiOnly ? 'API-only (no UI)' : 'Full (API + UI)'}`);
    console.debug(`  API URL: ${config.apiUrl}`);
    console.debug(`  Default Adapter: ${config.defaultKey || '(not set)'}`);
    console.debug(`  Port: ${serverConfig.port}`);
    console.debug(`  Host: ${serverConfig.host}`);
    if (yamlObj) {
      console.debug(`  Config: ${yamlPath}`);
    }
    if (serverConfig.rateLimit && serverConfig.rateLimit.enabled !== false) {
      console.debug(`  Guest Rate Limiting: enabled (${serverConfig.rateLimit.maxRequests || 30} req/${(serverConfig.rateLimit.windowMs || 60000) / 1000}s, chat: ${serverConfig.rateLimit.chat?.maxRequests || 10} req/${(serverConfig.rateLimit.chat?.windowMs || 60000) / 1000}s)`);
    }
    const startupAdapters = loadAdaptersConfig();
    if (startupAdapters) {
      console.debug(`  Available Adapters: ${Object.keys(startupAdapters).join(', ')}`);
    } else {
      console.debug(`  Warning: No adapters configured. Set ORBIT_ADAPTERS or VITE_ADAPTERS environment variable.`);
    }
    console.debug('');

    if (serverConfig.open) {
      openBrowser(url);
    }
  });

  process.on('SIGINT', () => {
    console.debug('\n\nShutting down server...');
    process.exit(0);
  });
}

// Run if called directly
const isMainModule = process.argv[1] && (
  import.meta.url === `file://${process.argv[1]}` ||
  import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/')) ||
  path.basename(process.argv[1]) === 'orbitchat' ||
  path.basename(process.argv[1]) === 'orbitchat.js'
);

if (isMainModule) {
  main();
}

export { main, createServer, loadAdaptersConfig };
