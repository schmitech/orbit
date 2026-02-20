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

// Provide adapters so the proxy routes are registered
const TEST_ADAPTERS = [
  {
    name: 'Test Agent',
    apiKey: 'test-key-1',
    apiUrl: 'http://localhost:19999',
    description: 'First test agent',
  },
];

process.env.ORBIT_ADAPTERS = JSON.stringify(TEST_ADAPTERS);

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
    const app = createServer(null, { apiUrl: 'http://localhost:19999' }, {
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
    const app = createServer(null, { apiUrl: 'http://localhost:19999' }, {
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
    const results = await sendRequests(`${BASE}/api/v1/status`, 3, {
      method: 'GET',
      headers: {},
    });

    for (const res of results) {
      assert.equal(res.status, 400, 'Within-limit requests should get 400 (missing adapter header)');
    }
  });

  // 3. Returns 429 when general limit exceeded
  it('returns 429 when guest general limit exceeded', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 5, {
      method: 'GET',
      headers: {},
    });

    const has429 = results.some((r) => r.status === 429);
    assert.ok(has429, 'Should get at least one 429 after exceeding the limit');
  });

  // 4. 429 response has correct body shape
  it('429 includes correct JSON body with retryAfterMs', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 10, {
      method: 'GET',
      headers: {},
    });

    const rateLimited = results.find((r) => r.status === 429);
    assert.ok(rateLimited, 'Expected at least one 429 response');

    const data = jsonBody(rateLimited);
    assert.equal(data.error, 'Too many requests');
    assert.ok(typeof data.message === 'string');
    assert.ok(typeof data.retryAfterMs === 'number');
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

// ---------------------------------------------------------------------------
// 6-8. Chat limiter tests (separate server to get fresh stores)
// ---------------------------------------------------------------------------

describe('Guest rate limiting – chat limiter', () => {
  let server;
  const PORT = 19902;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const app = createServer(null, { apiUrl: 'http://localhost:19999' }, {
      apiOnly: true,
      rateLimit: {
        enabled: true,
        windowMs: 60000,
        maxRequests: 50,   // High general limit
        chat: {
          windowMs: 60000,
          maxRequests: 3,  // Low chat limit
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

  // 6. Stricter chat limiter on POST /api/v1/chat
  it('returns 429 on POST /api/v1/chat when chat limit exceeded', async () => {
    const results = await sendRequests(`${BASE}/api/v1/chat`, 6, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'hello' }),
    });

    const has429 = results.some((r) => r.status === 429);
    assert.ok(has429, 'Should get 429 on POST /api/v1/chat after exceeding chat limit');

    const rateLimited = results.find((r) => r.status === 429);
    const data = jsonBody(rateLimited);
    assert.ok(data.message.includes('Chat rate limit'), 'Should be chat rate limit message');
  });

  // 7. Chat limiter doesn't apply to non-chat paths
  it('chat limiter does not apply to GET /api/v1/status', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 6, {
      method: 'GET',
      headers: {},
    });

    for (const res of results) {
      assert.equal(res.status, 400, 'Non-chat GET requests should not trigger chat limiter');
    }
  });

  // 8. Chat and general limiters are independent stores
  it('chat and general limiters use independent stores', async () => {
    const getResults = await sendRequests(`${BASE}/api/v1/other`, 5, {
      method: 'GET',
      headers: {},
    });

    for (const res of getResults) {
      assert.equal(res.status, 400, 'General limiter should still have budget');
    }
  });
});

// ---------------------------------------------------------------------------
// 9. No 429 when rateLimit.enabled is explicitly false
// ---------------------------------------------------------------------------

describe('Guest rate limiting – explicitly disabled', () => {
  let server;
  const PORT = 19903;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const app = createServer(null, { apiUrl: 'http://localhost:19999' }, {
      apiOnly: true,
      rateLimit: {
        enabled: false,
        windowMs: 60000,
        maxRequests: 1,  // Very low — but disabled, so shouldn't matter
      },
    });
    await new Promise((resolve) => {
      server = app.listen(PORT, 'localhost', resolve);
    });
  });

  after(async () => {
    if (server) await new Promise((r) => server.close(r));
  });

  it('does not return 429 when rateLimit.enabled is false', async () => {
    const results = await sendRequests(`${BASE}/api/v1/chat`, 10, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'hello' }),
    });

    for (const res of results) {
      assert.notEqual(res.status, 429, 'Should never get 429 when enabled: false');
    }
  });
});

// ---------------------------------------------------------------------------
// 10. Authenticated requests bypass rate limiting entirely
// ---------------------------------------------------------------------------

describe('Guest rate limiting – authenticated bypass', () => {
  let server;
  const PORT = 19904;
  const BASE = `http://localhost:${PORT}`;

  before(async () => {
    const app = createServer(null, { apiUrl: 'http://localhost:19999' }, {
      apiOnly: true,
      rateLimit: {
        enabled: true,
        windowMs: 60000,
        maxRequests: 2,   // Very low limit
        chat: {
          windowMs: 60000,
          maxRequests: 1,  // Very low chat limit
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

  it('authenticated requests are never rate-limited (general)', async () => {
    const results = await sendRequests(`${BASE}/api/v1/status`, 10, {
      method: 'GET',
      headers: { Authorization: 'Bearer some-token' },
    });

    for (const res of results) {
      assert.notEqual(res.status, 429, 'Authenticated requests should never get 429');
    }
  });

  it('authenticated POST /api/v1/chat is never rate-limited', async () => {
    const results = await sendRequests(`${BASE}/api/v1/chat`, 10, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer some-token',
      },
      body: JSON.stringify({ message: 'hello' }),
    });

    for (const res of results) {
      assert.notEqual(res.status, 429, 'Authenticated chat requests should never get 429');
    }
  });

  it('guest requests still get 429 on the same server', async () => {
    // maxRequests is 2, so 5 unauthenticated requests should trigger 429
    const results = await sendRequests(`${BASE}/api/v1/status`, 5, {
      method: 'GET',
      headers: {},
    });

    const has429 = results.some((r) => r.status === 429);
    assert.ok(has429, 'Guest requests should still be rate-limited');
  });
});
