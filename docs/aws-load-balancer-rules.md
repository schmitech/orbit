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

## AWS ALB Listener Rules Configuration

Configure these rules in order of priority (lower numbers = higher priority). Rules are evaluated in order, and the first matching rule is applied.

### Rule Priority Order

**Priority 1: Health Check**
- **Priority**: 1
- **Conditions**:
  - Path (value) = `/health`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group

**Priority 2: Chat Endpoint (Streaming)**
- **Priority**: 2
- **Conditions**:
  - Path (value) = `/v1/chat`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - This endpoint supports Server-Sent Events (SSE) streaming. Ensure your target group has appropriate timeout settings (recommended: 60+ seconds).
  - `OPTIONS` included for CORS preflight requests

**Priority 3: Admin API Key Status**
- **Priority**: 3
- **Conditions**:
  - Path (pattern) = `/admin/api-keys/*/status`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 4: Admin API Key Info**
- **Priority**: 4
- **Conditions**:
  - Path (value) = `/admin/api-keys/info`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 5: Admin Chat History**
- **Priority**: 5
- **Conditions**:
  - Path (pattern) = `/admin/chat-history/*`
  - HTTP request method = `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 6: Admin Conversations**
- **Priority**: 6
- **Conditions**:
  - Path (pattern) = `/admin/conversations/*`
  - HTTP request method = `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 7: Thread Creation**
- **Priority**: 7
- **Conditions**:
  - Path (value) = `/api/threads`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 8: Thread Operations (GET/DELETE)**
- **Priority**: 8
- **Conditions**:
  - Path (pattern) = `/api/threads/*`
  - HTTP request method = `GET` OR `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: This matches both `GET /api/threads/{thread_id}` and `DELETE /api/threads/{thread_id}`

**Priority 9: File Upload**
- **Priority**: 9
- **Conditions**:
  - Path (value) = `/api/files/upload`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: File uploads may require larger request size limits (default is 1MB). Configure your target group and ALB accordingly.

**Priority 10: File Query**
- **Priority**: 10
- **Conditions**:
  - Path (pattern) = `/api/files/*/query`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: Must come before the general `/api/files/*` pattern to match `/api/files/{file_id}/query` specifically

**Priority 11: File Operations (GET/DELETE)**
- **Priority**: 11
- **Conditions**:
  - Path (pattern) = `/api/files/*`
  - HTTP request method = `GET` OR `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: This matches both `GET /api/files/{file_id}` and `DELETE /api/files/{file_id}`

**Priority 12: List Files**
- **Priority**: 12
- **Conditions**:
  - Path (value) = `/api/files`
  - HTTP request method = `GET` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: Must come after `/api/files/*` pattern to match exact `/api/files` path

**Priority 13: Default Rule (Catch-All)**
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

**Priority 2: Admin Routes**
- Path (pattern) = `/admin/*`
- All HTTP methods

**Priority 3: API Routes**
- Path (pattern) = `/api/*`
- All HTTP methods

**Priority 4: Chat Endpoint**
- Path = `/v1/chat`, Method = `POST` OR `OPTIONS`

**Priority 5: Default**
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

**Priority 2: Chat Endpoint**
- Path = `/v1/chat`, Method = `POST` OR `OPTIONS`

**Priority 3: Admin API Key Operations**
- Path (pattern) = `/admin/api-keys/*`
- HTTP request method = `GET` OR `OPTIONS`
- **Note**: This covers both `/admin/api-keys/{api_key}/status` and `/admin/api-keys/info`

**Priority 4-5: Admin Chat Operations**
- Priority 4: `/admin/chat-history/*`, `DELETE` OR `OPTIONS`
- Priority 5: `/admin/conversations/*`, `DELETE` OR `OPTIONS`
- **Note**: ALB doesn't support OR conditions for paths, so you'll need two separate rules

**Priority 6: Thread Operations**
- Path (pattern) = `/api/threads*` (matches `/api/threads` and `/api/threads/*`)
- All HTTP methods (includes `POST`, `GET`, `DELETE`, `OPTIONS`)

**Priority 7: File Query (Specific)**
- Path (pattern) = `/api/files/*/query`
- HTTP request method = `POST` OR `OPTIONS`

**Priority 8: File Operations**
- Path (pattern) = `/api/files*` (matches `/api/files` and `/api/files/*`)
- All HTTP methods (includes `POST`, `GET`, `DELETE`, `OPTIONS`)

**Priority 9: Default**
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
- If you plan to use WebSocket connections, ensure your ALB supports WebSocket upgrades
- The `/v1/chat` endpoint uses SSE (Server-Sent Events), not WebSockets, so standard HTTP/HTTPS is sufficient

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

# Chat endpoint
resource "aws_lb_listener_rule" "chat" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 2

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
  priority     = 3

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
  priority     = 4

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
  priority     = 5

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
  priority     = 6

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
  priority     = 7

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
  priority     = 8

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
  priority     = 9

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
  priority     = 10

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
  priority     = 11

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
  priority     = 12

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

**Summary**: This configuration includes 13 rules (12 endpoint rules + 1 default reject rule) that expose only the endpoints used by the Node.js API client, providing optimal security while maintaining full functionality.

## Testing

After configuring the rules, test each endpoint:

```bash
# Health check
curl https://your-alb-dns-name/health

# Chat endpoint
curl -X POST https://your-alb-dns-name/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"messages":[{"role":"user","content":"test"}],"stream":false}'

# File upload
curl -X POST https://your-alb-dns-name/api/files/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@test.txt"
```

## Troubleshooting

1. **404 errors**: Check that path patterns match exactly (case-sensitive)
2. **Timeout errors**: Increase idle timeout for streaming endpoints
3. **502 errors**: Check target group health and security group rules
4. **413 errors**: Increase request size limits for file uploads

