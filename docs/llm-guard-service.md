# 🛡️ LLM Guard Service

## Overview

The LLM Guard Service provides advanced security scanning and content sanitization capabilities for the Orbit server. It integrates with external LLM Guard API services to detect and mitigate security risks in user prompts and AI responses, including prompt injection attacks, toxic content, sensitive data exposure, and other security threats.

## 🌟 Core Capabilities

- **🔍 Security Scanning**
  - Prompt injection detection
  - Toxicity screening
  - Sensitive data detection (API keys, passwords, PII)
  - Content bias analysis
  - Topic filtering and banned content detection

- **🧹 Content Sanitization**
  - Automatic removal or masking of sensitive information
  - Configurable sanitization rules
  - PII anonymization
  - Secret detection and redaction

- **⚡ Performance & Reliability**
  - Async HTTP client with connection pooling
  - Configurable retry logic with exponential backoff
  - Health monitoring and circuit breaker patterns
  - Graceful fallback behavior when service unavailable

- **🔧 Simple Configuration**
  - Minimal configuration with sensible defaults
  - Easy setup with just essential settings
  - Automatic fallback behavior configuration

---

## 🏗️ Architecture

### Service Integration

The LLM Guard Service is integrated into Orbit's service factory pattern and follows the same architectural principles as other core services:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Chat Service  │───▶│ LLM Guard Service│───▶│ External LLM    │
│                 │    │                  │    │ Guard API       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │
        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐
│   LLM Client    │    │ Health Monitor   │
│                 │    │ & Retry Logic    │
└─────────────────┘    └──────────────────┘
```

### Components

1. **LLMGuardService**: Main service class that handles security operations
2. **HTTP Client**: Async aiohttp client for API communication
3. **Health Monitor**: Periodic health checks with caching
4. **Retry Handler**: Exponential backoff retry logic
5. **Error Handler**: Fallback behavior configuration
6. **Validator**: Input validation and sanitization

---

## 📋 Configuration

### Simple Configuration

Add the following section to your `config.yaml`:

```yaml
llm_guard:
  enabled: true                           # Enable/disable the service
  service:
    base_url: "http://localhost:8000"     # LLM Guard API base URL
    timeout: 30                           # Request timeout (seconds)
  security:
    risk_threshold: 0.6                   # Default risk threshold (0.0-1.0)
  fallback:
    on_error: "allow"                     # Fallback behavior: "allow" or "block"
```

### Configuration Options

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `service.base_url` | string | `"http://localhost:8000"` | LLM Guard API base URL |
| `service.timeout` | integer | `30` | Request timeout in seconds |
| `security.risk_threshold` | float | `0.6` | Default risk threshold (0.0-1.0) |
| `fallback.on_error` | string | `"allow"` | Fallback behavior when service unavailable |

### Default Settings

The service uses sensible defaults for all other settings:

- **API Version**: `v1`
- **Connect Timeout**: `10` seconds
- **Retry Attempts**: `3` with exponential backoff
- **Health Check**: `/health` endpoint, 30s interval, 5s timeout
- **Available Scanners**: 7 input scanners, 4 output scanners
- **Content Validation**: 10,000 character limit, `["prompt", "response"]` types
- **Metadata**: Client name `"orbit-server"`, version `"1.0.0"`

---

## 🚀 Usage

### Service Integration

The LLM Guard Service is automatically initialized by the service factory when the `llm_guard` section exists in your configuration and `enabled` is set to `true`. It's available through the application state:

```python
# Access the service in your code
llm_guard_service = app.state.llm_guard_service
```

### Security Checking

```python
# Basic security check
result = await llm_guard_service.check_security(
    content="User input to check",
    content_type="prompt"
)

# Advanced security check with custom parameters
result = await llm_guard_service.check_security(
    content="Potentially risky content",
    content_type="prompt",
    scanners=["prompt_injection", "toxicity", "secrets"],
    risk_threshold=0.7,
    user_id="user123",
    metadata={"session_id": "sess_456", "source": "chat"}
)

# Process the result
if result["is_safe"]:
    print("Content is safe to process")
else:
    print(f"Content flagged by: {result['flagged_scanners']}")
    print(f"Risk score: {result['risk_score']}")
    print(f"Recommendations: {result['recommendations']}")
```

### Content Sanitization

```python
# Sanitize content to remove sensitive information
sanitized = await llm_guard_service.sanitize_content(
    "My phone number is 555-123-4567 and API key is sk-abc123"
)

print(f"Original: {content}")
print(f"Sanitized: {sanitized['sanitized_content']}")
print(f"Changes made: {sanitized['changes_made']}")
print(f"Removed items: {sanitized['removed_items']}")
```

### Service Health and Information

```python
# Check service health
is_healthy = await llm_guard_service.is_service_healthy()

# Get service information
info = await llm_guard_service.get_service_info()
print(f"Service enabled: {info['enabled']}")
print(f"Base URL: {info['base_url']}")
print(f"Available scanners: {info['available_input_scanners']}")

# Get available scanners dynamically
scanners = await llm_guard_service.get_available_scanners()
print(f"Input scanners: {scanners['input_scanners']}")
print(f"Output scanners: {scanners['output_scanners']}")
```

---

## 🔌 API Integration

### LLM Guard API Endpoints

The service integrates with the following LLM Guard API endpoints:

#### Security Check
- **Method**: POST
- **Endpoint**: `/v1/security/check`
- **Purpose**: Perform security analysis on content

**Request:**
```json
{
  "content": "Text to analyze",
  "content_type": "prompt",
  "risk_threshold": 0.6,
  "scanners": ["prompt_injection", "toxicity"],
  "user_id": "user123",
  "metadata": {
    "client_name": "orbit-server",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

**Response:**
```json
{
  "is_safe": false,
  "risk_score": 0.8,
  "sanitized_content": "Text to analyze",
  "flagged_scanners": ["secrets"],
  "recommendations": [
    "Content contains potential API key",
    "Consider sanitizing before processing"
  ],
  "scan_details": {
    "secrets": {
      "score": 0.9,
      "detected_items": ["api_key"]
    }
  }
}
```

#### Content Sanitization
- **Method**: POST
- **Endpoint**: `/v1/security/sanitize`
- **Purpose**: Remove or mask sensitive information

**Request:**
```json
{
  "content": "My API key is sk-1234567890abcdef"
}
```

**Response:**
```json
{
  "sanitized_content": "My API key is [REDACTED]",
  "changes_made": true,
  "removed_items": ["api_key"],
  "sanitization_log": [
    {
      "type": "api_key",
      "original": "sk-1234567890abcdef",
      "replacement": "[REDACTED]",
      "position": [13, 35]
    }
  ]
}
```

#### Health Check
- **Method**: GET
- **Endpoint**: `/health`
- **Purpose**: Check service availability and status

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "scanners": {
    "input": ["anonymize", "ban_substrings", "prompt_injection"],
    "output": ["bias", "relevance", "sensitive"]
  }
}
```

---

## ⚙️ Scanner Types

### Input Scanners (Prompt Analysis)

| Scanner | Purpose | Description |
|---------|---------|-------------|
| `anonymize` | Detect and anonymize PII data | Identifies and masks personal information |
| `ban_substrings` | Block content with banned phrases | Filters content containing banned substrings |
| `ban_topics` | Block content about banned topics | Prevents discussion of prohibited topics |
| `code` | Detect code injection attempts | Identifies potential code injection attacks |
| `prompt_injection` | Detect prompt injection attacks | Detects attempts to manipulate the AI system |
| `secrets` | Detect API keys, passwords, tokens | Identifies sensitive credentials and secrets |
| `toxicity` | Detect toxic/harmful content | Filters harmful, offensive, or inappropriate content |

### Output Scanners (Response Analysis)

| Scanner | Purpose | Description |
|---------|---------|-------------|
| `bias` | Detect biased or unfair content | Identifies biased or discriminatory responses |
| `no_refusal` | Ensure appropriate refusals | Checks that the AI appropriately refuses harmful requests |
| `relevance` | Check response relevance to prompt | Ensures responses are relevant to the original query |
| `sensitive` | Detect sensitive information leaks | Prevents disclosure of sensitive information |

---

## 🛠️ Error Handling

### Fallback Behaviors

When the LLM Guard service is unavailable, you can configure different fallback behaviors:

#### Allow (Default)
- **Behavior**: Allow content to pass through unscanned
- **Use Case**: Non-critical applications where availability is prioritized
- **Configuration**: `on_error: "allow"`

```python
# Returns safe response when service is down
{
  "is_safe": true,
  "risk_score": 0.0,
  "sanitized_content": original_content,
  "flagged_scanners": [],
  "recommendations": ["Service temporarily unavailable - content not scanned"]
}
```

#### Block
- **Behavior**: Block all content when service is unavailable
- **Use Case**: High-security applications where safety is prioritized
- **Configuration**: `on_error: "block"`

```python
# Returns unsafe response when service is down
{
  "is_safe": false,
  "risk_score": 1.0,
  "sanitized_content": original_content,
  "flagged_scanners": ["service_unavailable"],
  "recommendations": ["Service temporarily unavailable - content blocked as precaution"]
}
```

### Retry Logic

The service implements exponential backoff retry logic:

```python
# Retry configuration (hardcoded defaults)
max_attempts = 3
backoff_factor = 0.3
retry_delays = [0.3, 0.6, 1.2]  # seconds

# Status codes that trigger retries
retry_status_codes = [500, 502, 503, 504]
```

---

## 📊 Monitoring and Logging

### Health Monitoring

The service automatically monitors the health of the LLM Guard API:

```python
# Health check results are cached for efficiency
health_cache_ttl = 30  # seconds

# Health check endpoint
GET /health
```

### Logging

The service provides comprehensive logging:

```python
# Info level logs
logger.info("LLM Guard service initialized - Base URL: http://localhost:8000")
logger.info("Security check completed in 250.5ms")

# Warning level logs
logger.warning("LLM Guard service health check failed with status: 503")
logger.warning("Service unavailable, falling back to 'allow'")

# Error level logs
logger.error("Security check failed: Connection timeout")
logger.error("Failed to initialize LLM Guard Service: Service unreachable")
```

### Performance Metrics

Track service performance with built-in metrics:

- **Request Duration**: Time taken for security checks
- **Success Rate**: Percentage of successful requests
- **Health Status**: Service availability over time
- **Scanner Usage**: Which scanners are most frequently used

---

## 🔐 Security Considerations

### Network Security

- **HTTPS**: Always use HTTPS in production
- **Firewall**: Restrict access to LLM Guard service
- **VPN**: Use VPN for communication between services

```yaml
llm_guard:
  service:
    base_url: "https://llm-guard.internal.company.com"  # HTTPS endpoint
```

### Data Privacy

- **Content Logging**: The service does not log actual content by default
- **PII Handling**: Ensure PII is properly anonymized by the LLM Guard service
- **Data Retention**: Configure data retention on the LLM Guard service side

---

## 🐛 Troubleshooting

### Common Issues

#### Service Not Starting
```bash
# Check if LLM Guard is configured
grep -A5 "llm_guard:" config.yaml

# Verify the base URL is correct
curl -X GET "http://localhost:8000/health"
```

#### Connection Timeouts
```yaml
# Increase timeout in config.yaml
llm_guard:
  service:
    timeout: 60  # Increase from default 30 seconds
```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```yaml
logging:
  level: "DEBUG"
  loggers:
    services.llm_guard_service:
      level: "DEBUG"
```

### Health Check Command

```bash
# Test LLM Guard service health
curl -X GET "http://localhost:8000/health"

# Test security check endpoint
curl -X POST "http://localhost:8000/v1/security/check" \
  -H "Content-Type: application/json" \
  -d '{"content": "test", "content_type": "prompt"}'
```

### Service Status

Check service status through Orbit:

```python
# In your application
llm_guard_service = app.state.llm_guard_service
if llm_guard_service:
    health = await llm_guard_service.is_service_healthy()
    info = await llm_guard_service.get_service_info()
    print(f"Service healthy: {health}")
    print(f"Service info: {info}")
```

---

## 📈 Performance Optimization

### Connection Pooling

The service uses connection pooling for optimal performance:

```python
# aiohttp connector settings (hardcoded defaults)
connector = aiohttp.TCPConnector(
    limit=100,              # Total connection pool size
    limit_per_host=30,      # Connections per host
    keepalive_timeout=30,   # Keep connections alive
    enable_cleanup_closed=True
)
```

### Caching

Health check results are cached to reduce API calls:

```python
# Health check caching (hardcoded default)
health_cache_ttl = 30  # Cache health status for 30 seconds
```

### Content Batching

For high-volume scenarios, consider batching requests:

```python
# Process multiple content items together
contents = ["text1", "text2", "text3"]
tasks = [
    llm_guard_service.check_security(content, "prompt")
    for content in contents
]
results = await asyncio.gather(*tasks)
```

---

## 🔄 Updates and Maintenance

### Service Updates

When updating the LLM Guard service:

1. Update the base URL if changed
2. Check for new scanner types
3. Review configuration changes
4. Test fallback behavior

### Monitoring

Set up monitoring for:

- Service availability
- Response times
- Error rates
- Scanner effectiveness

### Backup and Recovery

Ensure your LLM Guard service has:

- High availability setup
- Backup instances
- Load balancing
- Disaster recovery plan

---

## 📚 Examples

### Complete Integration Example

```python
from services.llm_guard_service import LLMGuardService

class SecureChatService:
    def __init__(self, config, llm_guard_service):
        self.config = config
        self.llm_guard = llm_guard_service
    
    async def process_user_input(self, user_input: str, user_id: str) -> dict:
        """Process user input with security checking"""
        
        # Check input security
        security_result = await self.llm_guard.check_security(
            content=user_input,
            content_type="prompt",
            scanners=["prompt_injection", "toxicity", "secrets"],
            risk_threshold=0.6,
            user_id=user_id
        )
        
        if not security_result["is_safe"]:
            return {
                "error": "Input rejected due to security concerns",
                "details": security_result["recommendations"],
                "risk_score": security_result["risk_score"]
            }
        
        # Sanitize input before processing
        sanitized = await self.llm_guard.sanitize_content(user_input)
        safe_input = sanitized["sanitized_content"]
        
        # Process with LLM (your existing logic)
        response = await self.generate_response(safe_input)
        
        # Check response security
        response_security = await self.llm_guard.check_security(
            content=response,
            content_type="response",
            scanners=["bias", "sensitive", "relevance"],
            user_id=user_id
        )
        
        if not response_security["is_safe"]:
            return {
                "error": "Response blocked due to security concerns",
                "details": response_security["recommendations"]
            }
        
        return {
            "response": response,
            "security_passed": True,
            "sanitization_applied": sanitized["changes_made"]
        }
```

### Configuration Examples

#### Basic Setup
```yaml
llm_guard:
  enabled: true
  service:
    base_url: "http://localhost:8000"
    timeout: 30
  security:
    risk_threshold: 0.6
  fallback:
    on_error: "allow"
```

#### Production Setup
```yaml
llm_guard:
  enabled: true
  service:
    base_url: "https://llm-guard.prod.company.com"
    timeout: 60
  security:
    risk_threshold: 0.7
  fallback:
    on_error: "block"
```

#### High-Security Setup
```yaml
llm_guard:
  enabled: true
  service:
    base_url: "https://llm-guard.secure.company.com"
    timeout: 45
  security:
    risk_threshold: 0.5
  fallback:
    on_error: "block"
```

## 🔗 Chat Service Integration

The LLM Guard service is now fully integrated into the chat flow to provide real-time security checking for both user prompts and AI responses. This ensures unsafe content is blocked before processing or storage.

### Security Check Points

1. **User Message Validation**: Before LLM processing
   - Checks user input for security violations
   - Blocks unsafe messages immediately
   - No LLM inference occurs for blocked messages

2. **Response Validation**: Before chat history storage
   - Checks AI responses for security violations
   - Blocks unsafe responses from being stored
   - Prevents harmful content from entering chat history

### Integration Flow

```mermaid
flowchart TD
    A[User Message] --> B[Security Check]
    B -->|Safe| C[LLM Processing]
    B -->|Unsafe| D[Block & Return Error]
    C --> E[Response Generated]
    E --> F[Response Security Check]
    F -->|Safe| G[Store in Chat History]
    F -->|Unsafe| H[Block & Return Error]
    G --> I[Return Response to User]
```

### Implementation Details

#### Service Dependencies
The ChatService now accepts an `llm_guard_service` parameter:

```python
chat_service = ChatService(
    config, 
    llm_client, 
    logger_service,
    chat_history_service,
    llm_guard_service  # New parameter
)
```

#### Security Check Method
A new `_check_message_security()` method handles security validation:

```python
security_result = await self._check_message_security(
    content=message,
    content_type="prompt",  # or "response"
    user_id=user_id,
    session_id=session_id
)

if not security_result.get("is_safe", True):
    # Block and return error
    return {"error": "Message blocked by security scanner"}
```

#### Blocked Content Handling

When content is flagged as unsafe:

1. **Detailed Error Messages**: Include risk score, flagged scanners, and recommendations
2. **Logging**: Security violations are logged with full context
3. **No Storage**: Unsafe content is never stored in MongoDB chat history
4. **Audit Trail**: Blocked attempts are logged for security monitoring

#### Error Response Format

Blocked messages return user-friendly error responses without exposing sensitive security details:

```json
{
  "error": {
    "code": -32603,
    "message": "Message blocked by security scanner. Reason: prompt injection"
  }
}
```

**Note**: Detailed security information (risk scores, scanner names, technical recommendations) is logged for administrators but not exposed to clients for security reasons.

#### Streaming Support

The security integration works seamlessly with streaming responses:

- User messages are checked before streaming begins
- Complete responses are validated after streaming completes
- Security errors are streamed as proper JSON chunks
- Blocked responses don't interrupt the streaming protocol

### Configuration

LLM Guard integration is automatically enabled when the service is configured:

```yaml
llm_guard:
  enabled: true
  service:
    base_url: "http://localhost:8000"
    timeout: 30
  security:
    risk_threshold: 0.6
  fallback:
    on_error: "allow"
```

### Benefits

✅ **Comprehensive Protection**: Both input and output validation  
✅ **Zero Storage Pollution**: Unsafe content never enters chat history  
✅ **Transparent Integration**: Works with existing chat endpoints  
✅ **Streaming Compatible**: Full support for real-time responses  
✅ **Detailed Reporting**: Rich error messages and audit trails  
✅ **Graceful Fallbacks**: Continues working if LLM Guard is unavailable

This documentation provides comprehensive coverage of the LLM Guard Service integration with Orbit, including the simplified configuration, usage examples, and troubleshooting guidance.

#### Security Logging for Administrators

While clients receive user-friendly error messages, detailed security information is logged for administrators:

**Log Example:**
```
WARNING: Message blocked for session sess_123: Risk score: 0.85, Flagged by: toxicity, prompt_injection, Recommendations: Potential prompt injection detected. Review and sanitize user input.
```

**Logged Information:**
- Session ID for tracking
- Risk score (0.0-1.0)
- Specific scanners that flagged the content
- Technical recommendations for investigation
- Full security check results in metadata

This provides administrators with the information needed for security monitoring and incident response while keeping sensitive details away from end users. 