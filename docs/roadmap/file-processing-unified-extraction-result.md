# File Processing Service — Unified Extraction Result & Registry Dispatch

## Status

**Partially implemented.**

- Step 2a (compatibility bridge: `ExtractionResult`, `FileProcessor.extract()`
  default bridge, `extract_text` made non-abstract, `_FailingProcessor` fix,
  `_extract_content` switched to `processor.extract(...)`) — **done**.
- `DoclingProcessor.extract()` and `AIDocumentProcessor.extract()` — **done**,
  migrated directly (single conversion for Docling; local-variable
  usage/model capture for AI-OCR), with the concurrency/billing-attribution
  tests this doc specifies.
- The native format-specific processors (`text`, `pdf`, `docx`, `csv`,
  `json`, `html`, `pptx`, `xlsx`, `vtt`) and `MarkItDownProcessor` — **not
  migrated**; they have no instance-attribute state, so the step-2a bridge
  already produces identical, correct `ExtractionResult`s for them. There is
  no bug to fix there, so migrating them individually was deprioritized in
  favor of the two processors with real concurrency bugs (Docling, AI-OCR).
  Migrate them opportunistically whenever one of those files is touched for
  another reason; it's a mechanical override of `extract()`, not urgent.
- Step 2c (remove the bridge, make `extract()` the sole abstract method,
  delete `extract_text`/`extract_metadata`) — **not done**, and can't be
  until every processor above overrides `extract()` directly. Existing tests
  also still call `extract_text`/`extract_metadata` directly on native
  processors and Docling, so those methods stay in place regardless.

## Summary

This is the deferred, full-scope version of item 3 in
[`file-processing-service-simplification.md`](./complete/file-processing-service-simplification.md).
That doc's item 3 turned out to split into two independently-sizeable pieces:

- **Registry-based dispatch for vision/audio** (narrower, lower risk) — wrap
  vision/audio extraction as `FileProcessor`-conforming adapters and register
  them in `FileProcessorRegistry`, so `_extract_content` has one dispatch path
  (`get_processors(mime_type)`) instead of special-casing
  `mime_type.startswith(('image/', 'audio/'))` ahead of the registry. Not what
  this doc covers.
- **Unified per-extraction result object** (this doc) — replace the
  `FileProcessor.extract_text`/`extract_metadata` two-call contract, and the
  instance-attribute side channel every processor uses to smuggle extra data
  back to the caller, with a single `extract()` call returning one
  standardized result object.

This doc covers the second piece only, deferred because it requires changing
the shared interface across all ~10 existing processors, not a surgical
cleanup of one file.

## Why this is its own plan

`file_processing_service.py:_extract_content` currently reads extra data out
of registry processors via `getattr`, after two separate calls:

```python
text = await processor.extract_text(file_data, filename)
metadata = await processor.extract_metadata(file_data, filename)
tables = getattr(processor, "_last_tables", None) or []
page_segments = getattr(processor, "_last_page_segments", None) or []
last_usage = getattr(processor, "last_usage", None)
# ... getattr(processor, "provider", None), getattr(processor, "last_model", None)
```

This instance-attribute pattern (processor stores state from the last call on
`self`, caller reads it right after) is the root cause of two regressions
already hit and fixed during the `/simplify` pass that produced the parent
roadmap doc (see its Summary section): a shared processor instance's
per-call state got clobbered when two extractions ran concurrently. The
pattern is still in place for every processor that uses it today:

- `DoclingProcessor` — `_last_tables`, `_last_page_segments` (confirmed via
  `getattr` reads in `_extract_content`)
- `AIDocumentProcessor` (`services/file_processing/ai_document_processor.py:45-55`)
  — `self.last_usage`, `self.last_model`, `self.provider` (the comment there
  explains why: `FileProcessor.extract_text()` only returns a bare `str`, so
  callers that want usage read the instance attribute right after calling
  it, "rather than widening that shared return contract" — this doc is
  exactly that contract-widening, now proposed deliberately)
- `MarkItDownProcessor` and the native format-specific processors
  (`text_processor.py`, `pdf_processor.py`, `docx_processor.py`,
  `csv_processor.py`, `json_processor.py`, `html_processor.py`,
  `pptx_processor.py`, `xlsx_processor.py`, `vtt_processor.py`) implement the
  plain two-call contract today (no extra instance-attribute state), but all
  inherit from the same `FileProcessor` base
  (`services/file_processing/base_processor.py`) and would need to adopt
  whatever new interface replaces it.

Rewriting the interface touches every one of these files plus their existing
test suites, and the vision/audio paths (`_extract_image_content`,
`_extract_audio_content`) that would also adopt it if they're wrapped as
processors per the registry-dispatch piece. That's a double-digit-file diff
with real regression risk (per-call state bugs are exactly what already bit
this file twice), not a drive-by refactor.

## Current pinned behavior (already captured)

Two characterization-test files already pin down today's behavior so this
refactor (and the registry-dispatch piece) can be verified
behavior-preserving once attempted:

- `server/tests/file-adapter/test_file_processing_pipeline_characterization.py`
  — `process_file_content`/`process_file` pipeline behavior (success,
  extraction failure, timeout, encryption on/off, deletion-during-extraction).
- `server/tests/file-adapter/test_file_processing_dispatch_characterization.py`
  — dispatch behavior: upload-time validation accepts allowlisted image/audio
  MIME types independent of `enable_vision`/`enable_audio`; vision/audio
  extraction failures are not retried with another processor; AI-OCR-priority
  excludes generic vision entirely for image MIME types, even when OCR itself
  fails (no "OCR failed, fall back to vision" path today).

Any implementation of this doc must keep those tests green, or deliberately
update them with a stated reason (e.g. if the eventual design *does* want to
add an OCR-failure vision fallback — the parent doc flags that as a real
behavior change to decide explicitly, not a side effect to stumble into).

## Proposed design

### 1. `ExtractionResult` value object

```python
@dataclass
class ExtractionResult:
    text: str
    metadata: dict[str, Any]
    tables: list[dict[str, Any]] = field(default_factory=list)
    page_segments: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None
```

Lives next to `Chunk` (`services/file_processing/chunking/__init__.py` or
wherever `Chunk` is defined today) or in a new small module — not decided
yet, pick based on where `Chunk` actually lives when this is implemented.

### 2. New `FileProcessor` interface — via a compatibility bridge, not a flag day

Making `extract()` abstract immediately would break every existing processor
the moment this lands, since none of them implement it yet — they'd stop
being instantiable. Instead:

**Step 2a — add a concrete bridge, migrate nothing yet.** Add `extract()` to
`FileProcessor` as a **concrete** (not abstract) method that runs the legacy
`extract_text`/`extract_metadata` sequentially and assembles an
`ExtractionResult`, preserving every field callers rely on today (including
the `_last_tables`/`_last_page_segments`/`last_usage`/`last_model`/`provider`
instance-attribute reads, read right after the legacy calls, exactly as
`_extract_content` does now):

```python
async def extract(self, file_data: bytes, filename: str | None = None) -> ExtractionResult:
    """Default bridge: legacy extract_text/extract_metadata -> ExtractionResult.
    Processors override this directly once migrated; see migration order below."""
    text = await self.extract_text(file_data, filename)
    metadata = await self.extract_metadata(file_data, filename)
    return ExtractionResult(
        text=text,
        metadata=metadata,
        tables=getattr(self, "_last_tables", None) or [],
        page_segments=getattr(self, "_last_page_segments", None) or [],
        usage=getattr(self, "last_usage", None),
        provider=getattr(self, "provider", None),
        model=getattr(self, "last_model", None),
    )
```

Switch `_extract_content`'s registry loop to call `processor.extract(...)`
(see loop below) in this same step. Nothing about per-processor behavior
changes yet — every processor still works exactly as before, just through the
bridge. This step is low-risk and should be verified purely against the
existing pipeline/dispatch characterization tests (no new processor-specific
tests needed for it).

This same step must also make `extract_text` **non-abstract** on
`FileProcessor` (it is `@abstractmethod` today — `base_processor.py:37`), not
just leave the bridge in place. Step 2b (next) has each migrated processor
delete its own `extract_text`/`extract_metadata` once it overrides
`extract()` directly; if `extract_text` is still abstract at that point,
every migrated processor becomes **uninstantiable** the moment it stops
implementing it — the first processor migrated in step 2b would break
immediately. Give `extract_text` a concrete default alongside the bridge
(e.g. `raise NotImplementedError`, only ever called by the bridge itself for
processors that haven't migrated yet). `extract_metadata` is already
concrete today (the base class's filename/file_size dict) — keep it that way
and keep it available as a reusable helper throughout the migration, since a
migrated processor's `extract()` may still want that base metadata shape
without going through the now-bypassed two-call contract.

**Step 2b — migrate processors one at a time** (see migration order below),
each by overriding `extract()` directly on that processor and deleting its
now-unused `extract_text`/`extract_metadata`/instance-attribute state. The
default bridge keeps serving every not-yet-migrated processor throughout.

**Step 2c — once every processor overrides `extract()`,** remove the bridge
method and the now-dead `extract_text`/`extract_metadata` methods
from `FileProcessor` entirely, and make `extract()` the one abstract method.
If any migrated processor's `extract()` still calls
`self.extract_metadata(...)` for its base filename/file_size dict (per step
2a's note that this helper should stay reusable), that logic can't simply
vanish when `extract_metadata` is deleted here — move the base
`{'filename': ..., 'file_size': len(file_data)}` construction into a small
private helper (e.g. `self._base_metadata(file_data, filename)`) *before*
deleting `extract_metadata`, and repoint any processor still calling
`self.extract_metadata(...)` at that helper instead. Do this as the first
change within step 2c, ahead of deleting the method, so there's no gap where
a migrated processor's `extract()` references a method that no longer
exists:

```python
@abstractmethod
async def extract(self, file_data: bytes, filename: str | None = None) -> ExtractionResult:
    ...
```

`_extract_content`'s registry loop, true from step 2a onward:

```python
for index, processor in enumerate(processors):
    try:
        result = await processor.extract(file_data, filename)
        if result.usage:
            await self._log_extraction_usage(api_key, filename, result.provider, result.model, result.usage, call_type="document")
        return result.text, result.metadata, result.tables, result.page_segments
    except Exception as e:
        ...
```

**Test doubles are part of the migration, not exempt from it.** Several
tests construct their own processor stand-ins that will need the same
treatment as production processors:

- `CustomProcessor` in `test_file_processing.py::test_processor_registry_register_custom`
  and `_RacyProcessor` (`test_file_processing.py:2501`) both subclass the real
  `FileProcessor`, so they pick up the step-2a bridge automatically and keep
  working unmodified until step 2c removes the legacy methods — at that
  point they need updating like any other processor.
- `_FailingProcessor` in `test_file_processing_dispatch_characterization.py`
  is **not** a `FileProcessor` subclass at all — it's a plain duck-typed
  class implementing only `supports_mime_type`/`extract_text`/
  `extract_metadata` (`test_file_processing_dispatch_characterization.py:135-145`).
  It does not inherit the bridge, so the moment `_extract_content`'s registry
  loop switches to calling `processor.extract(...)` (step 2a, not step 2c —
  this is immediate, not deferred), this double has no `.extract()` method at
  all. Its test currently asserts `pytest.raises(RuntimeError, match=
  "simulated OCR failure")`; without a fix it would instead raise
  `AttributeError: 'object' has no attribute 'extract'`, silently changing
  what the test proves. Add an `extract()` method to `_FailingProcessor`
  itself (not inherited) that raises the same `RuntimeError`, in the same PR
  that lands step 2a — before any processor migration, since this break
  happens at the dispatch-switch, not at step 2c.

### 3. Migration order (one processor at a time, each with its own PR)

Migrate processors from simplest to riskiest, landing tests alongside each,
with step 2a (the bridge) landing first and step 2c (removing the bridge and
legacy methods) landing last, after every item below:

1. Native format-specific processors with no extra state today (`text`,
   `pdf`, `docx`, `csv`, `json`, `html`, `pptx`, `xlsx`, `vtt`) — mechanical,
   `tables`/`page_segments`/`usage` all empty/`None`. Lowest risk, good
   first batch to prove the interface.
2. `MarkItDownProcessor` — same shape, still no extra state, if it doesn't
   already set tables/page_segments.
3. `DoclingProcessor` — see dedicated section below; this is the one that's
   already bitten the file with concurrency bugs.
4. `AIDocumentProcessor` — see dedicated section below for the usage/model
   attribution test this needs.
5. Vision/audio (`_extract_image_content`/`_extract_audio_content`) are
   **not** part of this migration — see "Dispatch scope" below. They keep
   returning their current `(text, metadata)` tuple from `_extract_content`
   and are wrapped into `ExtractionResult` only if/when the separate
   registry-dispatch piece adopts the same interface for them.

### Docling: one conversion, not two

`DoclingProcessor.extract_text` and `DoclingProcessor.extract_metadata` each
call `self._converter.convert(temp_path)` independently today
(`docling_processor.py:187` inside `extract_text`, `:331` inside
`extract_metadata`) — the same file is converted twice per extraction, and
`extract_metadata`'s conversion is wrapped in a broad `try/except` that logs
and returns partial metadata on failure (`:349-350`), i.e. metadata
extraction is explicitly best-effort and independent of whether text
extraction succeeded.

The migrated `extract()` must call `convert()` once and derive text, tables,
page segments, *and* metadata from that single `result.document` — not
reintroduce a second conversion under a different name. Required tests
before this processor is considered migrated:

- **Conversion failure still triggers processor fallback.** If the single
  `convert()` call raises, `extract()` must raise too (not swallow it the
  way the current metadata-only try/except does), so `_extract_content`'s
  existing "try next processor" loop still falls back to MarkItDown/etc.
  exactly as it does today.
- **Metadata-derivation failure still returns the extracted content.**
  Today, a failure in the metadata-only conversion still returns the text
  extracted separately, because they're two independent calls. Once merged
  into one conversion, this needs an equivalent: if pulling extra fields out
  of the already-converted `doc` (page count, structure flags, etc.) raises,
  that failure must not discard the text/tables/page_segments already
  derived from the same successful `convert()` call — wrap only the
  metadata-field derivation in its own try/except, not the conversion itself
  or the whole `extract()` body.
- **The concurrency test must match how `convert()` actually runs.**
  `self._converter.convert()` is a synchronous, blocking call — it is not
  itself `await`ed, even though it's invoked from inside an `async def`. A
  monkeypatched fake written as `async def fake_convert(...): ...` would be
  wrong here: production code calls `self._converter.convert(temp_path)`
  directly (no `await`), so if the fake is a coroutine function, that call
  just constructs and discards a coroutine object without ever running its
  body — the test would silently test nothing. Since there is no real
  `await` point inside `convert()` to interleave at, two `extract()` calls
  scheduled together (e.g. via `asyncio.gather`) cannot genuinely overlap
  under today's synchronous-call design — the event loop never yields
  between them. Use two different tests for two different things:
  - **Regression test (no concurrency needed):** call `extract()` once on a
    shared `DoclingProcessor` instance and capture `result1`; call
    `extract()` again with different fake document data; assert `result1`'s
    `tables`/`page_segments` are still the first call's values, unchanged by
    the second call. This directly proves the design no longer has a shared
    mutable channel a second call could clobber — the actual bug class this
    doc exists to close — without needing true concurrency.
  - **Overlap test (only if/when relevant):** only write a genuine overlap
    test if `convert()` is ever moved off the event loop (e.g. wrapped in
    `asyncio.to_thread`) to avoid blocking it — at that point there's a real
    await boundary to interleave at, and the fake must pause with a plain
    (non-async) blocking primitive matching that boundary, not a bare
    `async def`. Until then, the sequential regression test above is the
    correct and sufficient test for this processor.

### AI-OCR usage/model attribution under concurrency

`AIDocumentProcessor` already documents (`ai_document_processor.py:45-55`)
that `last_usage`/`last_model`/`provider` are instance attributes read right
after `extract_text()` returns, specifically because the base interface
couldn't carry them — this doc's `ExtractionResult` is that contract widening
done deliberately. The concurrency test for this processor must do more than
check tables/page_segments don't leak (as Docling's test does): it must check
**billing attribution**, since usage data silently inherited from a
different concurrent call is a stealth billing/audit bug, not just a data
bug.

Unlike Docling's `convert()`, the OCR service call genuinely is awaited
(`await ocr_service....(...)`), so this processor *can* have two calls
actually interleave — but the test must force a specific, deliberately
adversarial ordering, not just fire both with `asyncio.gather` and hope:

1. Start the **no-usage** call's `extract()` first. Mock its OCR service
   call to block on an `asyncio.Event` (or similar) right after it would set
   `last_usage = None`, so this call is paused mid-flight, past the point
   where (in a naive migration) it might read stale shared state.
2. While the no-usage call is paused, start and fully run the
   **usage-reporting** call's `extract()` to completion on the same
   processor instance. Let it finish entirely before touching the first
   call again.
3. Only now set the `Event` so the paused no-usage call resumes and
   finishes.
4. Assert the **no-usage call's** result still has `usage=None` — not the
   other call's usage dict.

This specific order (pause the no-usage call, let the usage-reporting call
run to completion, *then* resume the paused call) is what exposes the bug: a
naive migration that reads `self.last_usage` *after* awaiting the OCR call,
rather than capturing it into a local variable before any other call gets a
chance to run, will have `self.last_usage` already overwritten by the other
call's value by the time the paused call resumes and reads it — a test that
only interleaves loosely (e.g. plain `gather`) could pass or fail
non-deterministically depending on scheduling, while this ordering
guarantees the stale value is present if the bug exists. Assert:

- Each returned `ExtractionResult.usage` matches only its own call — the
  no-usage call's result must not inherit the other call's usage dict.
- Each `ExtractionResult.model`/`.provider` matches its own call's resolved
  model, not whichever call happened to set the instance attribute last.
- The `_log_extraction_usage` audit write triggered per result (in
  `_extract_content`'s loop, guarded by `if result.usage:`) fires only for
  the call that actually reported usage, with that call's own model/provider
  — not for the no-usage call, and not with the wrong model attached to the
  right call.

This is the exact failure mode a naive migration could reintroduce: if
`extract()` is implemented as "call the OCR service, then read
`self.last_usage`" without passing usage through the call's own local scope,
a fast no-usage call finishing while a slow usage-reporting call is still
in flight would read the slow call's `self.last_usage` once it lands,
attributing someone else's usage (and billing) to the wrong request.

### Dispatch scope: keep the AI-OCR registry rule with the dispatch work, not gated on this doc

The parent doc's item 3 said the registry-dispatch piece "can land
independently" of this result-object unification, but also listed "fold
`_ai_ocr_is_priority()`'s override into the registry" as a step that comes
*after* this doc's full migration (previously: "Only after all of the
above"). Those two statements conflict — the AI-OCR eligibility rule is part
of registry dispatch, not part of unifying the result object, so it
shouldn't be blocked on this doc finishing.

**Resolution:** this doc's processor migration (items 1-4 above) must
preserve the *existing* `_extract_content` tuple return
(`text, metadata, tables, page_segments`) and existing `getattr`-free
`result.usage`/`result.provider`/`result.model` reads for the registry-driven
document processors it covers, while leaving vision/audio exactly where they
are today — still handled by `_extract_image_content`/`_extract_audio_content`
via the `mime_type.startswith(('image/', 'audio/'))` special case ahead of
the registry, untouched. Folding `_ai_ocr_is_priority()` into a registry
eligibility rule, and wrapping vision/audio as registry processors at all,
belongs entirely to the separate registry-dispatch piece and can be designed
and landed on its own schedule — it does not need to wait for every document
processor in this doc to finish migrating to `extract()`.

## Explicitly out of scope for this doc

- The registry-dispatch piece itself (wrapping vision/audio as processors,
  folding `_ai_ocr_is_priority()` into a registry eligibility rule, removing
  the `mime_type.startswith(('image/', 'audio/'))` special case from
  `_extract_content`) — lands independently, on its own schedule; see
  "Dispatch scope" above.
- Changing upload-time validation (`_validate_file`) to depend on
  `enable_vision`/`enable_audio` — pinned as current behavior; a real
  decision to make explicitly if ever revisited, not a side effect of this
  refactor.

## Risk

High in aggregate, but the compatibility-bridge rollout (step 2a/2b/2c above)
keeps each individual PR low-risk: the bridge means no processor is ever
broken mid-migration, and each processor's own PR can land and be verified
independently against the full test suite before the next one starts. The
two processors with actual per-call state (Docling, AI-OCR) need their own
concurrency tests written *immediately before* migrating each one, not
deferred to a final pass — see their dedicated sections above. No
behavior-pinning tests exist yet for each processor's current
`extract_text`/`extract_metadata` output individually beyond those two
(only pipeline- and dispatch-level pinning exists so far); write those
alongside each processor's migration PR, not all up front.
