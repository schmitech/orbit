# Language Detection Accuracy — Implementation Plan

## Summary

Improve ORBIT's language detection accuracy, confidence calibration, and
code-switching behavior without changing all of those dimensions at once.

The work is deliberately ordered so each phase produces a measurable,
reviewable improvement:

1. Establish a representative benchmark and record the current baseline.
2. Fix deterministic correctness problems in script handling, short-text
   handling, language-code normalization, and fallbacks.
3. Make conversation history and stickiness work with trustworthy evidence.
4. Replace top-1 weighted voting with calibrated candidate distributions.
5. Detect mixed-language text from spans rather than backend disagreement.
6. Benchmark modern detector options and adopt one only if it improves the
   agreed metrics.
7. Roll out with observability, compatibility controls, and updated docs.

Primary implementation files:

- `server/inference/pipeline/steps/language_detection.py`
- `server/inference/pipeline/prompt_builder.py`
- `server/inference/pipeline/steps/context_retrieval.py`
- `server/services/chat_handlers/response_processor.py`
- `server/tests/test_services/test_language_detection.py`
- `config/config.yaml`
- `install/default-config/config.yaml`
- `install/dependencies.toml`
- `docs/language-detection-architecture.md`

## Current-state problems

### Script detection returns a language too early

`_detect_by_script()` returns on the first matching Unicode range, and the
ensemble accepts most script results immediately at confidence `0.95`. This
incorrectly treats shared writing systems as languages:

- Devanagari can be Hindi, Marathi, Nepali, or another language.
- Arabic script can be Arabic, Urdu, Persian, Pashto, or another language.
- Cyrillic can be Russian, Ukrainian, Bulgarian, Serbian, and others.
- Bengali script can represent Bengali or Assamese.
- Hebrew script can represent Hebrew or Yiddish.
- Han-only text is not necessarily Chinese; Japanese text may contain only
  kanji in short labels or names.

A single matching character is currently enough, so mixed-script prompts are
also decided by pattern order instead of dominant evidence.

### Ensemble confidence is overconfident

Each backend contributes only its top result. Final confidence is the winning
top-1 vote divided by the sum of all top-1 votes. If every backend weakly picks
the same language, the result can still become `1.0`; alternative probability
mass is discarded. The result is therefore not a posterior probability even
though the code and architecture document currently describe it as one.

The three backend confidence values are also not directly comparable:

- `langdetect` exposes its model probabilities.
- `langid` is softmaxed over only its top five results.
- `pycld2` returns a percentage plus a separate reliability flag.

### Mixed-language detection measures disagreement

The current implementation marks a prompt as mixed when the second backend
vote is sufficiently large. Backend disagreement is uncertainty, not evidence
that two languages occupy different spans of the input. Conversely, backends
can agree on the dominant language of genuinely mixed text and miss the
secondary language entirely.

### Chat-history prior is not persisted consistently

The prior reader looks for `detected_language` at the message top level or in
message metadata. The detection step writes `last_detected_language` to the
processing context, while `ResponseProcessor` does not add either field to
stored chat metadata. The configured `use_chat_history_prior: true` therefore
appears to have no usable persisted evidence in normal chat history.

### English conflates detection with fallback policy

Ambiguous inputs frequently become detected English because `fallback_language`
is also used as the detection result. This turns an operational response
default into language evidence and can affect strict prompt instructions,
retrieval re-ranking, analytics, and future conversation priors.

The asymmetric ASCII heuristic also favors English over languages commonly
written without diacritics.

### Short input and normalization lose valid information

Text shorter than three characters bypasses statistical detection unless a
script heuristic exceeds `0.9`. This mishandles valid messages such as `sí`,
`да`, and `ça` when no usable conversation prior is available.

Unknown language codes are truncated to two characters. For example, `fil`
would become `fi`, conflating Filipino and Finnish. `pycountry` is installed
and imported but is not used by the normalization function.

### Existing tests are optimistic

The accuracy fixture mostly contains longer grammatical sentences with
distinctive markers. It does not provide adequate coverage for shared scripts,
ASCII-only non-English prompts, names, transliteration, noisy chat text,
code-switching, abstention, or confidence calibration. Its mock configuration
also enables stickiness while the canonical configuration disables it.

## Decisions that apply to every phase

- Treat `unknown`/ambiguous as a first-class detection outcome. Keep response
  fallback language separate from detected language.
- Prefer abstaining over emitting a confidently wrong language.
- Use Unicode letter counts and script coverage rather than raw string length
  and raw ASCII character ratios wherever possible.
- A script may narrow the candidate set. It may select a language only when
  the mapping is unambiguous and sufficient evidence is present.
- Do not hand-tune backend weights against individual regressions. Derive
  thresholds, weights, and calibration from a held-out benchmark.
- Persist and reuse only sufficiently trustworthy user-language evidence.
- Mirror user-facing configuration changes in both `config/config.yaml` and
  `install/default-config/config.yaml`.
- Preserve raw detector evidence in debug metadata, but do not expose user
  content or unbounded cardinality in production metrics.

## Phase 0 — Benchmark and baseline

Do this before changing production behavior. Later phases must report their
effect against the same frozen test split.

### Tasks

- [x] Add a versioned language-detection benchmark dataset under an appropriate
      test fixture directory. Each record should contain text, expected primary
      language, optional secondary languages/spans, source category, and whether
      abstention is acceptable.
- [x] Keep benchmark data license-compatible and record provenance. Use
      synthetic or internally owned prompts for product-specific examples.
- [x] Stratify cases by:
  - language and script;
  - 1–2 characters, single word, short chat prompt, and long text;
  - ASCII-only versus diacritic-bearing Latin text;
  - shared scripts such as Cyrillic, Arabic, Devanagari, and Han;
  - URLs, email, source code, emoji, numbers, product names, and proper nouns;
  - transliteration and romanized languages;
  - unambiguous single-language, ambiguous, unknown, and mixed-language text;
  - conversation-follow-up cases such as `OK`, `yes`, `non`, and `sí`.
- [x] Split cases into a tuning set and a held-out evaluation set. Never tune
      weights or thresholds against the held-out set.
- [x] Add a benchmark runner that can evaluate one backend or the full pipeline
      and emit machine-readable results.
- [x] Record at least:
  - top-1 accuracy and macro-averaged F1;
  - accuracy by language, script, and input-length bucket;
  - confusion matrices for related languages;
  - abstention coverage and accuracy among accepted predictions;
  - top-two margin distribution;
  - confidence calibration, including Brier score or expected calibration
    error;
  - mixed-language span precision/recall where span labels exist;
  - p50/p95 latency and process memory.
- [x] Capture the existing implementation's baseline results and dependency
      versions in this document or a checked-in benchmark report.

### Gate

- The benchmark runs deterministically in CI or in a documented optional test
  job, and baseline results are recorded before Phase 1 begins.

**Status: met.** The repository has no CI workflow, so the benchmark is a
documented optional job (`server/tests/language_eval/README.md`). Two runs
produce identical predictions, and `test_pipeline_is_deterministic` enforces
this.

### Phase 0 baseline (benchmark v1)

- Corpus: `server/tests/language_eval/data/benchmark_v1.jsonl`
  - 334 synthetic records covering 55 languages and 14 categories;
  - 168 tune / 166 held-out;
  - SHA-256 `658be6f1…`.
- Full report: `server/tests/language_eval/reports/phase0_baseline_v1.json`.
  It holds every metric listed above, per split and mode, plus per-record
  pipeline predictions.
- Environment: Python 3.12.11 on macOS, langdetect 1.0.9, langid 1.1.6,
  pycld2 0.42, pycountry 26.2.16, regex 2026.9.3.
- Configuration: the canonical `config/config.yaml` `language_detection`
  section.

Held-out split:

| Mode | Top-1 acc | Macro F1 | Acceptable | Coverage | Selective acc | High-conf errors (≥0.9) | Brier | ECE | p50 / p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| langdetect | 0.697 | 0.631 | 115/166 | 0.958 | 0.679 | 31 | 0.262 | 0.271 | 3.75 / 17.53 |
| langid | 0.742 | 0.731 | 120/166 | 0.988 | 0.720 | 13 | 0.162 | 0.126 | 1.28 / 1.97 |
| pycld2 | 0.690 | 0.800 | 139/166 | 0.669 | 0.964 | 4 | 0.038 | 0.014 | 0.02 / 0.07 |
| **pipeline** | 0.716 | 0.715 | 112/166 | 1.000 | 0.675 | 22 | 0.205 | 0.180 | 2.85 / 9.91 |
| pipeline+context | 0.723 | 0.719 | 113/166 | 1.000 | 0.681 | 22 | 0.202 | 0.186 | 2.80 / 10.52 |

Cold start: langdetect 406 ms, langid 1438 ms, pycld2 < 1 ms. Process peak
RSS after loading all backends was 351 MB. Latency and memory depend on the
machine and are not gated.

What the baseline confirms about the current-state problems:

- **The detector never abstains.** Coverage is 1.000 and all 9 held-out
  `no_language` records get a language. Emoji, numbers, URLs and `OK` become
  `en` through `length_fallback`/`threshold_fallback`, and `unknown→en` is the
  most common error.
- **Script evidence is conflated with language.**
  - Held-out `shared_script` records are acceptable in 31/50 cases, against
    81/116 for all other records.
  - Devanagari: `ne→hi` 3/3 and `mr→hi` 2/2.
  - Arabic script: Urdu and Pashto become `ar`/`fa`.
  - Cyrillic: Kazakh becomes `ru`.
  - Other shared scripts: Yiddish becomes `he` and Assamese becomes `bn`.
- **ASCII-only text favors English.** ASCII-only records are acceptable in
  33/62 cases, against 36/37 for Latin text with diacritics. `fr→en` is the
  second most common error.
- **Short text is unreliable.** Single words are acceptable in 9/24 held-out
  cases, and backends produce answers like `merci→es` and `yes→tr`.
- **Confidence is overconfident.**
  - 113 of 166 held-out predictions claim confidence ≥ 0.9, but only 80.5% of
    those are correct.
  - The pipeline's high-confidence error count (22) is five times pycld2's (4).
  - ECE is 0.180 for the pipeline, against 0.014 for pycld2 alone.
- **Mixed-language detection never fires.** Flag recall is 0/8 on held-out
  mixed prompts. The flag is correctly absent on monolingual text, but only
  because it never fires at all.
- **The conversation prior barely helps even when evidence exists.** Adding
  `context_lang` improves only one held-out record. `sí`, `да`, `ja` and `OK`
  still hit the `< 3` character fallback before the prior is consulted.
- **Romanized text is unsolved.** All 6 held-out romanized records fail (0/6).

The held-out regression gate (`test_heldout_does_not_regress`) fails if either
of these gets worse:

- selective accuracy, currently 112/166;
- high-confidence errors, currently 22.

Coverage is not gated. Phase 1 is expected to lower it on purpose, and must
report the change.

## Phase 1 — Deterministic correctness fixes

This phase improves rule behavior without replacing the statistical backends
or ensemble algorithm.

### 1.1 Unicode preprocessing

- [x] Normalize detector input with a documented Unicode normalization form.
      Prefer NFC unless benchmark evidence shows that compatibility
      normalization is needed.
- [x] Count Unicode letters separately from whitespace, punctuation, digits,
      emoji, and code when calculating evidence length and script coverage.
- [x] Handle the case where preprocessing removes all meaningful text and
      return `unknown` rather than invoking backends on an empty string.
- [x] Use the already-installed `regex` package's Unicode script properties,
      or an equivalently complete mechanism, instead of incomplete hand-coded
      Basic Multilingual Plane ranges.

### 1.2 Script evidence

- [x] Replace `(language, regex, confidence)` script entries with script
      evidence that maps to one or more candidate languages.
- [x] Require configurable minimum matching letters and minimum script
      coverage before taking a script-only fast path.
- [x] Do not fast-return for shared scripts. Pass their candidate language set
      to the statistical stage.
- [x] Make Japanese detection use kana as strong Japanese evidence while
      treating Han-only text as ambiguous between relevant candidates.
- [x] Make Persian-specific characters positive Persian evidence without
      treating all other Arabic-script text as Arabic.
- [x] Calculate all script evidence before choosing a result so mixed-script
      inputs are not dependent on pattern order.

Suggested configuration:

```yaml
language_detection:
  script_fast_path:
    min_letters: 2
    min_coverage: 0.8
```

Finalize these defaults from benchmark results rather than the illustrative
values above.

### 1.3 Short and ambiguous text

- [x] Remove the unconditional `< 3` character fallback.
- [x] For low-evidence text, return `unknown` or use a trustworthy conversation
      prior. Do not manufacture high confidence.
- [x] Preserve clear unique-script evidence for short text.
- [x] Add tests for meaningful two-character inputs, emoji-only messages,
      punctuation-only messages, numbers, acronyms, and names.

### 1.4 Language-code normalization

- [x] Replace arbitrary first-two-character truncation with an explicit ISO
      639/BCP-47 normalizer.
- [x] Add mappings for legacy and backend-specific codes such as `iw`/`he`,
      `fil`, and Chinese script/region variants.
- [x] Decide and document whether downstream components need only a base
      language or also a normalized full tag. If both are useful, store both.
- [x] Either use `pycountry` for validated conversions or remove the unused
      dependency. Do not use it as a substitute for explicit legacy and
      BCP-47 mappings it cannot resolve reliably.
- [x] Return `unknown` for unsupported or malformed codes.

### 1.5 Separate unknown from response fallback

- [x] Add an explicit outcome for `unknown`/abstained detection.
- [x] Keep a separate configuration value such as
      `ambiguous_response_language: en` for prompt behavior.
- [x] Ensure `unknown` does not trigger language-based retrieval boosting.
- [x] Update `PromptBuilder` so an unknown result asks the model to match the
      user's language, optionally falling back to the configured response
      language, without claiming that English was detected.
- [x] Do not store fallback results as language evidence for later turns.

### Gate

- Shared-script and short-text regression cases pass.
- No single shared-script character can cause a high-confidence language
  result.
- Benchmark accepted-prediction accuracy improves or remains neutral, and any
  reduction in coverage is explicitly reported.
- Existing callers handle `unknown` without errors or incorrect retrieval
  boosts.

**Status: met.**

- **Shared-script and short-text cases:** covered by regression tests in
  `test_language_detection.py` (`TestScriptDetection`,
  `TestUnicodePreprocessing`, `TestShortAndAmbiguousText`).
- **No single shared-script character yields high confidence:** a
  parametrized test checks this, and single-character input now abstains.
- **Callers handle `unknown`:**
  - `test_prompt_builder.py`: prompt instruction;
  - `test_context_retrieval_language_boost.py`: no retrieval boost,
    normalized document tags;
  - `test_adapter_capabilities.py`: `unknown` is not forwarded as a retriever
    filter.
- **Benchmark:** the numbers are below. The regression gate now reads
  `reports/phase1_baseline_v1.json`.

### Phase 1 decisions

- **Thresholds from the tune split only.**
  - Sweep: `min_letters` ∈ {2, 3, 4, 5, 6, 8}, `script_fast_path.min_letters`
    ∈ {1, 2} and `min_coverage` ∈ {0.6, 0.7, 0.8, 0.9}.
  - Selection rule: maximize acceptable outcomes, then break ties by higher
    coverage.
  - `min_letters` 5 and 6 tied at 149/168, so 5 was chosen for its higher
    coverage (0.726 against 0.708).
  - `min_coverage` made no difference between 0.6 and 0.9, so the plan's value
    of 0.8 was kept. A fast-path minimum of 1 letter beat 2, so a single Hangul
    syllable or kana word is enough.
- **Han weighting rejected.** Counting each Han character as two letters made
  no difference on the tune split, so it was not added. Short Han-only
  messages (≤ 4 characters) therefore abstain.
- **Base language only.** Downstream components store and compare the base
  language (`zh-Hant` → `zh`); a full BCP-47 tag is not stored. Prompting and
  retrieval both key on the base language. Preserving Chinese script
  variants is deferred.
- **Filipino.** `fil` maps to `tl`, the code the backends emit, so Filipino and
  Tagalog share one code.
- **`pycountry` is kept.** It validates 3-letter and bibliographic codes. The
  explicit table handles the legacy codes it cannot resolve (`iw`, `in`,
  `ji`).
- **Config keys.**
  - `fallback_language` → `ambiguous_response_language`. `PromptBuilder`
    still reads the old key as a fallback.
  - Added: `min_letters` and `script_fast_path.{min_letters, min_coverage}`.
  - Removed: `heuristic_nudges.script_boost`. It only ever applied to Russian,
    as an artifact of pattern order.
- **Priors on short text.** A prior used for short text (`sticky_previous`,
  `chat_history_prior`) gets confidence at most 0.6. That is below
  `retrieval_min_confidence`, so a prior can choose the reply language but
  never re-rank documents. Prior-derived results are not stored back as new
  evidence.

### Phase 1 results (held-out split, benchmark v1)

| Pipeline | Top-1 acc | Macro F1 | Acceptable | Coverage | Selective acc | High-conf errors | Brier | ECE |
|---|---|---|---|---|---|---|---|---|
| Phase 0 | 0.716 | 0.715 | 112/166 | 1.000 | 0.675 | 22 | 0.205 | 0.180 |
| **Phase 1** | 0.684 | 0.789 | **139/166** | 0.693 | **0.922** | **5** | 0.070 | 0.070 |
| Phase 1 + context | 0.710 | 0.795 | 139/166 | 0.717 | 0.924 | 5 | 0.072 | 0.082 |

Latency is unchanged: p50 2.9 ms and p95 10 ms, the same as Phase 0. Full
report: `server/tests/language_eval/reports/phase1_baseline_v1.json`.

**Coverage fell from 1.000 to 0.693. This is the intended effect.** Phase 0
never abstained. Top-1 accuracy falls because it counts abstentions as wrong.
Selective accuracy and high-confidence errors are the gated metrics.

Where it improved:
- **No-language input:** 8/9 now abstain correctly, up from 0/9.
- **Devanagari:** Nepali and Marathi are now resolved (`ne` 3/3, `mr` 2/2),
  where both used to be read as Hindi.
- **Short text:** 1–2 letters are acceptable in 10/11 cases (from 7/11), and
  single words in 15/24 (from 9/24).
- **Follow-ups:** 8/9, up from 4/9.
- **ASCII-only Latin:** 47/62, up from 33/62.
- **Romanized text:** 5/6, up from 0/6, but only because the detector now
  abstains on it, not because it detects it.

Six held-out records went from acceptable to abstaining:
- `谢谢` and `天气预报`: short Han text;
- `请帮我检查一下这个 pull request 有没有问题`: Han and Latin split, and backends
  disagree;
- `invoice` and `track package`: short ASCII English;
- `سلام، حالت چطوره؟`: Persian letters exclude Arabic, but the Arabic votes
  still count toward the total.

Five high-confidence errors remain:
- `благодаря→ru` and `рахмет→ru`: short Cyrillic, where all backends agree on
  Russian;
- pinyin→`sw`;
- two cases where the English ASCII heuristic overrides Dutch and Italian text
  that contains English words.

The ASCII heuristic and unanimous-but-weak votes are Phase 3 scope.

Known limitations carried forward:
- Single-word names and acronyms with 5 or more letters still reach the
  backends (`ORBIT→pt`, `Montréal→fr`).
- The mixed-language flag still never fires (Phase 4).
- The `pipeline+context` mode shows a prior would help, but production does
  not persist `detected_language` yet (Phase 2).

## Phase 2 — Conversation prior and stickiness

Fix persistence before enabling stickiness in canonical configuration.

### Tasks

- [x] Add detected language, calibrated/raw confidence, method, and abstention
      status to stored **user-message** metadata in the normal chat persistence
      path.
- [x] Do not attach the user's detected language to assistant messages as if it
      were independently detected assistant-language evidence.
- [x] Update `_get_chat_history_language_prior()` to read the canonical stored
      keys and ignore assistant/system messages.
- [x] Weight history by confidence and recency instead of occurrence count
      alone.
- [x] Exclude `unknown`, response fallbacks, backend failures, and low-confidence
      heuristic results from the prior.
- [x] Prevent the prior from overriding strong contradictory evidence in the
      current message.
- [x] Consolidate chat-history prior and Redis stickiness into one documented
      decision policy so they do not independently double-count the same prior.
- [x] Make the cache TTL configurable and align its documented meaning with the
      actual session policy; do not claim that one hour matches a 12-hour
      session duration.
- [x] After tests and benchmark validation, decide whether to enable stickiness
      by default in both canonical configuration files.

### Tests

- [x] Persisted user metadata is readable on the next request.
- [x] Assistant messages are excluded from the prior.
- [x] `OK` follows a strong recent language when stickiness is enabled.
- [x] A clear language switch overrides history immediately.
- [x] Low-confidence and fallback results do not poison later turns.
- [x] Cache unavailable, history unavailable, and multi-worker paths degrade
      safely.

### Gate

- An integration test stores one conversation turn, creates a fresh processing
  context, and demonstrates that the next turn consumes the persisted prior.
- Conversation tests use the same stickiness default as production config, or
  explicitly construct the alternate policy they are testing.

**Status: met.**
- **Gate:** `test_persisted_turn_is_the_prior_for_the_next_request` stores a
  French turn through `ResponseProcessor` into SQLite chat history. A second
  step instance, standing in for another worker, then reads it and answers
  `OK` in French (`chat_history_prior`).
- **Tests:** `server/tests/test_services/test_language_conversation_prior.py`.
  They load the canonical config (`enable_stickiness: false`) and turn
  stickiness on explicitly where they test it. The mock config in
  `test_language_detection.py` now matches the production default.

### Phase 2 decisions

- **Stored shape.** `metadata.language_detection = {language, confidence,
  method, abstained}` on the user message only. Abstentions are stored too, so
  the record is complete; the reader filters them. Raw backend results are
  not stored. Calibrated confidence arrives with Phase 3.
- **One policy.** The current message decides first; the prior is consulted
  only for letterless (emoji, numbers, links), short or below-threshold text, and below threshold only if the
  current votes include the prior's language.
  - The prior's top language needs at least half the weight.
  - Its confidence is at most 0.6, so it never re-ranks documents.
- **Vote nudge removed.** `chat_history_prior_weight` added the prior to the
  backend votes, which counted the same turns a second time and could flip an
  accepted result. The key is no longer read.
- **One source per request.** Chat history comes first; the session cache is
  used only when history yields nothing. The two are never combined.
- **Weighting.** Each user message contributes its confidence × 0.5^age, where
  age counts newer user messages. After one turn in a new language, that
  language leads.
- **Trusted evidence.** A stored result counts only if it:
  - is not an abstention;
  - is not prior-derived;
  - is not a `threshold_fallback`;
  - has confidence ≥ `prior_min_confidence` (0.7).
  
  On the tune split, 0.8 dropped 9 correct detections to remove one error; the
  remaining 5 errors all had confidence 0.9–1.0, so no threshold separates them.
- **TTL.** `stickiness_ttl_seconds` (default 3600) is documented as an idle
  window after the last trusted detection, not as a session duration.
- **Stickiness stays off by default.** The chat-history prior is on by default,
  is shared across workers and is now persisted, so it covers the main path.
  The session cache only adds coverage for adapters that do not store history.
  The benchmark cannot measure it, since no v1 record has a session cache, so
  it stays opt-in.

### Phase 2 results (held-out split, benchmark v1)

- `pipeline`: unchanged, 106/115 accepted correct (0.922), coverage 0.693,
  5 high-confidence errors;
- `pipeline+context`: 110/119 (0.924) → 111/120 (0.925), coverage 0.717 →
  0.723, 5 high-confidence errors.

The benchmark's simulated history now uses the persisted shape. Only 4 of 334
context-mode predictions changed across both splits:
- two letterless follow-ups now take the prior instead of abstaining, both
  correctly: `👍` after Portuguese (held-out) and `2` after Spanish (tune);
- two changed because the vote nudge was removed:
  - `followup-fr-03`: `es`, wrong either way, is now accepted at 0.70 instead
    of as a `threshold_fallback` at 0.63;
  - `followup-es-02`: correct, 0.738 → 0.716.

The baseline was not re-recorded.

Known limitations:
- v1 has no language-switch or multi-turn records, so recency and switching
  are covered by unit tests only.
- Editing a message (edit+regenerate) replaces its text but keeps the
  detection stored with the original text.

## Phase 3 — Candidate distributions and calibrated confidence

Do not retain the current top-1 vote ratio under a different name. This phase
changes the backend result contract.

### Data model

- [x] Introduce a backend result shape containing:
  - normalized language candidates and raw scores;
  - backend reliability/status;
  - backend name and version;
  - any backend-specific raw evidence needed for calibration;
  - optional detected spans.
- [x] Keep `DetectionResult` as the pipeline-facing decision, but add explicit
      fields for agreement, margin, accepted/abstained state, and calibrated
      confidence where appropriate.
- [x] Avoid presenting a heuristic score as a probability.

### Backend adapters

- [x] Preserve the available `detect_langs()` distribution from `langdetect`
      rather than only the first result.
- [x] Preserve a configurable top-k distribution from `langid`; do not label a
      top-five-only softmax as globally normalized probability.
- [x] Preserve all meaningful `pycld2` details and its reliability flag.
- [x] Normalize language codes before distribution aggregation.
- [x] Add contract tests using fixed backend outputs so aggregation tests do not
      depend on installed native libraries.

### Calibration and aggregation

- [x] Fit per-backend calibration on the tuning split. Compare temperature
      scaling, isotonic calibration, or a simpler empirically validated mapping.
- [x] Combine complete calibrated distributions with a documented method such
      as a weighted log-linear pool or a small stacking classifier.
- [x] Include text length, script evidence, and backend reliability as features
      only when benchmark evidence supports them.
- [x] Derive backend weights, acceptance confidence, and minimum margin from the
      tuning split.
- [x] Freeze calibration parameters as versioned data or deterministic config;
      record the benchmark/model version that produced them.
- [x] Apply conversation priors before the final decision in a way that cannot
      turn a weak prior into high confidence by renormalization alone.
- [x] Remove hard-coded English/Spanish vote nudges when calibrated evidence
      supersedes them. Retain a heuristic only if an ablation demonstrates a
      held-out improvement.

### Downstream semantics

- [x] Review `PromptBuilder` confidence thresholds against calibrated values.
- [x] Make context retrieval use the configured
      `retrieval_min_confidence` consistently; avoid a separate hard-coded
      pre-check with different semantics.
- [x] Apply language-based retrieval changes only to accepted predictions.
- [x] Include detector method/version in debug metadata so benchmark and
      production results can be compared.

### Gate

- Calibration error improves materially over the Phase 0 baseline.
- High-confidence errors decrease on the held-out set.
- No unanimous-but-weak backend case can automatically become confidence
  `1.0`.
- Prompt and retrieval thresholds are backed by calibration results rather
  than the previous score scale.

**Status: met.**
- **Calibration error:** held-out ECE 0.180 (Phase 0) → 0.040, Brier 0.205 →
  0.040.
- **High-confidence errors:** 5 → 0 on held-out.
- **No weak agreement becomes 1.0:** each backend keeps a floor for languages
  it did not list, and those languages keep their share of the probability.
  `test_language_calibration.py` checks three cases:
  - unanimous-but-weak backends stay below 0.9;
  - unanimous single candidates stay below 1.0;
  - a single script candidate that the backends disagree with abstains.
- **Thresholds:**
  - acceptance is fitted on tune, per set of backends (0.70 with all three);
  - `PromptBuilder` names the language only for accepted results at ≥ 0.9,
    where tune accuracy is 97% (84% below 0.9);
  - retrieval boosts only accepted results at ≥ `retrieval_min_confidence`
    (0.7); on tune, accepted results at ≥ 0.7 are 96% correct.
- **Regression gate:** held-out selective accuracy rose from 0.922 to 0.942,
  and the gate was re-baselined on the Phase 3 report.

### Phase 3 decisions

- **Backend contract.** Adapters return `BackendResult`:
  - backend name and package version;
  - every candidate, with codes normalized before merging;
  - the scale the scores are on;
  - raw evidence (langid log-probabilities; pycld2 details, text bytes and
    reliability flag);
  - an optional `spans` field for Phase 4.

  The scales are:
  - langdetect: `probability`;
  - langid: `softmax_top_k`, softmaxed over its top 10 only, so not a global
    probability;
  - pycld2: `text_percent`, its share of the text rather than a confidence.
- **Pooling.** A weighted log-linear pool:
  - Each backend's scores are renormalized and mixed with a floor, spread
    over a nominal 100 languages. A language it did not list is then
    unlikely, not impossible.
  - Languages that no backend listed share the remaining mass equally.
  - A shared script restricts which languages may win, but mass outside the
    candidates stays in the total.
- **One calibration per backend set.**
  - Weights and a threshold fitted for all three backends do not transfer to
    fewer: with the all-backend weights, a single 100% candidate from pycld2
    alone pooled to 0.41, so a pycld2-only deployment always abstained.
  - Each of the 7 non-empty backend sets therefore has its own weights, floor
    and threshold.
  - The step uses the set that actually answered. A backend that times out or
    answers only `unknown` falls back to the smaller set's calibration.
  - A backend with no calibration is ignored.
- **What was fitted, on tune only, for each backend set.**
  - **Training records:** those where every backend in the set answered,
    using only that set's results.
  - **Weights:** fitted by minimizing the negative log-likelihood (NLL) of the
    gold language. A gold language that no backend listed gets its share of
    the residual mass, as in the pool itself.
    - This applies to 7 of the 129 tune records.
    - v1 of the calibration scored those records at 1e-12 instead, which
      dominated the fit. Fixing it lowered all-backend tune NLL from 1.88 to
      0.36.
  - **Temperature:** the per-backend weight works as the backend's
    temperature. A separate temperature could not be identified from the
    weight, so it was dropped.
  - **Floor:** the one with the lowest NLL in {0.1, 0.03, 0.01, 0.003, 0.001}.
  - **All three backends:** weights langdetect 0.217, langid 0.261, pycld2
    0.355, floor 0.001.
  - `calibrate.py` reproduces the fit deterministically.
- **Acceptance threshold** (grid 0.40–0.90).
  - Rule: minimize 2 × wrong + unwarranted abstentions over the whole tune
    split. The real pipeline is run with only that backend set enabled, and
    the smallest sets are fitted first so fallbacks are final.
  - A wrong language costs twice as much, because an abstention still tells
    the model to reply in the user's language.
  - Result: 0.70 for all three backends. Single backends: langdetect 0.70,
    langid 0.45, pycld2 0.40.
  - The minimum margin was dropped: sweeping it (0–0.4) on the first fit
    never lowered the cost.
- **Frozen calibration.**
  `server/inference/pipeline/steps/language_detection_calibration.json`,
  version `v2`. It records:
  - the corpus SHA-256 and the split;
  - backend package versions;
  - for each set, the NLL for each floor and the cost for each threshold.

  `test_calibration_was_fitted_on_frozen_tune_split` fails if the corpus
  changes. The version is exposed as `detector_version` in detection
  metadata.
- **Heuristics removed after ablation.** Each was tested on tune by adding it
  back on top of the first (v1) pool:

  | Heuristic | Tune result when added back |
  |---|---|
  | ASCII-English early return (0.9) | one more error, one more high-confidence error |
  | Below-threshold English fallback | one record better |
  | `threshold_fallback` when a Latin word pattern matched | one record better, two more wrong answers |
  | `en_boost`/`es_penalty` nudges | no place in the pool |

  - A one-record change on 168 is not a demonstrated improvement.
  - Only the early return was re-checked against v2, where it again adds a
    high-confidence error on tune.
  - A report-only check on held-out agrees: it fixes `hello` but adds two
    high-confidence errors (Dutch and Italian text called English).
  - `test_english_search_query_not_misclassified_as_french` is now a strict
    xfail, because all three backends call "Car crime statistics Vancouver"
    French. It should be re-measured once a v2 corpus has English search
    queries.
- **Features not added.**
  - pycld2's reliability flag: on the first fit, a separate floor for
    unreliable results changed tune NLL by less than 0.001.
  - Text length: not tested as a feature.
- **Removed config keys:** `backend_weights`, `min_confidence`, `min_margin`,
  `prefer_english_for_ascii` and `heuristic_nudges`. The pool reads its
  parameters from the calibration file.
- **`DetectionResult` fields:**
  - `accepted`: the current message decided the language (not true for
    abstentions or prior results);
  - `calibrated`: true only for `calibrated_ensemble`. The script and phrase
    rule paths keep a fixed 0.95, and prior results keep ≤ 0.6;
  - `agreement`, `margin`.

  `raw_results.pool_backends` names the backend set whose calibration was
  used.
- **Method rename:** `ensemble_voting` → `calibrated_ensemble`. Stored
  Phase 2 evidence still counts, because the trust filter does not depend on
  the method name.
- **Downstream.**
  - `PromptBuilder` no longer reads `min_confidence` or the ASCII ratio, so a
    prior result on ASCII text (e.g. `OK` after French) no longer gets the
    "default to English" instruction.
  - Context retrieval dropped its hard-coded `> 0.5` pre-check. It now
    requires `accepted`, and `_apply_language_boost` applies
    `retrieval_min_confidence`.
- **Conversation prior:** unchanged from Phase 2. It is consulted only below
  threshold, and its confidence is capped at 0.6 × share rather than
  renormalized.

### Phase 3 results (held-out split, benchmark v1)

| Pipeline | Top-1 acc | Macro F1 | Acceptable | Coverage | Selective acc | High-conf errors | Brier | ECE |
|---|---|---|---|---|---|---|---|---|
| Phase 0 | 0.716 | 0.715 | 112/166 | 1.000 | 0.675 | 22 | 0.205 | 0.180 |
| Phase 1/2 | 0.684 | 0.789 | 139/166 | 0.693 | 0.922 (106/115) | 5 | 0.070 | 0.070 |
| **Phase 3** | 0.729 | 0.818 | **144/166** | 0.723 | **0.942 (113/120)** | **0** | **0.040** | **0.040** |
| Phase 3 + context | 0.768 | 0.828 | 144/166 | 0.759 | 0.944 (119/126) | 0 | 0.046 | 0.053 |

Other results:
- **Phase 2 + context** was 111/120 (0.925) at coverage 0.723.
- **Tune:** selective accuracy rose from 0.934 to 0.953 and ECE fell from
  0.053 to 0.020.
- **Latency:** unchanged (p50 2.8 ms, p95 10 ms).
- **Full report:** `server/tests/language_eval/reports/phase3_baseline_v1.json`.
  The regression gate now reads it.

Held-out, one backend set at a time (report only):

| Backends | Acceptable | Selective acc | High-conf errors |
|---|---|---|---|
| langdetect | 123/166 | 0.833 | 0 |
| langid | 130/166 | 0.818 | 0 |
| pycld2 | 140/166 | 0.973 | 3 |
| langdetect + langid | 134/166 | 0.866 | 8 |
| langdetect + pycld2 | 140/166 | 0.911 | 0 |
| langid + pycld2 | 144/166 | 0.934 | 0 |
| all three | 144/166 | 0.942 | 0 |

With the v1 calibration, a pycld2-only deployment could not accept anything.
langdetect + langid is the weakest set, with 8 high-confidence errors.

What changed on held-out, against Phase 1/2:
- **Fixed** (10 records):
  - Cyrillic: `дякую` → `uk`, `благодаря за помощта` → `bg`;
  - Persian: `سلام، حالت چطوره؟` → `fa`;
  - the Han/Latin `pull request` prompt → `zh`;
  - French: `bonjour`, `ou est ma commande`;
  - Dutch and Italian text that the ASCII-English heuristic used to call
    `en`;
  - `ORBIT` and `merci` now abstain instead of guessing.
- **Worse** (5 records):
  - `hello`, `grazie` and `Háblame de New York y de Silicon Valley` now
    abstain;
  - `хвала` → `ru` at 0.57 and romanized Vietnamese → `cy` at 0.55; both
    previously abstained.
- **Still wrong, now below 0.9:**
  - `благодаря` and `рахмет` → `ru` at 0.83;
  - pinyin → `sw` at 0.84.

The mixed-language flag, which still uses backend disagreement, no longer
fires on held-out monolingual text. It also still misses all 8 mixed records.

Known limitations:
- Most remaining errors are short Cyrillic words and romanized text, where
  the backends agree on the wrong language. Calibration can lower their
  confidence but cannot fix them.
- The v1 fit briefly traded selective accuracy for coverage, with 0.909 on
  held-out. The loss bug behind it was found in review. The v2 numbers above
  replace it; held-out was not used to choose between the two.
## Phase 4 — Real mixed-language detection

Implement this after the primary detector and confidence semantics are stable.

### Tasks

- [x] Define the product semantics: primary language, secondary languages,
      contiguous spans, minimum span length, and treatment of borrowed words,
      names, and source code.
- [x] Use `pycld2.detect(..., returnVectors=True)` as the first span detector
      candidate, since the installed dependency already exposes this data.
- [x] Normalize byte/character offsets carefully and test non-ASCII text.
- [x] Merge adjacent same-language spans and discard spans below configurable
      letter-count and coverage thresholds.
- [x] Exclude code, URLs, email addresses, and isolated named entities from
      mixed-language decisions unless product requirements say otherwise.
- [x] Derive primary and secondary languages from accepted span coverage, not
      from backend disagreement.
- [x] Remove the existing `second_confidence >= mixed_language_threshold`
      implementation once the span path is validated.
- [x] Decide downstream behavior explicitly: response language should normally
      follow the primary language, while metadata may expose secondary
      languages. Do not silently produce bilingual responses merely because
      mixed text was detected.

### Tests

- [x] Genuine two- and three-language prompts with labelled spans.
- [x] Monolingual ambiguous prompts that must not be marked mixed.
- [x] English prose containing foreign names or one borrowed word.
- [x] Natural-language prompts containing source code.
- [x] Mixed scripts, including offsets around emoji and supplementary-plane
      characters.

### Gate

- Mixed-language span metrics improve over the Phase 0 behavior, and
  monolingual false-positive rate stays within an agreed bound.

**Status: met.**
- **Span metrics:** held-out mixed-flag recall 0/8 (Phase 0) → 6/8, and
  character-level secondary-span recall from none to 0.69 at precision 0.77.
- **Agreed bound:** monolingual false-positive rate ≤ 2%. Held-out is 0.013
  (2 of 158), against 0 before; the flag never fired before.
- **Tests:** `test_heldout_mixed_language_does_not_regress` enforces the bound
  and fails if flag or span recall drops below the baseline. Primary-language
  predictions are identical to Phase 3.

### Phase 4 decisions

- **Semantics.**
  - Primary language: the calibrated whole-message decision
    (`detected_language`), unchanged from Phase 3. The reply follows it.
  - Secondary languages: languages of accepted spans other than the primary,
    most letters first. They are metadata only: no bilingual replies, no
    retrieval effect.
  - Spans: contiguous, code-point offsets into the original message,
    reported only when the primary detection is accepted.
- **Primary stays whole-message.** The plan said to derive primary and
  secondary languages from span coverage. Only the secondary is derived that
  way: letting span coverage override the gated primary decision would change
  Phase 3's benchmarked predictions, for example making
  "The client wrote back: «Nous avons…»" French by coverage.
- **pycld2 `returnVectors` rejected.** On the tune mixed and borrowed-word
  records, its vectors were one span for the whole sentence, or `un` for the
  embedded words. It found no secondary language in any of them.
- **Segmenter instead.** Cut at clause punctuation and script changes, then
  run the calibrated detector on each segment. Borrowed words and names
  inside a clause stay in that clause, so they are never spans.
- **Excluded from spans:**
  - code, URLs and email addresses, masked out and treated as boundaries;
  - Latin-script runs whose words are all capitalized, treated as names.
- **Thresholds, from the tune split.**
  - Sweep: `min_span_letters` ∈ {3, 5, 8, 12} × `min_span_coverage` ∈
    {0, 0.1, 0.2}.
  - Rule: best mixed-flag F1 with tune false-positive rate ≤ 2%, then span F1;
    ties go to the stricter setting.
  - Result: 5 letters and 0.1 coverage, tied with 3/0, 3/0.1 and 5/0. Every
    setting kept tune precision at 1.0 and the false-positive rate at 0.
- **Merge rule, fixed after seeing held-out.** The first version merged
  same-language spans across a skipped segment. The span around
  `pull request` in a Chinese prompt then covered English text. Spans now
  merge only when consecutive. This is a correctness fix; tune and held-out
  metrics are unchanged by it.
- **Merge rule, fixed in review.** Two same-language segments on either side
  of a URL, email address or code block were merged into one span that
  contained the masked content. Masked content now blocks merging.
  Benchmark output is unchanged.
- **Defaults.** A config without a `mixed_language` block gets the
  benchmarked values (5 letters, 0.1 coverage), not a coverage of 0.
- **Removed:** the `second_confidence >= mixed_language_threshold`
  disagreement rule and its config key.
- **Added:** `mixed_language.{min_span_letters, min_span_coverage}` in both
  configs.
- **Metadata:** `spans` and `secondary_languages` are new.
  `mixed_language_detected`, `secondary_language` and `secondary_confidence`
  now come from spans; the confidence is the lowest span confidence for that
  language.
- **Runner.** A record counts as mixed only if a span is in a language other
  than the prediction, so spans in the primary language alone are
  monolingual. Span character metrics are now computed.

### Phase 4 results (benchmark v1)

| Held-out | Flag precision | Flag recall | Monolingual FP rate | Secondary-language recall | Span char precision | Span char recall |
|---|---|---|---|---|---|---|
| Phase 0–3 | — | 0/8 | 0.000 | 0.000 | — | — |
| **Phase 4** | 0.75 (6/8) | **0.75 (6/8)** | 0.013 (2/158) | 0.75 | 0.77 | 0.69 |

On tune: precision 1.0, recall 0.75, false-positive rate 0, span character
precision 0.57 and recall 0.28. Full report:
`server/tests/language_eval/reports/phase4_baseline_v1.json`, which the
regression gate now reads. Primary-language metrics are unchanged from
Phase 3.

Held-out details:
- **Found:** English clauses inside French, German, Italian, Russian and
  Korean prompts, and German `und bis morgen` inside English.
- **Missed:**
  - `it's urgent`, too short to be accepted on its own;
  - `pull request` inside Chinese;
  - `merci beaucoup`, where the English prompt's German span was found
    instead.
- **False positives:** both are short Cyrillic greetings whose primary
  language was already wrong: `привет` read as `bg` under an `mk` primary,
  and `како си` as `mk` under `sr`.
- **Spurious third language:** `Отправь мне` was detected as `be` inside a
  Russian prompt.

Latency: span detection reruns the backends on each qualifying segment.
Pipeline p95 rose from about 11 ms to 15 ms, and p50 from 3.0 to 3.5 ms.

Known limitations:
- Single embedded words are unreliable on their own. In the Hindi and
  Japanese tune prompts, `meeting` is accepted as `nl` at 0.61, so the message
  is flagged mixed with the wrong secondary language. That is why tune
  secondary-language recall (0.375) is half its flag recall.
- Word-level switching inside a clause, such as Taglish `i-check yung email`,
  is not detected.
- v1 has only 8 mixed records per split, so these rates are coarse. A v2
  corpus should add more mixed, code and name-heavy prompts.