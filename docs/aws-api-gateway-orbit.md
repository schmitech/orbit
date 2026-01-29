# AWS API Gateway in Front of Orbit Server

This guide describes how to front an Orbit server (see `config/config.yaml`) with **AWS API Gateway** so that:

1. **Browser clients never see admin or key-management functionality** — only chat, threads, files, and autocomplete are exposed.
2. **Client API keys** (safe to embed in browser or mobile apps) are **translated to real Orbit API keys** on the backend, so the real keys never leave your infrastructure.
3. **Optional use of Lambda** for authorization and for limited “validate key” / “adapter info” endpoints that do not proxy to Orbit’s `/admin/*` routes.

The Node.js API client (`clients/node-api/api.ts`) is the reference for which Orbit endpoints exist; the goal is to **expose only a subset** to the public and perform key translation at the gateway.

---

## Endpoints Summary

Based on `clients/node-api/api.ts`, Orbit exposes the following. They are split into **browser-safe** (expose via API Gateway) and **admin-only** (do **not** expose to the browser).

### Browser-Safe Endpoints (Expose via API Gateway)

These are the only paths that should be reachable from the browser. The gateway (or Lambda) must add the **real** Orbit API key (`X-API-Key`) when calling Orbit.

| Method | Path | Purpose |
|--------|------|--------|
| `POST` | `/v1/chat` | Chat (supports SSE streaming; long timeouts) |
| `POST` | `/v1/chat/stop` | Stop an active stream |
| `GET` | `/v1/autocomplete` | Autocomplete suggestions (`q`, `limit`) |
| `POST` | `/api/threads` | Create thread |
| `GET` | `/api/threads/{thread_id}` | Get thread |
| `DELETE` | `/api/threads/{thread_id}` | Delete thread |
| `POST` | `/api/files/upload` | Upload file |
| `GET` | `/api/files` | List files |
| `GET` | `/api/files/{file_id}` | Get file info |
| `POST` | `/api/files/{file_id}/query` | Query file |
| `DELETE` | `/api/files/{file_id}` | Delete file |

Optional: a **gateway-only** "validate key" and "adapter info" (see [Lambda for validate and adapter info](#lambda-for-validate-and-adapter-info)) so the browser never calls Orbit's `/admin/*` routes.

### Infrastructure Endpoints (Optional)

These endpoints may be useful for infrastructure but should be evaluated based on your security requirements:

| Method | Path | Purpose | Recommendation |
|--------|------|---------|----------------|
| `GET` | `/health` | Health check | Expose without auth for load balancer health checks |
| `GET` | `/metrics` | Prometheus metrics | Keep internal (expose only to monitoring infrastructure) |
| `GET` | `/dashboard` | Monitoring dashboard | Keep internal (admin only) |

### WebSocket Endpoints (Not Covered)

Orbit supports WebSocket endpoints (`/ws`, `/mcp`) but these require special handling:

- **API Gateway HTTP API** has limited WebSocket support
- **API Gateway REST API** has a 29-second timeout limit
- **Recommendation**: Use a separate API Gateway WebSocket API or Application Load Balancer if you need WebSocket support

### Admin-Only Endpoints (Do NOT Expose to Browser)

These are used by the Node.js client when running in a trusted environment (e.g. backend). They must **not** be exposed through the public API Gateway used by the browser.

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/admin/api-keys/{api_key}/status` | Validate API key, get status |
| `GET` | `/admin/api-keys/info` or `/admin/adapters/info` | Adapter info for key |
| `GET` | `/admin/chat-history/{session_id}` | Get conversation history |
| `DELETE` | `/admin/chat-history/{session_id}` | Clear chat history |
| `DELETE` | `/admin/conversations/{session_id}` | Delete conversation and files |

Other admin routes (create/delete API keys, prompts, quotas, reload, shutdown, etc.) should also remain internal. Only the browser-safe list above should be exposed.

---

## Architecture Overview

- **Browser** sends requests to **API Gateway** with a **client API key** (e.g. in `X-API-Key` or a custom header like `X-Client-Key`).
- **API Gateway**:
  - Restricts which paths are exposed (only the browser-safe list).
  - Uses a **Lambda authorizer** (or a Lambda that proxies requests) to:
    - Validate the client API key.
    - Resolve **client key → real Orbit API key** (e.g. from DynamoDB or Secrets Manager).
    - Either inject the real key into the request to Orbit (authorizer + integration mapping) or call Orbit from Lambda with the real key (proxy).
- **Orbit** runs behind a VPC (e.g. on ECS/EC2 behind an NLB, or reachable from Lambda via VPC). It only receives requests that already carry the **real** `X-API-Key` and never sees the client key.

Two main patterns:

1. **HTTP API + Lambda authorizer + HTTP backend (Orbit)**  
   Authorizer returns the real API key in context; integration maps it to `X-API-Key` when forwarding to Orbit. No Lambda in the path for chat/files/threads.

2. **Lambda proxy (optional)**  
   Every request goes to Lambda; Lambda looks up the real key, calls Orbit, and returns the response. Useful if you need heavy request/response transformation or a single “validate/adapter info” endpoint implemented in Lambda.

---

## Client API Key → Real API Key Translation

### Data model

- **Client API key**: value you give to the browser (or mobile app). Example: `client_abc123` or a UUID. Safe to embed; it has no meaning except as an index into your mapping.
- **Real API key**: Orbit’s actual key (e.g. `orbit_...` from `config/config.yaml` and your key storage). Never sent to the browser.

Store the mapping in one of:

- **DynamoDB**  
  Table keyed by client API key; attribute `real_api_key` (or similar). Lambda authorizer reads from DynamoDB.
- **Secrets Manager**  
  One secret per client key (or one secret with a JSON map). Authorizer fetches and caches.
- **Parameter Store**  
  For small sets, e.g. `/orbit/client-keys/{client_key}` → real key string.

### Lambda authorizer (recommended)

1. **Input**: Request context (route, headers). Read the client API key from the header you use (e.g. `X-API-Key` or `X-Client-Key`).
2. **Lookup**: Fetch the real Orbit API key for that client key (DynamoDB/Secrets Manager/SSM).
3. **Output**:
   - If invalid: return a policy that **denies** the request (e.g. 401).
   - If valid: return an IAM policy that **allows** the request and put the real key in **context** (e.g. `realApiKey`).
4. **Integration**: In API Gateway, map the authorizer context to the backend request: add header `X-API-Key` = `context.realApiKey` (or the variable name you use).

Result: the browser sends `X-API-Key: client_abc123`; Orbit receives `X-API-Key: orbit_real_key_...`.

### Caching

Configure the authorizer result to be **cached** by API Gateway (e.g. TTL 300 seconds) so you don’t look up the same client key on every request. Cache key should include the client key (and optionally route).

---

## API Gateway Configuration

### Which routes to create

Create **only** routes for the browser-safe endpoints. Do **not** create routes for `/admin/*` (or any other internal paths).

Suggested mapping (path and method):

- `POST /v1/chat`
- `POST /v1/chat/stop`
- `GET /v1/autocomplete`
- `POST /api/threads`
- `GET /api/threads/{thread_id}`
- `DELETE /api/threads/{thread_id}`
- `POST /api/files/upload`
- `GET /api/files`
- `GET /api/files/{file_id}`
- `POST /api/files/{file_id}/query`
- `DELETE /api/files/{file_id}`

Use **proxy** or **greedy** path variables where your API Gateway type supports it (e.g. `{thread_id}`, `{file_id}`) so one configuration covers all IDs.

### Backend integration

- **Type**: HTTP backend (Orbit), or Lambda.
- **URL**: Your Orbit base URL (e.g. `https://orbit-internal.example.com` or NLB URL). Must be reachable from API Gateway (public URL) or from Lambda (VPC or public).
- **Headers**:  
  - Forward required headers (e.g. `Content-Type`, `X-Session-ID`, `X-User-ID`, `Accept` for SSE).  
  - Set `X-API-Key` from the authorizer context (real Orbit API key).  
  - Do **not** forward the raw client key to Orbit if you use a different header for clients (e.g. strip `X-Client-Key` or overwrite `X-API-Key`).

### Timeouts and payload size

- **Chat streaming**: Orbit uses SSE on `POST /v1/chat`. **Important limitations**:
  - **API Gateway HTTP API**: Fixed 30-second integration timeout (not configurable). Long conversations will be cut off.
  - **API Gateway REST API**: Maximum 29-second integration timeout.
  - **Workaround options**:
    1. Use **Application Load Balancer** (ALB) instead of API Gateway for `/v1/chat` (supports longer timeouts).
    2. Use **CloudFront + Lambda@Edge** with a longer timeout.
    3. Accept the limitation and handle reconnection on the client side.
    4. Use **NLB** (Network Load Balancer) with no timeout for pure TCP passthrough.
  - For non-streaming chat (`stream: false`), the 30-second limit is usually sufficient.
- **File upload**: Orbit allows large bodies (see `config/config.yaml` → `security.request_limits.max_body_size_mb`). Configure API Gateway and Lambda (if used) to allow the same (e.g. 10 MB). API Gateway has a 10 MB payload limit which matches the default Orbit configuration.

### CORS

If the browser calls the API from another origin, you need CORS headers. **Important**: Choose one of these approaches to avoid duplicate headers:

**Option 1: API Gateway handles CORS (recommended)**
- Enable CORS on API Gateway with allowed headers: `X-API-Key`, `X-Session-ID`, `X-User-ID`, `Content-Type`, `Accept`
- Disable CORS in Orbit's `config/config.yaml` → `security.cors` or set `allowed_origins: []`

**Option 2: Orbit handles CORS**
- Do not configure CORS in API Gateway
- Configure Orbit's `security.cors.allowed_origins` with your frontend domains
- Ensure API Gateway forwards `Origin` header to Orbit and returns Orbit's CORS headers to the client

If both API Gateway and Orbit add CORS headers, browsers may reject the response due to duplicate headers.

---

## Lambda for Validate and Adapter Info

The Node.js client’s `validateApiKey()` and `getAdapterInfo()` call Orbit’s `/admin/api-keys/{key}/status` and `/admin/adapters/info`. To avoid exposing `/admin/*` at all, you can implement two **gateway-only** endpoints that are handled by Lambda and never proxy to Orbit’s admin routes:

- `GET /v1/session/validate` (or `/v1/me`)  
  Accepts the **client** API key in the header. Lambda:
  1. Resolves client key → real key (same DynamoDB/Secrets Manager as the authorizer).
  2. Optionally calls Orbit’s `GET /admin/api-keys/{real_key}/status` from the Lambda (server-side only).
  3. Returns a minimal JSON, e.g. `{ "valid": true, "adapter_name": "..." }` or `{ "valid": false }`. Do **not** return the real key or internal details.

- `GET /v1/session/adapter-info` (or `/v1/me/adapter`)  
  Same idea: Lambda resolves client key → real key, calls Orbit’s `GET /admin/adapters/info` with the real key (from Lambda), then returns only the fields you consider safe for the browser (e.g. `client_name`, `adapter_name`, `model`).

Benefits:

- Browser only ever sends the client API key and only to these two paths and the other browser-safe paths.
- Orbit’s admin routes are never exposed; only Lambda (or your backend) talks to them.

Implement these as separate API Gateway routes with **Lambda integration** (no HTTP backend). The Lambda can run in a VPC if Orbit is only reachable privately.

---

## Example: Lambda Authorizer (Node.js)

This example assumes you store the mapping in **DynamoDB** with table name `orbit-client-keys`, partition key `client_key`, and attribute `real_api_key`.

```javascript
// Lambda authorizer: validate client key and return real key in context
const { DynamoDB } = require('@aws-sdk/client-dynamodb');
const { unmarshall } = require('@aws-sdk/util-dynamodb');

// Cache DynamoDB client outside handler for connection reuse
const client = new DynamoDB({});
const tableName = process.env.TABLE_NAME || 'orbit-client-keys';

exports.handler = async (event) => {
  // Note: Header names are lowercased by API Gateway
  const clientKey = event.headers?.['x-api-key'] || event.headers?.['X-API-Key'] || event.queryStringParameters?.apiKey;
  if (!clientKey) {
    return deny('Missing API key');
  }

  try {
    const result = await client.getItem({
      TableName: tableName,
      Key: { client_key: { S: clientKey } },
    });

    const row = result.Item ? unmarshall(result.Item) : null;

    if (!row || !row.real_api_key) {
      return deny('Invalid or inactive key');
    }

    // Optionally check if key is active
    if (row.active === false) {
      return deny('API key is disabled');
    }

    return allow(event.routeArn, { realApiKey: row.real_api_key });
  } catch (error) {
    console.error('DynamoDB error:', error);
    return deny('Authorization service error');
  }
};

function allow(routeArn, context) {
  return {
    principalId: 'user',
    policyDocument: {
      Version: '2012-10-17',
      Statement: [{ Action: 'execute-api:Invoke', Effect: 'Allow', Resource: routeArn }],
    },
    context: { realApiKey: context.realApiKey },
  };
}

function deny(reason) {
  // API Gateway turns this into 401 Unauthorized
  throw new Error(reason);
}
```

In API Gateway, configure the integration request to pass the authorizer context as a header:

- Header name: `X-API-Key`
- Header value: `context.realApiKey` (or the variable syntax your API Gateway type uses, e.g. `$context.authorizer.realApiKey`).

---

## Example: DynamoDB Table for Key Mapping

Minimal schema:

- **Table name**: e.g. `orbit-client-keys`
- **Partition key**: `client_key` (String) — the value you give to the browser.
- **Attributes**:  
  - `real_api_key` (String) — Orbit’s real API key.  
  - Optional: `name`, `ttl`, `active`, etc.

Restrict access so only the Lambda authorizer (and any admin Lambda) can read/write this table.

---

## Orbit Configuration Notes

### Rate Limiting Strategy

Orbit has built-in rate limiting (`security.rate_limiting` in config). With API Gateway in front, choose one approach:

**Option 1: Orbit handles rate limiting**
- Set `trust_proxy_headers: true` in Orbit config
- Add API Gateway's NAT IPs or Lambda's VPC NAT Gateway IPs to `trusted_proxies`
- This allows Orbit to see the real client IP from `X-Forwarded-For`

**Option 2: API Gateway handles rate limiting (recommended)**
- Disable Orbit's rate limiting (`security.rate_limiting.enabled: false`)
- Use API Gateway's built-in throttling (per-route or per-API key)
- Simpler to manage, no IP trust configuration needed

**Option 3: Both (defense in depth)**
- API Gateway provides first line of defense with coarse limits
- Orbit provides fine-grained per-session/per-key limits
- Requires proper `trusted_proxies` configuration

### Other Configuration

- **API key header**: Orbit reads the real key from `X-API-Key` (see `api_keys.header_name` in config). The gateway must send that header with the **real** key; the browser never needs to see it.
- **Session ID**: Orbit requires `X-Session-ID` when `general.session_id.required` is true. The browser can send session ID; the gateway should forward it unchanged.
- **User ID**: Orbit optionally accepts `X-User-ID` for user-level tracking. Forward this header if your application uses it.

---

## Testing

After deployment:

1. **Browser-safe endpoints**  
   Call the API Gateway URL with the **client** API key in the header (e.g. `X-API-Key: client_abc123`).  
   Example:
   ```bash
   curl -X POST "https://YOUR_API_GW_URL/v1/chat" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: YOUR_CLIENT_KEY" \
     -H "X-Session-ID: test-session-1" \
     -d '{"messages":[{"role":"user","content":"Hello"}],"stream":false}'
   ```
   Orbit should receive the request with the **real** API key and respond normally.

2. **Admin endpoints must not be reachable**  
   Requests to the same API Gateway base URL for paths like `/admin/api-keys/...` or `/admin/adapters/info` should return **403** or **404** (no such route), not Orbit’s admin response.

3. **Invalid client key**  
   Sending an unknown or revoked client key should result in **401** from the authorizer, and the request should never reach Orbit.

---

## Response Headers

Orbit returns several headers that should be forwarded to the browser:

### Quota/Rate Limit Headers
Forward these so clients can implement rate limit awareness:
- `X-Quota-Daily-Remaining`
- `X-Quota-Monthly-Remaining`
- `X-Quota-Daily-Reset`
- `X-Quota-Monthly-Reset`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `X-Throttle-Delay`

### Request Tracking
- `X-Request-ID` — Orbit generates this for tracing. Forward it back to the client.

### Security Headers
Orbit adds security headers (CSP, HSTS, X-Frame-Options, etc.). Options:
1. **Pass through** Orbit's security headers (simplest)
2. **Override** at API Gateway/CloudFront level for consistency across all your APIs
3. **Merge** if you need both

---

## Error Handling

Define consistent error responses for gateway-level failures:

| Scenario | HTTP Status | Response Body |
|----------|-------------|---------------|
| Missing client API key | 401 | `{"error": "Missing API key", "code": "MISSING_API_KEY"}` |
| Invalid client API key | 401 | `{"error": "Invalid API key", "code": "INVALID_API_KEY"}` |
| Disabled client API key | 403 | `{"error": "API key is disabled", "code": "API_KEY_DISABLED"}` |
| Orbit unreachable | 503 | `{"error": "Service temporarily unavailable", "code": "SERVICE_UNAVAILABLE"}` |
| Orbit timeout | 504 | `{"error": "Request timeout", "code": "TIMEOUT"}` |

For Lambda authorizer errors, configure API Gateway's gateway responses to return JSON instead of the default HTML.

---

## Summary

| Item | Recommendation |
|------|-----------------|
| **Public routes** | Only `/v1/chat`, `/v1/chat/stop`, `/v1/autocomplete`, `/api/threads`, `/api/files` and subpaths. Optionally `/health` for load balancer checks. |
| **Admin routes** | Do not expose `/admin/*`, `/metrics`, or `/dashboard` through the gateway used by the browser. |
| **Key translation** | Client key (browser) → real Orbit key (backend) via DynamoDB/Secrets Manager and a Lambda authorizer. |
| **Header to Orbit** | Set `X-API-Key` from authorizer context so Orbit always sees the real key. Forward `X-Session-ID` and `X-User-ID` from the client. |
| **Validate / adapter info** | Optionally implement `/v1/session/validate` and `/v1/session/adapter-info` in Lambda so the browser never calls Orbit admin. |
| **Timeouts** | API Gateway HTTP API has a fixed 30s timeout — consider ALB or NLB for long-running `/v1/chat` streams. 10 MB body limit for file uploads. |
| **CORS** | Handle in either API Gateway or Orbit, not both, to avoid duplicate headers. |
| **Rate limiting** | Choose API Gateway throttling, Orbit rate limiting, or both with proper `trusted_proxies` config. |
| **Response headers** | Forward quota headers (`X-Quota-*`, `X-RateLimit-*`) and `X-Request-ID` to the client. |
| **Error handling** | Configure gateway responses to return JSON errors for auth failures. |

Using this setup, the functionality used by `clients/node-api/api.ts` in the browser is restricted to the safe subset, and the real Orbit API key is only used on the backend after translating the client API key at API Gateway and/or Lambda.

---

## Example Terraform (HTTP API + Lambda Authorizer)

The following sketch creates an HTTP API with a Lambda authorizer and a single integration that forwards to Orbit. You would repeat the integration for each path/method or use a catch-all proxy if your API Gateway type supports it.

```hcl
# IAM role for Lambda authorizer
resource "aws_iam_role" "authorizer" {
  name = "orbit-api-authorizer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Allow Lambda to read from DynamoDB and write logs
resource "aws_iam_role_policy" "authorizer" {
  name = "orbit-api-authorizer-policy"
  role = aws_iam_role.authorizer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.client_keys.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Lambda authorizer
resource "aws_lambda_function" "authorizer" {
  filename      = "authorizer.zip"
  function_name = "orbit-api-authorizer"
  role          = aws_iam_role.authorizer.arn
  handler       = "index.handler"
  runtime       = "nodejs20.x"

  # Minimize cold start impact on auth latency
  memory_size = 256
  timeout     = 5

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.client_keys.name
    }
  }
}

resource "aws_lambda_permission" "authorizer" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
}

# HTTP API with authorizer
resource "aws_apigatewayv2_api" "orbit" {
  name          = "orbit-gateway"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_authorizer" "orbit" {
  api_id           = aws_apigatewayv2_api.orbit.id
  authorizer_type  = "REQUEST"
  authorizer_uri   = aws_lambda_function.authorizer.invoke_arn
  identity_sources = ["$request.header.X-API-Key"]
  name             = "orbit-key-authorizer"

  # Cache authorizer results to reduce Lambda invocations and latency
  # TTL in seconds (0 = no caching, max 3600)
  authorizer_result_ttl_in_seconds = 300
}

# Integration to Orbit backend (NLB or Orbit URL)
resource "aws_apigatewayv2_integration" "orbit" {
  api_id             = aws_apigatewayv2_api.orbit.id
  integration_type   = "HTTP_PROXY"
  integration_uri    = "https://your-orbit-internal.example.com"
  integration_method = "ANY"
  payload_format_version = "1.0"
  request_parameters = {
    "overwrite:header.X-API-Key" = "$context.authorizer.realApiKey"
  }
}

# Route example: POST /v1/chat
resource "aws_apigatewayv2_route" "chat" {
  api_id    = aws_apigatewayv2_api.orbit.id
  route_key = "POST /v1/chat"
  target    = "integrations/${aws_apigatewayv2_integration.orbit.id}"
  authorization_type = "CUSTOM"
  authorizer_id = aws_apigatewayv2_authorizer.orbit.id
}

# DynamoDB table for client_key -> real_api_key
# Note: Only key attributes need to be defined in attribute blocks.
# Non-key attributes (real_api_key, active, name, etc.) are schemaless.
resource "aws_dynamodb_table" "client_keys" {
  name         = "orbit-client-keys"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "client_key"

  attribute {
    name = "client_key"
    type = "S"
  }

  # Enable point-in-time recovery for production
  point_in_time_recovery {
    enabled = true
  }

  # Optional: Enable TTL for auto-expiring keys
  # ttl {
  #   attribute_name = "expires_at"
  #   enabled        = true
  # }

  tags = {
    Name        = "orbit-client-keys"
    Environment = "production"
  }
}
```

Add routes for each browser-safe path. Note: API Gateway HTTP API has a fixed 30-second integration timeout that cannot be changed. For long-running chat streams, consider the hybrid architecture below or use non-streaming mode (`stream: false`).

---

## Alternative: Full Lambda Proxy

Instead of HTTP backend + authorizer, you can send **all** browser-safe requests to a single Lambda (or one Lambda per route). The Lambda:

1. Reads the client API key from the request.
2. Looks up the real Orbit API key (DynamoDB/Secrets Manager).
3. Forwards the request to Orbit with `X-API-Key: <real_key>` and other headers/body.
4. Returns Orbit’s response (including streaming for `/v1/chat` if your runtime supports it).

Pros: full control over request/response, easy to add `/v1/session/validate` and `/v1/session/adapter-info` in the same Lambda. Cons: extra latency and cost per request; streaming requires careful handling in Lambda (e.g. response stream or chunked encoding).

---

## Alternative: Hybrid Architecture for Long Streams

If the 30-second API Gateway timeout is a problem for `/v1/chat` streaming, consider a hybrid approach:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │   API Gateway   │     │                 │
│     Browser     │────▶│  (most routes)  │────▶│      Orbit      │
│                 │     │                 │     │                 │
└────────┬────────┘     └─────────────────┘     └────────▲────────┘
         │                                               │
         │              ┌─────────────────┐              │
         │              │       ALB       │              │
         └─────────────▶│  (/v1/chat)     │──────────────┘
                        │                 │
                        └─────────────────┘
```

**Architecture**:
1. **API Gateway** handles all routes except `/v1/chat` (key translation, validation, etc.)
2. **Application Load Balancer (ALB)** handles `/v1/chat` with longer idle timeout (up to 4000 seconds)
3. **Lambda@Edge** or **ALB listener rules** perform key translation for the ALB path
4. Use **Route 53** or **CloudFront** to route `/v1/chat` to ALB, other paths to API Gateway

**ALB Key Translation Options**:
- **Lambda target group**: ALB forwards to a Lambda that does key lookup and proxies to Orbit
- **Cognito/OIDC auth**: If you can use JWT tokens instead of API keys
- **Custom auth service**: Separate microservice that validates keys and adds headers

This hybrid approach gives you API Gateway's features for most endpoints while supporting unlimited streaming duration for chat.
