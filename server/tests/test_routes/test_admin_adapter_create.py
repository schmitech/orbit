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
# Hardening: provider validation, skill-name collisions, multi-worker propagation
# --------------------------------------------------------------------------- #

def test_create_rejects_disabled_inference_provider(tmp_path):
    app = _build_app(tmp_path)
    app.state.config = {"inference": {"openai": {"enabled": True}, "anthropic": {"enabled": False}}}
    answers = _default_answers(get_spec("passthrough"))
    answers["name"] = "provider-check"
    answers["inference_provider"] = "anthropic"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters", json={"spec": "passthrough", "answers": answers})
    assert resp.status_code == 422
    assert "anthropic" in resp.json()["detail"]


def test_create_allows_enabled_inference_provider(tmp_path):
    app = _build_app(tmp_path)
    app.state.config = {"inference": {"openai": {"enabled": True}}}
    answers = _default_answers(get_spec("passthrough"))
    answers["name"] = "provider-check-ok"
    answers["inference_provider"] = "openai"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters", json={"spec": "passthrough", "answers": answers})
    assert resp.status_code == 200, resp.text


def test_create_skips_provider_check_without_inference_config(tmp_path):
    # app.state.config == {} in the shared fixture — no `inference:` section at all,
    # which must skip the check rather than reject every provider as "not enabled".
    answers = _default_answers(get_spec("passthrough"))
    answers["name"] = "provider-check-skip"
    answers["inference_provider"] = "some-unconfigured-provider"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "passthrough", "answers": answers})
    assert resp.status_code == 200, resp.text


def test_create_rejects_duplicate_skill_name(tmp_path):
    app = _build_app(tmp_path)
    first = _default_answers(get_spec("fetch"))
    first["name"] = "fetch-one"
    first["skill_name"] = "Shared Skill"
    second = _default_answers(get_spec("fetch"))
    second["name"] = "fetch-two"
    second["skill_name"] = "Shared Skill"
    with TestClient(app) as client:
        assert client.post("/admin/adapters", json={"spec": "fetch", "answers": first}).status_code == 200
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": second})
    assert resp.status_code == 409
    assert "Shared Skill" in resp.json()["detail"]
    assert "fetch-one" in resp.json()["detail"]


def test_skill_name_scan_skips_non_mapping_yaml_files(tmp_path):
    """A malformed but syntactically-valid adapter file (root is a list, or a bare
    scalar) must not crash the skill-name collision scan — it should be skipped,
    the same as invalid YAML, rather than raising AttributeError on `.get()`."""
    from routes.admin.adapters import _find_skill_name_owner

    adapters_dir = _config_dir(tmp_path) / "adapters"
    (adapters_dir / "not-a-mapping.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    (adapters_dir / "a-bare-scalar.yaml").write_text("just a string\n", encoding="utf-8")

    assert _find_skill_name_owner(adapters_dir, "Unique Skill") is None


def test_create_tolerates_non_mapping_yaml_files_in_adapters_dir(tmp_path):
    """End-to-end: a malformed sibling file elsewhere in config/adapters/ must not
    break create — _find_adapter_file's cross-file collision check and
    _find_skill_name_owner's collision scan both walk every file in the directory."""
    app = _build_app(tmp_path)
    adapters_dir = tmp_path / "config" / "adapters"
    (adapters_dir / "not-a-mapping.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    (adapters_dir / "a-bare-scalar.yaml").write_text("just a string\n", encoding="utf-8")

    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "fetch-past-malformed-files"
    answers["skill_name"] = "Unique Skill"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 200, resp.text


def test_delete_referrer_check_tolerates_non_mapping_yaml_files(tmp_path):
    """Same hardening, exercised through delete's referrer scan
    (_find_adapter_referrers), which walks every adapter file the same way."""
    app = _build_app(tmp_path)
    adapters_dir = tmp_path / "config" / "adapters"
    (adapters_dir / "not-a-mapping.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    (adapters_dir / "a-bare-scalar.yaml").write_text("just a string\n", encoding="utf-8")

    with TestClient(app) as client:
        resp = client.delete("/admin/adapters/fetch")
    assert resp.status_code == 200, resp.text


def test_create_overwrite_does_not_trip_its_own_skill_name(tmp_path):
    app = _build_app(tmp_path)
    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "fetch-self"
    answers["skill_name"] = "Self Skill"
    with TestClient(app) as client:
        assert client.post("/admin/adapters", json={"spec": "fetch", "answers": answers}).status_code == 200
        answers["fetch_timeout"] = 45
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers, "overwrite": True})
    assert resp.status_code == 200, resp.text


def test_import_rejects_duplicate_skill_name(tmp_path):
    app = _build_app(tmp_path)
    existing = _default_answers(get_spec("fetch"))
    existing["name"] = "fetch-existing"
    existing["skill_name"] = "Import Collision"
    payload = (
        "adapters:\n  - name: fetch-new\n    type: fetch\n    datasource: none\n"
        "    adapter: conversational\n    implementation: x\n"
        "    fetch_timeout: 30\n    fetch_user_agent: bot\n"
        "    capabilities:\n      skill_name: Import Collision\n"
    )
    with TestClient(app) as client:
        assert client.post("/admin/adapters", json={"spec": "fetch", "answers": existing}).status_code == 200
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 409
    assert "Import Collision" in resp.json()["detail"]


def test_create_propagates_generation_under_supervisor(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_SUPERVISOR_PID", "1234")
    calls = []

    async def fake_bump_generation(app_state, kind):
        calls.append(kind)
        return 7

    monkeypatch.setattr("services.adapter_reload_state.bump_generation", fake_bump_generation)

    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "propagation-check"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 200, resp.text
    assert calls == ["adapter_config"]


def test_create_does_not_propagate_generation_without_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBIT_SUPERVISOR_PID", raising=False)
    calls = []

    async def fake_bump_generation(app_state, kind):
        calls.append(kind)
        return 7

    monkeypatch.setattr("services.adapter_reload_state.bump_generation", fake_bump_generation)

    answers = _default_answers(get_spec("fetch"))
    answers["name"] = "no-propagation-check"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters", json={"spec": "fetch", "answers": answers})
    assert resp.status_code == 200, resp.text
    assert calls == []


# --------------------------------------------------------------------------- #
# Export / Import
# --------------------------------------------------------------------------- #

def test_export_returns_standalone_yaml_document(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.get("/admin/adapters/fetch/export")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="fetch.yaml"'
    parsed = yaml.safe_load(resp.text)
    assert parsed["adapters"][0]["name"] == "fetch"


def test_export_unknown_adapter_is_404(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.get("/admin/adapters/does-not-exist/export")
    assert resp.status_code == 404


def test_import_roundtrips_an_export(tmp_path):
    app = _build_app(tmp_path)
    (tmp_path / "config" / "adapters" / "fetch.yaml").write_text(
        "adapters:\n  - name: fetch\n    type: fetch\n    datasource: none\n"
        "    adapter: conversational\n    implementation: x\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        exported = client.get("/admin/adapters/fetch/export").text
        # Deleting the file but leaving its (still-present) import line behind
        # simulates moving the adapter to a fresh environment that already has
        # some other unrelated import to anchor new registrations against.
        (tmp_path / "config" / "adapters" / "fetch.yaml").unlink()

        resp = client.post("/admin/adapters/import", json={"content": exported})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "fetch"
    assert body["registered"] is True

    config_dir = tmp_path / "config"
    assert (config_dir / "adapters" / "fetch.yaml").is_file()
    assert '- "adapters/fetch.yaml"' in (config_dir / "adapters.yaml").read_text(encoding="utf-8")


def test_import_rejects_invalid_yaml(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": "not: valid: yaml: at: all:"})
    assert resp.status_code == 422


def test_import_rejects_missing_required_field(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import",
                           json={"content": "adapters:\n  - name: broken\n"})
    assert resp.status_code == 422


def test_import_accepts_bare_list_entry(tmp_path):
    """A single '- name: ...' entry copied out of a multi-adapter file, with no
    surrounding 'adapters:' wrapper, should import just like a full export."""
    payload = ("- name: bare-list\n"
               "  type: fetch\n"
               "  datasource: none\n"
               "  adapter: conversational\n"
               "  implementation: x\n")
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "bare-list"
    written = (tmp_path / "config" / "adapters" / "bare-list.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(written)["adapters"][0]["name"] == "bare-list"


def test_import_accepts_snippet_copied_at_nested_indentation(tmp_path):
    """Copying one adapter's block straight out of a multi-adapter file (as it appears
    on screen, e.g. selecting lines in an editor) keeps that file's 2-space base indent
    and CRLF line endings from the clipboard. Both must be tolerated."""
    payload = ("  - name: nested-copy\r\n"
               "    type: fetch\r\n"
               "    datasource: none\r\n"
               "    adapter: conversational\r\n"
               "    implementation: x\r\n")
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "nested-copy"


def test_import_accepts_bare_mapping(tmp_path):
    """A bare mapping (no 'adapters:' key, no leading '- ') is also accepted."""
    payload = ("name: bare-mapping\n"
               "type: fetch\n"
               "datasource: none\n"
               "adapter: conversational\n"
               "implementation: x\n")
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "bare-mapping"
    written = (tmp_path / "config" / "adapters" / "bare-mapping.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(written)["adapters"][0]["name"] == "bare-mapping"


def test_import_rejects_unrecognized_shape(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": "- 1\n- 2\n- 3\n"})
    assert resp.status_code == 422


def test_format_wraps_bare_mapping_under_adapters(tmp_path):
    payload = "name: bare-mapping\ntype: fetch\ndatasource: none\nadapter: conversational\nimplementation: x\n"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import/format", json={"content": payload})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == []
    assert yaml.safe_load(body["yaml"])["adapters"][0]["name"] == "bare-mapping"


def test_format_reports_errors_without_failing(tmp_path):
    payload = "adapters:\n  - name: broken\n"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import/format", json={"content": payload})
    assert resp.status_code == 200
    assert resp.json()["errors"]


def test_format_rejects_unparseable_yaml(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import/format", json={"content": "not: valid: yaml: at: all:"})
    assert resp.status_code == 422


def test_format_requires_content(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import/format", json={})
    assert resp.status_code == 422


def test_import_rejects_non_string_name_without_crashing(tmp_path):
    payload = "adapters:\n  - name: 123\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 400


def test_import_rolls_back_new_file_on_registration_failure(tmp_path):
    """If adapters.yaml has no usable import list, register_import raises after the file
    is already written — the write must be rolled back rather than left dangling."""
    app = _build_app(tmp_path)
    (tmp_path / "config" / "adapters.yaml").write_text("adapters: {}\n", encoding="utf-8")
    payload = "adapters:\n  - name: brand-new\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 500
    assert not (tmp_path / "config" / "adapters" / "brand-new.yaml").exists()


def test_import_rolls_back_overwrite_on_registration_failure(tmp_path):
    """An overwrite whose registration fails must restore the previous file contents,
    not leave the new (unregistered) content sitting on disk."""
    app = _build_app(tmp_path)
    fetch_yaml = tmp_path / "config" / "adapters" / "fetch.yaml"
    original = fetch_yaml.read_text(encoding="utf-8")
    (tmp_path / "config" / "adapters.yaml").write_text("adapters: {}\n", encoding="utf-8")
    payload = "adapters:\n  - name: fetch\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload, "overwrite": True})
    assert resp.status_code == 500
    assert fetch_yaml.read_text(encoding="utf-8") == original


def test_import_rejects_multi_adapter_bundle(tmp_path):
    bundle = "adapters:\n  - name: a\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n  - name: b\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": bundle})
    assert resp.status_code == 422
    assert "one adapter" in resp.json()["detail"]


def test_import_is_conflict_on_existing_file(tmp_path):
    exported = "adapters:\n  - name: fetch\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": exported})
        assert resp.status_code == 409

        overwritten = client.post("/admin/adapters/import", json={"content": exported, "overwrite": True})
        assert overwritten.status_code == 200


def test_import_overwrite_does_not_waive_cross_file_name_collision(tmp_path):
    """overwrite only forgives the target *file*; a name owned by another file is still 409."""
    app = _build_app(tmp_path)
    adapters = tmp_path / "config" / "adapters"
    adapters_yaml = tmp_path / "config" / "adapters.yaml"
    (adapters / "fetch.yaml").unlink()
    adapters_yaml.write_text(
        'adapters:\n  import:\n    - "adapters/legacy.yaml"\n', encoding="utf-8"
    )
    (adapters / "legacy.yaml").write_text(
        "adapters:\n  - name: fetch\n    type: fetch\n", encoding="utf-8"
    )
    payload = "adapters:\n  - name: fetch\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n"
    with TestClient(app) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload, "overwrite": True})
    assert resp.status_code == 409
    assert "legacy.yaml" in resp.json()["detail"]
    assert not (adapters / "fetch.yaml").exists()


def test_import_rejects_unsafe_name(tmp_path):
    payload = 'adapters:\n  - name: "../escape"\n    type: fetch\n    datasource: none\n    adapter: conversational\n    implementation: x\n'
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.post("/admin/adapters/import", json={"content": payload})
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Round-trip editing (edit-form)
# --------------------------------------------------------------------------- #

def test_edit_form_detects_spec_and_answers_for_a_created_adapter(tmp_path):
    spec = get_spec("passthrough")
    answers = _default_answers(spec)
    answers["name"] = "roundtrip-passthrough"
    answers["available_skills"] = ["Image"]
    with TestClient(_build_app(tmp_path)) as client:
        create = client.post("/admin/adapters", json={"spec": "passthrough", "answers": answers})
        assert create.status_code == 200, create.text

        resp = client.get("/admin/adapters/roundtrip-passthrough/edit-form")
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable"] is True
    assert body["spec"] == "passthrough"
    assert body["answers"]["name"] == "roundtrip-passthrough"
    assert body["answers"]["available_skills"] == ["Image"]


def test_edit_form_detects_variant_for_a_created_adapter(tmp_path):
    spec = get_spec("doc-generator")
    answers = _default_answers(spec, variant="docx")
    answers["name"] = "roundtrip-docx"
    with TestClient(_build_app(tmp_path)) as client:
        create = client.post("/admin/adapters", json={"spec": "doc-generator", "answers": answers})
        assert create.status_code == 200, create.text

        resp = client.get("/admin/adapters/roundtrip-docx/edit-form")
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable"] is True
    assert body["spec"] == "doc-generator"
    assert body["variant"] == "docx"
    assert body["answers"]["document_format"] == "docx"


def test_edit_save_preserves_shared_file_and_sibling(tmp_path):
    """An adapter detected as editable but living in a multi-adapter file (like
    web-search-providers.yaml) must be saved back in place, not moved to its own
    "<name>.yaml" — that's what POST /admin/adapters (create/overwrite) does, and
    it 409s here since the name is already owned by a different file. The admin
    panel's "Edit in Form" save instead goes through preview + the same
    PUT /adapters/config/entry/{name} block-splice the raw YAML editor uses."""
    duckduckgo_spec = get_spec("web-search-external")
    duckduckgo_answers = _default_answers(duckduckgo_spec, variant="duckduckgo")
    duckduckgo_answers["name"] = "web-search-duckduckgo"
    brave_answers = _default_answers(duckduckgo_spec, variant="brave")
    brave_answers["name"] = "web-search-brave"

    from adapter_sdk.renderer import render_adapter

    def block(spec, answers):
        text = render_adapter(spec, answers)
        return text[text.index("adapters:") + len("adapters:"):].strip("\n")

    app = _build_app(tmp_path)
    shared_file = tmp_path / "config" / "adapters" / "web-search-providers.yaml"
    shared_file.write_text(
        "adapters:\n"
        + block(duckduckgo_spec, duckduckgo_answers) + "\n\n"
        + block(duckduckgo_spec, brave_answers) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "adapters.yaml").write_text(
        'adapters:\n  import:\n    - "adapters/fetch.yaml"\n    - "adapters/web-search-providers.yaml"\n',
        encoding="utf-8",
    )

    with TestClient(app) as client:
        edit_form = client.get("/admin/adapters/web-search-duckduckgo/edit-form")
        assert edit_form.status_code == 200, edit_form.text
        body = edit_form.json()
        assert body["editable"] is True

        # The (unavailable, until now) create/overwrite path 409s on this name —
        # it belongs to web-search-providers.yaml, not "web-search-duckduckgo.yaml".
        rejected = client.post("/admin/adapters",
                               json={"spec": body["spec"], "answers": body["answers"], "overwrite": True})
        assert rejected.status_code == 409

        # Simulate the admin panel's actual save path: preview, then splice the
        # block back into its existing file by name.
        answers = dict(body["answers"])
        answers["result_count"] = 9
        preview = client.post("/admin/adapters/preview", json={"spec": body["spec"], "answers": answers})
        assert preview.status_code == 200, preview.text
        assert not preview.json()["errors"]

        save = client.put(
            "/admin/adapters/config/entry/web-search-duckduckgo",
            json={"content": block(duckduckgo_spec, answers)},
        )
        assert save.status_code == 200, save.text

    saved_text = shared_file.read_text(encoding="utf-8")
    parsed = yaml.safe_load(saved_text)
    names = {a["name"] for a in parsed["adapters"]}
    assert names == {"web-search-duckduckgo", "web-search-brave"}
    duckduckgo_entry = next(a for a in parsed["adapters"] if a["name"] == "web-search-duckduckgo")
    assert duckduckgo_entry["web_search"]["result_count"] == 9
    # The sibling adapter in the shared file must be untouched.
    brave_entry = next(a for a in parsed["adapters"] if a["name"] == "web-search-brave")
    assert brave_entry["web_search"]["provider"] == "brave"


def test_edit_form_unknown_adapter_is_404(tmp_path):
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.get("/admin/adapters/does-not-exist/edit-form")
    assert resp.status_code == 404


def test_edit_form_refuses_adapter_not_produced_by_a_spec(tmp_path):
    # The shared fixture's fetch.yaml is a hand-authored, incomplete entry
    # (just `type: fetch`) with no matching implementation/adapter tuple.
    with TestClient(_build_app(tmp_path)) as client:
        resp = client.get("/admin/adapters/fetch/edit-form")
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable"] is False
    assert "not" in body["reason"] or "wasn't generated" in body["reason"]


def test_edit_form_refuses_hand_edited_adapter(tmp_path):
    spec = get_spec("passthrough")
    answers = _default_answers(spec)
    answers["name"] = "hand-edited"
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        create = client.post("/admin/adapters", json={"spec": "passthrough", "answers": answers})
        assert create.status_code == 200, create.text

    # Add a field the spec doesn't model — a stand-in for an operator's manual tweak.
    adapter_file = tmp_path / "config" / "adapters" / "hand-edited.yaml"
    content = adapter_file.read_text(encoding="utf-8")
    adapter_file.write_text(content.rstrip("\n") + "\n    requires_authenticated_user: true\n", encoding="utf-8")

    with TestClient(app) as client:
        resp = client.get("/admin/adapters/hand-edited/edit-form")
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable"] is False
    assert "hand-edits" in body["reason"]


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
            client.get("/admin/adapters/fetch/export"),
            client.get("/admin/adapters/fetch/edit-form"),
            client.post("/admin/adapters/import/format", json={"content": ""}),
            client.post("/admin/adapters/import", json={"content": ""}),
            client.delete("/admin/adapters/fetch"),
        ]
    for resp in responses:
        if allowed:
            assert resp.status_code not in (401, 403)
        else:
            # permission_or_api_key answers 401 when the caller holds no admin
            # permission at all, 403 when it holds some but not adapters.manage.
            assert resp.status_code in (401, 403)
