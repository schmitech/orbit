# Language Detection Enhancements

**Date:** December 2024
**Component:** `server/inference/pipeline/steps/language_detection.py`
**Related Files:** `config/config.yaml`, `server/adapters/capabilities.py`, `server/inference/pipeline/steps/context_retrieval.py`

## Overview

Major overhaul of the language detection system to improve accuracy, performance, and robustness. The enhanced system ensures that user prompts are correctly identified so LLMs respond in the appropriate language.

## Changes Summary

### 1. Per-Backend Confidence Normalization

**Problem:** Different detection libraries return confidence scores in incompatible formats:
- `langdetect`: 0-1 probabilities
- `langid`: Log-probabilities (negative values)
- `pycld2`: 0-100 percentages

**Solution:** Each backend now has dedicated normalization:
- `langdetect`: Used as-is (already 0-1)
- `langid`: Softmax applied over top-K results
- `pycld2`: Divided by 100, reliability factor applied

### 2. Expanded Script Coverage (9 → 25 scripts)

Added support for:
- **South Asian:** Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Odia, Sinhala
- **Southeast Asian:** Lao, Myanmar, Khmer
- **Other:** Georgian, Armenian, Amharic, Persian

### 3. Expanded Latin Language Patterns (5 → 17 languages)

Added pattern detection for:
- Dutch, Swedish, Norwegian, Danish
- Polish, Czech, Turkish
- Indonesian, Finnish, Vietnamese
- Romanian, Hungarian

### 4. Performance Optimizations

- **Pre-compiled regex patterns:** All patterns compiled at module level
- **Combined marker patterns:** English/Spanish markers use single alternation regex
- **Async parallel execution:** Backends run concurrently with configurable timeout (default 2.0s)

### 5. Configurable Heuristic Nudges

New config options in `config.yaml`:
```yaml
heuristic_nudges:
  en_boost: 0.2       # Boost for English in ASCII-heavy text
  es_penalty: 0.1     # Penalty for Spanish in pure ASCII
  script_boost: 0.2   # Boost when script matches ensemble winner
```

### 6. Mixed-Language Detection

System now flags when secondary language has ≥30% confidence:
```yaml
mixed_language_threshold: 0.3
```

Metadata includes `mixed_language_detected`, `secondary_language`, and `secondary_confidence`.

### 7. Session Persistence (Redis)

Language stickiness now persists across API calls:
- Stored in Redis with key `lang_detect:{session_id}`
- 1-hour TTL matching session duration
- Graceful fallback if Redis unavailable

### 8. Chat History Language Prior

Uses recent conversation history to stabilize detection:
```yaml
use_chat_history_prior: true
chat_history_prior_weight: 0.3
chat_history_messages_count: 5
```

### 9. RAG Retrieval Language Boosting

Documents matching detected language get boosted in retrieval:
```yaml
retrieval_match_boost: 0.1
retrieval_mismatch_penalty: 0.05
retrieval_min_confidence: 0.7
```

### 10. Short Text Script Detection

CJK characters now detected even for 1-2 character inputs (e.g., "你好" correctly returns Chinese).

## Configuration

Full configuration block in `config.yaml`:

```yaml
language_detection:
  enabled: true
  backends:
    - "langdetect"
    - "langid"
    - "pycld2"
  backend_weights:
    langdetect: 1.0
    langid: 1.2
    pycld2: 1.5
  min_confidence: 0.7
  min_margin: 0.2
  prefer_english_for_ascii: true
  enable_stickiness: true
  fallback_language: "en"
  backend_timeout: 2.0  # Timeout per backend in seconds (increase for cold starts)

  heuristic_nudges:
    en_boost: 0.2
    es_penalty: 0.1
    script_boost: 0.2

  mixed_language_threshold: 0.3

  use_chat_history_prior: true
  chat_history_prior_weight: 0.3
  chat_history_messages_count: 5

  retrieval_match_boost: 0.1
  retrieval_mismatch_penalty: 0.05
  retrieval_min_confidence: 0.7
```

## Dependencies

Ensure the `language-detection` profile is installed:
```bash
./setup.sh --profile language-detection
```

This installs:
- `langdetect>=1.0.9`
- `langid>=1.1.6`
- `pycld2>=0.42`
- `pycountry>=24.6.1`

## Testing

Run the dedicated language detection tests:
```bash
pytest server/tests/test_language_detection.py -v
```

## Migration Notes

- No breaking changes to existing API
- New config options have sensible defaults
- Existing sessions will work without Redis (falls back to context metadata)

## Performance Impact

- Backend execution: ~50-150ms (parallel) vs ~150-450ms (sequential)
- Regex matching: ~10x faster with pre-compiled patterns
- Memory: Minimal increase (~50KB for compiled patterns)

## Bug Fixes (December 2024)

### Fix #1: Redis Stickiness Now Activates

**Problem:** The Redis session persistence code checked for `redis_client` service, but the pipeline only registered `redis_service`.

**Solution:**
- Added `redis_service` parameter to `PipelineFactory.create_service_container()`
- Updated `PipelineChatService` to accept and pass `redis_service`
- Updated `ServiceFactory` to pass `app.state.redis_service` when creating the chat service
- Changed `language_detection.py` to use `redis_service` with `get_json()`/`set_json()` methods

### Fix #2: Mixed-Language Metadata Exposed at Top Level

**Problem:** Mixed-language fields (`mixed_language_detected`, `secondary_language`, `secondary_confidence`) were only stored inside `raw_results`, requiring consumers to dig into nested data.

**Solution:** These fields are now exposed at the top level of `context.language_detection_meta`:
```python
context.language_detection_meta['mixed_language_detected']  # True/False
context.language_detection_meta['secondary_language']       # e.g., 'es'
context.language_detection_meta['secondary_confidence']     # e.g., 0.35
```

### Fix #3: Confidence Calculation for Retrieval Boost

**Problem:** Confidence was calculated as `best_score / total_backend_weights`, which rarely exceeded 0.7 even with unanimous detection, causing the RAG retrieval boost to almost never activate.

**Solution:** Confidence is now calculated as `best_score / sum(all_language_votes)` (true posterior probability). This gives realistic values that can exceed the 0.7 retrieval threshold when detection is unambiguous.

**Files Changed:**
- `server/inference/pipeline_factory.py`
- `server/services/pipeline_chat_service.py`
- `server/services/service_factory.py`
- `server/inference/pipeline/steps/language_detection.py`

**New Tests Added:** 10 new tests in `TestRedisServiceIntegration`, `TestMixedLanguageMetadataExposure`, `TestConfidenceCalculation`, and `TestRetrievalBoostIntegration` classes.
