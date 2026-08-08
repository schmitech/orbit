"""
Tests for the adapter SDK (server/adapter_sdk/*).

Run with the venv python from the repo root (server/ is the import root, set up by
server/tests/conftest.py):

    venv/bin/python -m pytest server/tests/test_adapters/test_adapter_sdk.py
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

_REPO_ROOT = Path(__file__).resolve().parents[3]
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


@pytest.mark.unit
def test_roundtrip_multimodal_simple_chat_with_files():
    spec = SPEC_REGISTRY["multimodal"]
    answers = _default_answers(spec)
    generated = yaml.safe_load(render_adapter(spec, answers))["adapters"][0]

    entries = yaml.safe_load((CONFIG_ADAPTERS / "multimodal.yaml").read_text())["adapters"]
    committed = next(e for e in entries if e["name"] == "simple-chat-with-files")

    for f in ("type", "datasource", "adapter", "implementation"):
        assert generated[f] == committed[f], f"{f}: {generated[f]!r} != {committed[f]!r}"

    gen_caps, com_caps = generated["capabilities"], committed["capabilities"]
    for f in ("retrieval_behavior", "supports_file_ids", "skip_when_no_files",
              "requires_api_key_validation", "optional_parameters"):
        assert gen_caps[f] == com_caps[f], f"capabilities.{f}: {gen_caps[f]!r} != {com_caps[f]!r}"

    gen_cfg, com_cfg = generated["config"], committed["config"]
    for f in ("storage_backend", "storage_root", "chunking_strategy", "chunk_size",
              "chunk_overlap", "vector_store", "collection_prefix"):
        assert gen_cfg[f] == com_cfg[f], f"config.{f}: {gen_cfg[f]!r} != {com_cfg[f]!r}"

    assert validate_yaml_text(render_adapter(spec, answers)) == []


@pytest.mark.unit
def test_roundtrip_multimodal_audio_variant():
    spec = SPEC_REGISTRY["multimodal"]
    answers = _default_answers(spec)
    answers["name"] = "simple-chat-with-files-audio"
    answers["enable_audio_transcription"] = True

    entries = yaml.safe_load((CONFIG_ADAPTERS / "multimodal.yaml").read_text())["adapters"]
    committed = next(e for e in entries if e["name"] == "simple-chat-with-files-audio")
    answers["supported_types"] = committed["config"]["supported_types"]

    text = render_adapter(spec, answers)
    generated = yaml.safe_load(text)["adapters"][0]

    assert generated["config"]["enable_audio_transcription"] == committed["config"]["enable_audio_transcription"]
    assert generated["config"]["supported_types"] == committed["config"]["supported_types"]
    assert validate_yaml_text(text) == []


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
# Writer — deletion
# --------------------------------------------------------------------------- #

_IMPORT_LIST = """adapters:
  import:
    # Retrieval adapters
    - "adapters/qa.yaml"
    - "adapters/doomed.yaml"
    # Generators
    - "adapters/file.yaml"
"""


def _delete_fixture(tmp_path):
    adapters_dir = tmp_path / "adapters"
    adapters_dir.mkdir()
    (adapters_dir / "doomed.yaml").write_text("adapters: []\n", encoding="utf-8")
    adapters_yaml = tmp_path / "adapters.yaml"
    adapters_yaml.write_text(_IMPORT_LIST, encoding="utf-8")
    return adapters_dir, adapters_yaml


@pytest.mark.unit
def test_unregister_import_removes_line_and_keeps_comments(tmp_path):
    _, adapters_yaml = _delete_fixture(tmp_path)

    assert writer.unregister_import("adapters/doomed.yaml", adapters_yaml) is True
    text = adapters_yaml.read_text(encoding="utf-8")
    assert "adapters/doomed.yaml" not in text
    assert "# Retrieval adapters" in text
    assert "# Generators" in text
    assert 'adapters/qa.yaml' in text and 'adapters/file.yaml' in text

    # Idempotent: a second call is a no-op, not an error.
    assert writer.unregister_import("adapters/doomed.yaml", adapters_yaml) is False


@pytest.mark.unit
def test_delete_adapter_removes_file_and_import(tmp_path):
    adapters_dir, adapters_yaml = _delete_fixture(tmp_path)

    assert writer.delete_adapter(
        "doomed", adapters_dir=adapters_dir, adapters_yaml=adapters_yaml
    ) is True
    assert not (adapters_dir / "doomed.yaml").exists()
    assert "adapters/doomed.yaml" not in adapters_yaml.read_text(encoding="utf-8")


@pytest.mark.unit
def test_delete_adapter_raises_when_missing(tmp_path):
    adapters_dir, adapters_yaml = _delete_fixture(tmp_path)
    with pytest.raises(FileNotFoundError):
        writer.delete_adapter("absent", adapters_dir=adapters_dir, adapters_yaml=adapters_yaml)
    # The import list is untouched by a failed delete.
    assert adapters_yaml.read_text(encoding="utf-8") == _IMPORT_LIST


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", ["../evil", "/abs/path", "a/b", "..", "has.dot", ""])
def test_delete_adapter_rejects_unsafe_names(tmp_path, bad_name):
    adapters_dir, adapters_yaml = _delete_fixture(tmp_path)
    with pytest.raises(ValueError, match="invalid adapter name"):
        writer.delete_adapter(bad_name, adapters_dir=adapters_dir, adapters_yaml=adapters_yaml)
    assert (adapters_dir / "doomed.yaml").exists()
