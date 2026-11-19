# Hierarchical Chunking — Phased Implementation Plan

Tracks item #13 (Hierarchical Chunking) from `chunking-strategies.md`, the next
item in that document's suggested implementation sequence after Context
Enriched Chunking and Recursive Sentence Chunking (both done).

**Status: done.** Phases 1–3 and the chunker-side generalization in Phase 4
are implemented (`server/services/file_processing/chunking/hierarchical_chunker.py`,
wired into `FileProcessingService`/`FileVectorRetriever`). The one deferred
piece is noted in Phase 4 below: retrieval-time expansion still attaches
only a leaf's immediate parent, not a full chain up to the root.

Earlier drafts of this plan assumed parent-chunk storage/lookup already
existed, that containment could be tracked through two independent
chunking passes, and that attaching context to a result's metadata was
sufficient. All three were wrong; this version fixed them against the
actual code, cited throughout.

## Decision: leaf-only embed, parent-expand on retrieval

1. **Multi-embed** — embed every level as its own searchable vector entry.
   Multiplies embedding/storage cost by the number of levels.
2. **Leaf-only embed, parent-expand on retrieval** — only the finest level is
   embedded/searched; a hit's parent (coarser) text is attached as extra
   context at query time, with no change to embedding cost or ranking.

**Chosen: option 2.**

## Contracts this plan depends on (verified against current code)

### 1. Chunk IDs must be assigned globally, not per sub-chunking call

- `TextChunker._generate_chunk_id(file_id, chunk_index)` returns
  `f"{file_id}_chunk_{chunk_index}"` (`base_chunker.py:121-123`) — deterministic
  from `chunk_index` alone, nothing else.
- `HierarchicalChunker` must chunk each parent's text *independently* (see
  contract #2 below) by calling an inner chunker's `chunk_text()` once per
  parent. Each of those calls restarts its own `chunk_index` at 0 and calls
  `_generate_chunk_id` itself — so leaves from different parents would collide
  on identical ids (`{file_id}_chunk_0`, `{file_id}_chunk_1`, ...) unless
  explicitly fixed up. `chunk_id` is the vector-store id and the
  `metadata_store` primary key, so a collision silently overwrites one leaf
  with another's record.
- **Plan — exact algorithm, all inside `HierarchicalChunker.chunk_text()`,
  before this method returns (i.e. before any encryption or indexing code
  runs):**
  1. Chunk the whole document once with the parent-level chunker → `parents`,
     a list of length `P` with already-unique, already-sequential ids
     `0..P-1` (the inner chunker's own existing final re-indexing pass
     handles this, since it's a single call over the whole document).
  2. For each parent `p` in `parents`, call the leaf-level chunker on just
     `p.text`, producing a locally-indexed list of leaf chunks. Immediately
     pair each with `p.chunk_id` (its future `hierarchy_parent_id`) before
     discarding the inner call's own ids/indices — do not rely on them past
     this point.
  3. Concatenate all parents' leaf lists in document order, then do one
     global re-indexing pass over the concatenation: for the `i`-th leaf
     (0-based across the whole concatenated list), set
     `chunk_index = P + i` and `chunk_id = self._generate_chunk_id(file_id, P + i)`.
  4. Return `parents + reindexed_leaves`. Every id is globally unique and
     every leaf's recorded `hierarchy_parent_id` (see contract #2) points at
     an id that was never itself reassigned.

### 2. The hierarchy link must survive encryption and budget-splitting — use `db_metadata`, not `metadata`

- `_encrypt_chunk_metadata()` (`file_processing_service.py:794-825`) runs
  right after chunking, before indexing, and replaces `chunk.metadata`
  **wholesale** with `{'encrypted': True, 'payload': <hex>}`. Any plaintext
  key placed in `chunk.metadata` (including a hierarchy link) is unreadable
  after this point except by decrypting the whole envelope.
- Worse: `FileVectorRetriever.index_file_chunks()`'s embedding-budget splitter
  (`file_retriever.py:596-669`) builds a split piece's `sub_metadata` as
  `dict(chunk.metadata)` — which, by the time it runs, is already the
  post-encryption envelope — then layers plaintext `parent_chunk_id`/
  `split_index` on top via `.update()`, *without* re-keying the envelope's
  AAD. That dict is never re-encrypted for the general `metadata` field (only
  `db_metadata` gets explicit re-keying — next bullet). So a hierarchy link
  placed in `chunk.metadata` would, for any leaf that also needs
  budget-splitting, become unrecoverable: the stale envelope is still
  AAD-bound to the pre-split chunk's id, but retrieval would try to decrypt
  it using the split piece's own (different) id and fail.
- **`chunk.db_metadata` already has a complete, working mechanism for exactly
  this problem**, built for table cell grids and reusable as-is:
  - `_encrypt_chunk_metadata()` encrypts `chunk.db_metadata` *independently*
    per chunk, same AAD pattern (`file_processing_service.py:823-825`).
  - When a chunk carrying `db_metadata` gets budget-split,
    `index_file_chunks()` explicitly decrypts the envelope under the
    *original* chunk's id and **re-encrypts it under the split piece's own
    new id** (`file_retriever.py:628-653` — comment there already explains
    this exact AAD-mismatch problem and why it's handled for `db_metadata`).
  - Split pieces carrying `db_metadata` are also explicitly persisted via a
    dedicated `metadata_store.record_chunk()` call inside the indexer
    (`file_retriever.py:768-791`), since the caller's pre-split `chunks` list
    never sees the newly-minted split id otherwise.
  - **Plan:** put the hierarchy link in `db_metadata`, not `metadata`:
    - Parent chunks: `db_metadata = {'text': <this parent's own text>}`.
      Parents never reach `index_file_chunks()` (see Phase 2), so they're
      never budget-split; this is a plain encrypt-and-persist case.
    - Leaf chunks: `db_metadata = {'hierarchy_parent_id': <parent's chunk_id>}`.
      If a leaf is later budget-split, the existing re-keying and
      split-piece-recording paths above already handle it correctly with
      *zero* new code — they were written generically, just previously only
      exercised by table chunks.
  - `metadata['level']` (`'parent'`/`'leaf'`) stays in the plain `metadata`
    dict, since it's only ever read in-process, before `_encrypt_chunk_metadata()`
    mutates it (Phase 2 reads it immediately after `_chunk_content()` returns).
- **Small correction from an earlier draft:** it's not true that "no existing
  strategy sets `level`" — `RecursiveChunker` already sets
  `metadata['level']` to an *integer* recursion depth
  (`recursive_chunker.py:246`, `:289`). The accurate claim is that no
  existing strategy sets it to the *string* `'parent'`, which is what Phase 2
  actually checks for.
- **Recovering the link at retrieval:** `FileVectorRetriever._search_collection()`
  already joins `metadata_store.get_chunk_info(chunk_id)` onto every search
  result as `result['chunk_metadata']` (`file_retriever.py:428-430`), and
  `MetadataStore.get_chunk_info()` already JSON-parses the stored
  `chunk_metadata` column back into a dict (`metadata_store.py:432-438`).
  `get_chunk()` (next section) reuses this directly — no new storage or
  query path, only a new caller of what's already there.

### 3. `get_chunk()` must be implemented; it currently just returns `None`

- `FileVectorRetriever.get_chunk(chunk_id)` is a stub:
  `return None` unconditionally (`file_retriever.py:799-802`).
- **Plan:** implement it as: call `self.metadata_store.get_chunk_info(chunk_id)`;
  if its `chunk_metadata` is an encrypted envelope (`{'encrypted': True, ...}`),
  decrypt with the existing `_decrypt_chunk_metadata_envelope(envelope,
  chunk_id.encode())` helper (`file_retriever.py:440-449`) — using the
  *current* row's `chunk_id` as AAD is correct here specifically because
  contract #2's re-keying already guarantees the stored envelope (for both
  plain and budget-split chunks) is AAD-bound to that same row's id; return
  the resulting dict (for a parent lookup, its `'text'` key).

### 4. Deletion must skip vector-store deletes for chunks that were never embedded

- `delete_file_chunks()` builds `chunk_ids` from every row
  `metadata_store.get_file_chunks(file_id)` returns and calls
  `delete_vector()` on all of them unconditionally (`file_retriever.py:836-853`).
  Parent chunks (Phase 2: never embedded) would get a pointless delete call —
  logged as a warning today, not fatal, but not a contract to lean on across
  every vector-store backend.
- **Plan:** `get_file_chunks()` rows carry `vector_store_id` per chunk.
  Filter to `vector_store_id is not None` before the vector-store deletion
  loop. Metadata-store row deletion (already keyed by `file_id` alone, no
  per-row filtering) removes parents for free, unchanged.

### 5. Expansion must land in prompt-visible content, run after truncation, and be bounded

- **Where context actually reaches the model:** `_format_context()` /
  `_format_standard()` in `inference/pipeline/steps/context_retrieval.py`
  build the LLM prompt purely from `doc.get('content', '')`
  (`context_retrieval.py:658`, `:698`); `metadata` is read only for citation
  labels (`source`, `confidence`), never injected as prompt text
  (`context_retrieval.py:699-701`). **A field added only under
  `formatted_item['metadata']` would never reach the model** — confirmed by
  reading the formatter, not assumed. Expansion must instead be appended into
  `formatted_item['content']` itself (clearly delimited, e.g. a labeled
  block ahead of the chunk's own text), with a copy also left in `metadata`
  only if useful for citation/debugging — not as the delivery mechanism.
- **Where expansion runs:** `get_relevant_context()` today formats, then
  truncates to `return_results` (`file_retriever.py:228-234`). Expansion must
  run **after** that truncation, operating only on the final retained list —
  not before. Reason: if expansion ran first and attached a shared parent's
  context to only one representative among several sibling results (to avoid
  redundant lookups), truncation could discard exactly that representative,
  silently losing the context for every surviving sibling. Running expansion
  last guarantees the representative chosen is one that's actually returned.
- **Where to read the recovered link from:** `_format_results()` already sets
  `formatted_item['file_metadata'] = dict(result['chunk_metadata'])` (the row
  `_search_collection()` joined from `metadata_store.get_chunk_info()`), and
  decrypts `file_metadata['chunk_metadata']` in place when it's an encrypted
  envelope (`file_retriever.py:529-535`). Either way — encrypted or not —
  this leaves the leaf's `db_metadata` dict sitting at
  `formatted_result['file_metadata']['chunk_metadata']`. Expansion reads
  `hierarchy_parent_id` from
  `formatted_result['file_metadata']['chunk_metadata']['hierarchy_parent_id']`
  — no new field path, this is exactly where the existing formatter already
  places a decrypted/parsed `db_metadata`.
- **Dedup:** among the final retained results, group by `hierarchy_parent_id`;
  call `get_chunk()` once per unique parent id (not once per result); attach
  that parent's context to one representative result per group (the
  highest-confidence one in that group), not to every sibling redundantly.
- **Budgets, both required, exact numbers set during implementation:**
  - a per-parent cap on how many characters of parent text get attached;
  - a total-request cap across all attached parent contexts combined, so a
    query whose top-k spans many distinct parents can't blow up the prompt.
  Both degrade by truncating the attached text, never by erroring.
- **Missing/failed lookup:** if `get_chunk()` returns `None` or raises,
  skip expansion for that result silently — degrades to today's behavior.
- **No-op for non-hierarchical files:** a result with no `hierarchy_parent_id`
  triggers zero calls to `get_chunk()`.

## Phases

### Phase 1 — `HierarchicalChunker` (chunking layer only)

Add `server/services/file_processing/chunking/hierarchical_chunker.py`
implementing the algorithm in contract #1, producing a flat `list[Chunk]`:
parents first (`metadata['level'] = 'parent'`, `db_metadata = {'text': ...}`),
then leaves (`metadata['level'] = 'leaf'`,
`db_metadata = {'hierarchy_parent_id': <parent chunk_id>}`). Two levels only
for Phase 1 (see Phase 4). Wire in as `chunking_strategy: "hierarchical"` in
`file_processing_service.py:_init_chunker()`.

**Verify:**
- All chunk ids/indices are globally unique across the whole output, parents
  and leaves together — explicitly assert no duplicates, since this is the
  exact bug contract #1 exists to prevent.
- Every leaf's `db_metadata['hierarchy_parent_id']` resolves to a real
  parent's `chunk_id` in the same output list.
- Per-level coverage, checked separately per the chunker's own whitespace
  normalization policy: concatenating one parent's own leaf children
  reconstructs that parent's text — not a single "parent + leaf reconstructs
  the source" check, which double-counts content present at both levels by
  design.
- Repeated text across different parents does not cause a leaf to resolve to
  the wrong parent (containment is structural — each parent's leaves are
  chunked from only that parent's own text slice — so this should hold by
  construction; test it to confirm).
- A file shorter than the leaf chunk size yields one parent with one leaf
  child, not degenerate/empty output.

### Phase 2 — Indexing: embed leaves only, persist parent text unembedded

- In `file_processing_service.py`, immediately after `_chunk_content()`
  returns and *before* `_encrypt_chunk_metadata()` runs, split `chunks` by
  `metadata.get('level') == 'parent'` (an exact string match — existing
  strategies that set an integer `level`, e.g. `RecursiveChunker`, are
  unaffected since `0 == 'parent'` is false). This must be a no-op for every
  existing strategy.
- Only non-parent chunks go to `_index_chunks_in_vector_store()` /
  `index_file_chunks()` for embedding.
- All chunks (parent and leaf) still go through the existing
  `metadata_store.record_chunk()` loop (`file_processing_service.py:981-990`),
  which already passes `metadata=chunk.db_metadata if chunk.db_metadata is not
  None else chunk.metadata` — no change needed there. Only change: parent
  chunks pass `vector_store_id=None` instead of `chunk.chunk_id`.
- No changes needed to `_encrypt_chunk_metadata()` itself or to the
  budget-split/re-keying code — contract #2 established both already handle
  `db_metadata` correctly for this exact shape.

**Verify:**
- Indexing a file with `hierarchical` strategy produces vector-store entries
  only for leaf chunks.
- `metadata_store.get_file_chunks(file_id)` still returns parent rows, each
  with `vector_store_id is None`.
- Encrypted upload round-trip: a parent's `db_metadata['text']` is only
  readable through the encryptor; `get_chunk()` (Phase 3) recovers it
  correctly end to end.
- A leaf chunk that is itself oversized for the embedding budget still gets
  split by the existing budget-split path, and the resulting pieces each
  resolve `hierarchy_parent_id` correctly via `get_chunk()` — this is the
  concrete regression test for contract #2's re-keying claim, not just a
  read of the code.

### Phase 3 — Retrieval-time parent expansion

- Implement `FileVectorRetriever.get_chunk(chunk_id)` per contract #3.
- In `get_relevant_context()`, after the existing `return_results` truncation
  (`file_retriever.py:230-234`): group the final results by
  `hierarchy_parent_id`, look up each unique parent once via `get_chunk()`,
  and attach its (length-capped) text into one representative result's
  `content` per group, per contract #5. Cap both per-parent and total-request
  attached length.
- Non-hierarchical results (no `hierarchy_parent_id`) pass through untouched,
  with zero `get_chunk()` calls.

**Verify:**
- A query matching a leaf chunk returns a result whose `content` includes
  the expected parent text, capped at the stated per-parent limit.
- Two final results sharing a parent produce exactly one `get_chunk()` call
  **and** exactly one of them carries the attached context (not zero, not
  both) — test both assertions, not just the call count.
- A non-hierarchical file's query path makes zero `get_chunk()` calls.
- Encrypted-file expansion round-trips end to end (upload → index → query →
  decrypted parent context in the final prompt-bound content).
- A `hierarchy_parent_id` pointing at a since-deleted/missing parent returns
  normally, with no attached context and no error.
- A request whose final results span enough distinct parents to exceed the
  total-request budget truncates/omits the excess rather than growing
  unbounded.

### Phase 4 — More than two levels

**Done, scoped to the chunker side.** `HierarchicalChunker` takes an optional
`intermediate_chunk_sizes: list[int]` (non-increasing from `parent_chunk_size`,
each `>= leaf_chunk_size`) to insert one or more additional parent levels
between the top parent and the leaf level. Every non-leaf level uses the same
`metadata['level'] = 'parent'` string (so `file_processing_service.py`'s
`== 'parent'` check and the never-embedded/never-vector-deleted handling in
Phase 2 apply uniformly to all of them, with no changes needed there), and
carries `db_metadata = {'text': ..., 'hierarchy_parent_id': <its own
parent's chunk_id>}` — except the top level, which omits
`hierarchy_parent_id` since it has no parent. ids are assigned level by
level: each level is globally re-indexed immediately after being built
(before being used as the parent for the next level), generalizing
contract #1's two-level re-indexing.

**Not done — beyond one parent hop in expansion.** Retrieval-time expansion
(`_expand_hierarchical_parents`) still only attaches a leaf's *immediate*
parent (whatever level that is), one `get_chunk()` call per unique
immediate parent, as it already did for two levels. Grandparent chaining
(attaching the immediate parent's own parent too) is still deferred —
revisit only once there's a concrete need for it, since it adds expansion-
budget accounting across more than one level.

## Out of scope for this plan

- Multi-embed retrieval (option 1 above) — revisit only if leaf-only search
  proves to miss coarse-grained queries in practice.
- Cross-file hierarchy, or hierarchy spanning adapters — this plan is
  file-adapter-scoped, matching every other chunking strategy.
- Table chunks (`_extract_tables_as_chunks`) — these are appended to `chunks`
  independently of whatever `chunking_strategy` produced the prose chunks and
  keep their existing, separate `db_metadata` (cell grid) use; hierarchy
  chunking only ever applies to the prose chunks a `hierarchical`-strategy
  chunker produces.
