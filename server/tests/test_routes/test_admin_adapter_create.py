"""Tests for the adapter-creation endpoints that expose the adapter SDK.

Covers GET /admin/adapters/specs, POST /admin/adapters/preview and POST /admin/adapters,
including the answer limits, collision rules and permission behaviour a create flow has
to get right.

    venv/bin/python -m pytest server/tests/test_routes/test_admin_adapter_create.py
"""

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter_sdk.specs import SPEC_REGISTRY, get_spec
from auth.rbac import permissions_for_roles
from routes import admin as admin_routes
from routes import auth_dependencies


def _user_info(roles):
    return {
        "id": "u1",
        "username": "u1",
        "email": None,
        "role": roles[0],
        "roles": roles,
        "permissions": sorted(permissions_for_roles(roles)),
        "active": True,
    }


def _config_dir(tmp_path):
    """A minimal runtime config tree: config.yaml + adapters/ + an import list."""
    config_dir = tmp_path / "config"
    (config_dir / "adapters").mkdir(parents=True)
    (config_dir / "config.yaml").write_text("general: {}\n", encoding="utf-8")
    (config_dir / "adapters.yaml").write_text(
        'adapters:\n  import:\n    - "adapters/fetch.yaml"\n', encoding="utf-8"
    )
    (config_dir / "adapters" / "fetch.yaml").write_text(
        "adapters:\n  - name: fetch\n    type: fetch\n", encoding="utf-8"
    )
    return config_dir


def _build_app(tmp_path, roles=("admin",)):
    app = FastAPI()
    app.include_router(admin_routes.admin_router)
    app.state.config = {}
    app.state.config_path = str(_config_dir(tmp_path) / "config.yaml")
    # No adapter_manager: creation still succeeds and reports reload_error.

    async def fake_user():
        return _user_info(list(roles))

    app.dependency_overrides[auth_dependencies.get_current_user] = fake_user
    app.dependency_overrides[auth_dependencies.get_optional_user] = fake_user
    return app


def _default_answers(spec, variant=None):
    if spec.variant_field and variant is None:
        variant = spec.variant_values()[0]
    answers = {}
    for q in spec.questions:
        if spec.variant_field and q.field == spec.variant_field:
            answers[q.field] = variant
        else:
            answers[q.field] = spec.question_default(q, variant)
    return answers


# --------------------------------------------------------------------------- #
# Spec listing
# --------------------------------------------------------------------------- #

def test_list_specs_returns_every_family(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.get("/admin/adapters/specs")
    assert resp.status_code == 200
    specs = resp.json()["specs"]
    assert {s["key"] for s in specs} == set(SPEC_REGISTRY)
    assert specs[0]["key"] == "passthrough"
    for s in specs:
        assert s["questions"], f"{s['key']} has no questions"


def test_variant_specs_carry_per_variant_defaults(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        specs = client.get("/admin/adapters/specs").json()["specs"]
    doc = next(s for s in specs if s["key"] == "doc-generator")
    name_q = next(q for q in doc["questions"] if q["field"] == "name")
    assert name_q["variant_defaults"]["pdf"] == "pdf-generator"
    assert name_q["variant_defaults"]["docx"] == "word-generator"

    # Specs without variants stay lean.
    passthrough = next(s for s in specs if s["key"] == "passthrough")
    assert all("variant_defaults" not in q for q in passthrough["questions"])


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spec_key", sorted(SPEC_REGISTRY))
def test_preview_renders_valid_yaml_for_every_spec(tmp_path, spec_key):
    answers = _default_answers(get_spec(spec_key))
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/preview", json={"spec": spec_key, "answers": answers})
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert "adapters:" in body["yaml"]


def test_preview_rejects_unknown_spec(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/preview", json={"spec": "nope", "answers": {}})
    assert resp.status_code == 404


def test_preview_rejects_bad_variant(tmp_path):
    answers = _default_answers(get_spec("doc-generator"))
    answers["document_format"] = "wat"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/preview",
                           json={"spec": "doc-generator", "answers": answers})
    assert resp.status_code == 422
    assert "wat" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Answer limits
# --------------------------------------------------------------------------- #

def test_specs_expose_resolved_limits(tmp_path):
    """The form can only enforce bounds the endpoint actually publishes."""
    with TestClient(_build_app(tmp_path)) as client:
        specs = client.get("/admin/adapters/specs").json()["specs"]
    fetch = next(s for s in specs if s["key"] == "fetch")
    by_field = {q["field"]: q for q in fetch["questions"]}

    assert by_field["name"]["max_length"] == 64
    assert by_field["skill_description"]["max_length"] == 500
    assert by_field["routing_examples"]["max_length"] == 200
    assert by_field["routing_examples"]["max_items"] == 50
    assert (by_field["fetch_timeout"]["min_value"],
            by_field["fetch_timeout"]["max_value"]) == (1, 600)
    # Nothing is unbounded: every non-bool question carries a limit.
    for q in by_field.values():
        if q["type"] == "bool":
            continue
        assert q.get("max_length") or q.get("max_value"), f"{q['field']} is unbounded"


def test_create_rejects_over_long_string(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["skill_description"] = "x" * 501
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 422
    assert "500 characters" in resp.json()["detail"]
    assert not (tmp_path / "config" / "adapters" / "my-fetch.yaml").exists()


def test_create_rejects_too_many_list_entries(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["routing_examples"] = [f"phrase {i}" for i in range(51)]
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 422
    assert "at most 50 entries" in resp.json()["detail"]


def test_create_rejects_over_long_list_entry(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["routing_examples"] = ["y" * 201]
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 422
    assert "200 characters" in resp.json()["detail"]


def test_create_rejects_out_of_range_int(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["fetch_timeout"] = 9999
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 422
    assert "at most 600" in resp.json()["detail"]


def test_preview_lists_limit_errors_without_failing(tmp_path):
    """Over-long answers are form mistakes, so preview still renders and lists them."""
    answers = _default_answers(get_spec("fetch"))
    answers["skill_description"] = "x" * 501
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/preview", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 200
    body = resp.json()
    assert body["yaml"]
    assert any("500 characters" in e for e in body["errors"])


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #

def test_create_writes_file_and_registers_import(tmp_path):
    answers = _default_answers(get_spec("doc-generator"))
    answers["name"] = "my-pdf"
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/admin/adapters", json={"spec": "doc-generator", "answers": answers})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "my-pdf"
    assert body["registered"] is True

    config_dir = tmp_path / "config"
    written = config_dir / "adapters" / "my-pdf.yaml"
    assert written.is_file()
    assert 'name: "my-pdf"' in written.read_text(encoding="utf-8")
    assert '- "adapters/my-pdf.yaml"' in (config_dir / "adapters.yaml").read_text(encoding="utf-8")


def test_create_is_conflict_on_existing_file(tmp_path):
    answers = _default_answers(get_spec("doc-generator"))
    answers["name"] = "my-pdf"
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        assert client.post("/admin/adapters",
                           json={"spec": "doc-generator", "answers": answers}).status_code == 200
        second = client.post("/admin/adapters", json={"spec": "doc-generator", "answers": answers})
        assert second.status_code == 409

        overwritten = client.post("/admin/adapters",
                                  json={"spec": "doc-generator", "answers": answers,
                                        "overwrite": True})
        assert overwritten.status_code == 200

    # Overwriting must not duplicate the import entry.
    text = (tmp_path / "config" / "adapters.yaml").read_text(encoding="utf-8")
    assert text.count('- "adapters/my-pdf.yaml"') == 1


def test_create_detects_name_collision_in_another_file(tmp_path):
    """'fetch' already exists inside fetch.yaml, so fetch-2.yaml must be rejected."""
    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "fetch"
    app = _build_app(tmp_path)
    # Force a different filename by writing the adapter under a name that is free
    # as a file but taken as an adapter name.
    (tmp_path / "config" / "adapters" / "fetch.yaml").write_text(
        "adapters:\n  - name: fetch\n    type: fetch\n", encoding="utf-8"
    )
    with TestClient(app) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_overwrite_does_not_waive_cross_file_name_collision(tmp_path):
    """overwrite only forgives the target *file*; a name owned by another file is still 409.

    Otherwise overwrite would be a route to the duplicate definition the guard exists
    to prevent — two files declaring 'fetch', one silently shadowing the other.
    """
    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "fetch"
    app = _build_app(tmp_path)
    # 'fetch' is defined in fetch.yaml; creating fetch.yaml-the-file is not the issue,
    # so put the existing definition in a differently-named file.
    adapters = tmp_path / "config" / "adapters"
    (adapters / "fetch.yaml").unlink()
    (adapters / "legacy.yaml").write_text(
        "adapters:\n  - name: fetch\n    type: fetch\n", encoding="utf-8"
    )
    with TestClient(app) as client:
        resp = client.post("/admin/adapters",
                           json={"spec": "fetch", "answers": answers, "overwrite": True})
    assert resp.status_code == 409
    assert "legacy.yaml" in resp.json()["detail"]
    assert not (adapters / "fetch.yaml").exists()


def test_create_rejects_unsafe_name(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "../escape"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 400


def test_create_requires_a_name(tmp_path):
    answers = _default_answers(get_spec("fetch"))
    answers["name"] = None
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #

_MULTI = """adapters:
  - name: alpha
    type: passthrough
    inference_provider: ollama

  - name: beta
    type: passthrough
    inference_provider: ollama
"""


def test_delete_removes_file_and_import_line(tmp_path):
    app = _build_app(tmp_path)
    config_dir = tmp_path / "config"
    with TestClient(app) as client:
        resp = client.delete("/admin/adapters/fetch")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_removed"] is True
    assert body["unregistered"] is True
    assert not (config_dir / "adapters" / "fetch.yaml").exists()
    assert "adapters/fetch.yaml" not in (config_dir / "adapters.yaml").read_text(encoding="utf-8")


def test_delete_from_multi_adapter_file_keeps_siblings(tmp_path):
    app = _build_app(tmp_path)
    config_dir = tmp_path / "config"
    multi = config_dir / "adapters" / "multi.yaml"
    multi.write_text(_MULTI, encoding="utf-8")

    with TestClient(app) as client:
        resp = client.delete("/admin/adapters/alpha")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_removed"] is False
    assert body["filename"] == "multi.yaml"

    text = multi.read_text(encoding="utf-8")
    assert "name: alpha" not in text
    assert "name: beta" in text
    assert yaml.safe_load(text)["adapters"][0]["name"] == "beta"


def test_delete_is_conflict_when_another_adapter_lists_it_as_a_skill(tmp_path):
    app = _build_app(tmp_path)
    adapters = tmp_path / "config" / "adapters"
    (adapters / "router.yaml").write_text(
        "adapters:\n"
        "  - name: router\n"
        "    type: passthrough\n"
        "    capabilities:\n"
        "      available_skills:\n"
        "        - fetch\n",
        encoding="utf-8",
    )

    with TestClient(app) as client:
        blocked = client.delete("/admin/adapters/fetch")
        assert blocked.status_code == 409
        assert "router" in blocked.json()["detail"]
        assert (adapters / "fetch.yaml").exists()

        forced = client.delete("/admin/adapters/fetch?force=true")
        assert forced.status_code == 200, forced.text

    assert not (adapters / "fetch.yaml").exists()


@pytest.mark.parametrize("referring_config,kind", [
    ("      child_adapters:\n        - fetch\n", "child_adapters"),
    ('      grounding_adapter: "fetch"\n', "grounding_adapter"),
])
def test_delete_is_conflict_on_non_skill_adapter_dependencies(tmp_path, referring_config, kind):
    """Composite children and realtime grounding targets are resolved by name at
    runtime, so deleting one silently breaks the referring adapter."""
    app = _build_app(tmp_path)
    adapters = tmp_path / "config" / "adapters"
    (adapters / "dependent.yaml").write_text(
        "adapters:\n"
        "  - name: dependent\n"
        "    type: retriever\n"
        "    config:\n" + referring_config,
        encoding="utf-8",
    )

    with TestClient(app) as client:
        blocked = client.delete("/admin/adapters/fetch")
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert "dependent" in detail and kind in detail
        assert (adapters / "fetch.yaml").exists()

        assert client.delete("/admin/adapters/fetch?force=true").status_code == 200

    assert not (adapters / "fetch.yaml").exists()


def test_delete_unknown_adapter_is_404(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        assert client.delete("/admin/adapters/nope").status_code == 404


def test_delete_rejects_unsafe_name(tmp_path):
    """A name that would escape config/adapters/ is refused before any file work.

    Separators never reach the handler at all — they don't route to a single path
    segment — so the dotted form is what proves the name guard itself fires.
    """
    with TestClient(_build_app(tmp_path)) as client:
        assert client.delete("/admin/adapters/..%2Fescape").status_code == 404
        assert client.delete("/admin/adapters/has.dot").status_code == 400
    assert (tmp_path / "config" / "adapters" / "fetch.yaml").exists()


# --------------------------------------------------------------------------- #
# Permissions
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("roles,allowed", [(["admin"], True), (["operator"], True),
                                           (["analyst"], False), (["user"], False)])
def test_create_routes_require_adapters_manage(tmp_path, roles, allowed):
    app = _build_app(tmp_path, roles=roles)
    with TestClient(app) as client:
        responses = [
            client.get("/admin/adapters/specs"),
            client.post("/admin/adapters/preview", json={"spec": "fetch", "answers": {}}),
            client.post("/admin/adapters", json={"spec": "fetch", "answers": {}}),
            client.delete("/admin/adapters/fetch"),
        ]
    for resp in responses:
        if allowed:
            assert resp.status_code not in (401, 403)
        else:
            # permission_or_api_key answers 401 when the caller holds no admin
            # permission at all, 403 when it holds some but not adapters.manage.
            assert resp.status_code in (401, 403)
