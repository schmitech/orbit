# API Key Security Implementation Guide

## Overview

This guide outlines the implementation strategy for securing API keys in a browser-based multi-tenant chatbot system where different API keys trigger different agent behaviors. Since API keys must be accessible client-side for tenant identification, we focus on minimizing exposure and implementing multiple layers of security.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Customer      │     │   Your Server    │     │   Chat API      │
│   Browser       │────▶│  (Proxy Layer)   │────▶│   Backend       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        │                        ├── Key Exchange
        ├── Temporary Key        ├── Rate Limiting
        └── Domain Validation    └── Anomaly Detection
```

## Phase 1: Temporary Key Exchange System

### 1.1 Client-Side Implementation

Update `api.ts` to support temporary key exchange:

```typescript
// api.ts additions
interface KeyExchangeResponse {
  temporaryKey: string;
  sessionId: string;
  expiresIn: number; // seconds
  expiresAt: number; // timestamp
}

let keyRefreshTimer: NodeJS.Timeout | null = null;

export const initializeChatbot = async (permanentApiKey: string): Promise<void> => {
  try {
    // Exchange permanent key for temporary session key
    const response = await fetch(`${getApiUrl()}/api/v1/exchange-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        apiKey: permanentApiKey,
        origin: window.location.origin
      })
    });
    
    if (!response.ok) {
      throw new Error('Failed to exchange API key');
    }
    
    const data: KeyExchangeResponse = await response.json();
    
    // Store only the temporary key
    configuredApiKey = data.temporaryKey;
    configuredSessionId = data.sessionId;
    
    // Clear permanent key from memory
    permanentApiKey = '';
    
    // Set up auto-refresh (90% of expiry time)
    const refreshInterval = data.expiresIn * 0.9 * 1000;
    keyRefreshTimer = setTimeout(() => refreshTemporaryKey(), refreshInterval);
    
  } catch (error) {
    console.error('Failed to initialize chatbot:', error);
    throw error;
  }
};

const refreshTemporaryKey = async (): Promise<void> => {
  if (!configuredSessionId) return;
  
  try {
    const response = await fetch(`${getApiUrl()}/api/v1/refresh-key`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-Session-ID': configuredSessionId
      }
    });
    
    if (!response.ok) {
      throw new Error('Failed to refresh key');
    }
    
    const data: KeyExchangeResponse = await response.json();
    configuredApiKey = data.temporaryKey;
    
    // Reset timer
    if (keyRefreshTimer) clearTimeout(keyRefreshTimer);
    const refreshInterval = data.expiresIn * 0.9 * 1000;
    keyRefreshTimer = setTimeout(() => refreshTemporaryKey(), refreshInterval);
    
  } catch (error) {
    console.error('Failed to refresh key:', error);
    // Emit event for handling by consumer
    window.dispatchEvent(new CustomEvent('chatbot:auth:failed'));
  }
};
```

### 1.2 Server-Side Key Exchange Endpoint

```javascript
// server/routes/keyExchange.js
const crypto = require('crypto');
const { validateApiKey, getKeyConfig } = require('../services/apiKeyService');

// In-memory store (use Redis in production)
const temporaryKeys = new Map();
const sessions = new Map();

app.post('/api/v1/exchange-key', async (req, res) => {
  const { apiKey, origin } = req.body;
  
  // Validate permanent API key
  const keyConfig = await getKeyConfig(apiKey);
  if (!keyConfig) {
    return res.status(401).json({ error: 'Invalid API key' });
  }
  
  // Validate origin
  if (!keyConfig.allowedOrigins.includes(origin)) {
    return res.status(403).json({ error: 'Origin not allowed' });
  }
  
  // Generate temporary key and session
  const temporaryKey = crypto.randomBytes(32).toString('hex');
  const sessionId = crypto.randomBytes(16).toString('hex');
  const expiresIn = 3600; // 1 hour
  const expiresAt = Date.now() + (expiresIn * 1000);
  
  // Store mapping
  temporaryKeys.set(temporaryKey, {
    permanentKey: apiKey,
    sessionId,
    expiresAt,
    origin,
    createdAt: Date.now()
  });
  
  sessions.set(sessionId, {
    permanentKey: apiKey,
    temporaryKey,
    expiresAt
  });
  
  res.json({
    temporaryKey,
    sessionId,
    expiresIn,
    expiresAt
  });
});

app.post('/api/v1/refresh-key', async (req, res) => {
  const sessionId = req.headers['x-session-id'];
  
  const session = sessions.get(sessionId);
  if (!session || session.expiresAt < Date.now()) {
    return res.status(401).json({ error: 'Invalid or expired session' });
  }
  
  // Generate new temporary key
  const newTemporaryKey = crypto.randomBytes(32).toString('hex');
  const expiresIn = 3600;
  const expiresAt = Date.now() + (expiresIn * 1000);
  
  // Update mappings
  temporaryKeys.delete(session.temporaryKey);
  temporaryKeys.set(newTemporaryKey, {
    permanentKey: session.permanentKey,
    sessionId,
    expiresAt,
    origin: req.headers.origin,
    createdAt: Date.now()
  });
  
  session.temporaryKey = newTemporaryKey;
  session.expiresAt = expiresAt;
  
  res.json({
    temporaryKey: newTemporaryKey,
    sessionId,
    expiresIn,
    expiresAt
  });
});
```

## Phase 2: Domain Locking & Request Validation

### 2.1 Enhanced Request Headers

Update `getFetchOptions` in `api.ts`:

```typescript
const getFetchOptions = (apiUrl: string, options: RequestInit = {}): RequestInit | any => {
  const isHttps = apiUrl.startsWith('https:');
  const requestId = Date.now().toString(36) + Math.random().toString(36).substring(2);
  const timestamp = Date.now();
  
  const headers: Record<string, string> = {
    'Connection': 'keep-alive',
    'X-Request-ID': requestId,
    'X-Timestamp': timestamp.toString(),
    'X-Origin': window.location.origin,
    'X-Referrer': document.referrer || 'direct',
  };
  
  // Add API key if configured
  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
    
    // Add request signature
    headers['X-Signature'] = generateRequestSignature(
      requestId,
      timestamp,
      options.body
    );
  }
  
  // Add session ID if exists
  const sessionId = getSessionId();
  if (sessionId) {
    headers['X-Session-ID'] = sessionId;
  }
  
  return {
    ...options,
    headers: {
      ...options.headers,
      ...headers
    }
  };
};

// Simple request signature (enhance with HMAC in production)
const generateRequestSignature = (
  requestId: string, 
  timestamp: number, 
  body?: any
): string => {
  const payload = `${requestId}:${timestamp}:${body ? JSON.stringify(body) : ''}`;
  return btoa(payload).substring(0, 16); // Simplified for example
};
```

### 2.2 Server-Side Validation Middleware

```javascript
// server/middleware/validateRequest.js
const { getTemporaryKeyInfo } = require('../services/keyService');

const validateRequest = async (req, res, next) => {
  const temporaryKey = req.headers['x-api-key'];
  const origin = req.headers['x-origin'];
  const timestamp = parseInt(req.headers['x-timestamp']);
  const signature = req.headers['x-signature'];
  
  // Basic validation
  if (!temporaryKey || !origin || !timestamp) {
    return res.status(400).json({ error: 'Missing required headers' });
  }
  
  // Timestamp validation (prevent replay attacks)
  const now = Date.now();
  if (Math.abs(now - timestamp) > 300000) { // 5 minutes
    return res.status(401).json({ error: 'Request timestamp invalid' });
  }
  
  // Get temporary key info
  const keyInfo = await getTemporaryKeyInfo(temporaryKey);
  if (!keyInfo || keyInfo.expiresAt < now) {
    return res.status(401).json({ error: 'Invalid or expired key' });
  }
  
  // Validate origin
  if (keyInfo.origin !== origin) {
    return res.status(403).json({ error: 'Origin mismatch' });
  }
  
  // Attach permanent key info for downstream use
  req.apiKey = keyInfo.permanentKey;
  req.keyConfig = await getKeyConfig(keyInfo.permanentKey);
  
  next();
};
```

## Phase 3: Rate Limiting & Monitoring

### 3.1 Client-Side Rate Limiting

Add to `api.ts`:

```typescript
// Rate limiter implementation
class RateLimiter {
  private requests: Map<string, number[]> = new Map();
  
  canMakeRequest(
    identifier: string, 
    maxRequests: number = 10, 
    windowMs: number = 60000
  ): boolean {
    const now = Date.now();
    const userRequests = this.requests.get(identifier) || [];
    const recentRequests = userRequests.filter(time => now - time < windowMs);
    
    if (recentRequests.length >= maxRequests) {
      return false;
    }
    
    recentRequests.push(now);
    this.requests.set(identifier, recentRequests);
    
    // Cleanup old entries
    if (this.requests.size > 1000) {
      this.cleanup(windowMs);
    }
    
    return true;
  }
  
  private cleanup(windowMs: number): void {
    const now = Date.now();
    for (const [key, requests] of this.requests.entries()) {
      const recent = requests.filter(time => now - time < windowMs);
      if (recent.length === 0) {
        this.requests.delete(key);
      } else {
        this.requests.set(key, recent);
      }
    }
  }
}

const rateLimiter = new RateLimiter();

// Update streamChat to include rate limiting
export async function* streamChat(
  message: string,
  stream: boolean = true
): AsyncGenerator<StreamResponse> {
  const sessionId = getSessionId() || 'anonymous';
  
  if (!rateLimiter.canMakeRequest(sessionId, 20, 60000)) {
    yield { 
      text: 'Rate limit exceeded. Please wait a moment before sending more messages.', 
      done: true 
    };
    return;
  }
  
  // ... existing implementation
}
```

### 3.2 Server-Side Rate Limiting

```javascript
// server/middleware/rateLimiter.js
const rateLimit = require('express-rate-limit');
const RedisStore = require('rate-limit-redis');

// Different limits for different API keys
const createRateLimiter = (keyConfig) => {
  return rateLimit({
    store: new RedisStore({
      client: redisClient,
      prefix: 'rl:',
    }),
    windowMs: keyConfig.rateLimitWindow || 60000,
    max: keyConfig.rateLimitMax || 100,
    message: 'Too many requests',
    keyGenerator: (req) => `${req.apiKey}:${req.ip}`,
    skip: (req) => keyConfig.unlimitedRateLimit === true
  });
};

// Apply in your routes
app.use('/api/v1/chat', validateRequest, (req, res, next) => {
  const limiter = createRateLimiter(req.keyConfig);
  limiter(req, res, next);
});
```

## Phase 4: Security Monitoring

### 4.1 Activity Logging

```javascript
// server/services/securityMonitor.js
class SecurityMonitor {
  async logActivity(apiKey, event, metadata) {
    await db.securityLogs.create({
      apiKey,
      event,
      metadata,
      timestamp: new Date(),
      ip: metadata.ip,
      origin: metadata.origin,
      userAgent: metadata.userAgent
    });
    
    // Check for suspicious patterns
    await this.checkAnomalies(apiKey);
  }
  
  async checkAnomalies(apiKey) {
    const recentLogs = await db.securityLogs.find({
      apiKey,
      timestamp: { $gte: new Date(Date.now() - 3600000) }
    });
    
    // Check for suspicious patterns
    const anomalies = {
      multipleOrigins: this.detectMultipleOrigins(recentLogs),
      unusualVolume: this.detectUnusualVolume(recentLogs),
      suspiciousPatterns: this.detectSuspiciousPatterns(recentLogs)
    };
    
    if (Object.values(anomalies).some(a => a)) {
      await this.alertAdministrator(apiKey, anomalies);
    }
  }
}
```

### 4.2 Client-Side Security Monitoring

```typescript
// Add to api.ts
const securityMonitor = {
  detectDevTools(): boolean {
    const threshold = 160;
    return (window.outerHeight - window.innerHeight > threshold) || 
           (window.outerWidth - window.innerWidth > threshold);
  },
  
  setupHoneypots(): void {
    // Detect attempts to access API keys via console
    const suspiciousProps = ['apiKey', 'api_key', 'apikey', 'key'];
    
    suspiciousProps.forEach(prop => {
      Object.defineProperty(window, prop, {
        get() {
          // Log suspicious activity
          fetch(`${getApiUrl()}/api/v1/security/suspicious`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: 'honeypot_triggered',
              property: prop,
              timestamp: Date.now(),
              url: window.location.href
            })
          }).catch(() => {}); // Fail silently
          
          return undefined;
        },
        set() {
          // Ignore sets
        }
      });
    });
  },
  
  init(): void {
    this.setupHoneypots();
    
    // Periodic dev tools check
    setInterval(() => {
      if (this.detectDevTools()) {
        console.warn('Development tools detected');
      }
    }, 1000);
  }
};

// Initialize security monitoring
securityMonitor.init();
```

## Implementation Plan

### Foundation
- [ ] Implement temporary key exchange system
- [ ] Update client-side API to use temporary keys
- [ ] Set up basic key storage (Redis/memory)
- [ ] Implement key refresh mechanism

### Validation & Security
- [ ] Add domain locking to API keys
- [ ] Implement request signature validation
- [ ] Add timestamp validation
- [ ] Set up CORS properly

### Rate Limiting & Monitoring
- [ ] Implement client-side rate limiting
- [ ] Set up server-side rate limiting with Redis
- [ ] Add comprehensive request logging
- [ ] Implement anomaly detection

### Testing & Documentation
- [ ] Security testing and penetration testing
- [ ] Performance testing under load
- [ ] Update API documentation
- [ ] Create customer integration guide

## Integration Guide

### Basic Integration

```html
<!-- Customer's website -->
<script>
  (function() {
    // Initialize chatbot with API key
    window.initializeChatbot('YOUR_API_KEY_HERE')
      .then(() => {
        console.log('Chatbot initialized');
      })
      .catch(error => {
        console.error('Failed to initialize chatbot:', error);
      });
  })();
</script>
```

### Advanced Integration with Error Handling

```javascript
// Customer's initialization code
const chatbotConfig = {
  apiKey: 'YOUR_API_KEY_HERE',
  onAuthFailure: () => {
    // Handle authentication failures
    console.error('Chatbot authentication failed');
  },
  onRateLimit: () => {
    // Handle rate limiting
    console.warn('Rate limit reached');
  }
};

// Listen for auth failures
window.addEventListener('chatbot:auth:failed', () => {
  // Re-initialize if needed
  initializeChatbot(chatbotConfig.apiKey);
});
```

## Security Best Practices

1. **Domain Whitelisting**: Only add trusted domains to your API key configuration
2. **Key Rotation**: Rotate API keys regularly (every 30-90 days)
3. **Monitoring**: Monitor API usage for unusual patterns
4. **HTTPS Only**: Always use HTTPS for production deployments
5. **CSP Headers**: Implement Content Security Policy headers

## Monitoring Dashboard Metrics

- Requests per minute/hour by API key
- Unique origins per API key
- Failed authentication attempts
- Rate limit violations
- Suspicious activity alerts
- Key usage by geographic location

## Rollback Plan

If issues arise:

1. **Phase 1**: Revert to direct API key usage (existing code)
2. **Phase 2**: Disable domain validation temporarily
3. **Phase 3**: Increase rate limits or disable temporarily
4. **Phase 4**: Continue logging but disable blocking

## Future Enhancements

1. **WebAuthn Support**: Add biometric authentication for high-security customers
2. **IP Whitelisting**: Allow customers to restrict access by IP
3. **Usage Analytics**: Provide detailed usage dashboards
4. **SDK Libraries**: Create official SDKs for popular frameworks
5. **Zero-Knowledge Proofs**: Investigate ZK proofs for authentication without key exposure

## References

- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [RFC 7617 - HTTP Basic Authentication](https://tools.ietf.org/html/rfc7617)
- [Web Crypto API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
- [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)