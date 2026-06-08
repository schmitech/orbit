# Language Detection — Remaining Open Items

These items were not addressed in the initial implementation pass. All are from the secondary/follow-up category — none block correctness.

---

## 1. `TestMixedLanguageMetadataExposure` duplicates production logic

**File:** `server/tests/test_services/test_language_detection.py`, lines 856–974

All three tests in this class manually re-implement the same if/else block from `process()` instead of calling it. A bug in the real code path is invisible to them.

**Fix:** Replace with calls to the actual method:

```python
@pytest.mark.asyncio
async def test_mixed_language_metadata_at_top_level(self, detector):
    context = create_context("Hello amigo, como estas?")
    await detector.process(context)
    assert context.language_detection_meta['mixed_language_detected'] is True
    assert context.language_detection_meta['secondary_language'] is not None

@pytest.mark.asyncio
async def test_non_mixed_language_sets_flag_false(self, detector):
    context = create_context("Hello world, how are you today?")
    await detector.process(context)
    assert context.language_detection_meta['mixed_language_detected'] is False
    assert context.language_detection_meta['secondary_language'] is None
    assert context.language_detection_meta['secondary_confidence'] is None

@pytest.mark.asyncio
async def test_stale_secondary_language_cleared(self, detector):
    context = create_context("Hello world, how are you today?")
    context.language_detection_meta = {
        'mixed_language_detected': True,
        'secondary_language': 'es',
        'secondary_confidence': 0.35
    }
    await detector.process(context)
    assert context.language_detection_meta['mixed_language_detected'] is False
    assert context.language_detection_meta['secondary_language'] is None
    assert context.language_detection_meta['secondary_confidence'] is None
```

---

## 2. Accuracy floor is too weak

**File:** `server/tests/test_services/test_language_detection.py`, line 761

`assert accuracy >= 0.66` allows one miss per language (with only 3 samples) to pass silently. A systematic regression goes undetected as long as one sample is correct.

**Fix:** Split the floor by script type, or add more samples per language so the 66% floor is meaningful:

```python
UNAMBIGUOUS_SCRIPT_LANGS = {'zh', 'ja', 'ko', 'ar', 'hi', 'th', 'ru'}

for lang, accuracy in results.items():
    floor = 1.0 if lang in UNAMBIGUOUS_SCRIPT_LANGS else 0.66
    assert accuracy >= floor, f"Language {lang} has only {accuracy*100:.0f}% accuracy"
```

---

## 3. No backend availability guard

**File:** `server/tests/test_services/test_language_detection.py`

If none of `langdetect`, `langid`, or `pycld2` are installed, all `_detect_language_ensemble_async` calls return `method='all_backends_failed', language='en'`. English tests pass vacuously; non-English tests fail with a misleading error that points to the wrong root cause.

**Fix:** Add a session-scoped autouse fixture near the top of the file:

```python
from inference.pipeline.steps.language_detection import (
    LANGDETECT_AVAILABLE, LANGID_AVAILABLE, PYCLD2_AVAILABLE
)

@pytest.fixture(scope="session", autouse=True)
def require_any_backend():
    if not any([LANGDETECT_AVAILABLE, LANGID_AVAILABLE, PYCLD2_AVAILABLE]):
        pytest.skip("No language detection backend installed — install langdetect, langid, or pycld2")
```

---

## 4. `TestRetrievalBoostIntegration` threshold too low

**File:** `server/tests/test_services/test_language_detection.py`, line 1067

The test asserts `result.confidence >= 0.6` but the actual retrieval boost activation threshold is `min_confidence = 0.7`. The test cannot verify that the boost actually activates.

**Fix:**
```python
assert result.confidence >= 0.7, \
    f"Clear English text '{text[:30]}...' got confidence {result.confidence}, expected >= 0.7"
```

---

## 5. Redis key uses unvalidated session_id

**File:** `server/inference/pipeline/steps/language_detection.py`, lines 585 and 608

```python
key = f"lang_detect:{context.session_id}"
```

If `session_id` contains `:`, `*`, or `[`, it can cause key-namespace collisions or unexpected behavior with Redis SCAN patterns.

**Fix:** Either document that session IDs are pre-validated upstream (and add an assertion), or encode before embedding:

```python
import urllib.parse
safe_id = urllib.parse.quote(str(context.session_id), safe='')
key = f"lang_detect:{safe_id}"
```

---

## 6. Architecture doc is stale

**File:** `docs/language-detection-architecture.md`

Two sections do not match the current code:

**Voting formula (lines 177–181):** Doc describes normalization by `total_weight` (sum of backend weights). Code normalizes by `total_votes` (sum of all weighted scores, including prior boosts and nudge adjustments). Update to:

```python
# Actual formula:
best_confidence = best_score / total_votes   # proportion of all accumulated votes
margin = best_confidence - second_confidence
# Script boost applied after margin is locked:
best_confidence = min(0.95, best_confidence + script_boost * script_coverage)
```

**Redis snippet (lines 249–254):** Doc shows `redis.hset() + redis.expire()`. Code uses `redis_service.store_json(key, data, ttl=3600)`. Update the snippet to match.

---

## 7. Redundant `second_confidence` assignment

**File:** `server/inference/pipeline/steps/language_detection.py`, line 805

`second_confidence` is computed identically at line 789 and again at line 805 (`second_score` and `second_vote_score` are both `sorted_votes[1][1]`). The second assignment is dead code.

**Fix:** Remove lines 803–805 and use the already-computed `second_confidence` directly in the mixed-language check:

```python
# Check for mixed language
if len(sorted_votes) > 1:
    second_language = sorted_votes[1][0]
    if second_confidence >= self.mixed_language_threshold and best_confidence < 0.8:
        raw_results['mixed_language_detected'] = True
        raw_results['secondary_language'] = second_language
        raw_results['secondary_confidence'] = second_confidence
```

---

## 8. Confidence threshold uses post-boost value (minor inconsistency)

**File:** `server/inference/pipeline/steps/language_detection.py`, line 814

`margin` is correctly computed in the pre-boost space, but the sibling check `best_confidence < self.min_confidence` uses the post-boost `best_confidence`. A detection that only crosses `min_confidence` due to the script boost will pass the threshold gate even though the raw ensemble was below the configured minimum.

**Fix:** Use `raw_best_confidence` for the threshold check:

```python
if raw_best_confidence < self.min_confidence or margin < self.min_margin:
    ...
```

`best_confidence` (post-boost) is still the value returned in the `DetectionResult`.
