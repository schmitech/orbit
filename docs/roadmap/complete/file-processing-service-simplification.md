# File Processing Service — Deferred Simplification Work

**Status: done**, except where explicitly split off below.

- **Item 1** (merge the two processing pipelines) — done. Characterization
  tests landed in `server/tests/file-adapter/test_file_processing_pipeline_characterization.py`,
  then `process_file_content`/`process_file` were merged at the persistence
  boundary into a shared `_persist_and_index_chunks` helper, preserving the
  lock/encryption-decision split each wrapper owns.
- **Item 2** (provider-lookup + upload/store dedup) — done. Collapsed into
  `_get_provider_for_api_key` and `_store_and_record_upload`.
- **Item 3** (registry-based dispatch for vision/audio) — behavior-pinning
  tests landed (`test_file_processing_dispatch_characterization.py`), but the
  full rewrite (unified per-extraction result object + registry dispatch) was
  split into its own tracked plan,
  [`file-processing-unified-extraction-result.md`](./file-processing-unified-extraction-result.md),
  since it requires changing the shared `FileProcessor` interface across all
  ~10 existing processors — out of scope for this doc.
- **Item 4** (chunker `from_config` registry) — done. Each `Chunker` subclass
  now has a `from_config(chunk_size, overlap, tokenizer, options)`
  classmethod; `_init_chunker` is a `{strategy: ChunkerClass}` lookup + call.

## Summary

A `/simplify` pass over `server/services/file_processing/file_processing_service.py`
(2,197 lines) applied the low-risk fixes directly (import hygiene, flattened
nesting, a small loop simplification — see git history for that commit). Four
findings were flagged but skipped because fixing them properly is a structural
refactor with real behavior risk, not a surgical cleanup. This doc tracks that
remaining work so it isn't lost.

A subsequent code review on that same commit caught two regressions the
simplify pass introduced, both since fixed:
- The `asyncio.gather`-based "parallelize independent I/O" change in
  `_extract_content` was reverted back to sequential `extract_text` →
  `extract_metadata`. A shared processor instance (e.g. Docling) stores
  per-call state on `_last_tables`/`_last_page_segments`, so running two
  extractions concurrently let a second in-flight upload's results overwrite
  the first's before it read them; running metadata extraction unconditionally
  also repeated an expensive failed conversion when text extraction failed
  instead of going straight to the next processor.
- The hoisted `chunking_options` lookup in `_init_chunker` now normalizes an
  explicit YAML `null` (e.g. `files.chunking_options:` with no value) to `{}`
  instead of leaving it `None`, which previously crashed `fixed`/`token`
  strategy construction (`_init_chunker` would raise and the service factory
  would disable file processing).

Reference: review findings from the four parallel cleanup agents (reuse,
simplification, efficiency, altitude) run against this file, revised after a
second review of this doc caught three issues with the original plan (see
each item below for what changed and why).

---

## 1. Merge the two near-duplicate processing pipelines

`process_file_content` (`file_processing_service.py:919`) and `process_file`
(`file_processing_service.py:1181`) are ~150-line pipelines that do the same
six steps — extract → strip tables → chunk → page-attribute → encrypt →
index → record chunks → update status — differing only in timeout/locking
behavior and return shape. The `embedded_chunk_ids` computation and the
chunk-recording loop are copy-pasted verbatim between them.

**Caller map (verified):** production only ever calls `process_file_content`,
never `process_file` — the upload route (`server/routes/file_routes.py:249`)
calls `quick_upload` then backgrounds `process_file_content`, and
`reprocess_file` (`file_processing_service.py:2117`) calls
`process_file_content` directly too. `process_file` has no production caller;
only tests call it directly. Any consolidation needs to preserve
`process_file`'s contract for those tests (or migrate them), not just
`process_file_content`'s.

**Revised plan (first pass omitted the metadata field — fixed here):**
- `process_file` returns `'metadata': file_metadata` (the dict from
  `_extract_content`, `file_processing_service.py:1309`) in its result;
  `process_file_content` has no return value to preserve. A shared helper
  must keep returning `file_metadata` alongside chunks/collection info, not
  just `(chunks, collection_name, embedding_provider, embedding_dimensions)`
  as originally proposed.
- Split the shared pipeline at the persistence boundary
  (`file_processing_service.py:978`, the `async with
  self._get_file_operation_lock(file_id):` block): extraction + chunking as
  one phase, chunk-persistence + indexing as a second phase.
- **Keep the lock, the file-existence check, and the stored-encryption
  lookup in the background wrapper (`process_file_content`), not in the
  shared persistence helper.** The two callers decide `requires_encryption`
  differently and that difference is intentional, not incidental duplication:
  the synchronous path (`process_file`) computes it once via
  `_requires_encryption_for_api_key` at upload time (`:1213`) and reuses that
  same value for persistence (`:1267`) — there's no re-read because there's
  no background gap for the file to be deleted or re-configured in between.
  The background wrapper instead re-reads the *stored* `encrypted` flag from
  `file_info` after acquiring the lock (`:985-989`), because extraction can
  take long enough for the file to be deleted (or its record altered) before
  persistence runs. So: the shared persistence helper takes
  `requires_encryption: bool` as a parameter: `process_file` passes its
  upload-time value, `process_file_content` passes the value it just re-read
  under its lock — the encryption *decision* stays with each wrapper, only
  the chunk-persistence/indexing/metadata-recording mechanics move into the
  shared helper.
- Write characterization tests against both public entry points first
  (success path, partial failure, timeout, encryption on/off, **and deletion
  during extraction** — cover the early-return-on-cancel path at
  `file_processing_service.py:985-987`) so the merge is provably
  behavior-preserving before deleting either duplicate.

**Risk:** high blast radius — hit from upload and reprocess flows in
production. Don't attempt without the characterization tests landing first.

---

## 2. Collapse vision/audio provider lookup and upload/store duplication

- `_get_vision_provider_for_api_key` (~631-678) and
  `_get_audio_provider_for_api_key` (~680-727) are structurally identical,
  differing only in the config key (`vision_provider` vs `stt_provider`) and
  default attribute. Collapse into one `_get_provider_for_api_key(api_key,
  config_key, default_provider, current_user_id, current_user_email)`.
- `quick_upload` (~848-912) and the first four steps of `process_file`
  (~1206-1238) duplicate the upload/store/record/mark-processing logic.
  Extract `_store_and_record_upload(file_id, file_data, filename, mime_type,
  api_key, current_user_id, current_user_email)` returning
  `requires_encryption`/`metadata`, called from both.

**Plan:** smallest, most independent item — do this first, as its own PR.
Cover with unit tests on the new helpers before switching the call sites.

---

## 3. Registry-based dispatch for vision/audio processing

**Status:** behavior-pinning tests landed
(`server/tests/file-adapter/test_file_processing_dispatch_characterization.py`).
The "standardize tables/page_segments/usage/provider/model as part of a
single per-extraction result object" sub-item below turned out to require
rewriting the shared `FileProcessor` interface across all ~10 existing
processors — too large to bundle into this item. That full-scope redesign is
now tracked separately in
[`file-processing-unified-extraction-result.md`](./file-processing-unified-extraction-result.md).
The registry-dispatch piece (wrapping vision/audio as processors, folding
`_ai_ocr_is_priority()` into a registry eligibility rule) can still land
independently once attempted — it doesn't require the result-object rewrite
first, despite the original ordering below.

`_extract_content` (~1376-1431) and `_validate_file` (~1353-1359, see also
`file_processing_service.py:1340`) both special-case
`mime_type.startswith(('image/', 'audio/'))` to bypass `FileProcessorRegistry`
entirely, rather than registering vision/audio extraction as processors. This
is a second, parallel dispatch mechanism living next to the registry.

**Before touching the registry, specify current behavior precisely** (the
original plan assumed a wildcard registration + priority ordering would be a
transparent refactor — it isn't, without pinning down two behaviors first):
- **Upload-time validation** currently accepts allowlisted image/audio MIME
  types independently of whether vision/audio is actually enabled for that
  adapter/provider (`_validate_file`). A registry-based rewrite could
  silently start rejecting uploads at validation time instead of failing
  later at extraction, or vice versa — decide and test which is correct
  before changing it.
- **Extraction-time fallback** currently lets vision/STT bypass the
  registry's multi-processor fallback loop entirely when selected — there's
  no "try the next processor" for a failed vision/audio call the way there
  is for Docling → MarkItDown. A wildcard registration plus priority
  ordering changes which provider runs after a failure; write a test that
  pins down today's behavior (no fallback) before changing it, even if the
  eventual goal is to add one.
- **The AI-OCR-priority override is a dispatch rule, not just a condition to
  preserve.** Today, when AI OCR is the priority processor
  (`_ai_ocr_is_priority()`, checked at `file_processing_service.py:1370-1373`),
  generic vision (`_extract_image_content`) is skipped *entirely* for image
  MIME types — including when the AI OCR processor itself then fails during
  extraction. There is no "OCR failed, fall back to generic vision" path
  today. If vision becomes just another (lower-priority) entry in the
  registry's ordered processor list for image MIME types, that ordering
  *would* introduce exactly that fallback as a side effect — a real behavior
  change, not a refactor. Decide explicitly whether that fallback is wanted;
  either way, write a test that pins down "AI-OCR-priority + OCR failure ⇒ no
  vision fallback" against the *current* code before changing the dispatch
  mechanism, so the registry rewrite is caught immediately if it accidentally
  introduces the fallback.
- Standardize `tables`, `page_segments`, and `usage`/`provider`/`model` as
  part of a single per-extraction result object (not instance attributes
  like `_last_tables`/`_last_page_segments` — see the two regressions this
  simplify pass already hit from that pattern) so results are tied to their
  upload regardless of dispatch mechanism, and the
  `getattr(processor, "last_usage", None)` duck-typing in the extraction loop
  goes away too.
- Once upload-acceptance and fallback behavior are both pinned down and
  tested, fold `_ai_ocr_is_priority()`'s override into an eligibility rule
  inside the registry instead of a branch in the caller: when AI OCR has
  priority, generic vision is excluded from the candidate list for that
  extraction entirely (not merely ordered after AI OCR), so an OCR failure
  still has nothing to fall back to. This gives `_extract_content` one
  dispatch path (`get_processors(mime_type)`) for every file type while
  preserving the no-fallback behavior the pinning test above locks in.

**Risk:** touches the processor registry contract used elsewhere in the file
processing stack, and can silently change upload-acceptance/fallback
behavior — needs its own design pass and behavior-pinning tests, not a
drive-by change.

---

## 4. Chunker construction cleanup (narrowed scope)

`_init_chunker` (~267-401) is a 7-branch `if/elif` chain picking a chunker
class by `strategy` string. Give each `Chunker` subclass a `from_config(
chunk_size, overlap, tokenizer, options) -> Chunker` classmethod and keep a
`{strategy_name: ChunkerClass}` registry dict, so `_init_chunker` becomes a
one-line lookup + call. Self-contained — no callers outside `_init_chunker`
to update.

**Lower priority than originally scoped — smaller payoff than item 1, and
`_assign_page_attribution` is no longer bundled in here.** Page attribution
(`_assign_page_attribution`, `file_processing_service.py:1566`) owns the
search cursor and the rules for synthetic table headers and
whitespace-normalized row matching (`_find_whitespace_insensitive`,
`file_processing_service.py:1659`); it's already independently testable from
processor/chunker dispatch (see the existing `test_assign_page_attribution_*`
tests) and gets no simpler by moving it onto a `Chunker`/`split_table_text`
interface. Leave `_assign_page_attribution` and the
`isinstance(self.chunker, TableAwareChunker)` check in
`_extract_tables_as_chunks` (~1859-1867) as-is; reassess only if a future
chunker actually needs table-splitting behavior the isinstance check can't
express.

**Plan:** do the `from_config` + registry dict in isolation, after item 1
lands, on its own merits — not bundled with page-attribution changes.

---

## Explicitly not planned

- **Hashing scheme for vector collection naming** (`hashlib.sha256` at
  ~2016-2017 instead of `hash_api_key_for_storage`): correct in isolation, but
  changing it changes the collection name derived from every existing API
  key, orphaning already-indexed collections in production. Any fix here
  needs a migration (dual-read old/new collection names, or a one-time
  re-index), not a code change — track separately if/when the pepper rotation
  or hashing scheme is revisited.
- **Hoisting deferred `ai_services`/`retriever_cache` imports to module
  scope**: these read as deliberate circular-import avoidance, not oversight.
  Leave as-is unless someone confirms there's no cycle.
- **Batching `metadata_store.record_chunk` calls**: would need a batch-insert
  API on `FileMetadataStore` first; out of scope for this file alone.

---

## Suggested order

1. **Item 2** (provider-lookup + upload/store dedup) — smallest, independent,
   good first PR.
2. **Characterization tests, then item 1** (merge pipelines at the
   persistence boundary) — ahead of the chunker work; don't start the merge
   itself until the tests (including deletion-during-extraction) are in
   place and passing against the current, unmerged code.
3. **Item 3** (per-extraction result object + registry-based vision/audio
   dispatch) — once upload-acceptance and fallback behavior are pinned down
   by tests.
4. **Item 4** (chunker `from_config` registry) — reassess on its own merits
   after the above land; not blocking, not blocked by, items 1-3.
