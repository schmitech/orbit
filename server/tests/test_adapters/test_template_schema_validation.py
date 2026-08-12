"""
Unit tests for the intent template schema and validator
(server/adapters/templates/schema.py, validator.py).

Includes a sweep of every real template library under examples/intent-templates/
per the Phase 3A verification checklist: warn-mode validation must produce
findings for the known-bad cases and zero errors for the well-formed ones.
"""

import glob
import os

import pytest
import yaml

from adapters.http.adapter import HttpAdapter
from adapters.templates.schema import ParameterSpec, TemplateSpec
from adapters.templates.validator import (
    TemplateValidationError,
    content_hash,
    scan_scaffolding_markers,
    validate_library,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples", "intent-templates")

HR_TEMPLATES_PATH = os.path.join(
    EXAMPLES_DIR, "sql-intent-template", "sqlite", "hr", "hr-templates.yaml"
)
CUSTOMER_ORDERS_PATH = os.path.join(
    EXAMPLES_DIR, "sql-intent-template", "postgres", "customer-orders", "customer_orders_templates.yaml"
)


def _minimal_template(**overrides):
    template = {
        "id": "get_employee_by_email",
        "description": "Look up an employee by email",
        "nl_examples": ["find employee with email {email}"],
        "sql": "SELECT * FROM employees WHERE email = ?",
        "parameters": [{"name": "email", "type": "string", "required": True}],
    }
    template.update(overrides)
    return template


class TestParameterSpec:
    def test_minimal_parameter_valid(self):
        ParameterSpec(name="email", type="string", required=True)

    def test_unknown_field_rejected(self):
        with pytest.raises(Exception):
            ParameterSpec(name="email", type="string", enum=["a", "b"])


class TestTemplateSpec:
    def test_minimal_template_valid(self):
        TemplateSpec.model_validate(_minimal_template())

    def test_missing_version_defaults(self):
        spec = TemplateSpec.model_validate(_minimal_template())
        assert spec.version == "0.0.0"

    def test_missing_approved_defaults_false(self):
        spec = TemplateSpec.model_validate(_minimal_template())
        assert spec.approved is False

    def test_unknown_top_level_field_rejected(self):
        with pytest.raises(Exception):
            TemplateSpec.model_validate(_minimal_template(totally_unknown_field=True))

    def test_semantic_tags_list_of_dicts_coerced_to_single_dict(self):
        spec = TemplateSpec.model_validate(
            _minimal_template(semantic_tags=[{"action": "search"}, {"primary_entity": "employees"}])
        )
        assert spec.semantic_tags == {"action": "search", "primary_entity": "employees"}

    def test_validation_hint_is_a_recognized_parameter_field(self):
        # Real field used by examples/intent-templates/http-intent-template/examples/
        # paris-open-data — must not be treated as schema drift.
        TemplateSpec.model_validate(_minimal_template(
            parameters=[{"name": "arrondissement", "type": "string", "validation_hint": "e.g. 75001"}]
        ))

    def test_backend_specific_payloads_all_optional(self):
        # A GraphQL-shaped template with no sql/mongodb/etc. fields is still valid.
        TemplateSpec.model_validate({
            "id": "get_rocket_by_id",
            "description": "Get a rocket by id",
            "graphql_template": "query GetRocket($id: ID!) { rocket(id: $id) { name } }",
            "parameters": [{"name": "id", "type": "string", "required": True}],
        })


class TestContentHash:
    def test_deterministic(self):
        t = _minimal_template()
        assert content_hash(t) == content_hash(dict(t))

    def test_changes_with_content(self):
        assert content_hash(_minimal_template()) != content_hash(_minimal_template(description="different"))


class TestScanScaffoldingMarkers:
    def test_finds_fixme_and_todo(self):
        text = "id: foo #FIXME\nid: bar\n# TODO clean this up\n"
        markers = scan_scaffolding_markers(text)
        assert len(markers) == 2
        assert "line 1" in markers[0]
        assert "line 3" in markers[1]

    def test_no_markers_returns_empty(self):
        assert scan_scaffolding_markers("id: foo\ndescription: bar\n") == []


class TestValidateLibrary:
    def test_valid_library_no_findings(self):
        raw = {"templates": [_minimal_template()]}
        report = validate_library(raw, path="in-memory")
        assert report.template_count == 1
        assert not report.findings

    def test_invalid_field_reported_as_warn_finding_not_raised(self):
        raw = {"templates": [_minimal_template(parameters=[{"name": "x", "enum": ["a"]}])]}
        report = validate_library(raw, path="in-memory", strict=False)
        assert report.has_errors
        assert any("enum" in str(f) for f in report.errors)

    def test_strict_mode_raises_on_error(self):
        raw = {"templates": [_minimal_template(parameters=[{"name": "x", "enum": ["a"]}])]}
        with pytest.raises(TemplateValidationError):
            validate_library(raw, path="in-memory", strict=True)

    def test_semantic_tags_normalization_written_back_to_raw_entry(self):
        # The raw dict is what the adapter keeps and what later embedding/
        # reranking code reads via .get()/.items() — not the discarded
        # TemplateSpec instance model_validate() produces internally.
        template = _minimal_template(semantic_tags=[{"action": "search"}, {"primary_entity": "employees"}])
        raw = {"templates": [template]}
        report = validate_library(raw, path="in-memory")
        assert not report.errors
        assert template["semantic_tags"] == {"action": "search", "primary_entity": "employees"}

    def test_dict_shaped_templates_supported(self):
        raw = {"templates": {"t1": _minimal_template()}}
        report = validate_library(raw, path="in-memory")
        assert report.template_count == 1

    def test_source_text_scaffolding_markers_surfaced_as_warnings(self):
        raw = {"templates": [_minimal_template()]}
        report = validate_library(raw, path="in-memory", source_text="id: x #FIXME\n")
        assert any(f.level == "warning" for f in report.findings)


@pytest.mark.skipif(not os.path.isdir(EXAMPLES_DIR), reason="examples/intent-templates not present")
class TestRealExampleLibraries:
    """Sweep every real template library — the Phase 3A verification checklist."""

    def _load_report(self, path):
        with open(path) as f:
            source_text = f.read()
        raw = yaml.safe_load(source_text)
        return validate_library(raw, path=path, source_text=source_text)

    def test_sqlite_hr_zero_findings(self):
        report = self._load_report(HR_TEMPLATES_PATH)
        assert report.template_count > 0
        assert not report.findings, [str(f) for f in report.findings]

    def test_postgres_customer_orders_zero_errors(self):
        report = self._load_report(CUSTOMER_ORDERS_PATH)
        assert report.template_count > 0
        assert not report.errors, [str(f) for f in report.errors]

    def test_elasticsearch_fixme_ids_detected(self):
        path = os.path.join(
            EXAMPLES_DIR, "elasticsearch-intent-template", "application-logs", "templates", "logs_templates.yaml"
        )
        if not os.path.exists(path):
            pytest.skip("elasticsearch example not present")
        report = self._load_report(path)
        assert any("FIXME" in str(f) for f in report.warnings)

    def test_sweep_all_libraries_parse_without_crashing(self):
        paths = glob.glob(os.path.join(EXAMPLES_DIR, "**", "*templates*.yaml"), recursive=True)
        assert paths, "expected to find at least one template library under examples/intent-templates"
        for path in paths:
            with open(path) as f:
                source_text = f.read()
            raw = yaml.safe_load(source_text)
            if not isinstance(raw, dict) or "templates" not in raw:
                continue
            validate_library(raw, path=path, source_text=source_text)


class TestHttpAdapterValidationWiring:
    """Wiring in adapters/http/adapter.py: template_validation, require_approved, _content_hash."""

    def _write_library(self, tmp_path, templates):
        path = os.path.join(tmp_path, "templates.yaml")
        with open(path, "w") as f:
            yaml.safe_dump({"templates": templates}, f)
        return path

    def test_strict_mode_fails_adapter_init(self, tmp_path):
        path = self._write_library(tmp_path, [_minimal_template(parameters=[{"name": "x", "enum": ["a"]}])])
        with pytest.raises(TemplateValidationError):
            HttpAdapter(template_library_path=path, config={"template_validation": "strict"})

    def test_warn_mode_keeps_invalid_template(self, tmp_path):
        path = self._write_library(tmp_path, [_minimal_template(parameters=[{"name": "x", "enum": ["a"]}])])
        adapter = HttpAdapter(template_library_path=path, config={"template_validation": "warn"})
        assert len(adapter.get_all_templates()) == 1

    def test_content_hash_attached_to_loaded_templates(self, tmp_path):
        path = self._write_library(tmp_path, [_minimal_template()])
        adapter = HttpAdapter(template_library_path=path, config={})
        templates = adapter.get_all_templates()
        assert templates[0]["_content_hash"] == content_hash(
            {k: v for k, v in _minimal_template().items()}
        )

    def test_require_approved_filters_unapproved_templates(self, tmp_path):
        path = self._write_library(tmp_path, [
            _minimal_template(id="approved_one", approved=True),
            _minimal_template(id="unapproved_one"),
        ])
        adapter = HttpAdapter(template_library_path=path, config={"require_approved": True})
        ids = [t["id"] for t in adapter.get_all_templates()]
        assert ids == ["approved_one"]

    def test_require_approved_off_by_default(self, tmp_path):
        path = self._write_library(tmp_path, [
            _minimal_template(id="approved_one", approved=True),
            _minimal_template(id="unapproved_one"),
        ])
        adapter = HttpAdapter(template_library_path=path, config={})
        ids = {t["id"] for t in adapter.get_all_templates()}
        assert ids == {"approved_one", "unapproved_one"}

    def test_require_approved_also_blocks_lookup_by_id(self, tmp_path):
        # get_template_by_id() is the path vector search hits with a template_id
        # from a persistent embedding collection — it must enforce the same
        # approval predicate as get_all_templates(), not just the listing path.
        path = self._write_library(tmp_path, [
            _minimal_template(id="approved_one", approved=True),
            _minimal_template(id="unapproved_one"),
        ])
        adapter = HttpAdapter(template_library_path=path, config={"require_approved": True})
        assert adapter.get_template_by_id("unapproved_one") is None
        assert adapter.get_template_by_id("approved_one") is not None

    def test_lookup_by_id_unaffected_when_require_approved_off(self, tmp_path):
        path = self._write_library(tmp_path, [_minimal_template(id="unapproved_one")])
        adapter = HttpAdapter(template_library_path=path, config={})
        assert adapter.get_template_by_id("unapproved_one") is not None
