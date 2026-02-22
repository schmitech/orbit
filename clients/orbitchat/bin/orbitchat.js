#!/usr/bin/env node
/**
 * ORBIT Chat CLI
 *
 * Serves the chat-app as a standalone application with runtime configuration.
 * Configuration is read from orbitchat.yaml.
 * Secrets come from VITE_ADAPTER_KEYS / ORBIT_ADAPTER_KEYS env var.
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

function getCliVersion() {
  try {
    const pkgPath = path.join(__dirname, '..', 'package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    return pkg.version || 'unknown';
  } catch {
    return 'unknown';
  }
}

function printHelp() {
  console.log(`orbitchat [options]

Options:
  --port PORT        Server port (default: 5173)
  --host HOST        Server host (default: localhost)
  --open             Open browser automatically
  --config PATH      Path to orbitchat.yaml (default: ./orbitchat.yaml)
  --api-only         Run API proxy only (no UI serving)
  --cors-origin URL  Allowed CORS origin in api-only mode (default: *)
  --help, -h         Show help message
  --version, -v      Show version number`);
}

// ---- Minimal .env loader ----

function parseDotEnvValue(raw) {
  const trimmed = raw.trim();
  if (!trimmed) return '';
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
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
    if (process.env[key] !== undefined) continue;
    let valueRaw = trimmed.slice(equalsIndex + 1);
    const startsWithDouble = valueRaw.startsWith('"');
    const startsWithSingle = valueRaw.startsWith("'");
    if ((startsWithDouble && !valueRaw.endsWith('"')) || (startsWithSingle && !valueRaw.endsWith("'"))) {
      const quote = startsWithDouble ? '"' : "'";
      while (i + 1 < lines.length) {
        i += 1;
        valueRaw += `\n${lines[i]}`;
        if (lines[i].trim().endsWith(quote)) break;
      }
    }
    process.env[key] = parseDotEnvValue(valueRaw);
  }
}

function loadDotEnv(baseDir) {
  loadDotEnvFromFile(path.join(baseDir, '.env.local'));
  loadDotEnvFromFile(path.join(baseDir, '.env'));
}

// ---- Deep Merge ----

function isObject(item) {
  return typeof item === 'object' && item !== null && !Array.isArray(item);
}

function deepMerge(target, source) {
  if (!isObject(target) || !isObject(source)) return source;
  const output = { ...target };
  Object.keys(source).forEach(key => {
    if (isObject(target[key]) && isObject(source[key])) {
      output[key] = deepMerge(target[key], source[key]);
    } else if (source[key] !== undefined) {
      output[key] = source[key];
    }
  });
  return output;
}

// ---- Defaults ----

const DEFAULTS = {
  application: {
    name: 'ORBIT Chat',
    description: "Explore ideas with ORBIT's AI copilots, share context, and build together.",
    inputPlaceholder: 'Message ORBIT...',
    settingsAboutMsg: 'ORBIT Chat',
    locale: 'en-US',
  },
  debug: {
    consoleDebug: false,
  },
  features: {
    enableUpload: false,
    enableAudioOutput: false,
    enableAudioInput: false,
    enableFeedbackButtons: false,
    enableConversationThreads: true,
    enableAutocomplete: false,
  },
  voice: {
    silenceTimeoutMs: 4000,
    recognitionLanguage: '',
  },
  github: {
    showStats: true,
    owner: 'schmitech',
    repo: 'orbit',
  },
  outOfServiceMessage: null,
  limits: {
    files: { perConversation: 5, maxSizeMB: 50, totalFiles: 100 },
    conversations: { maxConversations: 10, messagesPerConversation: 1000, messagesPerThread: 1000, totalMessages: 10000 },
    messages: { maxLength: 1000 },
  },
  guestLimits: {
    files: { perConversation: 1, maxSizeMB: 10, totalFiles: 2 },
    conversations: { maxConversations: 1, messagesPerConversation: 10, messagesPerThread: 10, totalMessages: 10 },
    messages: { maxLength: 500 },
  },
  auth: { enabled: false, domain: '', clientId: '', audience: '' },
  header: { enabled: false, logoUrl: '', logoUrlLight: '', logoUrlDark: '', brandName: '', bgColor: '', textColor: '', showBorder: true, navLinks: [] },
  footer: { enabled: false, text: '', bgColor: '', textColor: '', showBorder: false, layout: 'stacked', align: 'center', topPadding: 'large', navLinks: [] },
  adapters: [],
};

// ---- YAML config loading ----

function loadYamlConfig(configPath) {
  try {
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf8');
      return yaml.load(content);
    }
  } catch (error) {
    console.error(`Error: Failed to parse ${configPath}: ${error.message}`);
    process.exit(1);
  }
  return null;
}

// ---- Local asset handling ----

function resolveLocalAssetPath(rawValue, yamlPath) {
  if (!rawValue || typeof rawValue !== 'string') return null;
  const value = rawValue.trim();
  if (!value || /^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(value) || value.startsWith('//')) return null;
  const expandedValue = value.startsWith('~/') ? path.join(process.env.HOME || '', value.slice(2)) : value;
  const yamlDir = path.dirname(yamlPath);
  const candidates = path.isAbsolute(expandedValue) ? [expandedValue] : [path.resolve(yamlDir, expandedValue), path.resolve(process.cwd(), expandedValue)];
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return fs.realpathSync(candidate);
    } catch { /* ignore */ }
  }
  return null;
}

// ---- Adapter loading (env secrets + YAML metadata) ----

function loadAdaptersForProxy(yamlAdapters) {
  const adapters = {};
  const fallbackApiUrl = 'http://localhost:3000';

  if (Array.isArray(yamlAdapters)) {
    for (const ya of yamlAdapters) {
      if (!ya.id) {
        console.warn(`[orbitchat] Adapter "${ya.name || '(unnamed)'}" is missing a required 'id' field — skipping.`);
        continue;
      }
      const id = ya.id;
      adapters[id] = {
        apiKey: '',
        apiUrl: ya.apiUrl || fallbackApiUrl,
        name: ya.name,
        description: ya.description,
        notes: ya.notes,
        model: ya.model
      };
    }
  }

  const envKeysRaw = process.env.VITE_ADAPTER_KEYS || process.env.ORBIT_ADAPTER_KEYS;
  if (envKeysRaw) {
    try {
      const keys = JSON.parse(envKeysRaw);
      for (const [id, value] of Object.entries(keys)) {
        const isObjectValue = typeof value === 'object' && value !== null;
        const apiKey = isObjectValue
          ? String(value.apiKey || value.key || '')
          : String(value);
        const apiUrl = isObjectValue && value.apiUrl ? String(value.apiUrl) : undefined;
        const description = isObjectValue && value.description ? String(value.description) : undefined;
        const notes = isObjectValue && value.notes ? String(value.notes) : undefined;
        const model = isObjectValue && value.model ? String(value.model) : undefined;

        if (!adapters[id]) {
          adapters[id] = {
            apiKey,
            apiUrl: apiUrl || fallbackApiUrl,
            description,
            notes,
            model
          };
        } else {
          adapters[id].apiKey = apiKey;
          if (apiUrl) adapters[id].apiUrl = apiUrl;
          if (description !== undefined) adapters[id].description = description;
          if (notes !== undefined) adapters[id].notes = notes;
          if (model !== undefined) adapters[id].model = model;
        }
      }
    } catch { /* ignore */ }
  }

  const finalAdapters = {};
  for (const [id, config] of Object.entries(adapters)) {
    if (config.apiKey) finalAdapters[id] = config;
  }
  if (Object.keys(finalAdapters).length > 0) {
    console.debug(`Loaded ${Object.keys(finalAdapters).length} adapters with API keys from environment.`);
  }
  return Object.keys(finalAdapters).length > 0 ? finalAdapters : null;
}

// ---- Express server ----

function createServer(distPath, config, serverConfig = {}) {
  const app = express();
  const adapters = loadAdaptersForProxy(config.adapters);
  const apiOnly = serverConfig.apiOnly || false;
  const localAssets = serverConfig.localAssets || {};

  if (apiOnly) {
    const allowedOrigin = serverConfig.corsOrigin || '*';
    app.use((req, res, next) => {
      res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-API-Key, X-Session-ID, X-Thread-ID, X-Adapter-Name, Accept, Authorization');
      if (req.method === 'OPTIONS') return res.sendStatus(204);
      next();
    });
  }

  if (Object.keys(localAssets).length > 0) {
    app.get('/__orbitchat_assets/:assetId', (req, res) => {
      const assetPath = localAssets[req.params.assetId];
      if (!assetPath || !fs.existsSync(assetPath)) return res.status(404).send('Asset not found');
      res.setHeader('Cache-Control', 'public, max-age=300');
      res.sendFile(assetPath);
    });
  }

  // Guest rate limiting
  if (serverConfig.rateLimit?.enabled !== false) {
    const rl = serverConfig.rateLimit || {};
    const apiLimiter = rateLimit({
      windowMs: rl.windowMs || 60000, max: rl.maxRequests || 30,
      skip: (req) => req.method === 'OPTIONS' || req.path === '/adapters',
      handler: (req, res) => res.status(429).json({ error: 'Too many requests' }),
    });
    const chatLimiter = rateLimit({
      windowMs: rl.chat?.windowMs || 60000, max: rl.chat?.maxRequests || 10,
      handler: (req, res) => res.status(429).json({ error: 'Chat rate limit exceeded' }),
    });
    app.use('/api', (req, res, next) => { if (req.headers.authorization) return next(); apiLimiter(req, res, next); });
    app.use('/api', (req, res, next) => {
      if (req.headers.authorization) return next();
      if (req.method === 'POST' && (/\/chat/i.test(req.path) || /\/stream/i.test(req.path))) return chatLimiter(req, res, next);
      next();
    });
  }

  if (adapters) {
    // Lazy model hydration for adapter cards (mirrors vite dev behavior).
    let modelsLastFetchedAt = 0;
    let modelsFetchInFlight = null;
    const MODELS_CACHE_TTL_MS = 30000;

    async function fetchAdapterModels(adapterMap, force = false) {
      const now = Date.now();
      if (!force && (now - modelsLastFetchedAt) < MODELS_CACHE_TTL_MS) return;
      if (modelsFetchInFlight) return modelsFetchInFlight;

      modelsFetchInFlight = (async () => {
        const fetches = Object.entries(adapterMap).map(async ([, adapter]) => {
          if (!adapter.apiUrl || !adapter.apiKey) return;
          try {
            const url = `${String(adapter.apiUrl).replace(/\/+$/, '')}/admin/adapters/info`;
            const resp = await fetch(url, {
              headers: { 'X-API-Key': adapter.apiKey },
              signal: AbortSignal.timeout(5000),
            });
            if (resp.ok) {
              const info = await resp.json();
              adapter.model = typeof info?.model === 'string' ? info.model.trim() || undefined : undefined;
            }
          } catch {
            // Best-effort only; cards can render without model metadata.
          }
        });
        await Promise.all(fetches);
        modelsLastFetchedAt = Date.now();
      })().finally(() => {
        modelsFetchInFlight = null;
      });

      return modelsFetchInFlight;
    }

    const buildAdapterList = (adapterMap) =>
      Object.keys(adapterMap).map(id => ({
        id,
        name: adapterMap[id].name || id,
        description: adapterMap[id].description,
        notes: adapterMap[id].notes,
        model: adapterMap[id].model || null
      }));

    app.get('/api/adapters', (req, res) => {
      const cacheControlHeader = typeof req.headers['cache-control'] === 'string' ? req.headers['cache-control'] : '';
      const forceRefresh = req.url?.includes('refresh=1') || cacheControlHeader.includes('no-cache');

      fetchAdapterModels(adapters, forceRefresh).then(() => {
        res.setHeader('Cache-Control', 'no-store');
        res.json({ adapters: buildAdapterList(adapters) });
      }).catch(() => {
        res.setHeader('Cache-Control', 'no-store');
        res.json({ adapters: buildAdapterList(adapters) });
      });
    });

    const dynamicProxy = createProxyMiddleware({
      target: 'http://localhost:3000', // Default fallback
      router: (req) => {
        const adapterName = req.headers['x-adapter-name'];
        return adapters[adapterName]?.apiUrl;
      },
      changeOrigin: true,
      pathRewrite: (p) => p.startsWith('/files') || p.startsWith('/threads') ? '/api' + p : p,
      on: {
        proxyReq: (proxyReq, reqIncoming) => {
          const adapterName = reqIncoming.headers['x-adapter-name'];
          const adapter = adapters[adapterName];
          if (adapter) {
            proxyReq.setHeader('X-API-Key', adapter.apiKey);
          }
          proxyReq.removeHeader('x-adapter-name');
          ['content-type', 'x-session-id', 'x-thread-id', 'accept', 'content-length', 'authorization'].forEach(h => {
            if (reqIncoming.headers[h]) proxyReq.setHeader(h, reqIncoming.headers[h]);
          });
        },
        error: (err, _req, resProxy) => {
          console.error('[Proxy] Proxy error:', err);
          if (!resProxy.headersSent) {
            resProxy.status(500).json({ error: 'Proxy error', message: err.message });
          }
        }
      },
      logLevel: 'silent',
    });

    app.use('/api', (req, res, next) => {
      if (req.path === '/adapters') return next('route');
      const adapterName = req.headers['x-adapter-name'];
      if (!adapterName) return res.status(400).json({ error: 'X-Adapter-Name header is required' });
      if (!adapters[adapterName]) return res.status(404).json({ error: `Adapter '${adapterName}' not found` });
      dynamicProxy(req, res, next);
    });
  }

  app.use(express.json());
  if (!apiOnly && distPath) {
    app.use(express.static(distPath, { index: false }));
    app.get(/(.*)/, (req, res) => {
      if (req.path.startsWith('/api/')) return res.status(404).json({ error: 'Not found' });
      const indexPath = path.join(distPath, 'index.html');
      let content = fs.readFileSync(indexPath, 'utf8');
      content = content.replace(/<script id="orbit-chat-config" type="application\/json">[\s\S]*?<\/script>/, '<!-- Config injected -->');
      const configScript = `<script>window.ORBIT_CHAT_CONFIG = ${JSON.stringify(config)};</script>`;
      content = content.replace(/<head>/i, '<head>\n    ' + configScript);
      if (config.application?.name) content = content.replace(/<title>.*?<\/title>/i, `<title>${config.application.name}</title>`);
      res.setHeader('Content-Type', 'text/html');
      res.send(content);
    });
  }
  return app;
}

// ---- Main ----

function main() {
  const args = process.argv.slice(2);
  const serverConfig = { port: 5173, host: 'localhost', open: false, configFile: null, apiOnly: false, corsOrigin: '*' };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port') serverConfig.port = parseInt(args[++i], 10);
    else if (args[i] === '--host') serverConfig.host = args[++i];
    else if (args[i] === '--open') serverConfig.open = true;
    else if (args[i] === '--config') serverConfig.configFile = args[++i];
    else if (args[i] === '--api-only') serverConfig.apiOnly = true;
    else if (args[i] === '--cors-origin') serverConfig.corsOrigin = args[++i];
    else if (args[i] === '--help' || args[i] === '-h') { printHelp(); return; }
    else if (args[i] === '--version' || args[i] === '-v') { console.log(getCliVersion()); return; }
  }

  loadDotEnv(process.cwd());
  const yamlPath = serverConfig.configFile || path.join(process.cwd(), 'orbitchat.yaml');
  const yamlObj = loadYamlConfig(yamlPath);
  let config = deepMerge(DEFAULTS, yamlObj || {});

  // Overlay secret env vars if they exist
  if (process.env.VITE_AUTH_DOMAIN) config.auth.domain = process.env.VITE_AUTH_DOMAIN;
  if (process.env.VITE_AUTH_CLIENT_ID) config.auth.clientId = process.env.VITE_AUTH_CLIENT_ID;
  if (process.env.VITE_AUTH_AUDIENCE) config.auth.audience = process.env.VITE_AUTH_AUDIENCE;

  const localAssets = {};
  const mapHeaderLogoAsset = (fieldName, assetId) => {
    const resPath = resolveLocalAssetPath(config.header?.[fieldName], yamlPath);
    if (!resPath) return;
    localAssets[assetId] = resPath;
    config.header[fieldName] = `/__orbitchat_assets/${assetId}?v=${Date.now()}`;
  };

  mapHeaderLogoAsset('logoUrl', 'header_logo');
  mapHeaderLogoAsset('logoUrlLight', 'header_logo_light');
  mapHeaderLogoAsset('logoUrlDark', 'header_logo_dark');

  const distPath = path.join(__dirname, '..', 'dist');
  const app = createServer(distPath, config, { ...serverConfig, rateLimit: yamlObj?.guestLimits?.rateLimit, localAssets });

  const server = app.listen(serverConfig.port, serverConfig.host, () => {
    console.debug(`🚀 ORBIT Chat is running at http://${serverConfig.host}:${serverConfig.port}`);
    if (serverConfig.open) execSync(`open http://${serverConfig.host}:${serverConfig.port}`);
  });
  // http-proxy may register multiple close listeners when routing across many adapters.
  // Raise the listener cap to avoid noisy false-positive MaxListeners warnings.
  if (typeof server.setMaxListeners === 'function') {
    server.setMaxListeners(0);
  }
}

const isMainModule = process.argv[1] && (import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/')) || path.basename(process.argv[1]) === 'orbitchat');
if (isMainModule) main();
export { main, createServer };
