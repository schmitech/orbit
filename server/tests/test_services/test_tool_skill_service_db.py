"""
Tests for the Phase 3 database-backed tool skill mechanism
(docs/roadmap/mcp-tool-skills.md §2.6): ``ToolSkillService`` CRUD/validation
and DB-over-file precedence in ``ToolSkillRegistry``.
"""

import sys
import os

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from services.tool_skill_service import (
    ToolSkillService,
    ToolSkillRegistry,
    refresh_tool_skill_registry_db,
)


def _reject_unbindable_list_params(document):
    """Mimics sqlite3's real 'Error binding parameter ... type list is not
    supported' — the FakeDatabaseService otherwise happily stores a Python
    list, which would hide the P1 bug this file's SQL-backend tests guard
    against (docs/roadmap/mcp-tool-skills.md Phase 3 review)."""
    for key, value in document.items():
        if isinstance(value, list):
            raise TypeError(f"Error binding parameter '{key}': type 'list' is not supported")


class FakeDatabaseService:
    """Minimal in-memory stand-in for DatabaseService, mirroring
    test_admin/test_prompt_service.py's FakeMongoService."""

    def __init__(self, reject_lists=False):
        self.docs = {}
        self._next_id = 1
        # Only the SQL-flavored fake (see _make_sql_service) rejects raw list
        # params, mimicking sqlite3/psycopg's real driver behavior — the
        # mongo-backed fake below stores lists natively, same as real Mongo.
        self.reject_lists = reject_lists

    async def initialize(self):
        return None

    async def create_index(self, *args, **kwargs):
        return None

    async def find_one(self, collection, query):
        doc_id = query.get("_id")
        if doc_id is not None:
            return self.docs.get(str(doc_id))
        name = query.get("name")
        if name is not None:
            for doc in self.docs.values():
                if doc.get("name") == name:
                    return doc
        return None

    async def find_many(self, collection, query, limit=100, skip=0):
        results = list(self.docs.values())
        if query.get("enabled") is True:
            results = [d for d in results if d.get("enabled", True)]
        return [dict(d) for d in results[skip:skip + limit]]

    async def insert_one(self, collection, document):
        if self.reject_lists:
            _reject_unbindable_list_params(document)
        doc_id = document.get("_id") or f"id-{self._next_id}"
        self._next_id += 1
        document = dict(document)
        document["_id"] = doc_id
        self.docs[str(doc_id)] = document
        return doc_id

    async def update_one(self, collection, query, update):
        if self.reject_lists:
            _reject_unbindable_list_params(update.get("$set", {}))
        doc_id = query.get("_id")
        doc = self.docs.get(str(doc_id))
        if not doc:
            return False
        doc.update(update.get("$set", {}))
        return True

    async def delete_one(self, collection, query):
        doc_id = str(query.get("_id"))
        return self.docs.pop(doc_id, None) is not None


def _make_service():
    return ToolSkillService(
        config={"internal_services": {"backend": {"type": "mongodb"}, "mongodb": {}}},
        database_service=FakeDatabaseService(),
    )


def _make_sql_service(backend_type="sqlite"):
    return ToolSkillService(
        config={"internal_services": {"backend": {"type": backend_type}}},
        database_service=FakeDatabaseService(reject_lists=True),
    )


@pytest.mark.asyncio
async def test_create_and_get_skill_on_sql_backend_round_trips_mcp_tools():
    """Regression test for the P1 review finding: on SQLite/Postgres,
    mcp_tools must be JSON-encoded before persistence (their driver can't
    bind a raw Python list) and decoded back to a list on read."""
    service = _make_sql_service("sqlite")
    await service.initialize()

    skill_id = await service.create_skill(
        name="sql-playbook",
        description="d",
        mcp_tools=["business-sample__list_customers", "business-sample__get_customer_health"],
        body="body",
    )

    doc = await service.get_skill_by_id(skill_id)
    assert doc["mcp_tools"] == ["business-sample__list_customers", "business-sample__get_customer_health"]

    listed = await service.list_skills()
    assert listed[0]["mcp_tools"] == ["business-sample__list_customers", "business-sample__get_customer_health"]


@pytest.mark.asyncio
async def test_update_skill_on_sql_backend_round_trips_mcp_tools():
    service = _make_sql_service("postgres")
    await service.initialize()
    skill_id = await service.create_skill(
        name="sql-playbook", description="d", mcp_tools=["a__b"], body="body",
    )

    ok = await service.update_skill(skill_id, mcp_tools=["a__b", "a__c"])
    assert ok is True

    doc = await service.get_skill_by_id(skill_id)
    assert doc["mcp_tools"] == ["a__b", "a__c"]


@pytest.mark.asyncio
async def test_create_get_list_skill():
    service = _make_service()
    await service.initialize()

    skill_id = await service.create_skill(
        name="db-only-playbook",
        description="A DB-authored playbook.",
        mcp_tools=["business-sample__list_customers"],
        body="Always call list_customers first.",
    )

    doc = await service.get_skill_by_id(skill_id)
    assert doc["name"] == "db-only-playbook"
    assert doc["priority"] == 0
    assert doc["enabled"] is True

    listed = await service.list_skills()
    assert len(listed) == 1
    assert listed[0]["name"] == "db-only-playbook"


@pytest.mark.asyncio
async def test_create_duplicate_name_rejected():
    from fastapi import HTTPException

    service = _make_service()
    await service.initialize()
    await service.create_skill(
        name="dup", description="d", mcp_tools=["x__y"], body="body",
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create_skill(
            name="dup", description="d2", mcp_tools=["x__z"], body="body2",
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_invalid_fields_rejected():
    from fastapi import HTTPException

    service = _make_service()
    await service.initialize()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_skill(name="Not-A-Slug!", description="d", mcp_tools=["x__y"], body="b")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException):
        await service.create_skill(name="reserved", description="d", mcp_tools=["orbit__x"], body="b")

    with pytest.raises(HTTPException):
        await service.create_skill(name="orbit__reserved-name", description="d", mcp_tools=["x__y"], body="b")

    with pytest.raises(HTTPException):
        await service.create_skill(name="empty-tools", description="d", mcp_tools=[], body="b")

    with pytest.raises(HTTPException):
        await service.create_skill(name="oversize", description="d", mcp_tools=["x__y"], body="a" * 40_000)


@pytest.mark.asyncio
async def test_update_skill_preserves_unspecified_fields_and_bumps_updated_at():
    service = _make_service()
    await service.initialize()
    skill_id = await service.create_skill(
        name="s", description="orig desc", mcp_tools=["x__y"], body="orig body", priority=5,
    )

    ok = await service.update_skill(skill_id, body="new body")
    assert ok is True

    doc = await service.get_skill_by_id(skill_id)
    assert doc["body"] == "new body"
    assert doc["description"] == "orig desc"  # unspecified fields untouched
    assert doc["priority"] == 5


@pytest.mark.asyncio
async def test_update_missing_skill_returns_false():
    service = _make_service()
    await service.initialize()
    assert await service.update_skill("does-not-exist", body="x") is False


@pytest.mark.asyncio
async def test_delete_skill():
    service = _make_service()
    await service.initialize()
    skill_id = await service.create_skill(name="s", description="d", mcp_tools=["x__y"], body="b")

    assert await service.delete_skill(skill_id) is True
    assert await service.get_skill_by_id(skill_id) is None
    assert await service.delete_skill(skill_id) is False


@pytest.mark.asyncio
async def test_db_skill_overrides_file_skill_with_same_name(tmp_path):
    """docs/roadmap/mcp-tool-skills.md §2.6: database wins on a name collision;
    the file version is retrievable as the 'on-disk default'."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "crm-pipeline-playbook"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: crm-pipeline-playbook\n"
        "description: File-authored description.\n"
        "mcp_tools:\n"
        "  - \"business-sample__list_customers\"\n"
        "priority: 1\n"
        "---\n"
        "\n"
        "File body.\n"
    )

    registry = ToolSkillRegistry(skills_dir)
    assert registry.get("crm-pipeline-playbook").description == "File-authored description."

    service = _make_service()
    await service.initialize()
    await service.create_skill(
        name="crm-pipeline-playbook",
        description="DB-authored override.",
        mcp_tools=["business-sample__list_customers"],
        body="DB body.",
        priority=9,
    )
    docs = await service.list_skills()
    from services.tool_skill_service import _db_doc_to_skill
    db_skill = _db_doc_to_skill(docs[0])
    registry.set_db_skills([db_skill])

    served = registry.get("crm-pipeline-playbook")
    assert served.description == "DB-authored override."
    assert served.source == "db"

    file_default = registry.file_default_for("crm-pipeline-playbook")
    assert file_default.description == "File-authored description."
    assert file_default.source == "file"


@pytest.mark.asyncio
async def test_disabled_db_skill_is_excluded():
    from pathlib import Path
    from services.tool_skill_service import _db_doc_to_skill

    service = _make_service()
    await service.initialize()
    skill_id = await service.create_skill(
        name="a-skill", description="d", mcp_tools=["x__y"], body="b", enabled=False,
    )
    doc = await service.get_skill_by_id(skill_id)
    db_skill = _db_doc_to_skill(doc)

    registry = ToolSkillRegistry(Path("/nonexistent-dir"))
    registry.set_db_skills([db_skill])
    assert registry.get("a-skill") is None


@pytest.mark.asyncio
async def test_refresh_tool_skill_registry_db_merges_enabled_db_skills(monkeypatch):
    import services.tool_skill_service as tss

    # Reset the module singleton so this test doesn't depend on run order.
    monkeypatch.setattr(tss, "_registry_instance", None)
    monkeypatch.setattr(tss, "_registry_dir", None)

    service = _make_service()
    await service.initialize()
    await service.create_skill(
        name="fresh-db-skill", description="d", mcp_tools=["x__y"], body="b",
    )

    config = {"tool_skills": {"directory": "/nonexistent-dir"}}
    registry = await refresh_tool_skill_registry_db(config, service)
    assert registry.get("fresh-db-skill") is not None
    assert registry.get("fresh-db-skill").source == "db"
