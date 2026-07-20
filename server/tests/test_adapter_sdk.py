"""
Tests for the adapter SDK (server/adapter_sdk/*).

Run with the venv python from the repo root (server/ is the import root, set up by
server/tests/conftest.py):

    venv/bin/python -m pytest server/tests/test_adapter_sdk.py
"""

import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import yaml

from adapter_sdk.renderer import render_adapter
from adapter_sdk.specs import SPEC_REGISTRY, AdapterSpec
from adapter_sdk.validator import validate_structure, validate_yaml_text
from adapter_sdk import writer

_REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ADAPTERS = _REPO_ROOT / "config" / "adapters"


def _default_answers(spec: AdapterSpec, variant: Optional[str] = None) -> Dict[str, Any]:
    """Simulate a wizard run where every question is left at its (variant-aware) default."""
    if spec.variant_field and variant is None:
        variant = spec.variant_values()[0]
    answers: Dict[str, Any] = {}
    for q in spec.questions:
        if spec.variant_field and q.field == spec.variant_field:
            answers[q.field] = variant
        else:
            answers[q.field] = spec.question_default(q, variant)
    return answers


def _structure_keys(data: Any, prefix: str = "") -> set:
    """Recursive key-path set (lists analyzed via first element)."""
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            keys |= _structure_keys(v, full)
    elif isinstance(data, list) and data:
        keys |= _structure_keys(data[0], prefix + "[0]")
    return keys


# --------------------------------------------------------------------------- #
# Render + validate every spec (and every variant)
# --------------------------------------------------------------------------- #

def _spec_variant_params():
    params = []
    for key, spec in SPEC_REGISTRY.items():
        if spec.variant_field:
            for v in spec.variant_values():
                params.append(pytest.param(key, v, id=f"{key}:{v}"))
        else:
            params.append(pytest.param(key, None, id=key))
    return params


@pytest.mark.unit
@pytest.mark.parametrize("spec_key,variant", _spec_variant_params())
def test_render_and_validate(spec_key, variant):
    spec = SPEC_REGISTRY[spec_key]
    answers = _default_answers(spec, variant)
    text = render_adapter(spec, answers)

    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict) and isinstance(parsed["adapters"], list)
    assert len(parsed["adapters"]) == 1

    entry = parsed["adapters"][0]
    for f in ("name", "type", "datasource", "adapter", "implementation"):
        assert entry.get(f), f"{spec_key}:{variant} missing {f}"

    assert validate_yaml_text(text) == []


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["docx-typo", None, ""])
def test_render_rejects_unknown_variant(bad):
    spec = SPEC_REGISTRY["doc-generator"]  # variant_field = document_format
    answers = _default_answers(spec, "pdf")
    answers["document_format"] = bad
    with pytest.raises(ValueError, match="document_format"):
        render_adapter(spec, answers)


@pytest.mark.unit
def test_render_rejects_missing_variant_key():
    spec = SPEC_REGISTRY["web-search-external"]  # variant_field = search_provider
    answers = _default_answers(spec, "brave")
    del answers["search_provider"]
    with pytest.raises(ValueError, match="search_provider"):
        render_adapter(spec, answers)


# --------------------------------------------------------------------------- #
# Round-trip: regenerate a committed adapter and match its structure + values
# --------------------------------------------------------------------------- #

@pytest.mark.unit
def test_roundtrip_pdf_generator():
    spec = SPEC_REGISTRY["doc-generator"]
    answers = _default_answers(spec, "pdf")
    generated = yaml.safe_load(render_adapter(spec, answers))["adapters"][0]

    committed = yaml.safe_load((CONFIG_ADAPTERS / "pdf-generator.yaml").read_text())["adapters"][0]

    committed_keys = _structure_keys(committed)
    generated_keys = _structure_keys(generated)
    missing = committed_keys - generated_keys
    assert not missing, f"generated pdf-generator missing keys: {sorted(missing)}"

    for f in ("name", "type", "document_format", "datasource", "adapter", "implementation"):
        assert generated[f] == committed[f], f"{f}: {generated[f]!r} != {committed[f]!r}"
    assert generated["capabilities"]["skill_name"] == committed["capabilities"]["skill_name"]


# --------------------------------------------------------------------------- #
# Validator
# --------------------------------------------------------------------------- #

@pytest.mark.unit
def test_validator_flags_missing_required_field():
    errors = validate_structure({"name": "x", "type": "passthrough"})
    assert any("datasource" in e for e in errors)
    assert any("adapter" in e for e in errors)
    assert any("implementation" in e for e in errors)


@pytest.mark.unit
def test_validator_flags_bad_capability_enum():
    entry = {
        "name": "x", "type": "passthrough", "datasource": "none", "adapter": "conversational",
        "implementation": "impl", "capabilities": {"retrieval_behavior": "bogus"},
    }
    errors = validate_structure(entry)
    assert any("capabilities" in e for e in errors)


@pytest.mark.unit
def test_validator_flags_duplicate_names():
    text = """
adapters:
  - {name: dup, type: passthrough, datasource: none, adapter: conversational, implementation: i}
  - {name: dup, type: passthrough, datasource: none, adapter: conversational, implementation: i}
"""
    errors = validate_yaml_text(text)
    assert any("duplicate" in e for e in errors)


# --------------------------------------------------------------------------- #
# Writer (against a temp copy — never touches the real config)
# --------------------------------------------------------------------------- #

@pytest.mark.unit
def test_writer_writes_and_registers(tmp_path):
    adapters_dir = tmp_path / "adapters"
    adapters_dir.mkdir()
    adapters_yaml = tmp_path / "adapters.yaml"
    shutil.copy(_REPO_ROOT / "config" / "adapters.yaml", adapters_yaml)

    spec = SPEC_REGISTRY["fetch"]
    answers = _default_answers(spec)
    answers["name"] = "my-fetch-test"
    text = render_adapter(spec, answers)

    path = writer.write_adapter(
        "my-fetch-test", text,
        adapters_dir=adapters_dir, adapters_yaml=adapters_yaml,
    )
    assert path.exists()
    assert writer.is_registered("adapters/my-fetch-test.yaml", adapters_yaml)

    added_again = writer.register_import("adapters/my-fetch-test.yaml", adapters_yaml)
    assert added_again is False
    assert adapters_yaml.read_text().count('adapters/my-fetch-test.yaml') == 1


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", [
    "../evil", "../../etc/passwd", "/abs/path", "a/b", "a\\b", "..", ".hidden", "has.dot", "", "with space",
])
def test_writer_rejects_unsafe_names(tmp_path, bad_name):
    adapters_dir = tmp_path / "adapters"
    adapters_dir.mkdir()
    with pytest.raises(ValueError, match="invalid adapter name"):
        writer.write_adapter(bad_name, "adapters: []\n", register=False,
                             adapters_dir=adapters_dir, overwrite=True)
    # Nothing escaped the target directory.
    assert list(tmp_path.rglob("*.yaml")) == []


@pytest.mark.unit
def test_writer_refuses_overwrite(tmp_path):
    adapters_dir = tmp_path / "adapters"
    adapters_dir.mkdir()
    (adapters_dir / "dup.yaml").write_text("adapters: []\n")
    with pytest.raises(FileExistsError):
        writer.write_adapter("dup", "adapters: []\n", register=False, adapters_dir=adapters_dir)


# --------------------------------------------------------------------------- #
# Enricher (provider mocked — no network)
# --------------------------------------------------------------------------- #

@pytest.mark.unit
async def test_enricher_returns_only_soft_fields(monkeypatch):
    from adapter_sdk import enricher

    class _FakeClient:
        async def generate(self, prompt):
            return ('Here you go: {"skill_description": "Make PDFs", '
                    '"routing_examples": ["make a pdf", "export as pdf"], '
                    '"name": "SHOULD_BE_IGNORED"}')

    monkeypatch.setattr(
        enricher.UnifiedProviderFactory, "create_provider_by_name",
        staticmethod(lambda provider, config: _FakeClient()),
    )

    spec = SPEC_REGISTRY["doc-generator"]
    result = await enricher.enrich_soft_fields(spec, "I want to make PDFs", provider="openai")

    assert result["skill_description"] == "Make PDFs"
    assert result["routing_examples"] == ["make a pdf", "export as pdf"]
    assert "name" not in result
