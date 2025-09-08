# 🔒 Security Analysis & Implementation Plan: Temporary Key Service

## 1. Current Attack Scenarios

### 📱 Scenario 1: Dev Console Analysis
An attacker opens the browser's developer console, inspects network traffic, and extracts the API key from request headers.

```javascript
// Attacker sees this in the Network tab:
// POST /v1/chat
// Headers: { "X-API-Key": "temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA" }

// Attacker can now copy this key and use it for malicious requests:
fetch('https://your-api.com/v1/chat', {
  headers: { 'X-API-Key': 'temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA' },
  method: 'POST',
  body: JSON.stringify(maliciousPayload)
})
```

### 🤖 Scenario 2: Automated Abuse (DDoS)
Using a stolen key, an attacker scripts a large volume of requests to incur costs, cause a denial-of-service, or poison data.

```python
# Attacker scripts automated requests with a stolen key
import requests
stolen_temp_key = "temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA"

for i in range(10000):  # DDoS attack
    requests.post('https://your-api.com/v1/chat', 
                  headers={'X-API-Key': stolen_temp_key},
                  json={"messages": [{"role": "user", "content": "spam"}]})
```

## 2. System Architecture & Flow

To mitigate these risks, we will move from a simple static API key to a dynamic, short-lived session model.

1.  **Authentication**: A backend service (e.g., a web server) authenticates itself using a **permanent API key**, which is kept secret and never exposed to the browser.
2.  **Key Exchange**: The backend calls a new, secure endpoint (e.g., `POST /v1/auth/session/start`) with its permanent key.
3.  **Session Creation**: The server validates the permanent key, generates a `temporary_key` and a secret `signing_key`, and stores them in a new `api_key_sessions` database collection with a short expiry time (e.g., 15 minutes).
4.  **Credential Delivery**: The `temporary_key` and `signing_key` are returned to the backend, which then passes them to the client-side application (e.g., JavaScript in the browser).
5.  **Request Signing**: For each subsequent API call, the client-side code generates an HMAC signature for the request payload using the `signing_key`.
6.  **Signed Request**: The client sends the `temporary_key`, the `signature`, and a `timestamp` in the request headers.
7.  **Server-Side Validation**: The API server uses the `temporary_key` to look up the corresponding `signing_key` in its database, re-computes the signature, and validates it against the one provided, also checking the timestamp and IP address.

## 3. Recommended Security Enhancements

### 1. **Request Signing (HMAC)** (Critical)
This is the core of the new security model. A stolen `temporary_key` is useless without the corresponding `signing_key` to generate valid signatures for requests.

```python
# server/services/api_key_service.py
async def validate_request_signature(
    self,
    temporary_key: str,
    signature_header: str,
    timestamp_header: str,
    request_body: bytes,
    request_ip: str
) -> bool:
    # 1. Fetch session from DB
    session = await self.get_session_data(temporary_key)
    if not session: return False

    # 2. Check IP binding
    if session.get("ip_address") != request_ip: return False
            
    # 3. Check timestamp freshness (prevent replay attacks)
    if abs(time.time() - int(timestamp_header)) > 300: # 5 min window
        return False

    # 4. Verify HMAC signature
    expected_sig = hmac.new(
        session['signing_key'].encode(),
        f"{timestamp_header}:".encode() + request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_sig, signature_header)
```

### 2. **Server-Side Rate Limiting** (Critical)
This is the first line of defense against brute-force and DDoS attacks.

```python
# Add to a middleware or route decorator
from slowapi import Limiter
from slowapi.util import get_remote_address

# Limit by IP, but could be enhanced to limit by permanent key principal
limiter = Limiter(key_func=get_remote_address)

@limiter.limit("20/minute")  # 20 requests per minute per IP
@limiter.limit("5/second")   # Burst protection
async def chat_endpoint(...):
```

### 3. **Secure Key Exchange Endpoint** (High Priority)
A dedicated, secure endpoint is required to exchange a permanent key for a temporary session.
- **Endpoint**: `POST /v1/auth/session/start`
- **Request**: `{ "permanent_api_key": "api_..." }`
- **Response**: `{ "temporary_key": "temp_...", "signing_key": "...", "expires_at": "..." }`
- **Security**: This endpoint must be rate-limited and only accept valid, active permanent keys.

### 4. **IP Binding** (Medium Priority)
Tying a temporary key to the IP address that created it prevents a stolen key from being used by an attacker in another location. The validation logic is shown in the `validate_request_signature` example above.

### 5. **Scoped Permissions** (Medium Priority)
Temporary keys should be generated with the minimum required permissions. For example, a key for a chat widget should only be granted access to chat-related endpoints.
- The `api_key_sessions` document should contain a `scopes` field: `["chat:read", "chat:write"]`.
- API endpoints will check if the session has the required scope before proceeding.

### 6. **Enhanced Session Tracking & Anomaly Detection**
Log session activity and build a scoring system to proactively identify and block abuse.

```python
# Schema for api_key_sessions collection
session_document = {
    "permanent_key_id": ObjectId("..."),
    "temporary_key": "temp_...",
    "signing_key": "...", # Hashed, if possible
    "created_at": datetime.now(UTC),
    "expires_at": datetime.now(UTC) + timedelta(minutes=15),
    "ip_address": "123.45.67.89",
    "user_agent": "Mozilla/5.0...",
    "scopes": ["chat:read"],
    "request_count": 0,
    "suspicious_activity_score": 0
}
```

## 4. Service Implementation Details (`ApiKeyService`)

### New MongoDB Collection: `api_key_sessions`
- **Purpose**: Stores short-lived session data.
- **Fields**: As defined in the `session_document` schema above.
- **Indexes**:
    - A unique index on `temporary_key`.
    - A **TTL index** on `expires_at` to ensure automatic cleanup of expired sessions by MongoDB. `db.collection.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 })`

### New `ApiKeyService` Methods
- `async def create_temporary_session(permanent_api_key: str, request_info: dict)`: Validates permanent key, generates session, stores it, and returns `temporary_key`, `signing_key`, and `expires_at`.
- `async def validate_request_signature(...)`: The primary validation function for API endpoints, as detailed above.
- `async def revoke_temporary_session(temporary_key: str)`: An endpoint allowing for immediate, manual revocation of a session key by deleting its document.

## 5. Additional Security Layers

1.  **Use a Web Application Firewall (WAF) / CDN**: Services like Cloudflare or AWS WAF provide enterprise-grade DDoS mitigation, managed rate limiting, and malicious IP filtering.
2.  **Enforce Strict CORS Policy**: The server should only allow requests from known, trusted domains where the web client is hosted.
3.  **Return Security Headers**: Use headers like `Content-Security-Policy` (CSP), `Strict-Transport-Security` (HSTS), and `X-Content-Type-Options` to instruct browsers to enable built-in security features.
4.  **Client-Side Obfuscation**: While not a primary defense, simple obfuscation of the keys in browser memory can deter casual attackers. This is a low-priority "nice-to-have".

## 6. 🎯 Phased Implementation Plan

### **Phase 1 (Week 1-2): Core Session Service & Integration**
- **Task**: Implement the backend logic for the new session system.
- ✅ **`ApiKeyService`**: Add the new `api_key_sessions` collection with TTL index. Implement `create_temporary_session`, `validate_request_signature`, and `revoke_temporary_session`.
- ✅ **Endpoints**: Create the `POST /v1/auth/session/start` and `POST /v1/auth/session/end` (for revocation) endpoints.
- ✅ **Middleware**: Create a new authentication middleware/dependency that uses `validate_request_signature`.
- ✅ **Pilot Integration**: Update a single critical endpoint (e.g., `/v1/chat`) to use the new validation middleware.
- ✅ **Client Update**: Modify the `clients/node-api/api.ts` client to handle the key exchange and sign all requests to the pilot endpoint.

### **Phase 2 (Week 3): Rate Limiting & Hardening**
- **Task**: Add abuse prevention and roll out the new security model.
- ✅ **Rate Limiting**: Implement server-side rate limiting (`slowapi`) on the session creation endpoint and high-traffic API endpoints.
- ✅ **IP Binding**: Enforce IP address matching within the `validate_request_signature` function.
- ✅ **CORS & Headers**: Configure and deploy a strict CORS policy and add security headers (CSP, HSTS) to all API responses.
- ✅ **Full Rollout**: Migrate all remaining public-facing API endpoints to use the new signature validation middleware.

### **Phase 3 (Week 4): Monitoring & Advanced Detection**
- **Task**: Build visibility and proactive defense mechanisms.
- ✅ **Logging**: Implement detailed logging for session creation, validation success/failure, and revocation.
- ✅ **Alerting**: Create basic alerts for high rates of validation failures, multiple IPs using the same key, or rapid session creation from a single IP.
- ✅ **Session Tracking**: Begin populating and updating fields like `request_count` and `user_agent` to lay the groundwork for anomaly detection.