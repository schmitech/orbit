/**
 * Tests for guest rate limiting (express-rate-limit) in bin/orbitchat.js
 *
 * Rate limiting applies only to unauthenticated requests (no Authorization header).
 * Requests hit /api/v1/chat without X-Adapter-Name: within-limit → 400 (missing header),
 * over-limit → 429. No mock backend needed.
 *
 * Run:
 *   node --test tests/rate-limit.test.js
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

// Provide adapter keys so the proxy routes are registered
const TEST_ADAPTER_KEYS = {
  'Test Agent': 'test-key-1',
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

// Send N sequential requests to url
async function sendRequests(url, n, options = {}) {
  const results = [];
  for (let i = 0; i < n; i++) {
    results.push(await fetch(url, options));
  }
  return results;
}

// ---------------------------------------------------------------------------
// 1. No 429 when rateLimit not configured
// ---------------------------------------------------------------------------

describe('Guest rate limiting – disabled (no config)', () => {
  let server;
  const PORT = 19900;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const app = createServer(null, {
      apiOnly: true,
      // No rateLimit in serverConfig
    });
    await new Promise((resolve) => {
      server = app.listen(PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (server) await new Promise((r) => server.close(r));
  });

  it('does not return 429 even after many requests', async () => {
    const results = await sendRequests(`${BASE}/api/v1/chat`, 20, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'hello' }),
    });

    for (const res of results) {
      assert.notEqual(res.status, 429, 'Should never get 429 when rate limiting is disabled');
    }
  });
});

// ---------------------------------------------------------------------------
// 2-5. Guest rate limiting enabled (unauthenticated requests)
// ---------------------------------------------------------------------------

describe('Guest rate limiting – enabled', () => {
  let server;
  const PORT = 19901;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const app = createServer(null, {
      apiOnly: true,
      rateLimit: {
        enabled: true,
        windowMs: 60000,
        maxRequests: 5,    // Low limit for testing
        chat: {
          windowMs: 60000,
          maxRequests: 3,  // Even lower for chat
        },
      },
    });
    await new Promise((resolve) => {
      server = app.listen(PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (server) await new Promise((r) => server.close(r));
  });

  // 2. Within-limit requests succeed (get 400 for missing adapter header, not 429)
  it('returns 400 (not 429) for guest requests within the limit', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 2, {
      method: 'GET',
      headers: {},
    });

    for (const res of results) {
      assert.equal(res.status, 400, 'Within-limit requests should get 400 (missing adapter header)');
    }
  });

  // 3. Returns 429 when general limit exceeded
  it('returns 429 when guest general limit exceeded', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 7, {
      method: 'GET',
      headers: {},
    });

    const has429 = results.some((r) => r.status === 429);
    assert.ok(has429, 'Should get at least one 429 after exceeding the limit');
  });

  // 4. 429 response has correct body shape
  it('429 includes correct JSON body', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 10, {
      method: 'GET',
      headers: {},
    });

    const rateLimited = results.find((r) => r.status === 429);
    assert.ok(rateLimited, 'Expected at least one 429 response');

    const data = jsonBody(rateLimited);
    assert.equal(data.error, 'Too many requests');
  });

  // 5. GET /api/adapters is not rate-limited (skip function)
  it('GET /api/adapters is not rate-limited', async () => {
    const results = await sendRequests(`${BASE}/api/adapters`, 10, {
      method: 'GET',
    });

    for (const res of results) {
      assert.equal(res.status, 200, 'GET /api/adapters should never be rate-limited');
    }
  });
});
