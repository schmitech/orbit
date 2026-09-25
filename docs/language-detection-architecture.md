# Language Detection Architecture

This document describes the technical architecture of Orbit's language detection system, which ensures that user prompts are correctly identified so LLMs respond in the appropriate language.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Detection Pipeline](#detection-pipeline)
4. [Backend Ensemble](#backend-ensemble)
5. [Script Detection](#script-detection)
6. [Removed Heuristics](#removed-heuristics)
7. [Language Stickiness](#language-stickiness)
8. [Mixed-Language Spans](#mixed-language-spans)
9. [RAG Integration](#rag-integration)
10. [Configuration Reference](#configuration-reference)
11. [Extending the System](#extending-the-system)

## Overview

The language detection system is a pipeline step that runs before LLM inference to detect the language of user messages. This enables:

1. **Appropriate LLM responses** - LLM responds in the same language as the user
2. **Language-aware RAG** - Retrieved documents can be boosted/filtered by language
3. **Stable detection** - Prevents language flapping across conversation turns
4. **Mixed-language awareness** - Reports the spans of a message written in a secondary language

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
│                      │  └────────────┘ └────────────┘ └──────────┘ │  │
│                      │         │              │             │       │  │
│                      │         └──────────────┴─────────────┘       │  │
│                      │                        │                      │  │
│                      │                        ▼                      │  │
│                      │     Full candidate lists (BackendResult)      │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │     Calibrated Log-Linear Pool                │  │
│                      │  • Fit for the backends that answered         │  │
│                      │  • Script candidates restrict the winner      │  │
│                      └──────────────────────────────────────────────┘  │
│                                        │                                │
│                                        ▼                                │
│                      ┌──────────────────────────────────────────────┐  │
│                      │         Threshold & Conversation Prior        │  │
│                      │  • Accept if pooled prob. >= fitted threshold │  │
│                      │  • Else conversation prior, else abstain      │  │
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

Only a candidate can win. Pooled probability outside the candidate set stays
in the total, so dropping it cannot inflate confidence. If distinctive letters
leave a single candidate that the backends disagree with, its probability
stays low and detection abstains.

### 3. Word Pattern Detection

For Latin-script languages, keyword patterns provide disambiguation:

```python
# Example: Spanish detection
patterns = ['¿', '¡', r'\baño\b', r'\bestá\b', r'\bqué\b', r'\bgracias\b']

# Example: Vietnamese detection (Latin + diacritics)
patterns = [r'[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]']
```

## Backend Ensemble

Three statistical backends run in parallel. Each adapter returns a
`BackendResult` with its full candidate list, normalized language codes, the
scale its scores are on, its package version and raw evidence:

| Backend | Candidates | Scale | Raw evidence |
|---|---|---|---|
| langdetect | every language its sampling assigned a probability | `probability` | — |
| langid | top 10 of `rank()` | `softmax_top_k`: softmaxed over those 10 only, not a global probability | log-probabilities |
| pycld2 | each detail except `un` | `text_percent`: share of the text, not a confidence | details, text bytes, reliability flag |

A backend that answers only `unknown` (e.g. pycld2 `un`) contributes nothing.

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

### Calibrated Pooling

`pool_backend_distributions()` combines the candidate lists with a weighted
log-linear pool:

```python
# Each backend b: renormalize its scores, then mix in a floor so a language
# it did not list is unlikely rather than impossible.
q_b(l) = (1 - floor) * score_b(l) / sum(score_b) + floor / N
# Pool over a nominal universe of N languages.
log P(l) = sum_b w_b * log q_b(l)   # then normalized over all N languages
```

Languages that no backend listed share the remaining probability equally, so
backends agreeing on a weak answer cannot renormalize to 1.0.

There is one calibration (weights `w_b`, floor, acceptance threshold) for
each non-empty set of backends. The pool uses the one for exactly the backends
that answered, so a deployment with fewer backends, or a request where one
times out, is not weighted and thresholded as if all three were present.
Backends without a calibration are ignored, and `raw_results.pool_backends`
shows which set was used. The calibrations are fitted on the benchmark tune
split by `server/tests/language_eval/calibrate.py`. They are frozen in
`server/inference/pipeline/steps/language_detection_calibration.json`, which
also records the corpus hash and backend versions. The calibration version is
exposed as `language_detection_meta.detector_version`.

The result:
- **Accepted** (`method: calibrated_ensemble`, `calibrated: true`) when the
  best candidate's pooled probability is at least that set's
  `accept_confidence` (0.70 with all three backends).
  `confidence` is that probability.
- **Otherwise**, the conversation prior's language, if the current message's
  candidates include it (see [Conversation Prior](#language-stickiness)).
- **Otherwise**, abstains with reason `below_threshold`. It never substitutes
  a default language.

Detection metadata also carries:
- `accepted`: the current message decided the language;
- `agreement`: the share of backends whose top candidate won;
- `margin`: the gap to the next pooled candidate.

Rule paths (unique script, French phrases, Vietnamese diacritics) keep a fixed
0.95 and are marked `calibrated: false`.

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

## Removed Heuristics

Phase 3 removed these heuristics, because none of them improved the calibrated
pool on the benchmark (`docs/roadmap/language-detection-accuracy.md`):
- the ASCII-English early return and below-threshold English fallback
  (`prefer_english_for_ascii`);
- the `en_boost`/`es_penalty` vote nudges (`heuristic_nudges`);
- `threshold_fallback`, which accepted a below-threshold result when a Latin
  word pattern matched.

The ASCII-English rule added more high-confidence errors (Dutch and Italian
text called English) than it fixed. A known cost: English search queries that
all backends read as another language, such as "Car crime statistics
Vancouver" → `fr`, are no longer overridden.

## Language Stickiness

### Problem
Users typing in one language may occasionally produce ambiguous short messages
(e.g., "OK", "Yes"). Without a conversation prior, these abstain (`unknown`)
rather than resetting to English.

### Conversation Prior

One policy, one prior per request:

1. **The current message decides first.** A fast-path or accepted ensemble
   result is used as is; the prior never changes
   it, so a clear language switch is followed immediately.
2. **The prior is consulted only when the message cannot decide:** no letters
   at all (emoji, numbers, links), fewer than `min_letters` letters, or a
   pooled probability below `accept_confidence`. Below threshold, the prior's
   language must also be among the current message's candidates.
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
                          "method": "calibrated_ensemble", "abstained": False}}
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
`threshold_fallback` (a pre-Phase-3 method still found in stored history), and
has confidence ≥ `prior_min_confidence` (0.7). On
the tune split, raising this to 0.8 dropped 9 correct detections to remove one
error; the remaining errors all had confidence 0.9–1.0.

If the chat-history service or the cache is unavailable or fails, that source
yields no prior and detection proceeds on the current message alone.

## Mixed-Language Spans

A message is mixed when parts of it are detected, on their own, in a language
other than the primary one. Backend disagreement on the whole message is
uncertainty, not mixing, and no longer counts.

### Segmentation

`span_segments()` splits the original message into candidate spans:
- **Masked out:** code blocks, inline code, URLs and email addresses. They
  also act as boundaries.
- **Cuts:** clause punctuation (`, ; : « » " ( ) ? !`, their CJK forms, and
  a sentence-ending `.`), and every change of letter script. Kana and Han
  count as one script.
- **Trimmed:** each piece runs from its first letter to its last.
- **Offsets:** code-point indices into the original message, so emoji and
  supplementary-plane characters do not shift them.

### Detection

Only when the primary detection is accepted, each segment is detected with
the same calibrated detector. A segment becomes a span if:
- it has at least `min_span_letters` letters and `min_span_coverage` of the
  message's letters;
- it is not a capitalized name in Latin script (every word capitalized, e.g.
  `Blue Bottle Coffee`);
- the detector accepts it on its own text.

Consecutive spans of the same language are merged, but never across masked
code, URLs or email addresses, so a span never contains them. A message that
forms a
single segment has no spans, so a borrowed word or name inside a clause
(`The café downstairs`, `Das Meeting`, `Montréal`) never makes it mixed.

### Metadata and behavior

For "Preciso do relatório final até sexta-feira, please don't forget":

```python
context.language_detection_meta = {
    'spans': [{'start': 0, 'end': 42, 'language': 'pt', 'confidence': 0.9932, 'letters': 36},
              {'start': 44, 'end': 63, 'language': 'en', 'confidence': 0.9928, 'letters': 16}],
    'secondary_languages': ['en'],      # most letters first
    'mixed_language_detected': True,
    'secondary_language': 'en',         # the first secondary language
    'secondary_confidence': 0.9928,     # its lowest span confidence
    ...
}
```

`detected_language` stays the calibrated decision for the whole message, and
the reply follows it. Secondary languages are metadata only: the prompt never
asks for a bilingual reply, and retrieval does not use them.

Span detection runs the backends once more per qualifying segment, so a mixed
or multi-clause message costs a few extra milliseconds. On the benchmark, p95
latency rose from about 11 ms to 15 ms.

## RAG Integration

### Language-Aware Document Boosting

After retrieval, documents are re-scored based on language match. This
applies only to an accepted detection (`language_detection_meta.accepted`)
with confidence ≥ `retrieval_min_confidence`, so abstentions and
conversation-prior results never re-rank documents:

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
retrieval_min_confidence: 0.7    # Min calibrated confidence of an accepted detection
```

On the tune split, accepted detections at ≥ 0.7 are 96% correct.

### Prompt Instruction

`PromptBuilder` names the language ("The user is writing in French…") only
for an accepted detection at confidence ≥ 0.9. On the tune split those are
97% correct, against 84% below 0.9. Other detections, including
conversation-prior results, get the softer "match the language of the user's
message" instruction. Abstentions get the `ambiguous_response_language`
instruction.

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

  # Pooling weights and the acceptance threshold are not configured here:
  # they are fitted on the benchmark and frozen in
  # server/inference/pipeline/steps/language_detection_calibration.json.

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

  # Mixed-language spans (see Mixed-Language Spans)
  mixed_language:
    min_span_letters: 5
    min_span_coverage: 0.1

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

2. Add a detection method that returns every candidate:
```python
def _detect_new_backend(self, text: str) -> Optional[BackendResult]:
    if not NEW_BACKEND_AVAILABLE:
        return None
    # ... detection logic ...
    return BackendResult(
        backend='new_backend',
        candidates=candidate_scores(pairs),  # [(code, score), ...]; codes normalized here
        scale='probability',                  # say what the scores mean
        version=_package_version('new-backend'),
    )
```

3. Register in `_setup_backends()`:
```python
if 'new_backend' in enabled_backends and NEW_BACKEND_AVAILABLE:
    self.backends.append(('new_backend', self._detect_new_backend))
```

4. Add it to `BACKENDS` in `server/tests/language_eval/calibrate.py` and
   rerun the calibration, which fits every backend set that includes it. A
   backend without a calibration is ignored by the pool.

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
       'confidence': 0.97,
       'method': 'calibrated_ensemble',
       'accepted': True,
       'calibrated': True,
       'agreement': 1.0,
       'margin': 0.95,
       'detector_version': 'v2',
       'raw_results': {'pooled': {...}, 'residual': ..., 'langid': {...}, ...}
   }
   ```

3. **Verify backends are loaded:**
   ```
   INFO: Initialized 3 language detection backends: ['langdetect', 'langid', 'pycld2'] (calibration v2)
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
