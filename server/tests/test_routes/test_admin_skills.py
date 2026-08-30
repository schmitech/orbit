"""
Unit tests for routes/admin/skills.py — Tool Skill (SKILL.md) admin CRUD
(docs/roadmap/mcp-tool-skills.md Phase 3). Calls route handler functions
directly with a fake request, mirroring test_admin_mcp_reload.py's pattern,
rather than spinning up a full FastAPI TestClient.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routes.admin.skills as admin_skills
import services.tool_skill_service as tss
from services.tool_skill_service import ToolSkillService


class FakeDatabaseService:
    """Minimal in-memory stand-in for DatabaseService (mirrors the one in
    tests/test_services/test_tool_skill_service_db.py)."""

    def __init__(self):
        self.docs = {}
        self._next_id = 1

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

    async def find_many(self, collection, query, limit=100, sort=None, skip=0):
        results = list(self.docs.values())
        if query.get("enabled") is True:
            results = [d for d in results if d.get("enabled", True)]
        for field, direction in reversed(sort or []):
            results.sort(key=lambda d: d.get(field), reverse=direction < 0)
        return [dict(d) for d in results[skip:skip + limit]]

    async def count(self, collection, query):
        results = list(self.docs.values())
        if query.get("enabled") is True:
            results = [d for d in results if d.get("enabled", True)]
        return len(results)

    async def insert_one(self, collection, document):
        doc_id = document.get("_id") or f"id-{self._next_id}"
        self._next_id += 1
        document = dict(document)
        document["_id"] = doc_id
        self.docs[str(doc_id)] = document
        return doc_id

    async def update_one(self, collection, query, update):
        doc_id = query.get("_id")
        doc = self.docs.get(str(doc_id))
        if not doc:
            return False
        doc.update(update.get("$set", {}))
        return True

    async def delete_one(self, collection, query):
        doc_id = str(query.get("_id"))
        return self.docs.pop(doc_id, None) is not None


def _fake_request(tool_skill_service, config=None):
    state = SimpleNamespace(
        tool_skill_service=tool_skill_service,
        config=config or {"tool_skills": {"directory": "/nonexistent-dir"}},
    )
    # No ORBIT_SUPERVISOR_PID in the test environment, so _refresh_registry's
    # multi-worker propagation branch is not exercised here.
    return SimpleNamespace(app=SimpleNamespace(state=state), state=SimpleNamespace())


def _make_service():
    return ToolSkillService(
        config={"internal_services": {"backend": {"type": "mongodb"}, "mongodb": {}}},
        database_service=FakeDatabaseService(),
    )


@pytest.fixture(autouse=True)
def _reset_registry_singleton():
    tss._registry_instance = None
    tss._registry_dir = None
    yield
    tss._registry_instance = None
    tss._registry_dir = None


class TestCreateSkill:
    def test_request_schema_enforces_authoring_caps(self):
        from models.schema import ToolSkillCreate

        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="x" * 65,
                description="d",
                mcp_tools=["x__y"],
                body="b",
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid",
                description="d",
                mcp_tools=[f"x__{i}" for i in range(65)],
                body="b",
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid",
                description="d",
                mcp_tools=["x__y"],
                body="b" * 24_577,
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid", description="d", mcp_tools=["x__y"], body="b", priority=100,
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid", description="d", mcp_tools=["x__y"], body="b", priority=-2,
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid", description="d", mcp_tools=["x__y"], body="b", version="v" * 26,
            )
        with pytest.raises(ValidationError):
            ToolSkillCreate(
                name="valid", description="d", mcp_tools=["x__y"], body="b", version="3#@#@#!@#!@##!@",
            )

    @pytest.mark.asyncio
    async def test_create_returns_response_and_refreshes_registry(self):
        from models.schema import ToolSkillCreate

        service = await _init(_make_service())
        request = _fake_request(service)

        payload = ToolSkillCreate(
            name="new-playbook",
            description="A new playbook.",
            mcp_tools=["business-sample__list_customers"],
            body="Call list_customers first.",
        )
        response = await admin_skills.create_skill(payload, request)

        assert response["name"] == "new-playbook"
        assert response["enabled"] is True
        assert "id" in response
        assert request.state.audit_context["resource_id"] == response["id"]
        assert request.state.audit_context["summary"]["name"] == "new-playbook"
        assert "body" not in request.state.audit_context["summary"]

        registry = tss.get_tool_skill_registry(request.app.state.config)
        assert registry.get("new-playbook") is not None
        assert registry.get("new-playbook").source == "db"

    @pytest.mark.asyncio
    async def test_create_without_service_raises_503(self):
        from models.schema import ToolSkillCreate

        request = _fake_request(None)
        payload = ToolSkillCreate(name="x", description="d", mcp_tools=["a__b"], body="b")

        with pytest.raises(HTTPException) as exc_info:
            await admin_skills.create_skill(payload, request)
        assert exc_info.value.status_code == 503


class TestListAndGetSkill:
    @pytest.mark.asyncio
    async def test_list_and_get(self):
        service = await _init(_make_service())
        skill_id = await service.create_skill(
            name="s1", description="d", mcp_tools=["a__b"], body="body",
        )

        listed = await admin_skills.list_skills(tool_skill_service=service)
        assert len(listed) == 1
        assert listed[0]["name"] == "s1"

        fetched = await admin_skills.get_skill(str(skill_id), tool_skill_service=service)
        assert fetched["name"] == "s1"

    @pytest.mark.asyncio
    async def test_get_missing_raises_404(self):
        service = await _init(_make_service())
        with pytest.raises(HTTPException) as exc_info:
            await admin_skills.get_skill("does-not-exist", tool_skill_service=service)
        assert exc_info.value.status_code == 404


class TestValidateSkill:
    def test_validate_rejects_bad_name(self):
        result = admin_skills.validate_skill({
            "name": "Not A Slug",
            "description": "d",
            "mcp_tools": ["a__b"],
            "body": "b",
        })
        assert result["valid"] is False
        assert "name" in result["error"]

    def test_validate_accepts_good_payload(self):
        result = admin_skills.validate_skill({
            "name": "good-slug",
            "description": "d",
            "mcp_tools": ["a__b"],
            "body": "b",
        })
        assert result["valid"] is True
        assert result["normalized"]["name"] == "good-slug"

    def test_validate_rejects_out_of_range_priority_and_long_version(self):
        payload = {"name": "good-slug", "description": "d", "mcp_tools": ["a__b"], "body": "b"}

        assert "priority" in admin_skills.validate_skill({**payload, "priority": 100})["error"]
        assert "version" in admin_skills.validate_skill({**payload, "version": "v" * 26})["error"]
        assert "version" in admin_skills.validate_skill({**payload, "version": "1.beta"})["error"]

    def test_validate_accepts_lowest_documented_priority(self):
        result = admin_skills.validate_skill({
            "name": "good-slug", "description": "d", "mcp_tools": ["a__b"], "body": "b", "priority": -1,
        })
        assert result["valid"] is True
        assert result["normalized"]["priority"] == -1


class TestUpdateSkill:
    @pytest.mark.asyncio
    async def test_update_refreshes_registry_with_new_body(self):
        from models.schema import ToolSkillUpdate

        service = await _init(_make_service())
        skill_id = await service.create_skill(
            name="s1", description="d", mcp_tools=["a__b"], body="orig",
        )
        request = _fake_request(service)

        response = await admin_skills.update_skill(
            str(skill_id), ToolSkillUpdate(body="updated body"), request, tool_skill_service=service,
        )
        assert response["body"] == "updated body"

        registry = tss.get_tool_skill_registry(request.app.state.config)
        assert registry.get("s1").body == "updated body"

    @pytest.mark.asyncio
    async def test_update_renames_skill_and_refreshes_registry(self):
        from models.schema import ToolSkillUpdate

        service = await _init(_make_service())
        skill_id = await service.create_skill(name="typo-name", description="d", mcp_tools=["a__b"], body="body")
        request = _fake_request(service)

        response = await admin_skills.update_skill(
            str(skill_id), ToolSkillUpdate(name="corrected-name"), request, tool_skill_service=service,
        )

        assert response["name"] == "corrected-name"
        registry = tss.get_tool_skill_registry(request.app.state.config)
        assert registry.get("typo-name") is None
        assert registry.get("corrected-name") is not None

    @pytest.mark.asyncio
    async def test_update_rejects_duplicate_name(self):
        from models.schema import ToolSkillUpdate

        service = await _init(_make_service())
        first_id = await service.create_skill(name="first", description="d", mcp_tools=["a__b"], body="body")
        await service.create_skill(name="taken", description="d", mcp_tools=["a__b"], body="body")
        request = _fake_request(service)

        with pytest.raises(HTTPException) as exc_info:
            await admin_skills.update_skill(
                str(first_id), ToolSkillUpdate(name="taken"), request, tool_skill_service=service,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_update_missing_raises_404(self):
        from models.schema import ToolSkillUpdate

        service = await _init(_make_service())
        request = _fake_request(service)
        with pytest.raises(HTTPException) as exc_info:
            await admin_skills.update_skill(
                "does-not-exist", ToolSkillUpdate(body="x"), request, tool_skill_service=service,
            )
        assert exc_info.value.status_code == 404


class TestDeleteSkill:
    @pytest.mark.asyncio
    async def test_delete_removes_from_registry(self):
        service = await _init(_make_service())
        skill_id = await service.create_skill(
            name="s1", description="d", mcp_tools=["a__b"], body="body",
        )
        request = _fake_request(service)
        await tss.refresh_tool_skill_registry_db(request.app.state.config, service)
        assert tss.get_tool_skill_registry(request.app.state.config).get("s1") is not None

        result = await admin_skills.delete_skill(str(skill_id), request, tool_skill_service=service)
        assert result["status"] == "success"
        assert tss.get_tool_skill_registry(request.app.state.config).get("s1") is None

    @pytest.mark.asyncio
    async def test_delete_missing_raises_404(self):
        service = await _init(_make_service())
        request = _fake_request(service)
        with pytest.raises(HTTPException) as exc_info:
            await admin_skills.delete_skill("does-not-exist", request, tool_skill_service=service)
        assert exc_info.value.status_code == 404


async def _init(service: ToolSkillService) -> ToolSkillService:
    await service.initialize()
    return service
