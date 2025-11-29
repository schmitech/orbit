# Minimal AWS Load Balancer Rules for Node.js API Client

This document provides the **minimal set of ALB listener rules** required for the Node.js API client (`clients/node-api/api.ts`) to function. This configuration exposes only the endpoints actually used by the client, providing better security by limiting attack surface.

## Endpoints Used by Node.js API Client

Based on analysis of `clients/node-api/api.ts`, the client uses these specific endpoints:

1. **API Key Validation**: `GET /admin/api-keys/{api_key}/status`
2. **Adapter Info**: `GET /admin/api-keys/info`
3. **Chat**: `POST /v1/chat` (with SSE streaming support)
4. **Clear History**: `DELETE /admin/chat-history/{session_id}`
5. **Delete Conversation**: `DELETE /admin/conversations/{session_id}`
6. **Threads**: `POST /api/threads`, `GET /api/threads/{thread_id}`, `DELETE /api/threads/{thread_id}`
7. **Files**: `POST /api/files/upload`, `GET /api/files`, `GET /api/files/{file_id}`, `POST /api/files/{file_id}/query`, `DELETE /api/files/{file_id}`

## Minimal ALB Rules Configuration

Configure these rules in order of priority (lower numbers = higher priority). Rules are evaluated in order, and the first matching rule is applied.

### Rule Priority Order

**Priority 1: Health Check (Optional but Recommended)**
- **Priority**: 1
- **Conditions**:
  - Path (value) = `/health`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group
- **Note**: Useful for ALB health checks and monitoring. Can be omitted if not needed.

**Priority 2: Chat Endpoint**
- **Priority**: 2
- **Conditions**:
  - Path (value) = `/v1/chat`
  - HTTP request method = `POST` OR `OPTIONS`
- **Action**: Forward to backend target group
- **Note**: 
  - Supports Server-Sent Events (SSE) streaming
  - Requires idle timeout of 60+ seconds
  - `OPTIONS` included for CORS preflight

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

**Priority 5: Admin Chat History Delete**
- **Priority**: 5
- **Conditions**:
  - Path (pattern) = `/admin/chat-history/*`
  - HTTP request method = `DELETE` OR `OPTIONS`
- **Action**: Forward to backend target group

**Priority 6: Admin Conversations Delete**
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
- **Note**: File uploads may require larger request size limits (default is 1MB)

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
- **Action**: Return 404 (Fixed response)
- **Note**: Reject all unmatched requests for security. Do NOT forward to backend.

## Alternative: Even More Minimal (Grouped Rules)

If you want even fewer rules, you can group related endpoints:

**Priority 1: Health Check (Optional)**
- Path = `/health`, Method = `GET`

**Priority 2: Chat Endpoint**
- Path = `/v1/chat`, Method = `POST` OR `OPTIONS`

**Priority 3: Admin API Key Operations**
- Path (pattern) = `/admin/api-keys/*`
- HTTP request method = `GET` OR `OPTIONS`
- **Note**: This covers both `/admin/api-keys/{api_key}/status` and `/admin/api-keys/info`

**Priority 4: Admin Chat Operations**
- Path (pattern) = `/admin/chat-history/*` OR `/admin/conversations/*`
- HTTP request method = `DELETE` OR `OPTIONS`
- **Note**: ALB doesn't support OR conditions for paths, so you'll need two separate rules:
  - Priority 4: `/admin/chat-history/*`, `DELETE` OR `OPTIONS`
  - Priority 5: `/admin/conversations/*`, `DELETE` OR `OPTIONS`

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

## Security Considerations

1. **No Auth Endpoints**: This minimal configuration does NOT include `/auth/*` endpoints. If you need CLI access, add:
   - Priority 2: `/auth/*` with all methods (insert before chat endpoint)

2. **No Other Admin Endpoints**: This excludes other admin operations like:
   - Creating/deleting API keys
   - Managing system prompts
   - User management
   - Adapter reloading

3. **Default Rule**: Set the default rule to return 404, not forward to backend. This prevents exposing any endpoints you haven't explicitly allowed.

4. **Method Restrictions**: Each rule only allows the specific HTTP methods needed. This prevents unauthorized operations (e.g., preventing `DELETE` on chat endpoint).

## Example Terraform Configuration (Minimal)

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

## Summary

**Total Rules**: 13 (12 endpoint rules + 1 default reject rule)

**Endpoints Exposed**:
- ✅ Chat endpoint (`/v1/chat`)
- ✅ API key validation (`/admin/api-keys/*/status`, `/admin/api-keys/info`)
- ✅ Conversation management (`/admin/chat-history/*`, `/admin/conversations/*`)
- ✅ Thread operations (`/api/threads*`)
- ✅ File operations (`/api/files*`)

**Endpoints NOT Exposed**:
- ❌ Auth endpoints (`/auth/*`) - Add if you need CLI access
- ❌ Other admin endpoints (API key creation, system prompts, etc.)
- ❌ Dashboard (`/dashboard`)
- ❌ Metrics (`/metrics`)
- ❌ Any other endpoints not explicitly listed

This minimal configuration provides the best security posture while supporting all Node.js API client functionality.

