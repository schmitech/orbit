# Intent Query Result Caching with Follow-up Support

## Overview

Enable users to ask follow-up questions about SQL intent query results by caching the dataset in Redis and using semantic similarity to detect when a new query begins.

## Architecture Design

### Storage Strategy (Redis)

- **Cache Key Format**: `intent_result:{session_id}:{adapter_name}`
- **Stored Data**:
  - `query`: Original natural language query
  - `query_embedding`: Vector embedding for similarity comparison
  - `recent_followup_embeddings`: Rolling list of embeddings for the last N follow-up turns
  - `sql_executed`: The actual SQL query executed
  - `results`: The raw SQL result dataset (JSON)
  - `result_columns`: Ordered list of columns returned for applicability checks
  - `result_metadata`: Lightweight stats (row count, filters, time range, etc.)
  - `timestamp`: When results were cached
  - `adapter_name`: Which intent adapter was used
- **TTL**: 30 minutes of inactivity (reset on each follow-up)

### Query Detection Flow

1. Check if cached results exist for session+adapter
2. If cache exists:

   - Generate embedding for new query
   - Compute **follow-up confidence** using:
     - Similarity to the original cached query
     - Max similarity against the rolling follow-up embedding history
     - A lightweight intent classifier score (`FOLLOW_UP` vs `NEW_QUERY`)
   - Apply adapter-specific thresholds with hysteresis (e.g., promote to follow-up when confidence ≥ `threshold_high`, demote when ≤ `threshold_low`)
   - Run **result applicability checks**:
     - Ensure follow-up asks about dimensions/metrics included in `result_columns`
     - Validate cached metadata still satisfies implied filters (time range, granularity, etc.)
   - If confidence passes and applicability succeeds:
     - Check for refresh intent (keywords or explicit flag)
     - If refresh detected: Clear cache, execute fresh query
     - Otherwise: Use cached results (follow-up question) and append the new embedding to history
   - If applicability fails or confidence is below `threshold_low`: treat as new query, clear cache, execute fresh

When embeddings are unavailable, reuse the cached embedding history and lean on the classifier + keyword heuristics, skipping the similarity components but still producing a confidence score with lowered thresholds.

3. If no cache: Execute query normally and cache results

### Refresh Detection Strategy

To handle cases where users want fresh results for near real-time data, the system detects refresh intent through:

**1. Keyword Detection (Primary)**
- Time-focused keywords: `latest`, `current`, `now`, `today`, `recent`, `up-to-date`, `fresh`, `real-time`
- Action-focused keywords: `refresh`, `re-run`, `rerun`, `again`, `update`, `reload`
- Pattern matching: Case-insensitive, whole-word matching

**2. Explicit Request Override**
- Request metadata field: `bypass_cache: true` or `force_refresh: true`
- Allows API clients and power users to force fresh execution
- Useful for scheduled queries that always need current data

**3. Detection Scope**
- Refresh keywords only trigger cache bypass when follow-up confidence already exceeds the configured threshold
- Prevents false positives (e.g., unrelated query mentioning "latest products")
- Maintains semantic awareness of the caching system while allowing low-confidence turns to start new queries

**Example Scenarios:**
- Original: "Show me sales data for Q4" → Cached
- Follow-up: "Show me **latest** sales data for Q4" → **Refresh triggered**, cache cleared
- Follow-up: "Show me top customers" → **New query** (follow-up confidence below threshold_low), cache cleared
- Follow-up: "What were the top products?" → **Follow-up** (confidence ≥ threshold_high, uses cache)

**Complete Refresh Flow:**
```
1. User: "Show me Q4 sales" → SQL executes, results cached
2. User: "Show me latest Q4 sales"
   ├─ Embedding generated, similarity to original = 0.92
   ├─ Combined follow-up confidence = 0.88 (≥ threshold_high)
   ├─ Keyword "latest" detected
   ├─ Cache cleared
   └─ SQL re-executes with fresh data
3. User: "Show latest Q4 sales" (again, minutes later)
   ├─ Embedding generated, similarity to original = 0.94
   ├─ Combined follow-up confidence = 0.90
   ├─ Keyword "latest" detected
   └─ SQL re-executes again (each refresh is fresh)
```

**API Request with Explicit Bypass:**
```json
{
  "message": "Show me Q4 sales",
  "adapter_name": "sales_intent",
  "session_id": "user123",
  "metadata": {
    "bypass_cache": true
  }
}
```

### Integration Points

- **PipelineChatService**: Main orchestration logic
- **ContextRetrievalStep**: Modified to check cache before calling intent retriever
- **ProcessingContext**: Add fields for cached results and cache metadata
- **Redis Service**: Already available, add helper methods for intent caching

## Implementation Steps

### 1. Extend ProcessingContext

**File**: `server/inference/pipeline/base.py`

Add new fields to ProcessingContext dataclass:

```python
# Cached intent result fields
cached_intent_results: Optional[Dict[str, Any]] = None
cached_intent_query: Optional[str] = None
is_followup_query: bool = False
query_similarity_score: Optional[float] = None
cache_refresh_requested: bool = False  # User requested fresh results
bypass_cache: bool = False  # Explicit cache bypass from request metadata
followup_confidence: Optional[float] = None  # Combined follow-up confidence
cache_applicability_reason: Optional[str] = None  # Explanation when cache rejected
recent_followup_embeddings: List[List[float]] = field(default_factory=list)
```

### 2. Create Intent Result Cache Service

**File**: `server/services/intent_result_cache_service.py` (NEW)

Create a dedicated service to handle intent result caching:

- `store_intent_results()`: Cache SQL results with embeddings
- `get_cached_results()`: Retrieve cached results if they exist
- `check_query_similarity()`: Compare query embeddings
- `detect_refresh_intent()`: Check for refresh keywords in query
- `clear_cache()`: Remove cached results for session
- `update_ttl()`: Reset expiry on follow-up questions
- `evaluate_followup_confidence()`: Blend similarity scores and classifier output
- `validate_result_applicability()`: Confirm cached result covers requested fields/filters
- `append_followup_embedding()`: Maintain rolling embedding history for hysteresis
- Dataclasses:
  - `CacheDecision`: encapsulates follow-up confidence, similarity breakdowns, applicability reason, and embedding history
  - `ApplicabilityResult`: flags whether cached data satisfies the new request and provides a human-readable reason

Key methods:

```python
async def check_and_retrieve_cache(
    session_id: str,
    adapter_name: str, 
    new_query: str,
    similarity_thresholds: SimilarityThresholds,
    bypass_cache: bool = False
) -> CacheDecision  # Contains is_followup, cached_data, confidence, similarity, applicability_reason, refresh_requested

def detect_refresh_intent(self, query: str) -> bool:
    """
    Detect if query contains refresh keywords indicating user wants fresh results.
    
    Returns:
        True if refresh intent detected, False otherwise
    """
    # Check against configurable list of refresh keywords
    # Case-insensitive whole-word matching

def validate_result_applicability(self, cached_columns: Sequence[str], cached_metadata: Dict[str, Any], new_query: str) -> ApplicabilityResult:
    """
    Ensure cached dataset covers requested fields and filters.
    """
```

### 3. Modify ContextRetrievalStep

**File**: `server/inference/pipeline/steps/context_retrieval.py`

Update the process method to:

1. Check if adapter is an intent-based retriever
2. Fetch adapter-specific hysteresis thresholds and consult intent_result_cache_service before retrieval
3. Incorporate explicit cache bypass flag when evaluating the cache decision
4. If follow-up confidence passes and applicability succeeds (and no refresh intent), populate context with cached results
5. If refresh detected, applicability fails, or confidence drops below threshold, clear cache and proceed with normal retrieval
6. Format cached results appropriately for LLM context and persist updated embedding history

Add logic around line 76:

```python
# Check for cached intent results before retrieval
if self._is_intent_adapter(adapter_name):
    cache_service = self.container.get_or_none('intent_result_cache_service')
    if cache_service:
        decision = await cache_service.check_and_retrieve_cache(
            context.session_id, adapter_name, context.message,
            similarity_thresholds=self._get_intent_thresholds(adapter_name),
            bypass_cache=context.bypass_cache
        )
        
        # Store similarity, confidence, and refresh status in context
        context.query_similarity_score = decision.similarity_to_original
        context.followup_confidence = decision.confidence
        context.cache_refresh_requested = decision.refresh_requested
        context.cache_applicability_reason = decision.applicability_reason
        context.recent_followup_embeddings = decision.embedding_history
        
        if decision.is_followup and decision.cached_data and not decision.refresh_requested and not context.bypass_cache:
            # Use cached results for follow-up question
            context.cached_intent_results = decision.cached_data
            context.is_followup_query = True
            # Format cached results as context
            context.formatted_context = self._format_cached_intent_context(decision.cached_data)
            if self.verbose:
                logger.info(
                    "Using cached intent results "
                    f"(confidence: {decision.confidence:.3f}, similarity: {decision.similarity_to_original:.3f})"
                )
            return context
        
        elif decision.refresh_requested or context.bypass_cache:
            # Clear cache before executing fresh query
            await cache_service.clear_cache(context.session_id, adapter_name)
            if self.verbose:
                reason = "explicit bypass" if context.bypass_cache else "refresh keywords detected"
                logger.info(f"Cache cleared due to {reason}, executing fresh query")
```

### 4. Update PipelineChatService

**File**: `server/services/pipeline_chat_service.py`

Modify initialization to create intent_result_cache_service and register it with pipeline container.

Add in `__init__` around line 88:

```python
# Create intent result cache service
from services.intent_result_cache_service import IntentResultCacheService
intent_cache_service = IntentResultCacheService(config, redis_service, embedding_service)
```

Register with pipeline container when building pipeline.

Also update the chat processing to handle bypass_cache from request metadata:

```python
# In process_chat method, extract bypass_cache from request metadata
async def process_chat(self, message: str, adapter_name: str, ..., 
                      request_metadata: Optional[Dict[str, Any]] = None):
    # Create processing context
    context = ProcessingContext(
        message=message,
        adapter_name=adapter_name,
        session_id=session_id,
        bypass_cache=request_metadata.get('bypass_cache', False) if request_metadata else False,
        ...
    )
```

### 5. Post-Retrieval Cache Storage

**File**: `server/inference/pipeline/steps/context_retrieval.py`

After successful intent retrieval, store results in cache:

```python
# After retrieval at line 82, add:
if self._is_intent_adapter(adapter_name) and context.session_id:
    cache_service = self.container.get_or_none('intent_result_cache_service')
    if cache_service and not context.is_followup_query:
        # Store new query results in cache
        await cache_service.store_intent_results(
            session_id=context.session_id,
            adapter_name=adapter_name,
            query=context.message,
            results=docs,
            sql_query=self._extract_sql_from_docs(docs),
            result_columns=self._extract_columns_from_docs(docs),
            result_metadata=self._derive_result_metadata(docs),
            followup_embeddings=context.recent_followup_embeddings,
        )
```

### 6. Configuration Support

**File**: `config/config.yaml`

Add configuration section:

```yaml
intent_result_cache:
  enabled: true  # Requires Redis to be enabled
  ttl_seconds: 1800  # 30 minutes
  similarity_thresholds:
    default:
      high: 0.80  # Promote to follow-up when ≥ high
      low: 0.70   # Treat as new query when ≤ low
    adapters:
      sales_intent:
        high: 0.82
        low: 0.72
  max_result_size_mb: 10  # Max size of cached results
  verbose_logging: true  # Log cache hits/misses
  followup_classifier:
    enabled: true
    model: intent.followup.classifier
    min_probability: 0.60
  applicability:
    enforce_schema_check: true
    require_matching_dimensions: true
    allow_time_window_drift_minutes: 5
  
  # Refresh detection keywords (case-insensitive, whole-word matching)
  refresh_keywords:
    # Time-focused
    - latest
    - current
    - now
    - today
    - recent
    - up-to-date
    - fresh
    - real-time
    - realtime
    # Action-focused
    - refresh
    - re-run
    - rerun
    - again
    - update
    - reload
```

**Important**: This feature requires Redis to be enabled. The cache service will:

- Check `internal_services.redis.enabled` during initialization
- Automatically disable if Redis is not available
- Log a warning if cache is enabled but Redis is disabled
- Gracefully fall back to always executing queries (no caching)

### 7. Helper Utilities

Add utility methods to ContextRetrievalStep:

- `_is_intent_adapter()`: Detect if adapter is intent-based
- `_format_cached_intent_context()`: Format cached SQL results for LLM
- `_extract_sql_from_docs()`: Extract executed SQL from retriever response
- `_extract_columns_from_docs()`: Identify available fields for applicability checks
- `_derive_result_metadata()`: Capture lightweight stats for follow-up validation
- `_get_intent_thresholds()`: Retrieve adapter-specific hysteresis thresholds

### 8. User Feedback Enhancement

**File**: `server/services/pipeline_chat_service.py`

Add metadata to responses indicating cache usage:

```python
# In process_chat method, add to metadata:
if result.is_followup_query:
    metadata["cache_hit"] = True
    metadata["query_similarity"] = result.query_similarity_score
    metadata["cached_query"] = result.cached_intent_query
    metadata["followup_confidence"] = result.followup_confidence
elif result.cache_refresh_requested:
    metadata["cache_hit"] = False
    metadata["cache_refresh"] = True
    metadata["refresh_reason"] = "explicit" if result.bypass_cache else "keywords_detected"
    metadata["cache_applicability_reason"] = result.cache_applicability_reason
```

Optionally add user-visible indicators in verbose mode that surface follow-up confidence and applicability reasons.

## Testing Considerations

1. **Cache hit scenario**: Same/similar question twice
2. **Cache miss scenario**: Different question after cached query  
3. **Refresh detection**: Similar query with refresh keywords triggers fresh execution
4. **Applicability rejection**: Similar wording but unseen dimensions forces new query
5. **Dynamic thresholding**: Validate hysteresis around borderline confidence values
6. **Explicit bypass**: `bypass_cache: true` in request metadata forces fresh query
7. **Session isolation**: Different sessions don't share caches
8. **TTL expiry**: Cache expires after inactivity
9. **Large result handling**: Results exceeding size limits
10. **Embedding outage**: Classifier + history heuristics maintain follow-up support without embeddings
11. **Classifier disagreement**: Confidence low but similarity high should fall back to new query path

## Benefits

- ✅ **No re-execution**: Follow-up questions don't hit database again
- ✅ **Fast responses**: Cached results retrieved in milliseconds
- ✅ **Semantic awareness**: Accurately detects new vs follow-up queries
- ✅ **Session-scoped**: Isolated per user session
- ✅ **Auto-expiry**: No manual cleanup needed
- ✅ **Transparent**: Works automatically, no special commands
- ✅ **Applicability checks**: Prevents stale results when new dimensions are requested
- ✅ **Resilient fallback**: Classifier + history heuristics keep follow-up flow usable during embedding outages

## Edge Cases Handled

1. **Redis unavailable**: Gracefully fall back to always executing queries
2. **Embedding service unavailable**: Classifier + keyword heuristics step in with reduced confidence requirements
3. **Result too large**: Skip caching, log warning
4. **Multiple adapters**: Cache keyed by adapter name with adapter-specific thresholds
5. **Session expiry**: Cache naturally expires with session TTL
6. **Refresh keywords in new query**: Only trigger refresh when follow-up confidence is high (prevents false positives)
7. **Explicit bypass without cache**: `bypass_cache: true` on first query has no effect (no cache to bypass)
8. **Applicability failure**: Cache ignored when requested fields missing, reason logged
9. **Multiple refresh keywords**: Any single keyword match triggers refresh detection
