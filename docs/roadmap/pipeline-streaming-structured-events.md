# Pipeline Streaming Structured-Event Contract

## Summary

This item is spun out from Phase 4 of
`docs/roadmap/complete/routes-configurator-cleanup.md`, which found that the
per-chunk `json.loads` in `routes_configurator.py`'s `openai_stream_generator`
cannot be removed as a routes-layer change: there is no structured dict
sitting one layer below the SSE string it parses. This document scopes the
pipeline-wide refactor needed to remove the remaining round trips, without
implementing it: it requires sign-off from whoever owns
`PipelineChatService`/`StreamingHandler`, given the size of the change and
the number of consumers it touches.

**Not started. No code changes from this document. Scoping only — not yet
specified enough to schedule as tasks (see "What's missing" below).**

## Problem corrected

An earlier draft of this document claimed a chunk is serialized and
re-parsed three times, with two internal round trips inside the service
layer. That overstated the cost. Tracing the actual code:

1. `inference/pipeline/pipeline.py` (`Pipeline.process_stream`) and its steps
   `yield` JSON strings (not yet SSE-framed) — e.g.
   `json.dumps({"response": ..., "done": ...})`. **One serialize.**
2. `StreamingHandler.process_stream` (`services/chat_handlers/streaming_handler.py:238`)
   `json.loads()`s each chunk once, to update `StreamingState` bookkeeping
   (accumulated text, audio chunking, done-marker handling) — but then
   **forwards the original string unchanged**, wrapped in SSE framing:
   `yield f"data: {chunk}\n\n", state` (`streaming_handler.py:285`). It does
   not re-serialize the parsed dict. **One parse, no re-serialize.**
3. `PipelineChatService._consume_pipeline_stream`
   (`services/pipeline_chat_service.py:1147`) and `process_chat_stream`
   **relay** that SSE string as-is via `yield chunk` — no parse, no
   serialize, on the main relay path. (Other yield points in
   `process_chat_stream` and `_process_post_stream` construct their own SSE
   strings directly from data they already have, which is not a round trip —
   there is no pre-existing structured form to reuse there.)
4. `/v1/chat`'s native streaming path (`routes/routes_configurator.py:538-553`)
   **relays the SSE string directly to the client with no parsing at all** —
   confirmed by reading `stream_generator()`, which does
   `async for chunk in chat_service.process_chat_stream(...): yield chunk`.
5. `openai_stream_generator` (`routes/routes_configurator.py:614+`) and
   `a2a_routes.py:378` each parse the SSE string once, to convert it into
   their own protocol's chunk format, and then re-serialize their own
   output.

So the accurate picture: **`/v1/chat` has zero extra round trips** beyond the
current pipeline serialization at the pipeline source and the one parse
inside `StreamingHandler` (which is needed regardless, to maintain
`StreamingState`) — option (b) below would remove even that serialization,
so it is not strictly unavoidable, just present in the pipeline as it
exists today. The OpenAI-compatible and A2A endpoints each add one
additional parse-and-reserialize at their protocol boundary, which is the
real, narrower cost this refactor would remove — not a threefold round trip
across the whole request path.

## What's already available and underused

`StreamingHandler.process_stream_raw` (`streaming_handler.py:447`) already
returns structured dicts instead of SSE strings — but its current
implementation gets there by calling `process_stream` and re-parsing its SSE
output (`chunk_json = formatted_chunk[6:].strip(); json.loads(...)`), i.e. it
adds a round trip to produce the structured form that `process_stream`
internally already had before framing it as SSE. The natural direction is to
invert this: make the structured/dict form canonical inside
`StreamingHandler`, and make `process_stream` a thin SSE-formatting wrapper
around it, rather than adding a third sibling method that duplicates the
API surface.

## Why this still needs a separate, larger scope

- **Every yield point, not one.** Both `StreamingHandler.process_stream` and
  `PipelineChatService.process_chat_stream` have multiple distinct yield
  sites (cache-hit shortcut, safety-filter refusal, non-streaming skill
  results, the main pipeline relay loop, post-stream warning/audio/done
  chunks). A structured-event contract has to cover all of them consistently.
- **Three consumers, two of which actually benefit.** `/v1/chat` should stay
  on the SSE-string wrapper — it doesn't parse today and gains nothing from
  migrating. `openai_stream_generator` and `a2a_routes.py` are the two
  consumers with a real parse-then-reserialize cost to remove.
- **The done-chunk payload has one builder but several input sources.**
  `StreamingHandler.build_done_chunk()` (`streaming_handler.py:566`) already
  centrally constructs the done payload from `StreamingState` plus explicit
  arguments — it is not scattered across three separate dict-building sites.
  What a structured contract needs to settle is where each of its inputs
  (sources/metadata assembled in `PipelineChatService`, the audio remainder
  computed in `_process_post_stream`, threading metadata resolved elsewhere)
  gets assembled *before* being handed to the builder, so the builder's
  input shape is itself well-defined rather than an ad hoc kwargs list.
- **The proposed event contract is not yet specified.** A `chunk | error |
  done` discriminated union does not obviously cover audio chunks, generated
  media (image/video/document) fields, mid-stream warnings, sources, or
  model/assistant IDs seen in existing payloads. The exact union, terminal-
  event rules, ordering guarantees, and cancellation/error semantics need to
  be written out before any task breakdown, or the migration will discover
  missing cases mid-implementation. In particular, "exactly one terminal
  event per stream" is not today's actual behavior: both
  `_consume_pipeline_stream` (`pipeline_chat_service.py:780`) and
  `process_chat_stream` (`pipeline_chat_service.py:1208`) `return` on a set
  `cancel_event` with no done chunk sent at all. The spec must either state
  the rule as "exactly one terminal event, except cancellation, which ends
  the stream with none" (preserving current behavior) or explicitly decide
  to add a terminal cancellation event as an intentional behavior change —
  it must not silently assume the exactly-one rule holds today.
- **Scope decision not yet made.** Removing only the OpenAI/A2A boundary
  parse (route-layer benefit) is a materially smaller change than also
  converting `Pipeline.process_stream`'s current JSON-envelope construction
  to structured events (removing `StreamingHandler`'s parse of those
  envelopes too). This document does not decide between them — see "Open
  decision" below.

## Proposed sequence

1. **Inventory.** Snapshot every existing payload shape and ordering
   behavior across all yield points in `StreamingHandler.process_stream` and
   `PipelineChatService.process_chat_stream`/`_process_post_stream` (text,
   errors, safety-filter blocks, cache hits, audio chunks, generated media,
   warnings, sources, threading metadata, cancellation) as characterization
   tests, before changing anything.
2. **Define the contract.** Write the discriminated union (or dataclass
   hierarchy) covering every shape from step 1, plus terminal-event and
   ordering rules, and a single SSE formatter function.
3. **Make structured processing canonical in `StreamingHandler`.** Turn
   `process_stream`'s current body into the structured-event producer, and
   make both `process_stream` (SSE) and `process_stream_raw` (dicts) thin
   wrappers around it — removing `process_stream_raw`'s current
   parse-the-SSE-output implementation.
4. **Add `PipelineChatService.process_chat_stream_events`** as the canonical
   structured producer, with `process_chat_stream` becoming its SSE-wrapper
   for backward compatibility.
5. **Migrate consumers selectively.** Keep `/v1/chat` on
   `process_chat_stream` (the SSE wrapper) — it has nothing to gain from
   structured events. Migrate `openai_stream_generator` and `a2a_routes.py`
   to `process_chat_stream_events`, removing their `json.loads` entirely.
6. **Decide separately whether to convert `Pipeline.process_stream`**
   (the lowest layer) to yield structured events too, removing
   `StreamingHandler`'s remaining parse of its JSON envelopes. Only take
   this step if profiling or a maintainability argument justifies it — see
   "Open decision" below.
7. **Parity tests** covering text, errors, blocking, cache hits, audio,
   generated media, cancellation (including the no-terminal-event-on-cancel
   case), sources, and threading metadata, run against both the old and new
   paths before deleting the old ones.
8. **Deletion criteria.** The public SSE-producing entry points
   (`process_chat_stream` for `/v1/chat`, and the equivalent formatter at
   whatever boundary replaces it) must remain — `/v1/chat` has no reason to
   stop consuming SSE. What should disappear is the *duplicated* inline SSE
   construction inside `PipelineChatService`/`StreamingHandler` once a single
   formatter owns it, and the parse-to-recover-structure paths in
   `openai_stream_generator`, `a2a_routes.py`, and
   `process_stream_raw`'s current re-parse-of-SSE implementation — not all
   SSE-string-yielding code.

## Open decision

Is the goal:
- **(a) Route/protocol-layer maintainability only** — remove the
  OpenAI/A2A boundary parse-and-reserialize, leave `/v1/chat` and the
  pipeline's lowest layer untouched (steps 1-5 above only), or
- **(b) Structured events throughout the pipeline** — also convert
  `Pipeline.process_stream` (step 6), eliminating `StreamingHandler`'s
  parse entirely.

(a) is a materially smaller, lower-risk change. (b) is more thorough, but
does not necessarily touch every pipeline step's streaming implementation:
`LLMInferenceStep.process_stream` and `MCPAgentStep.process_stream`
(`inference/pipeline/steps/llm_inference.py`, `mcp_agent.py`) already yield
plain text, not JSON envelopes — it is `Pipeline.process_stream`
(`inference/pipeline/pipeline.py`) that wraps each step's text output into
the `json.dumps({"response": ..., "done": ...})` envelopes. Option (b) may
be largely containable to `pipeline.py` and its direct consumers, though
this needs confirming against every step type (not just these two) before
committing to that scope. Either way it should only be taken on if there's a
measured performance reason, not a purely aesthetic one — the current cost
at that layer is one `json.loads` per chunk with no re-serialize, which is
inexpensive.

## What's missing before this can be scheduled as tasks

- A decision between (a) and (b) above.
- The actual discriminated-event-type specification (not the placeholder
  `chunk | error | done` sketch from the earlier draft).
- Confirmation of whether any consumer of `StreamingHandler.process_stream`
  or `Pipeline.process_stream` exists beyond `PipelineChatService` (e.g.
  WebSocket paths — `process_stream_raw`'s docstring mentions "internal/
  WebSocket use", implying there may be one not yet checked here).
- Profiling data, if scope (b) is chosen, justifying the wider change.

## Recommendation

Do not schedule implementation from this document. It correctly identifies
that the change is real but narrower and less costly than first framed, and
that further specification work (event contract, scope decision, consumer
audit) is needed before task breakdown. Whoever owns
`PipelineChatService`/`StreamingHandler`/`inference/pipeline/` should resolve
the open decision and event-contract spec, then turn this into a phased,
task-level plan with characterization tests as the first deliverable.
