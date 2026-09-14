"""
Tests for the bounded, DB-side aggregation primitives added to DatabaseService:
`find_user_session_summaries()` and `delete_messages_beyond_token_budget()`.

See docs/roadmap/chat-history-bounded-aggregation-queries.md.
"""

import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta

import pytest
from pytest_asyncio import fixture
from services.sqlite_service import SQLiteService

COLLECTION = "chat_history"
CHARS_PER_TOKEN_ESTIMATE = 3


@fixture(scope="function")
async def sqlite_service():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")
    config = {
        'internal_services': {
            'backend': {'type': 'sqlite', 'sqlite': {'database_path': db_path}}
        },
        'general': {},
    }
    service = SQLiteService(config)
    await service.initialize()
    yield service
    service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


async def _insert_message(db, session_id, user_id, role, content, ts, token_count=None):
    return await db.insert_one(COLLECTION, {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "timestamp": ts,
        "token_count": token_count,
    })


@pytest.mark.asyncio
async def test_find_user_session_summaries_pagination_and_counts(sqlite_service):
    """Many sessions for one user: message_count/first_activity/last_activity are
    correct across the paginated grouped-query path, and pagination is applied
    in the database (only the requested page is returned)."""
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    num_sessions = 25
    for i in range(num_sessions):
        session_id = f"s{i:03d}"
        # Two messages per session, spaced so last_activity differs per session.
        await _insert_message(db, session_id, "u1", "user", "hi", base + timedelta(minutes=i))
        await _insert_message(db, session_id, "u1", "assistant", "hello", base + timedelta(minutes=i, seconds=30))

    page1 = await db.find_user_session_summaries(COLLECTION, "u1", offset=0, limit=10, include_summary=False)
    page2 = await db.find_user_session_summaries(COLLECTION, "u1", offset=10, limit=10, include_summary=False)
    page3 = await db.find_user_session_summaries(COLLECTION, "u1", offset=20, limit=10, include_summary=False)

    assert len(page1) == 10
    assert len(page2) == 10
    assert len(page3) == 5

    all_ids = [s["session_id"] for s in page1 + page2 + page3]
    assert len(set(all_ids)) == num_sessions

    # Ordered last_activity DESC: page1 has the most recent sessions (highest i).
    assert page1[0]["session_id"] == "s024"
    assert page3[-1]["session_id"] == "s000"

    for s in page1:
        assert s["message_count"] == 2
        assert isinstance(s["first_activity"], datetime)
        assert isinstance(s["last_activity"], datetime)
        assert s["last_activity"] > s["first_activity"]


@pytest.mark.asyncio
async def test_find_user_session_summaries_include_summary_preview(sqlite_service):
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    await _insert_message(db, "s1", "u1", "user", "first", base)
    await _insert_message(db, "s1", "u1", "assistant", "latest reply", base + timedelta(seconds=10))

    summaries = await db.find_user_session_summaries(COLLECTION, "u1", offset=0, limit=10, include_summary=True)

    assert len(summaries) == 1
    assert summaries[0]["last_message_content"] == "latest reply"
    assert summaries[0]["last_message_role"] == "assistant"


@pytest.mark.asyncio
async def test_find_user_session_summaries_without_summary_skips_preview_fields(sqlite_service):
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    await _insert_message(db, "s1", "u1", "user", "hi", base)

    summaries = await db.find_user_session_summaries(COLLECTION, "u1", offset=0, limit=10, include_summary=False)

    assert len(summaries) == 1
    assert "last_message_content" not in summaries[0]
    assert "last_message_role" not in summaries[0]


@pytest.mark.asyncio
async def test_find_user_session_summaries_group_ordering_tiebreak(sqlite_service):
    """Two different sessions whose latest message shares the same last_activity
    timestamp: session-group ordering must resolve the tie via session_id ASC,
    deterministically across repeated calls."""
    db = sqlite_service
    shared_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    await _insert_message(db, "session_b", "u1", "user", "hi", shared_ts)
    await _insert_message(db, "session_a", "u1", "user", "hi", shared_ts)

    for _ in range(3):
        summaries = await db.find_user_session_summaries(COLLECTION, "u1", offset=0, limit=10, include_summary=False)
        assert [s["session_id"] for s in summaries] == ["session_a", "session_b"]


@pytest.mark.asyncio
async def test_find_user_session_summaries_preview_selection_tiebreak(sqlite_service):
    """Two messages within the same session sharing the same timestamp: the
    last-message preview must be selected via `_id DESC`, not scan order."""
    db = sqlite_service
    shared_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    id1 = await _insert_message(db, "s1", "u1", "user", "first-inserted", shared_ts)
    id2 = await _insert_message(db, "s1", "u1", "assistant", "second-inserted", shared_ts)

    summaries = await db.find_user_session_summaries(COLLECTION, "u1", offset=0, limit=10, include_summary=True)

    expected_content = "second-inserted" if id2 > id1 else "first-inserted"
    assert summaries[0]["last_message_content"] == expected_content


@pytest.mark.asyncio
async def test_delete_messages_beyond_token_budget_keeps_newest_within_budget(sqlite_service):
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # 5 messages, 10 tokens each, budget 25 -> keep newest 2 (20 tokens), delete oldest 3.
    for i in range(5):
        await _insert_message(db, "s1", "u1", "user", f"msg{i}", base + timedelta(seconds=i), token_count=10)

    result = await db.delete_messages_beyond_token_budget(
        COLLECTION, {"session_id": "s1"}, token_field="token_count",
        content_field="content", budget=25, chars_per_token_estimate=CHARS_PER_TOKEN_ESTIMATE,
    )

    assert result["deleted_count"] == 3
    assert result["tokens_removed"] == 30

    remaining = await db.find_many(COLLECTION, {"session_id": "s1"}, sort=[("timestamp", 1)], limit=100)
    assert [m["content"] for m in remaining] == ["msg3", "msg4"]


@pytest.mark.asyncio
async def test_delete_messages_beyond_token_budget_reports_only_actually_deleted_rows(sqlite_service, monkeypatch):
    """If a concurrent writer removes one of the messages this call is about
    to delete after the boundary is determined but before the delete itself
    runs, deleted_count/tokens_removed must reflect only what this call
    actually deleted (via DELETE ... RETURNING), never a stale tally taken
    before the concurrent change."""
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # 5 messages, 10 tokens each, budget 25 -> boundary keeps newest 2, would
    # delete msg0/msg1/msg2 (30 tokens) absent any concurrent activity.
    for i in range(5):
        await _insert_message(db, "s1", "u1", "user", f"msg{i}", base + timedelta(seconds=i), token_count=10)

    original_fetchone = db._execute_sql_fetchone

    def _fetchone_with_concurrent_delete(sql, params):
        row = original_fetchone(sql, params)
        # Simulate another worker deleting msg0 between boundary detection
        # and this call's own delete.
        db.connection.execute('DELETE FROM chat_history WHERE content = ?', ("msg0",))
        db.connection.commit()
        return row

    monkeypatch.setattr(db, "_execute_sql_fetchone", _fetchone_with_concurrent_delete)

    result = await db.delete_messages_beyond_token_budget(
        COLLECTION, {"session_id": "s1"}, token_field="token_count",
        content_field="content", budget=25, chars_per_token_estimate=CHARS_PER_TOKEN_ESTIMATE,
    )

    # msg0 was already gone by the time the DELETE...RETURNING ran, so only
    # msg1/msg2 were actually deleted by this call — not the stale count of 3.
    assert result["deleted_count"] == 2
    assert result["tokens_removed"] == 20

    remaining = await db.find_many(COLLECTION, {"session_id": "s1"}, sort=[("timestamp", 1)], limit=100)
    assert [m["content"] for m in remaining] == ["msg3", "msg4"]


@pytest.mark.asyncio
async def test_delete_messages_beyond_token_budget_no_op_when_under_budget(sqlite_service):
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        await _insert_message(db, "s1", "u1", "user", f"msg{i}", base + timedelta(seconds=i), token_count=10)

    result = await db.delete_messages_beyond_token_budget(
        COLLECTION, {"session_id": "s1"}, token_field="token_count",
        content_field="content", budget=1000, chars_per_token_estimate=CHARS_PER_TOKEN_ESTIMATE,
    )

    assert result == {"deleted_count": 0, "tokens_removed": 0}


@pytest.mark.asyncio
async def test_delete_messages_beyond_token_budget_large_session(sqlite_service):
    """A session with >10,000 messages: the budget-walk boundary and
    deleted_count/tokens_removed must be correct without any hardcoded fetch cap."""
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    total = 10050
    for i in range(total):
        await db.insert_one(COLLECTION, {
            "session_id": "big",
            "user_id": "u1",
            "role": "user",
            "content": "x",
            "timestamp": base + timedelta(seconds=i),
            "token_count": 1,
        })

    # Budget 100 -> keep newest 100 messages (100 tokens), delete the rest.
    result = await db.delete_messages_beyond_token_budget(
        COLLECTION, {"session_id": "big"}, token_field="token_count",
        content_field="content", budget=100, chars_per_token_estimate=CHARS_PER_TOKEN_ESTIMATE,
    )

    assert result["deleted_count"] == total - 100
    assert result["tokens_removed"] == total - 100

    remaining_count = await db.count(COLLECTION, {"session_id": "big"})
    assert remaining_count == 100


@pytest.mark.asyncio
async def test_delete_messages_beyond_token_budget_legacy_rows_unicode_estimate(sqlite_service):
    """Legacy rows with NULL token_count must be estimated via
    max(1, len(content) // 3) using Unicode codepoint length, matching
    ChatHistoryService._estimate_token_count exactly."""
    db = sqlite_service
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Non-ASCII content: 9 codepoints (emoji + CJK), estimate = max(1, 9 // 3) = 3
    content = "\U0001F600\U0001F600\U0001F600你好你好你好"
    assert len(content) == 9

    await _insert_message(db, "s1", "u1", "user", content, base, token_count=None)
    await _insert_message(db, "s1", "u1", "assistant", "keep-me", base + timedelta(seconds=1), token_count=50)

    result = await db.delete_messages_beyond_token_budget(
        COLLECTION, {"session_id": "s1"}, token_field="token_count",
        content_field="content", budget=50, chars_per_token_estimate=CHARS_PER_TOKEN_ESTIMATE,
    )

    assert result["deleted_count"] == 1
    assert result["tokens_removed"] == 3
