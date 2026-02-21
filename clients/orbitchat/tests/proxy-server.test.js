/**
 * Tests for the ORBIT Chat Express proxy server (bin/orbitchat.js)
 *
 * Uses Node's built-in test runner — no extra dependencies required.
 *
 * Run:
 *   node --test tests/proxy-server.test.js
 *   npm test
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

// Set ORBIT_ADAPTER_KEYS before importing the server module so loadAdaptersConfig picks them up
const TEST_ADAPTER_KEYS = {
  'Test Agent': 'test-key-1',
  'Second Agent': 'test-key-2',
  'Backend Agent': 'secret-key-abc',
};

process.env.ORBIT_ADAPTER_KEYS = JSON.stringify(TEST_ADAPTER_KEYS);

const { createServer } = await import('../bin/orbitchat.js');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const reqOptions = {
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname + parsed.search,
      method: options.method || 'GET',
      headers: options.headers || {},
    };

    const req = http.request(reqOptions, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });

    req.on('error', reject);

    if (options.body) {
      req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
    }
    req.end();
  });
}

function jsonBody(res) {
  return JSON.parse(res.body);
}

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// API-only server tests
// ---------------------------------------------------------------------------

describe('Express proxy – api-only mode', () => {
  let server;
  const PORT = 19876;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const config = {
       
      adapters: [
        {
          name: 'Test Agent',
          apiUrl: 'http://localhost:19999',
          description: 'First test agent',
          notes: 'Some **markdown** notes',
        },
        {
          name: 'Second Agent',
          apiUrl: 'http://localhost:19999',
          description: 'Second test agent',
        },
      ]
    };
    const serverConfig = { apiOnly: true, port: PORT, host: 'localhost' };
    const app = createServer(null, config, serverConfig);

    await new Promise((resolve) => {
      server = app.listen(PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  // -- GET /api/adapters ---------------------------------------------------

  describe('GET /api/adapters', () => {
    it('returns adapter names and descriptions', async () => {
      const res = await fetch(`${BASE}/api/adapters`);
      assert.equal(res.status, 200);

      const data = jsonBody(res);
      assert.ok(Array.isArray(data.adapters));
      assert.equal(data.adapters.length, 2);

      const names = data.adapters.map((a) => a.name);
      assert.ok(names.includes('Test Agent'));
      assert.ok(names.includes('Second Agent'));
    });

    it('includes description and notes but not apiKey or apiUrl', async () => {
      const res = await fetch(`${BASE}/api/adapters`);
      const data = jsonBody(res);

      const first = data.adapters.find((a) => a.name === 'Test Agent');
      assert.equal(first.description, 'First test agent');
      assert.equal(first.notes, 'Some **markdown** notes');
      assert.equal(first.apiKey, undefined);
      assert.equal(first.apiUrl, undefined);
    });
  });

  // -- CORS ----------------------------------------------------------------

  describe('CORS (default wildcard)', () => {
    it('sets Access-Control-Allow-Origin: * on responses', async () => {
      const res = await fetch(`${BASE}/api/adapters`);
      assert.equal(res.headers['access-control-allow-origin'], '*');
    });

    it('responds 204 to OPTIONS preflight', async () => {
      const res = await fetch(`${BASE}/api/adapters`, {
        method: 'OPTIONS',
        headers: {
          Origin: 'http://example.com',
          'Access-Control-Request-Method': 'POST',
          'Access-Control-Request-Headers': 'X-Adapter-Name',
        },
      });
      assert.equal(res.status, 204);
      assert.equal(res.headers['access-control-allow-origin'], '*');
      assert.ok(res.headers['access-control-allow-headers'].toLowerCase().includes('x-adapter-name'));
    });
  });

  // -- Missing adapter header ----------------------------------------------

  describe('Proxy routing', () => {
    it('returns 400 when X-Adapter-Name header is missing', async () => {
      const res = await fetch(`${BASE}/api/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'hello' }),
      });
      assert.equal(res.status, 400);
      const data = jsonBody(res);
      assert.ok(data.error.toLowerCase().includes('x-adapter-name'));
    });

    it('returns 404 for unknown adapter name', async () => {
      const res = await fetch(`${BASE}/api/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Adapter-Name': 'nonexistent',
        },
        body: JSON.stringify({ message: 'hello' }),
      });
      assert.equal(res.status, 404);
      const data = jsonBody(res);
      assert.ok(data.error.includes('nonexistent'));
    });
  });
});

// ---------------------------------------------------------------------------
// Custom CORS origin
// ---------------------------------------------------------------------------

describe('Express proxy – custom CORS origin', () => {
  let server;
  const PORT = 19877;
  const BASE = `http://localhost:${PORT}`;
  const ALLOWED_ORIGIN = 'http://my-custom-app.test';

  before(async () => {
    const config = {};
    const serverConfig = { apiOnly: true, port: PORT, host: 'localhost', corsOrigin: ALLOWED_ORIGIN };
    const app = createServer(null, config, serverConfig);

    await new Promise((resolve) => {
      server = app.listen(PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  it('sets Access-Control-Allow-Origin to the configured origin', async () => {
    const res = await fetch(`${BASE}/api/adapters`);
    assert.equal(res.headers['access-control-allow-origin'], ALLOWED_ORIGIN);
  });
});

// ---------------------------------------------------------------------------
// Proxy forwarding — spin up a mock backend to verify headers
// ---------------------------------------------------------------------------

describe('Express proxy – header forwarding to backend', () => {
  let proxyServer;
  let backendServer;
  let lastBackendRequest;
  const BACKEND_PORT = 19878;
  const PROXY_PORT = 19879;
  const PROXY_BASE = `http://localhost:${PROXY_PORT}`;

  before(async () => {
    // Mock backend that records the request it receives
    backendServer = http.createServer((req, res) => {
      let body = '';
      req.on('data', (chunk) => (body += chunk));
      req.on('end', () => {
        lastBackendRequest = {
          method: req.method,
          url: req.url,
          headers: { ...req.headers },
          body,
        };
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      });
    });

    await new Promise((resolve) => {
      backendServer.listen(BACKEND_PORT, 'localhost', resolve);
    });

    const config = {
       
      adapters: [
        {
          name: 'Backend Agent',
          apiUrl: `http://localhost:${BACKEND_PORT}`,
          description: 'Points at mock backend',
        },
      ]
    };
    const serverConfig = { apiOnly: true, port: PROXY_PORT, host: 'localhost' };
    const app = createServer(null, config, serverConfig);

    await new Promise((resolve) => {
      proxyServer = app.listen(PROXY_PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (proxyServer) await new Promise((r) => proxyServer.close(r));
    if (backendServer) await new Promise((r) => backendServer.close(r));
  });

  it('injects X-API-Key and forwards session headers to backend', async () => {
    await fetch(`${PROXY_BASE}/api/v1/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Adapter-Name': 'Backend Agent',
        'X-Session-ID': 'sess-123',
      },
      body: JSON.stringify({ message: 'hello' }),
    });

    assert.ok(lastBackendRequest, 'Backend should have received a request');
    assert.equal(lastBackendRequest.headers['x-api-key'], 'secret-key-abc');
    assert.equal(lastBackendRequest.headers['x-session-id'], 'sess-123');
  });

  it('preserves Content-Type on forwarded requests', async () => {
    await fetch(`${PROXY_BASE}/api/v1/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Adapter-Name': 'Backend Agent',
      },
      body: JSON.stringify({ message: 'test' }),
    });

    assert.equal(lastBackendRequest.headers['content-type'], 'application/json');
  });

  it('rewrites /files paths to /api/files for the backend', async () => {
    await fetch(`${PROXY_BASE}/api/files/upload`, {
      method: 'POST',
      headers: {
        'X-Adapter-Name': 'Backend Agent',
        'Content-Type': 'application/octet-stream',
      },
      body: 'fake-file-content',
    });

    // The pathRewrite in orbitchat.js prepends /api to /files paths
    assert.ok(
      lastBackendRequest.url.startsWith('/api/files'),
      `Expected backend URL to start with /api/files, got: ${lastBackendRequest.url}`
    );
  });
});
