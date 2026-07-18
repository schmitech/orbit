import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import routes.admin_panel_routes as admin_panel_routes
from services.postgres_service import PostgresService
from services.sqlite_service import SQLiteService


class FakeDatabase:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.feedback = [
            {
                "message_id": "assistant-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "feedback_type": "up",
                "adapter_name": "sales",
                "comment": None,
                "created_at": now - timedelta(days=1),
            },
            {
                "message_id": "assistant-2",
                "session_id": "session-2",
                "user_id": "user-2",
                "feedback_type": "down",
                "adapter_name": "sales",
                "comment": "The total is incorrect.",
                "created_at": now,
            },
        ]
        self.messages = {
            "assistant-2": {
                "_id": "assistant-2",
                "session_id": "session-2",
                "role": "assistant",
                "content": "The total is $40.",
                "timestamp": now.isoformat(),
            },
        }

    async def find_many(self, collection, query, limit=100, sort=None, skip=0):
        if collection == "feedback":
            return self.feedback[skip:skip + limit]
        if collection == "chat_history" and query.get("session_id") == "session-2":
            return [
                self.messages["assistant-2"],
                {
                    "_id": "user-message-2",
                    "session_id": "session-2",
                    "role": "user",
                    "content": "What is the invoice total?",
                    "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                },
            ]
        return []

    async def find_one(self, collection, query):
        if collection == "chat_history":
            return self.messages.get(query.get("_id"))
        if collection == "users":
            return {"_id": query.get("_id"), "email": "admin@example.com"}
        return None

    async def count(self, collection, query):
        if collection == "feedback":
            return len(self.feedback)
        if collection == "chat_history":
            return 4
        return 0


@pytest.mark.asyncio
async def test_feedback_analytics_aggregates_and_enriches(monkeypatch):
    async def fake_admin_user(_request):
        return {"id": "admin", "role": "admin"}

    monkeypatch.setattr(admin_panel_routes, "get_admin_user", fake_admin_user)
    database = FakeDatabase()
    state = SimpleNamespace(
        config={},
        feedback_service=SimpleNamespace(database_service=database),
        chat_history_service=SimpleNamespace(collection_name="chat_history"),
        auth_service=SimpleNamespace(users_collection_name="users"),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    router = admin_panel_routes.create_admin_panel_router()
    endpoint = next(
        route.endpoint for route in router.routes
        if getattr(route, "path", None) == "/admin/api/feedback-analytics"
    )

    response = await endpoint(request, days=30)
    payload = json.loads(response.body)

    assert payload["summary"] == {
        "total": 2,
        "positive": 1,
        "negative": 1,
        "satisfaction_rate": 50.0,
        "comments": 1,
        "negative_comment_rate": 100.0,
        "sessions": 2,
        "users": 2,
        "eligible_messages": 4,
        "response_rate": 50.0,
    }
    assert payload["adapters"][0]["adapter"] == "sales"
    assert payload["adapters"][0]["satisfaction_rate"] == 50.0
    assert payload["recent_negative"][0]["user_prompt"] == "What is the invoice total?"
    assert payload["recent_negative"][0]["assistant_response"] == "The total is $40."
    assert payload["recent_negative"][0]["user"] == "admin@example.com"


@pytest.mark.asyncio
async def test_sqlite_user_lookup_translates_logical_id(tmp_path):
    config = {
        "internal_services": {
            "backend": {
                "type": "sqlite",
                "sqlite": {"database_path": str(tmp_path / "feedback-admin.db")},
            }
        }
    }
    database = SQLiteService(config)
    await database.initialize()
    try:
        await database.insert_one("users", {
            "_id": "user-123",
            "username": "feedback-admin",
            "password": "unused-test-hash",
            "role": "user",
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "email": "feedback@example.com",
        })

        user = await database.find_one("users", {"_id": "user-123"})

        assert user is not None
        assert user["email"] == "feedback@example.com"
    finally:
        database.close()


def test_postgres_user_lookup_translates_logical_id():
    database = PostgresService({
        "internal_services": {
            "backend": {
                "postgres": {"host": "localhost", "database": "orbit-test"},
            }
        }
    })
    try:
        where_clause, params = database._convert_query_to_sql("users", {"_id": "user-123"})

        assert where_clause == '"id" = %s'
        assert params == ("user-123",)
    finally:
        database.close()
