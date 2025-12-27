# Rate Limiting & Throttling Architecture

This document describes the rate limiting and throttling implementation in ORBIT, designed to protect API endpoints from abuse, DDoS attacks, and excessive usage.

## Overview

ORBIT implements a two-layer traffic control system:

1. **Throttle Middleware** - Delays requests progressively as quota usage increases (soft limit)
2. **Rate Limit Middleware** - Rejects requests that exceed hard limits (hard limit)

Both systems use Redis-backed fixed window counters. Rate limits are applied based on **IP address** and optionally **API key**, while throttling supports **per-API-key daily/monthly quotas** with database persistence.

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
│                      ThrottleMiddleware (executes first)                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. Extract API key from request                                  │   │
│  │ 2. Check quota config (daily/monthly limits, throttle priority)  │   │
│  │ 3. Atomic increment: Redis daily + monthly counters              │   │
│  │ 4. If over hard limit → reject with 429                          │   │
│  │ 5. Calculate delay based on usage percentage                     │   │
│  │ 6. Apply delay (asyncio.sleep)                                   │   │
│  │ 7. Add quota headers to response                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      RateLimitMiddleware (executes second)               │
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

### Throttling Configuration

Throttling is configured separately under the `security.throttling` section:

```yaml
security:
  throttling:
    enabled: true                     # Master switch (requires Redis)

    # Default quotas for new API keys
    default_quotas:
      daily_limit: 10000              # Requests per day (null = unlimited)
      monthly_limit: 100000           # Requests per month (null = unlimited)

    # Delay settings
    delay:
      min_ms: 100                     # Minimum delay when throttling starts
      max_ms: 5000                    # Maximum delay at 100% quota usage
      curve: "exponential"            # Delay curve: "exponential" or "linear"
      threshold_percent: 70           # Start throttling at this usage %

    # Priority multipliers (1=premium, 10=low priority)
    priority_multipliers:
      1: 0.5                          # Premium: half the delay
      5: 1.0                          # Standard: normal delay
      10: 2.0                         # Low priority: double delay

    # Paths excluded from throttling
    exclude_paths: []

    # Redis configuration
    redis_key_prefix: "quota:"
    usage_sync_interval_seconds: 60   # Sync Redis counters to database

    # Response header names
    headers:
      delay: "X-Throttle-Delay"
      daily_remaining: "X-Quota-Daily-Remaining"
      monthly_remaining: "X-Quota-Monthly-Remaining"
      daily_reset: "X-Quota-Daily-Reset"
      monthly_reset: "X-Quota-Monthly-Reset"
```

### Prerequisites

Both rate limiting and throttling require:

1. **Redis enabled** - Used for distributed counter storage
   ```yaml
   internal_services:
     redis:
       enabled: true
       host: localhost
       port: 6379
   ```

2. **Feature enabled** - Set `security.rate_limiting.enabled: true` and/or `security.throttling.enabled: true`

If Redis is disabled, both middleware will log a warning and pass all requests through (fail-open behavior).

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

## Throttling & Quotas

### Storage Architecture

Quota management uses a **two-tier storage approach**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Quota System                                   │
├─────────────────────────────────┬───────────────────────────────────────┤
│         Redis (Real-time)       │      Database (Configuration)         │
├─────────────────────────────────┼───────────────────────────────────────┤
│ • Daily/monthly usage counters  │ • Quota limits (daily/monthly)        │
│ • Atomic increments via Lua     │ • Throttle enabled flag               │
│ • Auto-expiring keys (TTL)      │ • Priority settings                   │
│ • Last request timestamp        │ • Stored in api_keys collection       │
└─────────────────────────────────┴───────────────────────────────────────┘
```

**Database**: Uses your existing database (MongoDB or SQLite, based on `config.yaml`). No separate database is created - quota fields are added to the existing `api_keys` collection/table.

**Redis**: Stores real-time usage counters with automatic expiration. Required for throttling to function.

### Per-API-Key Quotas

Each API key can have individual quota settings stored in the database:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quota_daily_limit` | int (nullable) | null | Daily request limit (null = unlimited) |
| `quota_monthly_limit` | int (nullable) | null | Monthly request limit (null = unlimited) |
| `quota_throttle_enabled` | bool | true | Enable throttling for this key |
| `quota_throttle_priority` | int | 5 | Priority 1-10 (lower = less delay) |

### Backward Compatibility

**No database migration is required.** The system is designed for backward compatibility:

1. **Default values**: If an API key record doesn't have quota fields, defaults from `config.yaml` are used:
   ```python
   # Defaults applied when fields are missing
   daily_limit = config['security']['throttling']['default_quotas']['daily_limit']      # e.g., 10000
   monthly_limit = config['security']['throttling']['default_quotas']['monthly_limit']  # e.g., 100000
   throttle_enabled = True
   throttle_priority = 5
   ```

2. **On-demand field creation**: Quota fields are added to existing API key records only when you explicitly set them:
   ```bash
   # This adds quota_daily_limit to an existing API key record
   orbit quota set --key sk-existing-key --daily-limit 5000
   ```

3. **Existing API keys work immediately**: All existing API keys will use the default quotas without any changes.

| Scenario | Behavior |
|----------|----------|
| API key has no quota fields | Uses defaults from `config.yaml` |
| API key has some quota fields | Uses stored values, defaults for missing fields |
| API key has all quota fields | Uses all stored values |

### Redis Key Structure

Quota counters use daily/monthly windows with automatic expiration:

```
quota:{api_key}:daily:{YYYYMMDD}   # TTL: ~2 days (end of day + 1 day buffer)
quota:{api_key}:monthly:{YYYYMM}   # TTL: ~35 days (end of month + 5 day buffer)
quota:{api_key}:last_request       # Last request Unix timestamp
```

Examples:
```
quota:sk-abc123:daily:20241227     # Daily counter for Dec 27, 2024
quota:sk-abc123:monthly:202412     # Monthly counter for Dec 2024
quota:sk-abc123:last_request       # Timestamp of last request
```

Counters are incremented atomically using Lua scripts to prevent race conditions.

### Throttle Algorithm

```
1. Extract API key from request
2. If no API key or throttling disabled for key → pass through
3. Atomic Redis increment: daily + monthly counters
4. Check hard limits:
   - If daily_used > daily_limit → reject with 429 + quota headers
   - If monthly_used > monthly_limit → reject with 429 + quota headers
5. Calculate delay:
   usage_pct = max(daily_used/daily_limit, monthly_used/monthly_limit)
   if usage_pct < threshold (70%):
       delay = 0
   else:
       normalized = (usage_pct - 0.7) / 0.3
       if curve == "exponential":
           delay = min_delay + (max_delay - min_delay) * (normalized ^ 2)
       else:  # linear
           delay = min_delay + (max_delay - min_delay) * normalized
       delay *= priority_multipliers[key.priority]
6. await asyncio.sleep(delay / 1000)
7. Add response headers
8. Continue to next middleware
```

### Usage Tracking

The quota system tracks usage in Redis for performance, with the following characteristics:

| Aspect | Details |
|--------|---------|
| **Real-time tracking** | Redis counters increment atomically on each request |
| **Automatic reset** | Daily counters reset at midnight UTC, monthly on the 1st |
| **TTL-based expiration** | Redis keys auto-expire after their period + buffer |
| **Fail-open** | If Redis is unavailable, requests pass through (no throttling) |

**Important**: Usage counters live in Redis only. If Redis data is lost (restart without persistence), counters reset to zero. This is by design for simplicity - quota limits stored in the database remain intact.

## Response Headers

### Rate Limit Headers

All responses include standard rate limit headers:

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Maximum requests allowed in window | `60` |
| `X-RateLimit-Remaining` | Requests remaining in current window | `45` |
| `X-RateLimit-Reset` | Unix timestamp when window resets | `1703602800` |

### Throttle/Quota Headers

When throttling is enabled, additional quota headers are included:

| Header | Description | Example |
|--------|-------------|---------|
| `X-Throttle-Delay` | Delay applied in milliseconds | `250` |
| `X-Quota-Daily-Remaining` | Requests remaining today | `7500` |
| `X-Quota-Monthly-Remaining` | Requests remaining this month | `92500` |
| `X-Quota-Daily-Reset` | Unix timestamp of daily reset | `1703721600` |
| `X-Quota-Monthly-Reset` | Unix timestamp of monthly reset | `1704067200` |

### CORS Configuration

These headers are exposed via CORS configuration:
```yaml
security:
  cors:
    expose_headers:
      - "X-RateLimit-Limit"
      - "X-RateLimit-Remaining"
      - "X-RateLimit-Reset"
      - "X-Throttle-Delay"
      - "X-Quota-Daily-Remaining"
      - "X-Quota-Monthly-Remaining"
      - "X-Quota-Daily-Reset"
      - "X-Quota-Monthly-Reset"
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

## Quota Exceeded Response (429)

When a quota limit is exceeded (daily or monthly):

**HTTP Status:** `429 Too Many Requests`

**Headers:**
```
Retry-After: 3600
X-Quota-Daily-Remaining: 0
X-Quota-Monthly-Remaining: 50000
X-Quota-Daily-Reset: 1703721600
X-Quota-Monthly-Reset: 1704067200
```

**Body:**
```json
{
  "detail": "Daily quota exceeded. Limit: 10000, Used: 10001. Resets at 2024-12-28T00:00:00Z",
  "quota_type": "daily",
  "limit": 10000,
  "used": 10001,
  "reset_at": "2024-12-28T00:00:00Z"
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

### Rate Limiting

| File | Purpose |
|------|---------|
| `server/middleware/rate_limit_middleware.py` | Rate limit middleware implementation |
| `server/config/middleware_configurator.py` | Middleware registration |
| `config/config.yaml` | Configuration (security.rate_limiting) |

### Throttling & Quotas

| File | Purpose |
|------|---------|
| `server/middleware/throttle_middleware.py` | Throttle middleware with delay logic |
| `server/services/quota_service.py` | Quota management (Redis/DB operations) |
| `server/services/quota_background_tasks.py` | Background sync to database |
| `server/routes/admin_routes.py` | Quota REST API endpoints |
| `bin/orbit/commands/quota.py` | CLI quota commands |
| `config/config.yaml` | Configuration (security.throttling) |

## Middleware Execution Order

Middleware is added in reverse execution order (last added = first executed):

1. **Throttle Middleware** ← Executes first (delays before rate limiting)
2. **Rate Limit Middleware** ← Executes second (rejects before processing)
3. Metrics Middleware
4. Logging Middleware
5. CORS Middleware
6. Security Headers Middleware ← Executes last (adds headers to response)

This order ensures:
- Throttle delays happen before hard rate limits are checked
- Rate-limited requests are rejected without consuming resources
- Metrics capture includes both throttled and rate-limited requests

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

## Quota Management API

Admin endpoints for managing per-API-key quotas:

### Get Quota

```
GET /admin/api-keys/{api_key}/quota
Authorization: Bearer {admin_token}
```

Response:
```json
{
  "api_key_masked": "sk-abc...xyz",
  "quota": {
    "daily_limit": 10000,
    "monthly_limit": 100000,
    "throttle_enabled": true,
    "throttle_priority": 5
  },
  "usage": {
    "daily_used": 2500,
    "monthly_used": 45000,
    "daily_reset_at": 1703721600,
    "monthly_reset_at": 1704067200
  },
  "daily_remaining": 7500,
  "monthly_remaining": 55000,
  "throttle_delay_ms": 0
}
```

### Update Quota

```
PUT /admin/api-keys/{api_key}/quota
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "daily_limit": 20000,
  "monthly_limit": 200000,
  "throttle_enabled": true,
  "throttle_priority": 3
}
```

### Reset Usage

```
POST /admin/api-keys/{api_key}/quota/reset?period=daily
Authorization: Bearer {admin_token}
```

Period options: `daily`, `monthly`, `all`

### Usage Report

```
GET /admin/quotas/usage-report?period=daily&limit=50
Authorization: Bearer {admin_token}
```

Returns usage statistics for all API keys.

## CLI Quota Commands

Manage quotas via the `orbit` CLI:

### Get Quota

```bash
orbit quota get --key sk-abc123

# Output format options
orbit quota get --key sk-abc123 --output json
```

### Set Quota

```bash
# Set daily limit
orbit quota set --key sk-abc123 --daily-limit 10000

# Set monthly limit
orbit quota set --key sk-abc123 --monthly-limit 100000

# Set priority (1=premium, 10=low)
orbit quota set --key sk-abc123 --priority 3

# Enable/disable throttling
orbit quota set --key sk-abc123 --throttle-enabled true

# Set unlimited (0 = no limit)
orbit quota set --key sk-abc123 --daily-limit 0
```

### Reset Usage

```bash
# Reset daily usage
orbit quota reset --key sk-abc123 --period daily

# Reset monthly usage
orbit quota reset --key sk-abc123 --period monthly

# Reset all usage
orbit quota reset --key sk-abc123 --period all
```

### Usage Report

```bash
# Daily usage report (top 50 keys)
orbit quota report --period daily

# Monthly report with limit
orbit quota report --period monthly --limit 100

# JSON output
orbit quota report --period daily --output json
```

## Rollback

To disable throttling:

1. **Disable in config**:
   ```yaml
   security:
     throttling:
       enabled: false
   ```

2. **Clear Redis quota keys** (optional):
   ```bash
   redis-cli KEYS "quota:*" | xargs redis-cli DEL
   ```

3. **Restart the server**

Database quota fields are nullable and don't require migration to remove.
