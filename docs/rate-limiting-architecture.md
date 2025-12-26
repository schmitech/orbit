# Rate Limiting Architecture

This document describes the rate limiting implementation in ORBIT, designed to protect API endpoints from abuse, DDoS attacks, and excessive usage.

## Overview

ORBIT implements Redis-backed rate limiting using a fixed window counter algorithm. Rate limits are applied based on **IP address** and optionally **API key**, providing tiered access control for authenticated vs. anonymous requests.

**Note:** Fixed window counting resets at minute/hour boundaries. This means theoretically up to 2x the limit could occur at window boundaries (e.g., 60 requests at 11:59:59 + 60 at 12:00:00). For most use cases this is acceptable and provides simpler, faster Redis operations.

**Important:** Rate limiting is completely independent of session tracking. The `X-Session-ID` header is used for conversation history and is **not involved** in rate limit calculations.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Incoming Request                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      RateLimitMiddleware                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Check if rate limiting is enabled                            │   │
│  │ 2. Check if path is excluded (/health, /metrics, etc.)          │   │
│  │ 3. Check if Redis service is available                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Extract Rate Limit Keys:                                         │   │
│  │   • IP Address (from X-Forwarded-For, X-Real-IP, or client.host)│   │
│  │   • API Key (from X-API-Key header, optional)                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Check IP Rate Limit                                              │   │
│  │   Redis: INCR ratelimit:ip:min:{minute}:{ip}                    │   │
│  │   Redis: INCR ratelimit:ip:hr:{hour}:{ip}                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                    │                          │
│                   Exceeded?              Within Limit                    │
│                          │                    │                          │
│                          ▼                    ▼                          │
│                   ┌──────────┐    ┌─────────────────────────────────┐   │
│                   │ 429 JSON │    │ Has API Key?                    │   │
│                   │ Response │    │   Yes → Check API Key Limit     │   │
│                   └──────────┘    │   No  → Allow Request           │   │
│                                   └─────────────────────────────────┘   │
│                                               │                          │
│                                               ▼                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Add Response Headers:                                            │   │
│  │   • X-RateLimit-Limit: {limit}                                  │   │
│  │   • X-RateLimit-Remaining: {remaining}                          │   │
│  │   • X-RateLimit-Reset: {unix_timestamp}                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          Continue to Route Handler
```

## Configuration

Rate limiting is configured in `config/config.yaml` under the `security` section:

```yaml
security:
  rate_limiting:
    enabled: true                    # Master switch (requires Redis to be enabled)
    
    # IP-based limits (applies to ALL requests)
    ip_limits:
      requests_per_minute: 60        # Max requests per IP per minute
      requests_per_hour: 1000        # Max requests per IP per hour
      
    # API key limits (higher limits for authenticated requests)
    api_key_limits:
      requests_per_minute: 120       # Max requests per API key per minute
      requests_per_hour: 5000        # Max requests per API key per hour
    
    # Paths to exclude from rate limiting
    exclude_paths:
      - "/health"
      - "/favicon.ico"
      - "/metrics"
      - "/static"
      
    # Response configuration
    retry_after_seconds: 60          # Retry-After header value when limited
```

### Prerequisites

Rate limiting requires:

1. **Redis enabled** - The rate limiter uses Redis for distributed counter storage
   ```yaml
   internal_services:
     redis:
       enabled: true
       host: localhost
       port: 6379
   ```

2. **Rate limiting enabled** - Set `security.rate_limiting.enabled: true`

If Redis is disabled, the rate limiter will log a warning and pass all requests through (fail-open behavior).

## Rate Limit Keys

### IP Address Extraction

Client IP is extracted in the following priority order:

1. `X-Forwarded-For` header (first IP in comma-separated list)
2. `X-Real-IP` header
3. `request.client.host` (direct connection IP)
4. Falls back to `"unknown"` if none available

This ensures proper rate limiting when behind load balancers or reverse proxies.

### API Key Extraction

API key is extracted from the header configured in `api_keys.header_name` (default: `X-API-Key`).

**Note:** The API key is used for rate limiting separately from authentication. A valid API key grants higher rate limits regardless of whether it's validated for access control.

## Dual-Key Limiting Strategy

When a request includes an API key, **both** IP and API key limits are checked:

1. **IP limit check** - Always performed first
2. **API key limit check** - Only if API key is present in the request

If either limit is exceeded, the request is rejected with 429.

| Request Type | IP Limit Applied | API Key Limit Applied |
|--------------|------------------|----------------------|
| Anonymous (no API key) | Yes | No |
| Authenticated (with API key) | Yes | Yes |

This prevents abuse scenarios where:
- A single IP cycles through multiple API keys
- A single API key is used from multiple IPs

## Redis Key Structure

Rate limit counters are stored in Redis with the following key patterns:

```
ratelimit:{type}:{window}:{timestamp}:{identifier}
```

Examples:
```
ratelimit:ip:min:44853280:192.168.1.100      # IP minute window
ratelimit:ip:hr:12459:192.168.1.100          # IP hour window
ratelimit:apikey:min:44853280:sk-abc123...   # API key minute window
ratelimit:apikey:hr:12459:sk-abc123...       # API key hour window
```

Keys automatically expire after their window duration (60s for minute, 3600s for hour).

## Response Headers

All responses (including rate-limited ones) include standard rate limit headers:

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Maximum requests allowed in window | `60` |
| `X-RateLimit-Remaining` | Requests remaining in current window | `45` |
| `X-RateLimit-Reset` | Unix timestamp when window resets | `1703602800` |

These headers are exposed via CORS configuration:
```yaml
security:
  cors:
    expose_headers:
      - "X-RateLimit-Limit"
      - "X-RateLimit-Remaining"
      - "X-RateLimit-Reset"
```

## Rate Limited Response (429)

When a rate limit is exceeded:

**HTTP Status:** `429 Too Many Requests`

**Headers:**
```
Retry-After: 60
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1703602800
```

**Body:**
```json
{
  "detail": "Rate limit exceeded. Please retry after 60 seconds.",
  "retry_after": 60
}
```

## Excluded Paths

Certain paths are excluded from rate limiting to ensure critical functionality:

| Path | Reason |
|------|--------|
| `/health` | Health checks from load balancers/orchestrators |
| `/favicon.ico` | Browser favicon requests |
| `/metrics` | Prometheus/monitoring scrapes |
| `/static` | Static file serving |

Subpaths are also excluded (e.g., `/static/css/style.css`).

## Fail-Open Behavior

The rate limiter is designed to fail-open to prevent blocking legitimate traffic during infrastructure issues:

| Condition | Behavior |
|-----------|----------|
| Redis disabled | Pass through, no limiting |
| Redis unavailable | Pass through, log warning |
| Redis connection error | Pass through, log warning |
| Redis operation fails | Pass through, log warning |

This ensures service availability even when Redis is temporarily unreachable.

## Implementation Files

| File | Purpose |
|------|---------|
| `server/middleware/rate_limit_middleware.py` | Core middleware implementation |
| `server/config/middleware_configurator.py` | Middleware registration |
| `config/config.yaml` | Configuration (security.rate_limiting) |
| `server/tests/test_middleware/test_rate_limit_middleware.py` | Unit tests |

## Middleware Execution Order

Rate limiting middleware is added last in the configuration (meaning it executes first):

1. **Rate Limit Middleware** ← Executes first (rejects before processing)
2. Metrics Middleware
3. Logging Middleware
4. CORS Middleware
5. Security Headers Middleware ← Executes last (adds headers to response)

This ensures rate-limited requests are rejected immediately without consuming resources.

## Security Considerations

### DDoS Protection

- Per-IP limits prevent single-source flooding
- Hour-based limits prevent sustained attacks
- Low memory footprint (Redis counters only)

### API Key Abuse Prevention

- Dual-key limiting prevents key sharing across many IPs
- Per-key limits prevent automation abuse
- Separate tracking allows identifying problematic keys

### Proxy/CDN Compatibility

- Respects `X-Forwarded-For` and `X-Real-IP` headers
- Takes first IP from X-Forwarded-For (original client)
- Works correctly behind AWS ALB, nginx, Cloudflare, etc.

## Tuning Guidelines

### For High-Traffic APIs

```yaml
security:
  rate_limiting:
    ip_limits:
      requests_per_minute: 100
      requests_per_hour: 3000
    api_key_limits:
      requests_per_minute: 500
      requests_per_hour: 20000
```

### For Strict Rate Limiting

```yaml
security:
  rate_limiting:
    ip_limits:
      requests_per_minute: 20
      requests_per_hour: 200
    api_key_limits:
      requests_per_minute: 60
      requests_per_hour: 1000
```

### For Development/Testing

```yaml
security:
  rate_limiting:
    enabled: false  # Disable during development
```

## Monitoring

Monitor rate limiting effectiveness via:

1. **Application Logs** - Rate limit exceeded warnings include IP/API key
2. **Redis Keys** - Query `ratelimit:*` keys to see active counters
3. **Response Headers** - Track `X-RateLimit-Remaining` from client side
4. **429 Response Rate** - Monitor via metrics middleware

Example log output when limit exceeded:
```
WARNING - Rate limit exceeded for IP: 192.168.1.100
WARNING - Rate limit exceeded for API key: sk-abc1...
```

## Relationship with Session ID

**Session ID (`X-Session-ID`) is NOT used for rate limiting.**

| Header | Purpose | Used in Rate Limiting? |
|--------|---------|----------------------|
| `X-Session-ID` | Conversation history tracking | No |
| Client IP | Rate limiting key | Yes |
| `X-API-Key` | Rate limiting key (higher limits) | Yes |

Session tracking and rate limiting are independent systems:
- A user can have multiple sessions under one IP (all count toward IP limit)
- Rate limits reset regardless of session activity
- Session expiry has no effect on rate limit counters

