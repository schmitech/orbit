# AWS Load Balancer Listener Rules

This document outlines the necessary listener rules for an AWS Application Load Balancer (ALB) to route traffic to all backend endpoints used by the Node.js API client.

## Endpoints Summary

Based on `clients/node-api/api.ts`, the following endpoints need to be accessible:

### Admin Endpoints
- `GET /admin/api-keys/{api_key}/status`
- `GET /admin/api-keys/info`
- `DELETE /admin/chat-history/{session_id}`
- `DELETE /admin/conversations/{session_id}`

### Chat Endpoints
- `POST /v1/chat` (supports streaming with `text/event-stream`)

### Thread Endpoints
- `POST /api/threads`
- `GET /api/threads/{thread_id}`
- `DELETE /api/threads/{thread_id}`

### File Endpoints
- `POST /api/files/upload`
- `GET /api/files`
- `GET /api/files/{file_id}`
- `POST /api/files/{file_id}/query`
- `DELETE /api/files/{file_id}`

### Health Check (recommended)
- `GET /health`

### Dashboard Endpoints
- `GET /dashboard` (serves HTML dashboard)
- `GET /metrics` (Prometheus metrics endpoint)
- `GET /metrics/json` (JSON metrics endpoint)
- `WebSocket /ws/metrics` (real-time metrics streaming)

## AWS ALB Listener Rules Configuration

Configure these rules in order of priority (lower numbers = higher priority). Rules are evaluated in order, and the first matching rule is applied.

### Rule Priority Order

**Priority 1: Health Check**
- **Priority**: 1
- **Conditions**:
  - Path (value) = `/health`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group

**Priority 2: Dashboard WebSocket (Real-time Metrics)**
- **Priority**: 2
- **Conditions**:
  - Path (value) = `/ws/metrics`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group
- **Note**: 
  - This endpoint uses WebSocket protocol for real-time metrics streaming
  - AWS ALB supports WebSocket connections natively - ensure your target group has appropriate timeout settings (recommended: 60+ seconds for long-lived connections)
  - The WebSocket connection requires HTTP Basic authentication or cookie-based session authentication

**Priority 3: Dashboard HTML**
- **Priority**: 3
- **Conditions**:
  - Path (value) = `/dashboard`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - Serves the monitoring dashboard HTML page
  - Requires HTTP Basic authentication with admin credentials
  - `OPTIONS` included for CORS preflight requests

**Priority 4: Dashboard Metrics (Prometheus)**
- **Priority**: 4
- **Conditions**:
  - Path (value) = `/metrics`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - Prometheus-compatible metrics endpoint
  - Returns metrics in Prometheus text format
  - `OPTIONS` included for CORS preflight requests

**Priority 5: Dashboard Metrics (JSON)**
- **Priority**: 5
- **Conditions**:
  - Path (value) = `/metrics/json`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - JSON metrics endpoint for custom integrations
  - Returns metrics in JSON format
  - `OPTIONS` included for CORS preflight requests

**Priority 6: Chat Endpoint (Streaming)**
- **Priority**: 6
- **Conditions**:
  - Path (value) = `/v1/chat`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - This endpoint supports Server-Sent Events (SSE) streaming. Ensure your target group has appropriate timeout settings (recommended: 60+ seconds).
  - `OPTIONS` included for CORS preflight requests

**Priority 7: Admin API Key Status**
- **Priority**: 7
- **Conditions**:
  - Path (pattern) = `/admin/api-keys/*/status`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 8: Admin API Key Info**
- **Priority**: 8
- **Conditions**:
  - Path (value) = `/admin/api-keys/info`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 9: Admin Chat History**
- **Priority**: 9
- **Conditions**:
  - Path (pattern) = `/admin/chat-history/*`
  - HTTP request method = `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 10: Admin Conversations**
- **Priority**: 10
- **Conditions**:
  - Path (pattern) = `/admin/conversations/*`
  - HTTP request method = `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 11: Thread Creation**
- **Priority**: 11
- **Conditions**:
  - Path (value) = `/api/threads`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 12: Thread Operations (GET/DELETE)**
- **Priority**: 12
- **Conditions**:
  - Path (pattern) = `/api/threads/*`
  - HTTP request method = `GET` OR `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: This matches both `GET /api/threads/{thread_id}` and `DELETE /api/threads/{thread_id}`

**Priority 13: File Upload**
- **Priority**: 13
- **Conditions**:
  - Path (value) = `/api/files/upload`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: File uploads may require larger request size limits (default is 1MB). Configure your target group and ALB accordingly.

**Priority 14: File Query**
- **Priority**: 14
- **Conditions**:
  - Path (pattern) = `/api/files/*/query`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: Must come before the general `/api/files/*` pattern to match `/api/files/{file_id}/query` specifically

**Priority 15: File Operations (GET/DELETE)**
- **Priority**: 15
- **Conditions**:
  - Path (pattern) = `/api/files/*`
  - HTTP request method = `GET` OR `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: This matches both `GET /api/files/{file_id}` and `DELETE /api/files/{file_id}`

**Priority 16: List Files**
- **Priority**: 16
- **Conditions**:
  - Path (value) = `/api/files`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: Must come after `/api/files/*` pattern to match exact `/api/files` path

**Priority 17: Default Rule (Catch-All)**
- **Priority**: 50000 (or highest available)
- **Conditions**: None (default action)
- **Action**: Forward to backend target group OR return 404
- **Note**: 
  - This catches any unmatched requests. You can either forward them to the backend (if you have other endpoints) or return a 404.
  - **Security recommendation**: For minimal configurations, return 404 to prevent exposing any endpoints you haven't explicitly allowed.

## Alternative: Simplified Rule Set

If you prefer fewer rules, you can use these broader patterns:

**Priority 1: Health Check**
- Path = `/health`, Method = `GET`

**Priority 2: Dashboard WebSocket**
- Path = `/ws/metrics`, Method = `GET` (WebSocket upgrade)

**Priority 3: Dashboard Routes**
- Path (pattern) = `/dashboard` OR `/metrics*`
- All HTTP methods

**Priority 4: Admin Routes**
- Path (pattern) = `/admin/*`
- All HTTP methods

**Priority 5: API Routes**
- Path (pattern) = `/api/*`
- All HTTP methods

**Priority 6: Chat Endpoint**
- Path = `/v1/chat`, Method = `POST` OR `OPTIONS`

**Priority 7: Default**
- Catch-all rule

## Minimal Security-Focused Configuration

For production deployments, you may want to use a **minimal set of ALB listener rules** that expose only the endpoints actually used by the Node.js API client. This provides better security by limiting attack surface.

### Endpoints Used by Node.js API Client

Based on analysis of `clients/node-api/api.ts`, the client uses these specific endpoints:

1. **API Key Validation**: `GET /admin/api-keys/{api_key}/status`
2. **Adapter Info**: `GET /admin/api-keys/info`
3. **Chat**: `POST /v1/chat` (with SSE streaming support)
4. **Clear History**: `DELETE /admin/chat-history/{session_id}`
5. **Delete Conversation**: `DELETE /admin/conversations/{session_id}`
6. **Threads**: `POST /api/threads`, `GET /api/threads/{thread_id}`, `DELETE /api/threads/{thread_id}`
7. **Files**: `POST /api/files/upload`, `GET /api/files`, `GET /api/files/{file_id}`, `POST /api/files/{file_id}/query`, `DELETE /api/files/{file_id}`

Additionally, if you're using the monitoring dashboard (`server/routes/dashboard_routes.py`), you'll need:

8. **Dashboard**: `GET /dashboard` (HTML dashboard page)
9. **Dashboard Metrics**: `GET /metrics` (Prometheus format), `GET /metrics/json` (JSON format)
10. **Dashboard WebSocket**: `WebSocket /ws/metrics` (real-time metrics streaming)

The detailed rule configuration above already follows this minimal approach. The key differences from a more permissive configuration are:

- **Method Restrictions**: Each rule only allows the specific HTTP methods needed (including `OPTIONS` for CORS). This prevents unauthorized operations (e.g., preventing `DELETE` on chat endpoint).
- **Default Rule**: Set the default rule to return 404, not forward to backend. This prevents exposing any endpoints you haven't explicitly allowed.
- **No Auth Endpoints**: This minimal configuration does NOT include `/auth/*` endpoints. If you need CLI access, add:
  - Priority 2: `/auth/*` with all methods (insert before chat endpoint)
- **No Other Admin Endpoints**: This excludes other admin operations like:
  - Creating/deleting API keys
  - Managing system prompts
  - User management
  - Adapter reloading

### Alternative: Even More Minimal (Grouped Rules)

If you want even fewer rules, you can group related endpoints:

**Priority 1: Health Check (Optional)**
- Path = `/health`, Method = `GET`

**Priority 2: Dashboard WebSocket (if using dashboard)**
- Path = `/ws/metrics`, Method = `GET` (WebSocket upgrade)

**Priority 3: Dashboard Routes (if using dashboard)**
- Path (pattern) = `/dashboard` OR `/metrics*`
- All HTTP methods (includes `GET`, `OPTIONS`)

**Priority 4: Chat Endpoint**
- Path = `/v1/chat`, Method = `POST` OR `OPTIONS`

**Priority 5: Admin API Key Operations**
- Path (pattern) = `/admin/api-keys/*`
- HTTP request method = `GET` OR `OPTIONS`
- **Note**: This covers both `/admin/api-keys/{api_key}/status` and `/admin/api-keys/info`

**Priority 6-7: Admin Chat Operations**
- Priority 6: `/admin/chat-history/*`, `DELETE` OR `OPTIONS`
- Priority 7: `/admin/conversations/*`, `DELETE` OR `OPTIONS`
- **Note**: ALB doesn't support OR conditions for paths, so you'll need two separate rules

**Priority 8: Thread Operations**
- Path (pattern) = `/api/threads*` (matches `/api/threads` and `/api/threads/*`)
- All HTTP methods (includes `POST`, `GET`, `DELETE`, `OPTIONS`)

**Priority 9: File Query (Specific)**
- Path (pattern) = `/api/files/*/query`
- HTTP request method = `POST` OR `OPTIONS`

**Priority 10: File Operations**
- Path (pattern) = `/api/files*` (matches `/api/files` and `/api/files/*`)
- All HTTP methods (includes `POST`, `GET`, `DELETE`, `OPTIONS`)

**Priority 11: Default**
- Return 404 for all unmatched requests

### Security Considerations

1. **Default Rule**: Set the default rule to return 404, not forward to backend. This prevents exposing any endpoints you haven't explicitly allowed.
2. **Method Restrictions**: Each rule only allows the specific HTTP methods needed. This prevents unauthorized operations.
3. **No Unused Endpoints**: Only expose endpoints that are actually used by your client application.
4. **CORS Support**: Include `OPTIONS` method in rules to support CORS preflight requests from web clients.

## Important Configuration Notes

### Timeout Settings
- **Idle timeout**: Set to at least 60 seconds for streaming endpoints (`/v1/chat`)
- **Target group health check**: Configure appropriate intervals and thresholds

### Request Size Limits
- **File uploads**: Ensure ALB and target group can handle large file uploads (default is 1MB, may need to increase)
- Consider using S3 for large file uploads if needed

### WebSocket Support
- AWS ALB natively supports WebSocket connections - no special configuration needed
- The `/ws/metrics` endpoint uses WebSocket protocol for real-time metrics streaming
- Ensure your target group has appropriate timeout settings (recommended: 60+ seconds for long-lived WebSocket connections)
- The `/v1/chat` endpoint uses SSE (Server-Sent Events), not WebSockets, so standard HTTP/HTTPS is sufficient
- WebSocket connections require HTTP Basic authentication or cookie-based session authentication (handled by the backend)

### SSL/TLS
- Configure HTTPS listener on port 443
- Use ACM (AWS Certificate Manager) for SSL certificates
- Redirect HTTP (port 80) to HTTPS

### Security Groups
- Ensure your ALB security group allows inbound traffic on ports 80/443
- Ensure your target group security group allows traffic from the ALB security group

## Example Terraform Configuration

### Complete Minimal Configuration

This example provides the complete minimal security-focused configuration with all required rules:

```hcl
# Health check (optional)
resource "aws_lb_listener_rule" "health_check" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/health"]
    }
  }

  condition {
    http_request_method {
      values = ["GET"]
    }
  }
}

# Dashboard WebSocket (real-time metrics)
resource "aws_lb_listener_rule" "dashboard_websocket" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 2

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/ws/metrics"]
    }
  }

  condition {
    http_request_method {
      values = ["GET"]
    }
  }
}

# Dashboard HTML
resource "aws_lb_listener_rule" "dashboard_html" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 3

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/dashboard"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Dashboard Prometheus metrics
resource "aws_lb_listener_rule" "dashboard_metrics" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 4

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/metrics"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Dashboard JSON metrics
resource "aws_lb_listener_rule" "dashboard_metrics_json" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 5

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/metrics/json"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Chat endpoint
resource "aws_lb_listener_rule" "chat" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 6

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/v1/chat"]
    }
  }

  condition {
    http_request_method {
      values = ["POST", "OPTIONS"]
    }
  }
}

# Admin API key status
resource "aws_lb_listener_rule" "admin_api_key_status" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 7

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/admin/api-keys/*/status"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Admin API key info
resource "aws_lb_listener_rule" "admin_api_key_info" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 8

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/admin/api-keys/info"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Admin chat history delete
resource "aws_lb_listener_rule" "admin_chat_history" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 9

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/admin/chat-history/*"]
    }
  }

  condition {
    http_request_method {
      values = ["DELETE", "OPTIONS"]
    }
  }
}

# Admin conversations delete
resource "aws_lb_listener_rule" "admin_conversations" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/admin/conversations/*"]
    }
  }

  condition {
    http_request_method {
      values = ["DELETE", "OPTIONS"]
    }
  }
}

# Thread creation
resource "aws_lb_listener_rule" "threads_create" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 11

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/threads"]
    }
  }

  condition {
    http_request_method {
      values = ["POST", "OPTIONS"]
    }
  }
}

# Thread operations (GET/DELETE)
resource "aws_lb_listener_rule" "threads_ops" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 12

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/threads/*"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "DELETE", "OPTIONS"]
    }
  }
}

# File upload
resource "aws_lb_listener_rule" "files_upload" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 13

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/files/upload"]
    }
  }

  condition {
    http_request_method {
      values = ["POST", "OPTIONS"]
    }
  }
}

# File query
resource "aws_lb_listener_rule" "files_query" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 14

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/files/*/query"]
    }
  }

  condition {
    http_request_method {
      values = ["POST", "OPTIONS"]
    }
  }
}

# File operations (GET/DELETE)
resource "aws_lb_listener_rule" "files_ops" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 15

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/files/*"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "DELETE", "OPTIONS"]
    }
  }
}

# List files
resource "aws_lb_listener_rule" "files_list" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 16

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/files"]
    }
  }

  condition {
    http_request_method {
      values = ["GET", "OPTIONS"]
    }
  }
}

# Default rule - reject all unmatched
resource "aws_lb_listener_rule" "default_reject" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 50000

  action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({
        error = "Not Found"
        message = "The requested endpoint is not available"
      })
      status_code = "404"
    }
  }
}
```

**Summary**: This configuration includes 17 rules (16 endpoint rules + 1 default reject rule) that expose the endpoints used by the Node.js API client and the dashboard, providing optimal security while maintaining full functionality. The dashboard rules include WebSocket support for real-time metrics streaming.

## Testing

After configuring the rules, test each endpoint:

```bash
# Health check
curl https://your-alb-address/health

# Chat endpoint
curl -X POST https://your-alb-address/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"messages":[{"role":"user","content":"test"}],"stream":false}'

# Dashboard (requires HTTP Basic auth)
curl -u admin:password https://your-alb-address/dashboard

# Dashboard metrics (Prometheus format)
curl -u admin:password https://your-alb-address/metrics

# Dashboard metrics (JSON format)
curl -u admin:password https://your-alb-address/metrics/json

# File upload
curl -X POST https://your-alb-address/api/files/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@test.txt"
```
### Recommended Rule Configuration for Dashboard

If the dashboard WebSocket is not working, verify these rules are configured correctly:

**Priority 2: Dashboard WebSocket**
```
Path (value) = /ws/metrics
HTTP request method = GET
```
*Note: AWS ALB automatically handles the WebSocket upgrade protocol. You don't need to explicitly match the `Upgrade` header.*

**Priority 3: Dashboard HTML**
```
Path (value) = /dashboard
HTTP request method = GET OR OPTIONS
```
*Note: OPTIONS is required for CORS preflight requests from the browser.*

**Priority 4: Dashboard Metrics (Prometheus)**
```
Path (value) = /metrics
HTTP request method = GET OR OPTIONS
```

**Priority 5: Dashboard Metrics (JSON)**
```
Path (value) = /metrics/json
HTTP request method = GET OR OPTIONS
```

### Testing WebSocket Connection

To test if the WebSocket endpoint is accessible:

```bash
# Test WebSocket connection (requires wscat or similar tool)
wscat -c wss://your-alb-address/ws/metrics \
  -H "Authorization: Basic $(echo -n 'admin:password' | base64)"

# Or test with curl (will show upgrade response)
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test" \
  -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
  https://your-alb-address/ws/metrics
```

Expected response should include:
- `HTTP/1.1 101 Switching Protocols`
- `Upgrade: websocket`
- `Connection: Upgrade`

## Troubleshooting: Works Locally but 404 Through ALB

If your dashboard works locally (e.g., `http://localhost:3000/dashboard`) but returns 404 through the ALB, check the following:

### Common Causes

1. **Rule Priority Conflict**:
   - A higher priority rule might be matching first and rejecting the request
   - **Fix**: Ensure dashboard rules have higher priority (lower numbers) than catch-all rules
   - **Check**: Verify your rule priorities are in the correct order (1, 2, 3, 4, 5 for dashboard rules)

2. **Path Pattern Mismatch**:
   - **Problem**: Using path pattern `/dashboard/*` instead of exact path `/dashboard`
   - **Fix**: Use exact path match: `Path (value) = /dashboard` (not pattern)
   - **Why**: The dashboard route is `/dashboard`, not `/dashboard/*`

3. **HTTP Method Not Included**:
   - **Problem**: Missing `OPTIONS` method for CORS preflight
   - **Fix**: Add `OPTIONS` to HTTP request method: `GET OR OPTIONS`
   - **Test**: Try accessing the dashboard with authentication:
     ```bash
     curl -u admin:admin123 https://your-alb-address/dashboard
     ```

4. **Default Rule Catching Request**:
   - **Problem**: Default rule (lowest priority) is returning 404 before dashboard rules match
   - **Fix**: Ensure dashboard rules have higher priority than the default rule
   - **Check**: Your dashboard rules should be priorities 2-5, default should be 50000

5. **Case Sensitivity**:
   - **Problem**: Path matching is case-sensitive
   - **Fix**: Ensure path is exactly `/dashboard` (lowercase), not `/Dashboard` or `/DASHBOARD`

### Step-by-Step Debugging

1. **Test each endpoint individually**:
   ```bash
   # Test health (should work)
   curl https://your-alb-address/health
   
   # Test dashboard with auth
   curl -u admin:admin123 https://your-alb-address/dashboard
   
   # Test metrics
   curl -u admin:admin123 https://your-alb-address/metrics
   
   # Test metrics JSON
   curl -u admin:admin123 https://your-alb-address/metrics/json
   ```

2. **Check ALB access logs**:
   - Enable ALB access logs in CloudWatch
   - Look for requests to `/dashboard` and see which rule matched
   - Check if the request is being forwarded to the target group

3. **Verify target group health**:
   - Check EC2 → Target Groups → Your Target Group → Health checks
   - Ensure targets are healthy
   - If unhealthy, check security groups and backend service logs

4. **Test WebSocket connection**:
   ```bash
   # Test WebSocket upgrade
   curl -i -N \
     -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
     -H "Authorization: Basic $(echo -n 'admin:admin123' | base64)" \
     https://your-alb-address/ws/metrics
   ```

### Correct Rule Configuration Checklist

Verify your ALB rules match this exact configuration:

- [ ] **Priority 1**: `/health` with `GET` method
- [ ] **Priority 2**: `/ws/metrics` with `GET` method (WebSocket)
- [ ] **Priority 3**: `/dashboard` with `GET OR OPTIONS` methods
- [ ] **Priority 4**: `/metrics` with `GET OR OPTIONS` methods
- [ ] **Priority 5**: `/metrics/json` with `GET OR OPTIONS` methods
- [ ] **Priority 6+**: Other API routes
- [ ] **Priority 50000**: Default rule (should be last)

### Authentication Notes

The dashboard requires HTTP Basic authentication:
- **Username**: `admin`
- **Password**: `admin123` (or your configured admin password)
- When accessing through a browser, you'll be prompted for credentials
- The dashboard sets a `dashboard_token` cookie for subsequent requests
- WebSocket connections use either Basic auth or the session cookie

