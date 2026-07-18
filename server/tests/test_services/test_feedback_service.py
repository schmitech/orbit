"""
Feedback Service Tests
======================

Tests the feedback service toggle/comment semantics and the SQLite
additive-column migration that adds the `comment` column to pre-existing
databases.

Covers:
- thumb-only toggle logic (create / toggle-off / switch type)
- optional free-text comment: add, trim, clear, and one-call create
- comment cleared when the reaction is toggled off or switched
- get_session_feedback returns the comment
- comment length bound (MAX_COMMENT_LENGTH) enforcement
- invalid feedback_type rejection
- migration of a legacy feedback table (no `comment` column)
"""

import os
import sqlite3
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from pytest_asyncio import fixture

# Ensure server modules can be imported
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.sqlite_service import SQLiteService
from services.feedback_service import FeedbackService, MAX_COMMENT_LENGTH


def _make_config(db_path):
  return {
    'internal_services': {
      'backend': {
        'type': 'sqlite',
        'sqlite': {
          'database_path': db_path
        }
      }
    }
  }


@fixture(scope="function")
async def feedback_service():
  """Set up a feedback service backed by a fresh temp SQLite database."""
  temp_dir = tempfile.mkdtemp()
  db_path = os.path.join(temp_dir, "test_orbit.db")
  config = _make_config(db_path)

  sqlite_service = SQLiteService(config)
  await sqlite_service.initialize()

  service = FeedbackService(config, database_service=sqlite_service)
  await service.initialize()

  yield service

  sqlite_service.close()
  shutil.rmtree(temp_dir, ignore_errors=True)


MID = "msg-1"
SID = "sess-1"


@pytest.mark.asyncio
async def test_create_down_without_comment(feedback_service):
  result = await feedback_service.submit_feedback(MID, SID, "down")
  assert result["action"] == "created"
  assert result["feedback_type"] == "down"
  assert result["comment"] is None


@pytest.mark.asyncio
async def test_same_type_toggles_off(feedback_service):
  await feedback_service.submit_feedback(MID, SID, "down")
  result = await feedback_service.submit_feedback(MID, SID, "down")
  assert result["action"] == "removed"
  assert result["feedback_type"] is None
  assert result["comment"] is None
  # Row is gone
  assert await feedback_service.get_session_feedback(SID) == []


@pytest.mark.asyncio
async def test_add_comment_trims_and_does_not_toggle_off(feedback_service):
  await feedback_service.submit_feedback(MID, SID, "down")
  result = await feedback_service.submit_feedback(MID, SID, "down", comment="  bad answer  ")
  assert result["action"] == "updated"
  assert result["feedback_type"] == "down"
  assert result["comment"] == "bad answer"


@pytest.mark.asyncio
async def test_get_session_feedback_includes_comment(feedback_service):
  await feedback_service.submit_feedback(MID, SID, "down", comment="wrong data")
  feedbacks = await feedback_service.get_session_feedback(SID)
  assert feedbacks == [{"message_id": MID, "feedback_type": "down", "comment": "wrong data"}]


@pytest.mark.asyncio
async def test_empty_comment_clears_but_keeps_reaction(feedback_service):
  await feedback_service.submit_feedback(MID, SID, "down", comment="bad")
  result = await feedback_service.submit_feedback(MID, SID, "down", comment="   ")
  assert result["action"] == "updated"
  assert result["feedback_type"] == "down"
  assert result["comment"] is None
  feedbacks = await feedback_service.get_session_feedback(SID)
  assert feedbacks == [{"message_id": MID, "feedback_type": "down", "comment": None}]


@pytest.mark.asyncio
async def test_switch_reaction_clears_comment(feedback_service):
  await feedback_service.submit_feedback(MID, SID, "down", comment="still bad")
  result = await feedback_service.submit_feedback(MID, SID, "up")
  assert result["feedback_type"] == "up"
  assert result["comment"] is None
  feedbacks = await feedback_service.get_session_feedback(SID)
  assert feedbacks == [{"message_id": MID, "feedback_type": "up", "comment": None}]


@pytest.mark.asyncio
async def test_create_with_comment_in_one_call(feedback_service):
  result = await feedback_service.submit_feedback("msg-2", SID, "down", comment="wrong")
  assert result["action"] == "created"
  assert result["comment"] == "wrong"


@pytest.mark.asyncio
async def test_over_length_comment_rejected(feedback_service):
  too_long = "x" * (MAX_COMMENT_LENGTH + 1)
  with pytest.raises(ValueError, match="maximum length"):
    await feedback_service.submit_feedback(MID, SID, "down", comment=too_long)
  # Nothing persisted
  assert await feedback_service.get_session_feedback(SID) == []


@pytest.mark.asyncio
async def test_exactly_max_length_comment_accepted(feedback_service):
  at_limit = "y" * MAX_COMMENT_LENGTH
  result = await feedback_service.submit_feedback(MID, SID, "down", comment=at_limit)
  assert result["action"] == "created"
  assert len(result["comment"]) == MAX_COMMENT_LENGTH


@pytest.mark.asyncio
async def test_invalid_feedback_type_rejected(feedback_service):
  with pytest.raises(ValueError, match="Invalid feedback_type"):
    await feedback_service.submit_feedback(MID, SID, "sideways")


@pytest.mark.asyncio
async def test_migration_adds_comment_column_to_legacy_db():
  """A pre-existing feedback table without `comment` gains it on startup."""
  temp_dir = tempfile.mkdtemp()
  db_path = os.path.join(temp_dir, "legacy_orbit.db")
  try:
    # Create a legacy feedback table WITHOUT the comment column.
    conn = sqlite3.connect(db_path)
    conn.execute(
      """CREATE TABLE feedback (
          id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL,
          user_id TEXT, feedback_type TEXT NOT NULL, adapter_name TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""
    )
    conn.commit()
    conn.close()

    config = _make_config(db_path)
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()  # runs the additive-column migration

    columns = {
      row[1]
      for row in sqlite3.connect(db_path).execute("PRAGMA table_info(feedback)").fetchall()
    }
    assert "comment" in columns

    # Feedback with a comment works against the migrated table.
    service = FeedbackService(config, database_service=sqlite_service)
    await service.initialize()
    result = await service.submit_feedback(MID, SID, "down", comment="after migration")
    assert result["comment"] == "after migration"

    sqlite_service.close()
  finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
