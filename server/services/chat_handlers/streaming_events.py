"""
Structured streaming-event contract for the client-facing SSE stream produced
by `PipelineChatService.process_chat_stream`.

Step 2 ("Define the contract") of
docs/roadmap/pipeline-streaming-structured-events.md, under scope (a)
(route/protocol-layer only, per that document's "Open decision"): this module
defines a discriminated union covering every payload shape that
`PipelineChatService.process_chat_stream` currently yields as an SSE
`data: {...}\\n\\n` string (see the yield-point inventory in
`server/tests/test_services/test_streaming_contract_characterization.py` and
`server/tests/chat_handlers/test_streaming_handler.py`), plus a formatter
that reproduces today's exact SSE string for each event.

Nothing in this module changes runtime behavior yet — `PipelineChatService`,
`StreamingHandler`, `openai_stream_generator`, and `a2a_routes.py` are not
wired to it (that is step 3 onward). `Pipeline.process_stream`'s internal
JSON envelopes are out of scope under (a) and are not represented here.
`/v1/chat` itself is also out of scope — it relays the SSE string it
receives without parsing it at all and has nothing to gain from this
contract — but the specific *chunk shape* it relays unparsed (a pipeline
chunk that failed `json.loads`) is the same shape `openai_stream_generator`
and `a2a_routes.py` would hit once migrated, so it is represented below as
`RawEvent`.

## Terminal-event and ordering rules (current behavior, unchanged)

- `ResponseEvent` and `AudioChunkEvent` may repeat any number of times, in
  any interleaving (audio chunk completion order is not synchronized with
  text chunk order beyond each audio chunk's own `chunk_index`).
- Exactly one of `ErrorEvent` or `DoneEvent` terminates the stream normally.
- **Exception: cancellation.** If the stream is cancelled via `cancel_event`
  (either mid-relay in `_consume_pipeline_stream`, or after the pipeline
  finishes but before post-stream persistence in `process_chat_stream`), the
  stream ends with **no terminal event at all** — it is truncated, not
  closed with a `DoneEvent`. This preserves today's actual behavior
  (see `test_consume_pipeline_stream_cancelled_mid_stream_emits_no_done_chunk`);
  it is a known quirk, not a design choice made here.
- `DoneEvent`'s optional fields vary by source: a cache hit only ever sets
  `sources`/`metadata`; a safety-filter refusal or non-binary skill response
  sets none of them (bare `{"done": true}`); a normal pipeline completion
  goes through `StreamingHandler.build_done_chunk` and may set any of the
  audio/image/video/document/threading fields. `metadata` is cache-only —
  `build_done_chunk` never sets it, and cache hits never set the
  audio/image/video/document/threading fields. A `DoneEvent` will not have
  both populated in practice, but the type does not forbid it.
- **Non-JSON chunks are not an edge case to reject.** `StreamingHandler.
  process_stream` relays a pipeline chunk unchanged when `json.loads` fails
  on it (streaming_handler.py:397-400), and `PipelineChatService` forwards
  that SSE string to the client as-is. `RawEvent` represents this — use
  `parse_stream_chunk` (not `parse_stream_payload`, which assumes the chunk
  already parsed as JSON) when classifying a chunk straight from the
  pipeline stream, so this path round-trips instead of raising.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass(frozen=True)
class ResponseEvent:
    """A text delta. Wire shape: {"response": str, ...extra}.

    `extra` carries every additional field a producer put on the response
    payload beyond `response` — including `done`, and including its
    *absence* — same rationale as `ErrorEvent.extra`. The legacy code
    relayed non-terminal chunks byte-for-byte regardless of their exact
    shape, so nothing here may assume `done` (or any other field) is
    present, absent, or any particular value.
    """
    text: str
    extra: dict[str, Any] = field(default_factory=dict)
    raw: Optional[str] = None
    """The exact original chunk text (pre-json.loads), when this event was
    parsed from a producer's chunk rather than synthesized internally. When
    set, `format_stream_event` relays `raw` verbatim instead of
    re-serializing `text`/`extra` — the legacy code relayed the untouched
    upstream string, and json.dumps is not guaranteed to reproduce its exact
    whitespace/key-order. `stream_event_to_dict` (used by process_stream_raw,
    which already yields the parsed dict rather than a JSON string) ignores
    `raw` — there is no serialization step for it to affect there.
    """


@dataclass(frozen=True)
class AudioChunkEvent:
    """A mid-stream TTS audio chunk.
    Wire shape: {"audio_chunk": str, "audioFormat": str, "chunk_index": int, "done": false}.

    No `.raw`/`extra` fields, unlike `ResponseEvent`/`ErrorEvent`: this dict
    is always built fresh in-process by `StreamingHandler` itself (from TTS
    output), never parsed from an external producer's JSON text, so there is
    no original serialization to lose or reproduce. The legacy code
    re-serialized it with `json.dumps` too — see
    `test_audio_chunk_matches_streaming_handler_format` for the exact key
    order both agree on.
    """
    audio_chunk: str
    audio_format: str
    chunk_index: int


@dataclass(frozen=True)
class ErrorEvent:
    """A terminal error. Wire shape: {"error": str, ...extra}.

    `extra` carries every additional field a producer put on the error
    payload beyond `error` — including `done`, and including its *absence*.
    The legacy code relayed error chunks byte-for-byte, so this must too:
    `{"error": "x"}` (no `done` at all — see test_process_stream_handles_
    errors) and `{"error": "x", "done": false}` are both real, currently
    valid inputs, not just the common `{"error": "x", "done": true}` shape.
    There is no default-filling of `done` anywhere in this module — a
    caller that synthesizes an ErrorEvent internally (rather than parsing
    one from a producer's payload) is responsible for putting `done` in
    `extra` itself if it wants it present, exactly like the legacy code's
    own hand-built `{"error": ..., "done": True}` dicts did.
    """
    error: str
    extra: dict[str, Any] = field(default_factory=dict)
    raw: Optional[str] = None
    """See `ResponseEvent.raw` — same rationale, same relay-verbatim behavior
    in `format_stream_event`."""


@dataclass(frozen=True)
class RawEvent:
    """A pipeline chunk that failed `json.loads` and is relayed unchanged.

    `StreamingHandler.process_stream` deliberately does this
    (streaming_handler.py:397-400, `except json.JSONDecodeError`) rather than
    dropping the chunk or erroring, and `PipelineChatService` then relays that
    SSE string to the client as-is. There is no structured form to recover
    here — `raw` is the exact chunk content as it arrived, pre-json.loads.
    """
    raw: str


@dataclass(frozen=True)
class DoneEvent:
    """A terminal, successful completion. Wire shape: {"done": true, ...optional fields}.

    See the module docstring for which fields co-occur in practice.

    No `.raw` field, unlike `ResponseEvent`/`ErrorEvent`: as of Step 3
    (`StreamingHandler`), nothing constructs a `DoneEvent` at all — the
    pipeline's own done-marker chunk is deliberately swallowed (accumulated
    into `StreamingState`, never yielded), matching the legacy code exactly.
    `DoneEvent` exists for Step 4+, when `PipelineChatService`'s hand-built
    done dicts (cache hit, safety-filter refusal, `build_done_chunk`) get
    converted — those are themselves freshly constructed in-process, like
    `AudioChunkEvent`, not parsed from an external chunk, so the same
    no-raw-needed reasoning should still apply there; re-verify this
    assumption when Step 4 is implemented rather than carrying it over
    unchecked.
    """
    sources: Optional[list[dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None
    total_audio_chunks: Optional[int] = None
    assistant_message_id: Optional[str] = None
    model: Optional[str] = None
    threading: Optional[dict[str, Any]] = None
    audio: Optional[str] = None
    audio_format: Optional[str] = None
    image: Optional[str] = None
    image_format: Optional[str] = None
    image_revised_prompt: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    video_format: Optional[str] = None
    video_revised_prompt: Optional[str] = None
    document_url: Optional[str] = None
    document_format: Optional[str] = None
    document_revised_prompt: Optional[str] = None
    generated_audio_url: Optional[str] = None
    generated_audio_format: Optional[str] = None
    generated_audio_revised_prompt: Optional[str] = None


StreamEvent = Union[ResponseEvent, AudioChunkEvent, ErrorEvent, DoneEvent, RawEvent]


class UnknownStreamPayloadError(ValueError):
    """Raised when a payload dict matches none of the known event shapes.

    Surfacing this loudly (rather than silently coercing) is the point: the
    roadmap doc explicitly warns the proposed union might not cover every
    existing shape, and any gap needs to be caught here before it is trusted
    as complete.
    """


def parse_stream_payload(payload: dict[str, Any]) -> StreamEvent:
    """Classify an already-json.loads'd SSE payload dict into a StreamEvent.

    Discriminator order matters: audio chunks and error/done chunks all
    happen to have a `"done"` key, so `"error"` and `"audio_chunk"` are
    checked before falling back to the generic done/response split.
    """
    if "error" in payload:
        return ErrorEvent(
            error=payload["error"],
            extra={k: v for k, v in payload.items() if k != "error"},
        )

    if "audio_chunk" in payload:
        return AudioChunkEvent(
            audio_chunk=payload["audio_chunk"],
            audio_format=payload.get("audioFormat", "opus"),
            chunk_index=payload["chunk_index"],
        )

    if payload.get("done") is True:
        return DoneEvent(
            sources=payload.get("sources"),
            metadata=payload.get("metadata"),
            total_audio_chunks=payload.get("total_audio_chunks"),
            assistant_message_id=payload.get("assistant_message_id"),
            model=payload.get("model"),
            threading=payload.get("threading"),
            audio=payload.get("audio"),
            audio_format=payload.get("audioFormat"),
            image=payload.get("image"),
            image_format=payload.get("image_format"),
            image_revised_prompt=payload.get("image_revised_prompt"),
            image_url=payload.get("image_url"),
            video_url=payload.get("video_url"),
            video_format=payload.get("video_format"),
            video_revised_prompt=payload.get("video_revised_prompt"),
            document_url=payload.get("document_url"),
            document_format=payload.get("document_format"),
            document_revised_prompt=payload.get("document_revised_prompt"),
            generated_audio_url=payload.get("generated_audio_url"),
            generated_audio_format=payload.get("generated_audio_format"),
            generated_audio_revised_prompt=payload.get("generated_audio_revised_prompt"),
        )

    if "response" in payload:
        return ResponseEvent(
            text=payload["response"],
            extra={k: v for k, v in payload.items() if k != "response"},
        )

    raise UnknownStreamPayloadError(f"Unrecognized stream payload shape: {sorted(payload.keys())}")


def parse_stream_chunk(chunk: str) -> StreamEvent:
    """Classify a raw pipeline chunk (pre-json.loads) into a StreamEvent.

    This is the entry point that mirrors what StreamingHandler.process_stream
    actually receives from the pipeline stream: a `json.JSONDecodeError`
    here is not a bug to propagate, it is the existing raw-relay path
    (streaming_handler.py:397-400), so it maps to `RawEvent` rather than
    raising.
    """
    try:
        payload = json.loads(chunk)
    except json.JSONDecodeError:
        return RawEvent(raw=chunk)
    event = parse_stream_payload(payload)
    if isinstance(event, (ResponseEvent, ErrorEvent)):
        event = dataclasses.replace(event, raw=chunk)
    return event


def stream_event_to_dict(event: StreamEvent) -> dict[str, Any]:
    """Render a StreamEvent's wire payload as a dict (no SSE framing).

    Raises TypeError for `RawEvent` — by definition it has no structured
    dict form (that's the whole reason it exists); callers that need a dict
    per event (e.g. `process_stream_raw`) must handle `RawEvent` themselves,
    same as the legacy code they replace does.
    """
    if isinstance(event, RawEvent):
        raise TypeError("RawEvent has no dict form — it is an unparseable relayed chunk")
    if isinstance(event, ErrorEvent):
        payload: dict[str, Any] = {"error": event.error, **event.extra}
    elif isinstance(event, AudioChunkEvent):
        payload = {
            "audio_chunk": event.audio_chunk,
            "audioFormat": event.audio_format,
            "chunk_index": event.chunk_index,
            "done": False,
        }
    elif isinstance(event, ResponseEvent):
        payload = {"response": event.text, **event.extra}
    elif isinstance(event, DoneEvent):
        payload = {"done": True}
        if event.sources:
            payload["sources"] = event.sources
        if event.total_audio_chunks:
            payload["total_audio_chunks"] = event.total_audio_chunks
        if event.assistant_message_id:
            payload["assistant_message_id"] = event.assistant_message_id
        if event.model:
            payload["model"] = event.model
        if event.threading:
            payload["threading"] = event.threading
        if event.audio:
            payload["audio"] = event.audio
            payload["audioFormat"] = event.audio_format or "mp3"
        if event.image:
            payload["image"] = event.image
            payload["image_format"] = event.image_format or "png"
            if event.image_revised_prompt:
                payload["image_revised_prompt"] = event.image_revised_prompt
            if event.image_url:
                payload["image_url"] = event.image_url
        if event.video_url:
            payload["video_url"] = event.video_url
            payload["video_format"] = event.video_format or "mp4"
            if event.video_revised_prompt:
                payload["video_revised_prompt"] = event.video_revised_prompt
        if event.document_url:
            payload["document_url"] = event.document_url
            payload["document_format"] = event.document_format or "pdf"
            if event.document_revised_prompt:
                payload["document_revised_prompt"] = event.document_revised_prompt
        if event.generated_audio_url:
            payload["generated_audio_url"] = event.generated_audio_url
            payload["generated_audio_format"] = event.generated_audio_format or "mp3"
            if event.generated_audio_revised_prompt:
                payload["generated_audio_revised_prompt"] = event.generated_audio_revised_prompt
        # metadata is cache-hit-only and never co-occurs with the fields above
        # in practice, but is included here for completeness.
        if event.metadata:
            payload["metadata"] = event.metadata
    else:
        raise TypeError(f"Unknown StreamEvent type: {type(event)!r}")

    return payload


def format_stream_event(event: StreamEvent) -> str:
    """Render a StreamEvent back to the exact SSE string the client sees
    today: "data: {json}\\n\\n".

    For `RawEvent`, and for a `ResponseEvent`/`ErrorEvent` that carries the
    original chunk text in `.raw` (i.e. it was parsed from a producer's
    chunk, not synthesized internally), this relays that text verbatim —
    `json.dumps` is not guaranteed to reproduce the source's exact
    whitespace or key order, and the legacy code never re-serialized these.
    Only events with no `.raw` (synthesized internally, or hand-built for a
    test/other caller) go through `stream_event_to_dict` + `json.dumps`.
    """
    if isinstance(event, RawEvent):
        return f"data: {event.raw}\n\n"
    if isinstance(event, (ResponseEvent, ErrorEvent)) and event.raw is not None:
        return f"data: {event.raw}\n\n"
    return f"data: {json.dumps(stream_event_to_dict(event))}\n\n"
