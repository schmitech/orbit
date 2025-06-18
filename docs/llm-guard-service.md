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

- **🔧 Flexible Configuration**
  - Multiple scanner types and configurations
  - Adjustable risk thresholds
  - Environment-specific settings
  - Custom metadata and user tracking

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

### Basic Configuration

Add the following section to your `config.yaml`:

```yaml
llm_guard:
  enabled: false                    # Enable/disable the service
  service:
    base_url: "http://localhost:8000"    # LLM Guard API base URL
    api_version: "v1"                    # API version
    timeout:
      connect: 10                        # Connection timeout (seconds)
      read: 30                          # Read timeout (seconds)
      total: 60                         # Total request timeout (seconds)
    retry:
      max_attempts: 3                   # Maximum retry attempts
      backoff_factor: 0.3               # Exponential backoff factor
      status_forcelist: [500, 502, 503, 504]  # HTTP status codes to retry
    health_check:
      endpoint: "/health"               # Health check endpoint
      interval: 30                     # Health check interval (seconds)
      timeout: 5                       # Health check timeout (seconds)
```

### Security Check Configuration

```yaml
llm_guard:
  security_check:
    default_risk_threshold: 0.5         # Default risk threshold (0.0-1.0)
    default_scanners: []                # Default scanners (empty = use all available)
    available_input_scanners:           # Available input content scanners
      - "anonymize"                     # Anonymize PII data
      - "ban_substrings"                # Block banned substrings
      - "ban_topics"                    # Block banned topics
      - "code"                          # Detect code injection
      - "prompt_injection"              # Detect prompt injection attacks
      - "secrets"                       # Detect API keys, passwords, etc.
      - "toxicity"                      # Detect toxic/harmful content
    available_output_scanners:          # Available output content scanners
      - "bias"                          # Detect biased content
      - "no_refusal"                    # Ensure appropriate refusals
      - "relevance"                     # Check response relevance
      - "sensitive"                     # Detect sensitive information
```

### Client Defaults

```yaml
llm_guard:
  defaults:
    metadata:
      client_name: "orbit-server"       # Client identification
      client_version: "1.0.0"          # Client version
    user_id: null                       # Default user ID (null = not included)
    include_timestamp: true             # Include timestamp in requests
```

### Validation Settings

```yaml
llm_guard:
  validation:
    max_content_length: 10000           # Maximum content length to process
    valid_content_types: ["prompt", "response"]  # Valid content types
```

### Error Handling

```yaml
llm_guard:
  error_handling:
    fallback:
      on_service_unavailable: "allow"   # Fallback behavior: "allow", "block", or "raise"
      default_safe_response:            # Response when service unavailable and fallback="allow"
        is_safe: true
        risk_score: 0.0
        sanitized_content: null
        flagged_scanners: []
        recommendations: ["Service temporarily unavailable - content not scanned"]
```

---

## 🚀 Usage

### Service Integration

The LLM Guard Service is automatically initialized by the service factory when enabled. It's available through the application state:

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

| Scanner | Purpose | Configuration |
|---------|---------|---------------|
| `anonymize` | Detect and anonymize PII data | `pii_types`, `anonymization_method` |
| `ban_substrings` | Block content with banned phrases | `banned_phrases`, `case_sensitive` |
| `ban_topics` | Block content about banned topics | `banned_topics`, `threshold` |
| `code` | Detect code injection attempts | `languages`, `suspicious_patterns` |
| `prompt_injection` | Detect prompt injection attacks | `injection_patterns`, `threshold` |
| `secrets` | Detect API keys, passwords, tokens | `secret_types`, `entropy_threshold` |
| `toxicity` | Detect toxic/harmful content | `toxicity_threshold`, `categories` |

### Output Scanners (Response Analysis)

| Scanner | Purpose | Configuration |
|---------|---------|---------------|
| `bias` | Detect biased or unfair content | `bias_types`, `threshold` |
| `no_refusal` | Ensure appropriate refusals | `refusal_patterns`, `min_confidence` |
| `relevance` | Check response relevance to prompt | `relevance_threshold`, `similarity_method` |
| `sensitive` | Detect sensitive information leaks | `sensitivity_categories`, `threshold` |

---

## 🔧 Advanced Configuration

### Environment-Specific Settings

You can override configuration for different environments:

```yaml
llm_guard:
  enabled: false  # Default setting
  service:
    base_url: "http://localhost:8000"  # Default URL

# Override for production
# Set LLM_GUARD_ENABLED=true and LLM_GUARD_BASE_URL=https://llm-guard.prod.com
```

### Custom Scanner Configuration

```yaml
llm_guard:
  security_check:
    scanner_configs:
      prompt_injection:
        threshold: 0.7
        patterns: ["ignore previous", "system:", "prompt:"]
      toxicity:
        threshold: 0.8
        categories: ["hate", "violence", "harassment"]
      secrets:
        entropy_threshold: 4.0
        secret_types: ["api_key", "password", "token", "certificate"]
```

### Performance Tuning

```yaml
llm_guard:
  service:
    timeout:
      connect: 5      # Faster connection timeout
      read: 15        # Faster read timeout
      total: 30       # Faster total timeout
    retry:
      max_attempts: 2 # Fewer retries for faster response
      backoff_factor: 0.5  # Faster backoff
  validation:
    max_content_length: 5000  # Smaller content limit
```

---

## 🛠️ Error Handling

### Fallback Behaviors

When the LLM Guard service is unavailable, you can configure different fallback behaviors:

#### Allow (Default)
- **Behavior**: Allow content to pass through unscanned
- **Use Case**: Non-critical applications where availability is prioritized
- **Configuration**: `on_service_unavailable: "allow"`

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
- **Configuration**: `on_service_unavailable: "block"`

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

#### Raise
- **Behavior**: Raise exception when service is unavailable
- **Use Case**: Applications that need explicit error handling
- **Configuration**: `on_service_unavailable: "raise"`

### Retry Logic

The service implements exponential backoff retry logic:

```python
# Retry configuration
max_attempts = 3
backoff_factor = 0.3
retry_delays = [0.3, 0.6, 1.2]  # seconds

# Status codes that trigger retries
retry_status_codes = [500, 502, 503, 504, 429]
```

### Circuit Breaker Pattern

The service includes circuit breaker functionality:

- **Failure Threshold**: After 5 consecutive failures, circuit opens
- **Recovery Timeout**: 30 seconds before attempting recovery
- **Health Monitoring**: Automatic health checks to close circuit

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

### Authentication

If your LLM Guard service requires authentication, configure it in the service settings:

```yaml
llm_guard:
  service:
    auth:
      type: "bearer"  # or "api_key", "basic"
      token: "${LLM_GUARD_TOKEN}"
      # For API key auth:
      # api_key_header: "X-API-Key"
      # For basic auth:
      # username: "${LLM_GUARD_USERNAME}"
      # password: "${LLM_GUARD_PASSWORD}"
```

### Network Security

- **HTTPS**: Always use HTTPS in production
- **Firewall**: Restrict access to LLM Guard service
- **VPN**: Use VPN for communication between services

```yaml
llm_guard:
  service:
    base_url: "https://llm-guard.internal.company.com"  # HTTPS endpoint
    verify_ssl: true  # Verify SSL certificates
```

### Data Privacy

- **Content Logging**: Configure whether to log request/response content
- **PII Handling**: Ensure PII is properly anonymized
- **Data Retention**: Configure how long scan results are kept

```yaml
llm_guard:
  privacy:
    log_content: false          # Don't log actual content
    anonymize_logs: true        # Anonymize any logged data
    retention_days: 7           # Keep scan results for 7 days
```

---

## 🐛 Troubleshooting

### Common Issues

#### Service Not Starting
```bash
# Check if LLM Guard is enabled
grep -A5 "llm_guard:" config.yaml

# Verify the base URL is correct
curl -X GET "http://localhost:8000/health"
```

#### Connection Timeouts
```yaml
# Increase timeouts in config.yaml
llm_guard:
  service:
    timeout:
      connect: 30
      read: 60
      total: 120
```

#### High Error Rates
```yaml
# Increase retry attempts and adjust backoff
llm_guard:
  service:
    retry:
      max_attempts: 5
      backoff_factor: 0.5
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
# aiohttp connector settings
connector = aiohttp.TCPConnector(
    limit=100,              # Total connection pool size
    limit_per_host=30,      # Connections per host
    keepalive_timeout=30,   # Keep connections alive
    enable_cleanup_closed=True
)
```

### Caching

Health check results are cached to reduce API calls:

```yaml
llm_guard:
  service:
    health_check:
      interval: 30  # Cache health status for 30 seconds
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

This documentation provides comprehensive coverage of the LLM Guard Service integration with Orbit, including architecture, configuration, usage examples, and troubleshooting guidance. 