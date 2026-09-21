"""
Tests for the structured streaming-event contract (streaming_events.py).

Step 2 ("Define the contract") of
docs/roadmap/pipeline-streaming-structured-events.md. These tests check two
things for every payload shape in the inventory (step 1): parse_stream_payload
classifies it correctly, and format_stream_event reproduces the exact SSE
string the current hand-built code produces — so wiring this in later (step
3+) is guaranteed not to change any consumer-visible bytes.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.chat_handlers.streaming_events import (
    AudioChunkEvent,
    DoneEvent,
    ErrorEvent,
    RawEvent,
    ResponseEvent,
    UnknownStreamPayloadError,
    format_stream_event,
    parse_stream_chunk,
    parse_stream_payload,
    stream_event_to_dict,
)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class TestParseStreamPayload:
    def test_response_chunk(self):
        assert parse_stream_payload({"response": "hi", "done": False}) == ResponseEvent(
            text="hi", extra={"done": False}
        )

    def test_response_chunk_without_done_preserves_its_absence(self):
        assert parse_stream_payload({"response": "hi"}) == ResponseEvent(text="hi", extra={})

    def test_error_chunk(self):
        assert parse_stream_payload({"error": "boom", "done": True}) == ErrorEvent(
            error="boom", extra={"done": True}
        )

    def test_error_chunk_without_done_preserves_its_absence(self):
        # {"error": "x"} with no "done" key at all is a real, valid input
        # (see test_process_stream_handles_errors) — must not gain one.
        assert parse_stream_payload({"error": "boom"}) == ErrorEvent(error="boom", extra={})

    def test_error_chunk_preserves_extra_fields(self):
        event = parse_stream_payload({"error": "rate limited", "status": 429, "done": True})
        assert event == ErrorEvent(error="rate limited", extra={"status": 429, "done": True})

    def test_audio_chunk(self):
        event = parse_stream_payload({
            "audio_chunk": "YmFzZTY0", "audioFormat": "mp3", "chunk_index": 2, "done": False,
        })
        assert event == AudioChunkEvent(audio_chunk="YmFzZTY0", audio_format="mp3", chunk_index=2)

    def test_bare_done_chunk(self):
        assert parse_stream_payload({"done": True}) == DoneEvent()

    def test_cache_hit_done_chunk(self):
        event = parse_stream_payload({
            "done": True, "sources": [{"title": "doc1"}], "metadata": {"cached": True},
        })
        assert event == DoneEvent(sources=[{"title": "doc1"}], metadata={"cached": True})

    def test_full_done_chunk_with_image(self):
        event = parse_stream_payload({
            "done": True,
            "assistant_message_id": "msg-1",
            "model": "gpt-4o",
            "threading": {"thread_id": "t1"},
            "image": "base64img",
            "image_format": "png",
            "image_revised_prompt": "a cat",
            "image_url": "https://example.com/cat.png",
        })
        assert event == DoneEvent(
            assistant_message_id="msg-1",
            model="gpt-4o",
            threading={"thread_id": "t1"},
            image="base64img",
            image_format="png",
            image_revised_prompt="a cat",
            image_url="https://example.com/cat.png",
        )

    def test_unrecognized_shape_raises(self):
        with pytest.raises(UnknownStreamPayloadError):
            parse_stream_payload({"some_new_field": 1})


class TestParseStreamChunk:
    """parse_stream_chunk takes the raw pre-json.loads chunk, matching what
    StreamingHandler.process_stream actually receives from the pipeline."""

    def test_valid_json_chunk_delegates_to_parse_stream_payload(self):
        chunk = json.dumps({"response": "hi", "done": False})
        assert parse_stream_chunk(chunk) == ResponseEvent(text="hi", extra={"done": False}, raw=chunk)

    def test_valid_json_chunk_carries_original_text_in_raw(self):
        # Attaching .raw is what lets format_stream_event relay the chunk
        # byte-for-byte instead of re-serializing it (which json.dumps does
        # not guarantee reproduces the source's exact whitespace/key order).
        chunk = '{"response":"hi","done":false}'  # deliberately no spaces
        event = parse_stream_chunk(chunk)
        assert event.raw == chunk

    def test_unparseable_chunk_becomes_raw_event(self):
        # Matches streaming_handler.py's `except json.JSONDecodeError` relay path.
        assert parse_stream_chunk("not valid json") == RawEvent(raw="not valid json")


class TestFormatStreamEvent:
    def test_response_matches_pipeline_chat_service_format(self):
        # Matches pipeline_chat_service.py's `{'response': ..., 'done': False}`
        assert format_stream_event(ResponseEvent(text="hi", extra={"done": False})) == _sse(
            {"response": "hi", "done": False}
        )

    def test_response_without_extra_omits_done(self):
        assert format_stream_event(ResponseEvent(text="hi")) == _sse({"response": "hi"})

    def test_response_with_raw_relays_original_text_verbatim(self):
        # No spaces after ':' — default json.dumps would add them. .raw must
        # win so the exact upstream bytes are preserved, not just the fields.
        raw_chunk = '{"response":"hi","done":false}'
        event = ResponseEvent(text="hi", extra={"done": False}, raw=raw_chunk)
        assert format_stream_event(event) == f"data: {raw_chunk}\n\n"

    def test_error_with_raw_relays_original_text_verbatim(self):
        raw_chunk = '{"error":"boom"}'
        event = ErrorEvent(error="boom", raw=raw_chunk)
        assert format_stream_event(event) == f"data: {raw_chunk}\n\n"

    def test_error_matches_pipeline_chat_service_format(self):
        assert format_stream_event(ErrorEvent(error="boom", extra={"done": True})) == _sse(
            {"error": "boom", "done": True}
        )

    def test_error_without_extra_omits_done(self):
        # No auto-filling of "done" — a caller that wants it present must put
        # it in `extra` itself, same as the legacy hand-built dicts did.
        assert format_stream_event(ErrorEvent(error="boom")) == _sse({"error": "boom"})

    def test_error_with_extra_fields_round_trips(self):
        event = ErrorEvent(error="rate limited", extra={"status": 429, "done": True})
        assert format_stream_event(event) == _sse({"error": "rate limited", "status": 429, "done": True})

    def test_audio_chunk_matches_streaming_handler_format(self):
        # Matches the dict built in streaming_handler.py's _generate_sentence_audio
        # (key order: audio_chunk, audioFormat, chunk_index, done).
        event = AudioChunkEvent(audio_chunk="YmFzZTY0", audio_format="opus", chunk_index=0)
        assert format_stream_event(event) == _sse({
            "audio_chunk": "YmFzZTY0", "audioFormat": "opus", "chunk_index": 0, "done": False,
        })

    def test_bare_done_matches_safety_filter_format(self):
        assert format_stream_event(DoneEvent()) == _sse({"done": True})

    def test_cache_hit_done_matches_pipeline_chat_service_format(self):
        event = DoneEvent(sources=[{"title": "doc1"}], metadata={"cached": True})
        assert format_stream_event(event) == _sse({
            "done": True, "sources": [{"title": "doc1"}], "metadata": {"cached": True},
        })

    def test_raw_event_relays_unchanged(self):
        # Matches streaming_handler.py:399's `yield f"data: {chunk}\n\n", state`.
        assert format_stream_event(RawEvent(raw="not valid json")) == "data: not valid json\n\n"

    def test_full_done_matches_build_done_chunk_key_order(self):
        # Matches StreamingHandler.build_done_chunk's field insertion order.
        event = DoneEvent(
            sources=[{"title": "doc1"}],
            total_audio_chunks=3,
            assistant_message_id="msg-1",
            model="gpt-4o",
            threading={"thread_id": "t1"},
            video_url="https://example.com/v.mp4",
            video_format="mp4",
            video_revised_prompt="a dog running",
        )
        assert format_stream_event(event) == _sse({
            "done": True,
            "sources": [{"title": "doc1"}],
            "total_audio_chunks": 3,
            "assistant_message_id": "msg-1",
            "model": "gpt-4o",
            "threading": {"thread_id": "t1"},
            "video_url": "https://example.com/v.mp4",
            "video_format": "mp4",
            "video_revised_prompt": "a dog running",
        })


class TestStreamEventToDict:
    """stream_event_to_dict is the dict-only sibling of format_stream_event,
    used by process_stream_raw's structured (non-SSE) consumers."""

    def test_response_event_to_dict(self):
        assert stream_event_to_dict(ResponseEvent(text="hi", extra={"done": False})) == {
            "response": "hi", "done": False
        }

    def test_raw_event_has_no_dict_form(self):
        with pytest.raises(TypeError):
            stream_event_to_dict(RawEvent(raw="not valid json"))


class TestRoundTrip:
    @pytest.mark.parametrize("payload", [
        {"response": "hello", "done": False},
        {"response": "hello"},
        {"error": "oops", "done": True},
        {"error": "oops"},
        {"error": "rate limited", "status": 429, "done": True},
        {"audio_chunk": "abc", "audioFormat": "mp3", "chunk_index": 1, "done": False},
        {"done": True},
        {"done": True, "sources": [{"title": "x"}]},
        {"done": True, "generated_audio_url": "https://x/a.mp3", "generated_audio_format": "mp3"},
    ])
    def test_parse_then_format_reproduces_input(self, payload):
        event = parse_stream_payload(payload)
        assert format_stream_event(event) == _sse(payload)

    def test_raw_chunk_round_trips_through_parse_stream_chunk(self):
        chunk = "not valid json"
        assert format_stream_event(parse_stream_chunk(chunk)) == f"data: {chunk}\n\n"
