# 🔒 Security Analysis: Temporary Key Service

## Current Attack Scenarios

### 📱 **Scenario 1: Dev Console Analysis**
```javascript
// Attacker opens dev console, sees this in Network tab:
// POST /v1/chat
// Headers: { "X-API-Key": "temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA" }

// Attacker can now copy this key and use it:
fetch('https://your-api.com/v1/chat', {
  headers: { 'X-API-Key': 'temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA' },
  method: 'POST',
  body: JSON.stringify(maliciousPayload)
})
```

### 🤖 **Scenario 2: Automated DDoS**
```python
# Attacker scripts automated requests
import requests
stolen_temp_key = "temp_key:OgtQHJcp4qXiWaSi8un4I6ggdshqSMToGvGMOQCZenA"

for i in range(10000):  # DDoS attack
    requests.post('https://your-api.com/v1/chat', 
                  headers={'X-API-Key': stolen_temp_key},
                  json={"jsonrpc": "2.0", "method": "tools/call", ...})
```

## 🛡️ Recommended Security Enhancements

### 1. **Server-Side Rate Limiting** (Critical)
```python
# Add to routes/routes_configurator.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@limiter.limit("20/minute")  # 20 requests per minute per IP
@limiter.limit("5/second")   # Burst protection
async def chat_endpoint(...):
```

### 2. **Request Signing** (High Priority)
```python
# Enhanced temporary key validation
async def validate_temporary_key_with_signature(
    self, 
    temporary_key: str, 
    request_signature: str,
    timestamp: str,
    request_body: str
) -> bool:
    # Get session data
    session = await self.get_session_data(temporary_key)
    if not session:
        return False
    
    # Check timestamp freshness (prevent replay attacks)
    if abs(time.time() - int(timestamp)) > 300:  # 5 minute window
        return False
    
    # Verify signature
    expected_sig = hmac.new(
        session['signing_key'].encode(),
        f"{timestamp}:{request_body}".encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_sig, request_signature)
```

### 3. **Enhanced Session Tracking**
```python
# Track suspicious activity per session
session_info = {
    "permanent_key": permanent_key,
    "origin": origin,
    "user_agent": user_agent,
    "ip_address": real_ip,
    "created_at": datetime.now(UTC).isoformat(),
    "request_count": 0,
    "last_request_time": None,
    "request_rate_violations": 0,
    "signing_key": secrets.token_urlsafe(32),  # For request signing
    "max_requests_per_minute": 20,
    "suspicious_activity_score": 0
}
```

### 4. **IP Binding** (Medium Priority)
```python
async def validate_request_ip(self, temporary_key: str, request_ip: str) -> bool:
    session = await self.get_session_data(temporary_key)
    if not session:
        return False
    
    # Bind temporary key to original IP (with some flexibility for mobile)
    original_ip = ipaddress.ip_address(session['ip_address'])
    request_ip_obj = ipaddress.ip_address(request_ip)
    
    # Allow same /24 subnet for mobile users
    if original_ip.version == 4:
        original_network = ipaddress.ip_network(f"{original_ip}/24", strict=False)
        return request_ip_obj in original_network
    
    return str(original_ip) == str(request_ip_obj)
```

### 5. **Anomaly Detection**
```python
async def detect_suspicious_activity(self, session_data: dict, request_info: dict) -> bool:
    suspicious_score = 0
    
    # Check request rate
    if session_data['request_count'] > session_data['max_requests_per_minute']:
        suspicious_score += 30
    
    # Check user agent consistency  
    if request_info['user_agent'] != session_data['user_agent']:
        suspicious_score += 20
    
    # Check for automation patterns
    if self.is_likely_bot_behavior(session_data):
        suspicious_score += 25
    
    # Check geographic consistency
    if await self.ip_geolocation_changed_significantly(session_data, request_info):
        suspicious_score += 15
    
    return suspicious_score >= 50  # Threshold for suspicious activity
```

## 🚨 Immediate Actions Needed

### **Priority 1: Server-Side Rate Limiting**
- Add rate limiting middleware to all API endpoints
- Track by IP + temporary key combination
- Implement progressive penalties

### **Priority 2: Request Signing**
- Generate signing keys during key exchange
- Require HMAC signatures on all requests
- Validate signatures server-side

### **Priority 3: Enhanced Monitoring**
- Log all temporary key usage
- Alert on suspicious patterns
- Automatic key revocation on abuse

### **Priority 4: Shorter Expiry Times**
- Reduce default expiry from 1 hour to 15 minutes
- Implement automatic refresh for legitimate users
- Aggressive cleanup of expired keys

## 📊 Risk Assessment

| Attack Vector | Current Risk | With Enhancements |
|---------------|-------------|-------------------|
| Key Theft from Dev Console | HIGH | MEDIUM |
| Automated DDoS | HIGH | LOW |
| Session Hijacking | HIGH | LOW |
| Replay Attacks | MEDIUM | LOW |
| Geographic Abuse | MEDIUM | LOW |

## 🔍 Detection Mechanisms

```python
# Example monitoring alerts
async def monitor_temporary_key_abuse():
    # Alert if same temp key used from multiple IPs
    # Alert if request rate exceeds normal patterns  
    # Alert if user agent changes mid-session
    # Alert if geographic location jumps significantly
    # Alert if automation patterns detected
```

## 💡 Additional Recommendations

1. **Client-Side Obfuscation**: Obfuscate temp keys in browser memory
2. **Key Rotation**: Rotate temp keys every 5-10 minutes automatically
3. **Behavioral Analysis**: Machine learning for abuse detection
4. **Legal Protection**: Terms of service with anti-abuse clauses
5. **CDN Protection**: Use Cloudflare or similar for DDoS protection

## 🎯 Implementation Priority

1. ✅ **Week 1**: Server-side rate limiting
2. ✅ **Week 2**: Request signing
3. ✅ **Week 3**: Enhanced monitoring & alerting
4. ✅ **Week 4**: Anomaly detection & auto-revocation 