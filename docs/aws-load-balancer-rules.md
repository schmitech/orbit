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
  - HTTP request method = `POST`
- **Action**: Forward to backend target group
- **Note**: This endpoint supports Server-Sent Events (SSE) streaming. Ensure your target group has appropriate timeout settings (recommended: 60+ seconds).

**Priority 3: Admin API Key Status**
- **Priority**: 3
- **Conditions**:
  - Path (pattern) = `/admin/api-keys/*/status`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group

**Priority 4: Admin API Key Info**
- **Priority**: 4
- **Conditions**:
  - Path (value) = `/admin/api-keys/info`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group

**Priority 5: Admin Chat History**
- **Priority**: 5
- **Conditions**:
  - Path (pattern) = `/admin/chat-history/*`
  - HTTP request method = `DELETE`
- **Action**: Forward to backend target group

**Priority 6: Admin Conversations**
- **Priority**: 6
- **Conditions**:
  - Path (pattern) = `/admin/conversations/*`
  - HTTP request method = `DELETE`
- **Action**: Forward to backend target group

**Priority 7: Thread Creation**
- **Priority**: 7
- **Conditions**:
  - Path (value) = `/api/threads`
  - HTTP request method = `POST`
- **Action**: Forward to backend target group

**Priority 8: Thread Operations (GET/DELETE)**
- **Priority**: 8
- **Conditions**:
  - Path (pattern) = `/api/threads/*`
  - HTTP request method = `GET` OR `DELETE`
- **Action**: Forward to backend target group

**Priority 9: File Upload**
- **Priority**: 9
- **Conditions**:
  - Path (value) = `/api/files/upload`
  - HTTP request method = `POST`
- **Action**: Forward to backend target group
- **Note**: File uploads may require larger request size limits. Configure your target group and ALB accordingly.

**Priority 10: File Query**
- **Priority**: 10
- **Conditions**:
  - Path (pattern) = `/api/files/*/query`
  - HTTP request method = `POST`
- **Action**: Forward to backend target group

**Priority 11: File Operations (GET/DELETE)**
- **Priority**: 11
- **Conditions**:
  - Path (pattern) = `/api/files/*`
  - HTTP request method = `GET` OR `DELETE`
- **Action**: Forward to backend target group

**Priority 12: List Files**
- **Priority**: 12
- **Conditions**:
  - Path (value) = `/api/files`
  - HTTP request method = `GET`
- **Action**: Forward to backend target group

**Priority 13: Default Rule (Catch-All)**
- **Priority**: 50000 (or highest available)
- **Conditions**: None (default action)
- **Action**: Forward to backend target group OR return 404
- **Note**: This catches any unmatched requests. You can either forward them to the backend (if you have other endpoints) or return a 404.

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
- Path = `/v1/chat`, Method = `POST`

**Priority 5: Default**
- Catch-all rule

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

```hcl
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

resource "aws_lb_listener_rule" "chat_endpoint" {
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
      values = ["POST"]
    }
  }
}

# Add similar rules for other endpoints...
```

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

