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
│                      │  • Unicode script evidence (unique/shared)   │  │
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
│                      │  • Apply heuristic nudges                     │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │         Threshold & Stickiness Logic          │  │
│                      │  • Check min_confidence & min_margin          │  │
│                      │  • Apply conversation prior if ambiguous      │  │
│                      │  • Apply ASCII bias if applicable             │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │              Session Persistence              │  │
│                      │  • Update context.detected_language           │  │
│                      │  • Stickiness: Redis (lang_detect:{safe_id}) │  │
│                      │  • Chat history: stored on the user message   │  │
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

### 2. Script Evidence and Short Text

The cleaned text is NFC-normalized. Evidence is then counted as Unicode letters
and combining marks, using the `regex` package's `\p{Script=...}` properties.
Digits, punctuation, emoji and other Common/Inherited characters are not
evidence. All scripts are counted before any decision, so the dominant script
does not depend on pattern order.

| Outcome | Rule |
|---|---|
| No letters (emoji, numbers, URLs, code only) | Uses a conversation prior if one is available, at a confidence below `retrieval_min_confidence`. Otherwise abstains with reason `no_letters`. Backends are not called. |
| Single-language script | Selects its language (`script_detection`, 0.95) when it has at least `script_fast_path.min_letters` letters and covers at least `script_fast_path.min_coverage` of them. Applies to Hangul, Thai, Greek, Georgian, Armenian, Tamil, Telugu and similar scripts, and to Japanese when kana is present. |
| Shared script | Narrows the candidates the backends may choose from, but only when it covers at least `min_coverage` of the letters. Cyrillic, Arabic, Devanagari, Bengali, Hebrew, Ethiopic, and Han without kana (`zh`/`ja`) are shared. |
| Fewer than `min_letters` letters | Uses a conversation prior (stickiness or chat history) if one is available, at a confidence below `retrieval_min_confidence`. Otherwise abstains with reason `low_evidence`. |

Arabic-script letters narrow the candidates further:
- The Persian letters پ چ ژ گ rule out Arabic but do not select Persian, because
  Urdu and Pashto use them too.
- Urdu-only letters narrow the candidates to `ur`.
- Pashto-only letters narrow the candidates to `ps`.

If no backend votes for a candidate, the result is `unknown`. The exception is
when distinctive letters narrowed the set to a single language: that language
is returned as `script_letters` at 0.75.

Backend votes outside the candidate set still count toward the vote total, so
dropping them cannot inflate confidence.

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

# Final confidence:
total_votes = sum(language_votes.values())
best_confidence = best_score / total_votes
second_confidence = second_score / total_votes
margin = best_confidence - second_confidence
```

`total_votes` is the sum of all weighted language scores after backend weighting
and heuristic vote nudges. The conversation prior does not add votes. This is not the same as the sum
of configured backend weights. The result is a vote share, not a calibrated
probability (see `docs/roadmap/language-detection-accuracy.md`, Phase 3). The
former `script_boost` nudge has been removed: it only ever applied to Russian,
as an artifact of script-pattern order.

When confidence or margin is below threshold, the detector tries these in order:
1. the conversation prior's language, if the current votes include it (see
   [Conversation Prior](#language-stickiness));
2. the English ASCII heuristic, when English markers are present;
3. the best-voted language, when a non-English Latin word pattern matched.

Otherwise it abstains with reason `below_threshold`. It never substitutes a
default language.

## Abstention and the Response Language

`unknown` is a first-class outcome. When detection abstains:
- `method` is `abstained`, `language_detection_meta.abstained` is `true`, and
  `raw_results.reason` says why;
- nothing is stored as evidence for later turns, neither in the session cache
  nor in `last_detected_language`;
- retrieval applies no language boost, and `unknown` is not passed to
  retrievers as a language filter;
- the prompt asks the model to reply in the user's language, and to use
  `ambiguous_response_language` only if the language is unclear. It never
  states that English was detected.

Results that come from conversation state (`sticky_previous`,
`chat_history_prior`) are not stored as new evidence either.

Language codes are normalized to a base ISO 639 code:
- BCP-47 subtags are dropped (`zh-Hant` → `zh`, `pt-BR` → `pt`), because
  prompting and retrieval key only on the base language;
- legacy codes are mapped (`iw` → `he`, `in` → `id`, `fil` → `tl`, `nb`/`nn` →
  `no`);
- 3-letter codes are validated with `pycountry`;
- malformed or unsupported codes become `unknown` instead of being truncated.

## Heuristic Biasing

### ASCII Bias (English preference)

For short, high-ASCII text starting with English interrogatives:

```python
if ascii_ratio > 0.98 and len(text) <= 120:
    if starts_with_english_question and no_spanish_markers:
        return English with 0.9 confidence
```

This prevents "How do I export code?" from being classified as Portuguese.

The same ASCII bias also applies to short English search-style noun phrases when they
contain common English content markers and no stronger non-English signal:

```python
if ascii_ratio > 0.98 and len(text) <= 120:
    if looks_like_english_query and no_non_english_latin_patterns:
        return English with 0.9 confidence
```

This prevents queries like "Car crime statistics Vancouver" from being classified as French.

### Configurable Nudges

```yaml
heuristic_nudges:
  en_boost: 0.2       # Added to English votes in ASCII text
  es_penalty: 0.1     # Subtracted from Spanish in pure ASCII
```

## Language Stickiness

### Problem
Users typing in one language may occasionally produce ambiguous short messages
(e.g., "OK", "Yes"). Without a conversation prior, these abstain (`unknown`)
rather than resetting to English.

### Conversation Prior

One policy, one prior per request:

1. **The current message decides first.** A fast-path, ensemble or heuristic
   result that passes the thresholds is used as is; the prior never changes
   it, so a clear language switch is followed immediately.
2. **The prior is consulted only when the message cannot decide:** no letters
   at all (emoji, numbers, links), fewer than `min_letters` letters, or below `min_confidence`/`min_margin`. Below
   threshold, the prior's language must also be among the current votes.
3. **The prior decides only with a majority:** its top language must hold at
   least half the prior's weight. The result's confidence is at most 0.6
   (`chat_history_prior` or `sticky_previous`), below
   `retrieval_min_confidence`, so a prior picks the reply language but never
   re-ranks documents.

### Sources

The prior comes from one source, never both, because both describe the same
earlier turns:

- **Chat history** (`use_chat_history_prior`, default on). After each turn,
  the detection is stored on the **user** message's metadata:

  ```python
  {"language_detection": {"language": "fr", "confidence": 0.93,
                          "method": "ensemble_voting", "abstained": False}}
  ```

  Assistant messages carry no language evidence and are skipped. The
  `chat_history_messages_count` most recent messages are read; each user
  message contributes its confidence, halved for every newer user message.
  This works across workers because it lives in the chat-history database.
  Requires `chat_history.store_metadata: true`.
- **Session cache** (`enable_stickiness`, default off). The last trusted
  detection, in Redis under `lang_detect:{safe_id}`. It is read only when chat
  history yields nothing, for example for adapters that do not store history.
  The entry expires `stickiness_ttl_seconds` after the last trusted detection.
  That is an idle window, unrelated to `auth.session_duration_hours`.

### What counts as evidence

A stored detection informs later turns only if it is not an abstention, not
itself prior-derived (`chat_history_prior`, `sticky_previous`), not a
`threshold_fallback`, and has confidence ≥ `prior_min_confidence` (0.7). On
the tune split, raising this to 0.8 dropped 9 correct detections to remove one
error; the remaining errors all had confidence 0.9–1.0.

If the chat-history service or the cache is unavailable or fails, that source
yields no prior and detection proceeds on the current message alone.

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

The canonical language detection settings live in `config/config.yaml` under
the `language_detection` key.

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

  # Session cache as a fallback conversation-prior source
  enable_stickiness: false

  # Reply language when detection abstains; never recorded as a detected
  # language. Replaces `fallback_language`, which is still read if present.
  ambiguous_response_language: "en"

  # Evidence thresholds (chosen on the benchmark tune split)
  min_letters: 5           # Fewer letters: conversation prior or abstain
  script_fast_path:
    min_letters: 1
    min_coverage: 0.8

  # Backend timeout
  backend_timeout: 10.0

  # Heuristic vote adjustments
  heuristic_nudges:
    en_boost: 0.2
    es_penalty: 0.1

  # Mixed-language detection threshold
  mixed_language_threshold: 0.3

  # Conversation prior (see Language Stickiness)
  use_chat_history_prior: true
  chat_history_messages_count: 5
  prior_min_confidence: 0.7
  stickiness_ttl_seconds: 3600

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

1. **Verify session_id is present:**
   The conversation prior requires `context.session_id` to be set.

2. **Verify chat history stores metadata:**
   The chat-history source needs `chat_history.store_metadata: true` and an
   adapter that stores history. Otherwise enable `enable_stickiness` and check
   that the cache service is available.

3. **Check the stored evidence:**
   Only detections with confidence ≥ `prior_min_confidence` count; abstentions
   and prior-derived results never do.

## Performance Metrics

| Metric | Value |
|--------|-------|
| Average detection time | 50-150ms |
| Script detection (fast path) | <5ms |
| Backend timeout | 500ms each |
| Memory overhead | ~50KB (compiled patterns) |
| Redis storage per session | ~100 bytes |
