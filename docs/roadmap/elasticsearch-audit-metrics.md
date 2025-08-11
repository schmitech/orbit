# Elasticsearch Audit Metrics Enhancement

## Overview
This document outlines additional metrics that should be captured in Elasticsearch for comprehensive auditing, monitoring, and analytics of the Orbit inference server.

## Current State
As of 2025-08-10, the Elasticsearch logger service captures:
- Basic conversation data (query, response)
- Session and user IDs
- IP addresses and metadata
- Backend information
- Blocked conversation flags
- Timestamps
- API keys (masked)

## Proposed Enhancements

### 1. Performance Metrics
**Priority: HIGH**
- `request_id`: Unique identifier for tracking/debugging (UUID v4)
- `processing_time_ms`: Total end-to-end response time
- `token_count_input`: Number of input tokens processed
- `token_count_output`: Number of output tokens generated
- `model_name`: Specific model used (e.g., "llama2:13b", "gpt-4")
- `latency_breakdown`: Detailed timing breakdown
  ```json
  {
    "retrieval_ms": 150,
    "inference_ms": 2300,
    "safety_check_ms": 50,
    "embedding_ms": 75,
    "reranking_ms": 100
  }
  ```

### 2. Security & Safety Metrics
**Priority: HIGH**
- `threat_indicators`: Security assessment scores
  ```json
  {
    "prompt_injection_score": 0.15,
    "jailbreak_attempt": false,
    "sensitive_data_detected": false,
    "toxicity_score": 0.02,
    "llm_guard_result": "pass"
  }
  ```
- `safety_interventions`: Array of applied safety measures
- `rate_limit_status`: Current rate limiting state
- `authentication_method`: "api_key" | "jwt" | "session" | "none"

### 3. RAG/Context Metrics
**Priority: MEDIUM**
- `adapter_used`: Which adapter was used for retrieval
- `documents_retrieved`: Number of documents retrieved
- `relevance_scores`: Array of relevance scores
- `sources_cited`: List of source documents used
- `embedding_model`: Model used for embeddings
- `search_query_generated`: Reformulated/expanded query
- `retrieval_strategy`: "semantic" | "hybrid" | "keyword"
- `context_window_used`: Percentage of context window utilized

### 4. Error & Failure Tracking
**Priority: HIGH**
- `error_type`: Categorized error type
- `error_details`: Detailed error information
- `retry_count`: Number of retry attempts
- `fallback_used`: Whether fallback mechanism was triggered
- `circuit_breaker_status`: Circuit breaker state
- `recovery_action`: Action taken to recover from error

### 5. Usage & Cost Metrics
**Priority: MEDIUM**
- `estimated_cost`: Estimated cost in dollars
- `quota_remaining`: Remaining quota for the period
- `organization_id`: Organization identifier
- `project_id`: Project identifier
- `environment`: "production" | "staging" | "development"
- `billing_tier`: User's billing tier/plan
- `resource_usage`: CPU/memory usage snapshot

### 6. Client Information
**Priority: LOW**
- `client_version`: Version of client application
- `user_agent`: Full user agent string
- `request_source`: "web" | "api" | "mobile" | "cli"
- `geographic_region`: Geographic region of request
- `referrer_url`: Source URL if applicable
- `sdk_version`: Version of SDK being used
- `protocol_version`: API/protocol version

### 7. Conversation Context
**Priority: MEDIUM**
- `conversation_turn`: Turn number in conversation
- `total_session_tokens`: Cumulative tokens in session
- `session_duration_ms`: Total session duration
- `previous_intent`: Detected intent from previous turn
- `conversation_summary`: Auto-generated summary
- `context_switches`: Number of topic changes
- `user_satisfaction_score`: If feedback provided

### 8. Compliance & Legal
**Priority: HIGH**
- `data_classification`: "public" | "internal" | "confidential"
- `retention_period`: How long to retain the log
- `gdpr_consent`: GDPR consent status
- `data_residency`: Where data is processed/stored
- `audit_flags`: Array of compliance flags
- `pii_detected`: Whether PII was detected
- `data_masking_applied`: Whether sensitive data was masked

## Implementation Plan

### Phase 1 (Immediate)
1. Add performance metrics (processing time, token counts)
2. Add basic error tracking
3. Add request_id for correlation

### Phase 2 (Q1 2025)
1. Implement security/safety metrics
2. Add RAG/context metrics
3. Enhance error tracking with retry/fallback info

### Phase 3 (Q2 2025)
1. Add usage/cost tracking
2. Implement compliance metrics
3. Add conversation context tracking

### Phase 4 (Future)
1. Add client information tracking
2. Implement advanced analytics
3. Add custom business metrics

## Technical Considerations

### Index Mapping Updates
The Elasticsearch index mapping will need to be updated to accommodate these new fields. Consider:
- Using nested objects for complex structures
- Setting appropriate data types for each field
- Creating separate indices for different metric types if needed

### Performance Impact
- Minimize synchronous processing during request handling
- Consider async logging for non-critical metrics
- Batch updates where possible

### Storage Considerations
- Implement data retention policies
- Consider using Index Lifecycle Management (ILM)
- Compress older indices
- Archive to cheaper storage tiers

### Privacy & Security
- Ensure PII is properly masked
- Implement field-level encryption for sensitive data
- Maintain audit trail of who accesses logs
- Comply with data residency requirements

## Monitoring & Alerting

### Key Metrics to Monitor
1. High error rates
2. Unusual token usage patterns
3. Security threat indicators
4. Performance degradation
5. Rate limit violations

### Suggested Dashboards
1. **Operational Dashboard**: Performance, errors, availability
2. **Security Dashboard**: Threats, authentication, safety interventions
3. **Usage Dashboard**: Token usage, costs, quota tracking
4. **Quality Dashboard**: Relevance scores, user satisfaction
5. **Compliance Dashboard**: Data classification, retention, PII detection

## Dependencies
- Elasticsearch 9.0.2+ (currently using)
- Pipeline components need to expose these metrics
- May require updates to chat service and inference pipeline

## Related Documents
- [Logger Service Implementation](../../server/services/logger_service.py)
- [Pipeline Chat Service](../../server/services/pipeline_chat_service.py)
- [Test Suite](../../server/tests/test_elasticsearch_integration.py)

## Status
**Created**: 2025-08-10
**Status**: PLANNED
**Priority**: MEDIUM-HIGH
**Owner**: TBD

## Notes
- These metrics were identified during the Elasticsearch integration update
- Focus on metrics that provide actionable insights
- Balance between comprehensive logging and performance impact
- Consider GDPR and other regulatory requirements