# Language Detection Architecture

This document describes the technical architecture of Orbit's language detection system, which ensures that user prompts are correctly identified so LLMs respond in the appropriate language.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Detection Pipeline](#detection-pipeline)
4. [Backend Ensemble](#backend-ensemble)
5. [Script Detection](#script-detection)
6. [Heuristic Biasing](#heuristic-biasing)
7. [Language Stickiness](#language-stickiness)
8. [RAG Integration](#rag-integration)
9. [Configuration Reference](#configuration-reference)
10. [Extending the System](#extending-the-system)

## Overview

The language detection system is a pipeline step that runs before LLM inference to detect the language of user messages. This enables:

1. **Appropriate LLM responses** - LLM responds in the same language as the user
2. **Language-aware RAG** - Retrieved documents can be boosted/filtered by language
3. **Stable detection** - Prevents language flapping across conversation turns
4. **Mixed-language awareness** - Detects code-switching in multilingual conversations

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Language Detection Step                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────────────────────────────────────┐  │
│  │ Input Text   │───▶│            Pre-processing                    │  │
│  └──────────────┘    │  • Remove URLs, emails, code blocks          │  │
│                      │  • Collapse whitespace                       │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │         Script Detection (Fast Path)         │  │
│                      │  • 25 Unicode script patterns                │  │
│                      │  • French phrase patterns                    │  │
│                      │  • Latin word patterns (17 languages)        │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                         High confidence? ───Yes──▶ Return result       │
│                                        │                                │
│                                        ▼ No                             │
│                      ┌──────────────────────────────────────────────┐  │
│                      │      Backend Ensemble (Parallel Async)       │  │
│                      │                                              │  │
│                      │  ┌────────────┐ ┌────────────┐ ┌──────────┐ │  │
│                      │  │ langdetect │ │  langid    │ │ pycld2   │ │  │
│                      │  │ weight:1.0 │ │ weight:1.2 │ │weight:1.5│ │  │
│                      │  └────────────┘ └────────────┘ └──────────┘ │  │
│                      │         │              │             │       │  │
│                      │         └──────────────┴─────────────┘       │  │
│                      │                        │                      │  │
│                      │                        ▼                      │  │
│                      │           Per-Backend Normalization           │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │            Weighted Voting                    │  │
│                      │  • Aggregate normalized confidences           │  │
│                      │  • Apply chat history prior                   │  │
│                      │  • Apply heuristic nudges                     │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │         Threshold & Stickiness Logic          │  │
│                      │  • Check min_confidence & min_margin          │  │
│                      │  • Apply session stickiness if ambiguous      │  │
│                      │  • Apply ASCII bias if applicable             │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │              Session Persistence              │  │
│                      │  • Store in Redis (lang_detect:{session_id}) │  │
│                      │  • Update context.detected_language           │  │
│                      └──────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Detection Pipeline

### 1. Pre-processing

Text is cleaned to remove elements that confuse statistical detectors:

```python
# Patterns removed:
- URLs: https?://... and www....
- Emails: user@domain.com
- Code fences: ```code```
- Inline code: `code`
- Excessive punctuation/numbers: 123-456-789
```

### 2. Script Detection (Fast Path)

Before calling heavyweight backends, script-based detection provides high-confidence results for non-Latin scripts:

| Script | Unicode Range | Languages | Confidence |
|--------|---------------|-----------|------------|
| CJK Unified | U+4E00-U+9FFF | Chinese | 0.95 |
| Hiragana/Katakana | U+3040-U+30FF | Japanese | 0.95 |
| Hangul | U+AC00-U+D7AF | Korean | 0.95 |
| Arabic | U+0600-U+06FF | Arabic | 0.95 |
| Devanagari | U+0900-U+097F | Hindi, Marathi | 0.95 |
| Bengali | U+0980-U+09FF | Bengali | 0.95 |
| Tamil | U+0B80-U+0BFF | Tamil | 0.95 |
| Thai | U+0E00-U+0E7F | Thai | 0.95 |
| Cyrillic | U+0400-U+04FF | Russian, etc. | 0.80 |
| Greek | U+0370-U+03FF | Greek | 0.95 |
| Georgian | U+10A0-U+10FF | Georgian | 0.95 |
| Armenian | U+0530-U+058F | Armenian | 0.95 |
| ... | ... | ... | ... |

### 3. Word Pattern Detection

For Latin-script languages, keyword patterns provide disambiguation:

```python
# Example: Spanish detection
patterns = ['¿', '¡', r'\baño\b', r'\bestá\b', r'\bqué\b', r'\bgracias\b']

# Example: Vietnamese detection (Latin + diacritics)
patterns = [r'[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]']
```

## Backend Ensemble

Three statistical backends are used with weighted voting:

### langdetect (weight: 1.0)
- Based on Google's language-detection library
- Good for longer text
- Returns probability directly (0-1)

### langid (weight: 1.2)
- Pre-trained Naive Bayes classifier
- Fast and accurate
- Returns log-probabilities → normalized via softmax

### pycld2 (weight: 1.5)
- Google's Compact Language Detector 2
- Highest weight (most accurate)
- Returns percentage (0-100) → normalized to 0-1
- Reliability flag applied as confidence multiplier

### Parallel Execution

Backends run concurrently with individual timeouts:

```python
async def _run_backend_with_timeout(self, backend_name, detector_func, text, timeout=0.5):
    loop = asyncio.get_event_loop()
    result = await asyncio.wait_for(
        loop.run_in_executor(None, detector_func, text),
        timeout=timeout
    )
    return result
```

### Weighted Voting

```python
# For each backend result:
weighted_score = normalized_confidence * backend_weight
language_votes[lang] += weighted_score
total_weight += backend_weight

# Final confidence:
best_confidence = best_score / total_weight
```

## Heuristic Biasing

### ASCII Bias (English preference)

For short, high-ASCII text starting with English interrogatives:

```python
if ascii_ratio > 0.98 and len(text) <= 120:
    if starts_with_english_question and no_spanish_markers:
        return English with 0.9 confidence
```

This prevents "How do I export code?" from being classified as Portuguese.

### Configurable Nudges

```yaml
heuristic_nudges:
  en_boost: 0.2       # Added to English votes in ASCII text
  es_penalty: 0.1     # Subtracted from Spanish in pure ASCII
  script_boost: 0.2   # Added when script matches ensemble winner
```

### Chat History Prior

Recent messages' language distribution is used as a soft prior:

```python
if chat_history_prior:
    for lang, freq in chat_history_prior.items():
        language_votes[lang] += prior_weight * freq
```

## Language Stickiness

### Problem
Users typing in one language may occasionally produce ambiguous short messages (e.g., "OK", "Yes", numbers). Without stickiness, these would reset to English.

### Solution
1. Store detected language in session (Redis or context metadata)
2. When detection is ambiguous (below threshold or margin), prefer previous language
3. Stickiness decays if new detection strongly contradicts it

```python
if best_confidence < min_confidence or margin < min_margin:
    if previous_language in language_votes:
        return previous_language with sticky confidence
```

### Session Persistence

```python
# Redis storage
key = f"lang_detect:{session_id}"
await redis.hset(key, {
    'language': result.language,
    'confidence': result.confidence,
    'method': result.method
})
await redis.expire(key, 3600)  # 1 hour TTL
```

## RAG Integration

### Language-Aware Document Boosting

After retrieval, documents are re-scored based on language match:

```python
if doc_language == detected_language:
    score += match_boost * language_confidence
else:
    score -= mismatch_penalty * language_confidence

# Re-sort by adjusted scores
docs.sort(key=lambda d: d['confidence'], reverse=True)
```

### Configuration

```yaml
retrieval_match_boost: 0.1       # Boost for matching language
retrieval_mismatch_penalty: 0.05 # Penalty for non-matching
retrieval_min_confidence: 0.7    # Min detection confidence to apply
```

## Configuration Reference

### Full Configuration Block

```yaml
language_detection:
  # Enable/disable the feature
  enabled: true

  # Backends to use (order doesn't matter - all run in parallel)
  backends:
    - "langdetect"
    - "langid"
    - "pycld2"

  # Backend weights for voting (higher = more influence)
  backend_weights:
    langdetect: 1.0
    langid: 1.2
    pycld2: 1.5

  # Detection thresholds
  min_confidence: 0.7    # Minimum to accept detection
  min_margin: 0.2        # Minimum gap between top-2 candidates

  # English bias for ASCII text
  prefer_english_for_ascii: true

  # Session stickiness
  enable_stickiness: true

  # Fallback when detection fails
  fallback_language: "en"

  # Heuristic vote adjustments
  heuristic_nudges:
    en_boost: 0.2
    es_penalty: 0.1
    script_boost: 0.2

  # Mixed-language detection threshold
  mixed_language_threshold: 0.3

  # Chat history prior
  use_chat_history_prior: true
  chat_history_prior_weight: 0.3
  chat_history_messages_count: 5

  # RAG retrieval boosting
  retrieval_match_boost: 0.1
  retrieval_mismatch_penalty: 0.05
  retrieval_min_confidence: 0.7
```

## Extending the System

### Adding a New Script

Add to `SCRIPT_PATTERNS` in `language_detection.py`:

```python
SCRIPT_PATTERNS.append(
    ('xx', re.compile(r'[\uXXXX-\uXXXX]'), 0.95)
)
```

### Adding a New Latin Language

Add to `LATIN_WORD_PATTERNS`:

```python
LATIN_WORD_PATTERNS.append(
    ('xx', [
        re.compile(r'unique_pattern_1', re.IGNORECASE),
        re.compile(r'unique_pattern_2', re.IGNORECASE),
    ], 0.85)
)
```

### Adding a New Backend

1. Add availability check:
```python
try:
    import new_backend
    NEW_BACKEND_AVAILABLE = True
except ImportError:
    NEW_BACKEND_AVAILABLE = False
```

2. Add detection method:
```python
def _detect_new_backend(self, text: str) -> Optional[DetectionResult]:
    if not NEW_BACKEND_AVAILABLE:
        return None
    # ... detection logic ...
    return DetectionResult(
        language=lang,
        confidence=normalized_confidence,  # Must be 0-1
        method='new_backend'
    )
```

3. Register in `_setup_backends()`:
```python
if 'new_backend' in enabled_backends and NEW_BACKEND_AVAILABLE:
    self.backends.append(('new_backend', weight, self._detect_new_backend))
```

### Language Code Normalization

Add mappings to `LANGUAGE_CODE_MAP`:

```python
LANGUAGE_CODE_MAP.update({
    'xxx': 'xx',  # 3-letter to 2-letter
    'xx-variant': 'xx',  # Variant to base
})
```

## Troubleshooting

### Detection Accuracy Issues

1. **Enable verbose logging:**
   ```yaml
   general:
     verbose: true
   ```

2. **Check detection metadata:**
   ```python
   context.language_detection_meta = {
       'confidence': 0.85,
       'method': 'ensemble_voting',
       'raw_results': {...}
   }
   ```

3. **Verify backends are loaded:**
   ```
   INFO: Initialized 3 language detection backends: ['langdetect', 'langid', 'pycld2']
   ```

### Performance Issues

1. **Check backend timeouts:**
   Backends have 500ms individual timeouts. If consistently timing out, check system load.

2. **Verify regex compilation:**
   Patterns should compile once at module load. If seeing re-compilation, check imports.

### Stickiness Not Working

1. **Verify Redis connection:**
   Check `redis_client` is registered in service container.

2. **Verify session_id is present:**
   Stickiness requires `context.session_id` to be set.

## Performance Metrics

| Metric | Value |
|--------|-------|
| Average detection time | 50-150ms |
| Script detection (fast path) | <5ms |
| Backend timeout | 500ms each |
| Memory overhead | ~50KB (compiled patterns) |
| Redis storage per session | ~100 bytes |
