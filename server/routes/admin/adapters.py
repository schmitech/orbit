"""
Adapter capabilities, config file CRUD, creation via the adapter SDK, and hot reload.
"""

import logging
import asyncio
import importlib
import textwrap
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Body

from models.schema import (
    AdapterReloadResponse,
    TemplateReloadResponse, TemplateTestRequest,
)
from config.config_manager import reload_adapters_config
from services.mcp_auth_policy import apply_mcp_auth_policy

# Adapter SDK — generates new adapter configs from spec + answers
from jinja2 import UndefinedError
from adapter_sdk import writer as adapter_writer
from adapter_sdk.detector import detect_editable_spec
from adapter_sdk.renderer import render_adapter
from adapter_sdk.specs import get_spec, serialize_registry
from adapter_sdk.validator import validate_answers, validate_providers, validate_yaml_text

# Import auth dependencies
from routes.auth_dependencies import require_permission
from routes.admin._shared import (
    adapters_auth,
)
from routes.admin.jobs import _create_admin_job, _update_admin_job
from routes.admin._yaml_config import (
    _find_adapter_block, _find_adapter_file, _get_adapters_dir,
    _validate_adapter_filename, _write_adapter_config,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _supports_template_reload(adapter_instance, adapter_config: dict) -> bool:
    """Whether an adapter's implementation exposes reload_templates().

    Checks the live instance when cached; otherwise resolves the implementation
    class from config without instantiating it, so uncached adapters report
    accurately instead of always False.
    """
    if adapter_instance is not None:
        return hasattr(adapter_instance, 'reload_templates')

    implementation_path = (adapter_config or {}).get('implementation')
    if not implementation_path or '.' not in implementation_path:
        return False
    try:
        module_path, class_name = implementation_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        return hasattr(adapter_class, 'reload_templates')
    except Exception:
        return False


def _supports_test_query(adapter_instance, adapter_config: dict) -> bool:
    """Whether an adapter is an intent/composite retriever eligible for /test-query.

    Mirrors the isinstance check in test_adapter_query() itself. Checks the live
    instance when cached; otherwise resolves the implementation class from config
    without instantiating it, so uncached adapters report accurately.
    """
    from retrievers.base.intent_sql_base import IntentSQLRetriever
    from retrievers.base.intent_http_base import IntentHTTPRetriever
    from retrievers.base.intent_composite_base import CompositeIntentRetriever

    intent_bases = (IntentSQLRetriever, IntentHTTPRetriever, CompositeIntentRetriever)

    if adapter_instance is not None:
        return isinstance(adapter_instance, intent_bases)

    implementation_path = (adapter_config or {}).get('implementation')
    if not implementation_path or '.' not in implementation_path:
        return False
    try:
        module_path, class_name = implementation_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        return issubclass(adapter_class, intent_bases)
    except Exception:
        return False


@router.get("/adapters/capabilities", dependencies=[adapters_auth])
async def get_adapter_capabilities(
    request: Request,
):
    """Return adapter capability metadata relevant to admin operations."""
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    try:
        available_names = adapter_manager.get_available_adapters() if hasattr(adapter_manager, 'get_available_adapters') else []
        base_manager = getattr(adapter_manager, 'base_adapter_manager', adapter_manager)
        adapter_cache = getattr(base_manager, 'adapter_cache', None)

        capabilities = []
        for adapter_name in available_names:
            adapter_config = adapter_manager.get_adapter_config(adapter_name) if hasattr(adapter_manager, 'get_adapter_config') else {}
            adapter_instance = adapter_cache.get(adapter_name) if adapter_cache and adapter_cache.contains(adapter_name) else None
            capabilities.append({
                "name": adapter_name,
                "adapter_type": (adapter_config or {}).get("adapter"),
                "cached": bool(adapter_instance),
                "supports_template_reload": _supports_template_reload(adapter_instance, adapter_config),
                "supports_test_query": _supports_test_query(adapter_instance, adapter_config),
            })

        return {"adapters": capabilities}
    except Exception as e:
        logger.error(f"Failed to get adapter capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get adapter capabilities")


# ---------------------------------------------------------------------------
# Adapter config file management
# ---------------------------------------------------------------------------


@router.get("/adapters/config", dependencies=[adapters_auth])
async def list_adapter_configs(
    request: Request,
):
    """List all adapter config files with a summary of each adapter entry."""
    adapters_dir = _get_adapters_dir(request)
    if not adapters_dir.is_dir():
        return {"files": [], "imports": [], "adapters_yaml": ""}

    # Read adapters.yaml to get current imports
    adapters_yaml_path = adapters_dir.parent / "adapters.yaml"
    adapters_yaml_content = ""
    current_imports = []
    if adapters_yaml_path.is_file():
        adapters_yaml_content = adapters_yaml_path.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(adapters_yaml_content) or {}
            raw_imports = parsed.get("import", [])
            if isinstance(raw_imports, str):
                raw_imports = [raw_imports]
            current_imports = [str(i) for i in (raw_imports or [])]
        except yaml.YAMLError:
            pass

    files = []
    for yaml_file in sorted(adapters_dir.glob("*.yaml")):
        entry = {
            "filename": yaml_file.name,
            "path": f"adapters/{yaml_file.name}",
            "imported": f"adapters/{yaml_file.name}" in current_imports,
            "adapters": [],
        }
        try:
            parsed = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            for adapter in parsed.get("adapters", []):
                if isinstance(adapter, dict):
                    entry["adapters"].append({
                        "name": adapter.get("name", ""),
                        "enabled": adapter.get("enabled", True),
                        "type": adapter.get("type", ""),
                        "adapter": adapter.get("adapter", ""),
                        "datasource": adapter.get("datasource", ""),
                        "inference_provider": adapter.get("inference_provider", ""),
                        "model": adapter.get("model", ""),
                        "embedding_provider": adapter.get("embedding_provider", ""),
                        "allowed_models": adapter.get("allowed_models") or [],
                        "allowed_image_models": adapter.get("allowed_image_models") or [],
                    })
        except Exception:
            pass  # File might have invalid YAML — show it anyway with empty adapters
        files.append(entry)

    return {"files": files, "imports": current_imports, "adapters_yaml": adapters_yaml_content}


@router.get("/adapters/config/entry/{adapter_name}", dependencies=[adapters_auth])
async def get_adapter_entry(
    adapter_name: str,
    request: Request,
):
    """Return just the YAML block for a single adapter (preserves comments)."""
    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    block = "\n".join(lines[start:end])
    return {"content": block, "filename": file_path.name, "adapter_name": adapter_name}


@router.put("/adapters/config/entry/{adapter_name}", dependencies=[adapters_auth])
async def save_adapter_entry(
    adapter_name: str,
    request: Request,
    body: dict = Body(...)
):
    """Replace a single adapter's YAML block in its source file."""
    new_block = body.get("content")
    if new_block is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    try:
        yaml.safe_load(new_block)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    new_lines = lines[:start] + new_block.split("\n") + lines[end:]
    new_content = "\n".join(new_lines)
    _write_adapter_config(file_path, new_content)
    return {
        "message": f"Adapter '{adapter_name}' saved. Use 'Reload Adapter' to apply changes.",
    }


@router.patch("/adapters/config/entry/{adapter_name}/toggle", dependencies=[adapters_auth])
async def toggle_adapter_enabled(
    adapter_name: str,
    request: Request,
    body: dict = Body(...)
):
    """Toggle the enabled field of a single adapter in its YAML file."""
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=422, detail="Missing 'enabled' field")

    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    enabled_str = "true" if enabled else "false"
    found_enabled = False
    for i in range(start, end):
        stripped = lines[i].lstrip()
        if stripped.startswith("enabled:"):
            indent = lines[i][:len(lines[i]) - len(stripped)]
            lines[i] = f"{indent}enabled: {enabled_str}"
            found_enabled = True
            break

    if not found_enabled:
        name_line = lines[start]
        indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)
        lines.insert(start + 1, f"{indent}enabled: {enabled_str}")

    new_content = "\n".join(lines)
    _write_adapter_config(file_path, new_content)

    state = "enabled" if enabled else "disabled"

    # Apply the change to the running adapter manager so the toggle takes
    # effect immediately (disabled adapters are evicted from cache and
    # removed from config_manager; enabled adapters are preloaded).
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config, adapter_name)
            apply_mcp_auth_policy(request.app.state, new_config)
        except Exception as e:
            logger.error(
                f"Adapter '{adapter_name}' YAML was {state} but runtime reload failed: {e}",
                exc_info=True,
            )
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"
        logger.warning(
            f"Adapter '{adapter_name}' YAML was {state} but runtime reload skipped: {reload_error}"
        )

    if reload_error:
        message = (
            f"Adapter '{adapter_name}' {state} in config, but runtime reload failed "
            f"({reload_error}). Use 'Reload Adapter' to apply."
        )
    else:
        message = f"Adapter '{adapter_name}' {state} and applied."

    return {
        "message": message,
        "enabled": enabled,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


@router.get("/adapters/config/{filename}", dependencies=[adapters_auth])
async def get_adapter_config_file(
    filename: str,
    request: Request,
):
    """Read the raw YAML content of a specific adapter config file."""
    _validate_adapter_filename(filename)
    file_path = _get_adapters_dir(request) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Adapter file not found: {filename}")
    content = file_path.read_text(encoding="utf-8")
    return {"content": content, "filename": filename}


@router.put("/adapters/config/{filename}", dependencies=[adapters_auth])
async def save_adapter_config_file(
    filename: str,
    request: Request,
    body: dict = Body(...)
):
    """Validate and write an adapter config file."""
    _validate_adapter_filename(filename)

    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    file_path = _get_adapters_dir(request) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Adapter file not found: {filename}")

    _write_adapter_config(file_path, content)
    return {
        "message": f"Adapter config '{filename}' saved. Use 'Reload Adapter' to apply changes.",
    }


# ---------------------------------------------------------------------------
# Adapter creation (adapter SDK)
# ---------------------------------------------------------------------------

def _adapter_sdk_paths(request: Request) -> tuple[Path, Path]:
    """Adapters dir + adapters.yaml for the *running* config.

    The SDK writer's module constants are repo-root relative; the server may run
    with --config elsewhere, so both paths are always passed explicitly.
    """
    adapters_dir = _get_adapters_dir(request)
    return adapters_dir, adapters_dir.parent / "adapters.yaml"


def _render_from_spec(spec_key: str, answers: Dict[str, Any]) -> str:
    """Render a spec + answers to YAML, mapping SDK errors onto HTTP codes."""
    try:
        spec = get_spec(spec_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        return render_adapter(spec, answers)
    except ValueError as exc:
        # Bad/missing variant — the message already lists the valid values.
        raise HTTPException(status_code=422, detail=str(exc))
    except UndefinedError as exc:
        raise HTTPException(status_code=422, detail=f"Missing answer: {exc}")


def _enabled_inference_providers(config: Dict[str, Any]) -> Optional[set]:
    """The set of provider names enabled under `inference:`, for `validate_providers`.

    Mirrors `ai_services.registry._is_enabled`'s bool/str-flag semantics (a
    provider with no `enabled` key defaults to enabled) without importing that
    module's startup-registration side effects. Returns None (skip the check)
    when the running config has no `inference` section at all — an empty dict
    would instead mean "every provider is disabled," which is never the intent
    of a missing section.
    """
    inference_cfg = config.get("inference")
    if not isinstance(inference_cfg, dict):
        return None

    def is_enabled(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() != "false"
        return True

    return {
        name for name, settings in inference_cfg.items()
        if isinstance(settings, dict) and is_enabled(settings.get("enabled", True))
    }


async def _propagate_adapter_generation(request: Request, action: str) -> None:
    """Bump the cross-worker adapter-config generation counter, if running under
    a multi-worker supervisor. `create_adapter`/`import_adapter`/`delete_adapter`
    each apply their change to the worker that served the request only — under
    `performance.workers > 1`, sibling workers only pick it up once this counter
    changes (see server/services/adapter_reload_state.py). `action` is just for
    the warning log line (e.g. "creation", "import", "deletion")."""
    import os
    if not os.environ.get("ORBIT_SUPERVISOR_PID"):
        return
    from services import adapter_reload_state
    new_generation = await adapter_reload_state.bump_generation(request.app.state, "adapter_config")
    if new_generation is None:
        logger.warning(f"Failed to propagate adapter {action} to other workers")
        return
    last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
    if last_seen is not None:
        last_seen["adapter_config"] = new_generation


def _find_skill_name_owner(adapters_dir: Path, skill_name: str, exclude_name: Optional[str] = None) -> Optional[str]:
    """The adapter name already using `skill_name`, if any (other than `exclude_name`).

    Skill routing is ambiguous once two adapters share a `capabilities.skill_name`
    — clients invoke it as `skill=<name>` and auto-routing keys off it — so this
    is checked before a new/edited adapter can claim one.
    """
    for yaml_file in adapters_dir.glob("*.yaml"):
        try:
            parsed = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        for entry in parsed.get("adapters", []):
            if not isinstance(entry, dict):
                continue
            entry_name = entry.get("name")
            if entry_name == exclude_name:
                continue
            if (entry.get("capabilities") or {}).get("skill_name") == skill_name:
                return entry_name
    return None


@router.get("/adapters/specs", dependencies=[adapters_auth])
async def list_adapter_specs():
    """List the adapter families the SDK can generate, with their form questions."""
    return {"specs": serialize_registry()}


@router.post("/adapters/preview", dependencies=[adapters_auth])
async def preview_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Render a spec + answers to YAML without writing it.

    Validation problems come back in `errors` (still HTTP 200) so the UI can show
    them alongside the preview rather than replacing it with an error.
    """
    spec_key = body.get("spec")
    answers = body.get("answers") or {}
    yaml_text = _render_from_spec(spec_key, answers)
    # Over-long answers are ordinary form mistakes, so they are listed alongside the
    # preview rather than replacing it with an error.
    errors = validate_answers(get_spec(spec_key), answers) + validate_yaml_text(yaml_text)
    return {"yaml": yaml_text, "errors": errors}


@router.get("/adapters/{adapter_name}/export", dependencies=[adapters_auth])
async def export_adapter(
    adapter_name: str,
    request: Request,
):
    """Export a single adapter as a standalone YAML document, for moving it to
    another environment. Thin wrapper over the same block lookup used by
    GET /adapters/config/entry/{name}, just wrapped in its own `adapters:` root
    and served with a download filename instead of as a JSON field."""
    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    block = "\n".join(lines[start:end])
    yaml_text = f"adapters:\n{block}\n"
    from fastapi.responses import Response
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{adapter_name}.yaml"'},
    )


@router.get("/adapters/{adapter_name}/edit-form", dependencies=[adapters_auth])
async def get_adapter_edit_form(
    adapter_name: str,
    request: Request,
):
    """Whether an existing adapter can be edited through the create form, and if
    so, the (spec, variant, answers) that reproduce it.

    Detection matches the adapter's fixed type/datasource/adapter/implementation
    tuple against the SDK spec registry, then confirms the round trip is
    lossless by re-rendering the recovered answers and comparing them to the
    entry on disk. Anything not produced by a known spec, or hand-edited beyond
    what the form can represent, comes back `editable: false` with a reason —
    the caller should fall back to the raw YAML editor rather than guess."""
    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    block_text = "adapters:\n" + "\n".join(lines[start:end]) + "\n"
    try:
        parsed = yaml.safe_load(block_text) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse adapter block: {exc}")

    entries = parsed.get("adapters") or []
    if len(entries) != 1 or not isinstance(entries[0], dict):
        raise HTTPException(status_code=500, detail="Could not parse a single adapter entry from its block")

    return detect_editable_spec(entries[0])


def _clean_pasted_yaml(content: str) -> str:
    """Undo the whitespace damage clipboards and editors routinely do to a pasted
    YAML snippet, before it ever reaches the parser:
      - CRLF/CR line endings (Windows clipboards, some terminals) → LF.
      - Tabs (invalid as YAML indentation — PyYAML rejects them outright) → spaces.
      - A shared leading indent (copying one adapter block out of a nested,
        multi-adapter file keeps that file's 2/4/6-space base indent) → stripped,
        so a snippet copied at any nesting depth still parses as a fresh document.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if "\t" in normalized:
        normalized = normalized.expandtabs(2)
    return textwrap.dedent(normalized)


def _normalize_import_document(content: str) -> str:
    """Coerce an imported single adapter into a full `adapters:` document.

    Accepts three shapes, since an operator hand-copying one adapter out of a
    multi-adapter file naturally strips the wrapper:
      - a full document: `adapters:\n  - name: ...`  (what /export produces).
      - a bare list entry: `- name: ...\n  type: ...` — re-indented under `adapters:`.
      - a bare mapping: `name: ...\n type: ...` (no leading `- `) — re-serialized under
        `adapters:` (comments/formatting are not preserved for this shape).
    `content` is cleaned of clipboard/editor whitespace damage (see `_clean_pasted_yaml`)
    before parsing. Raises HTTPException(422) if it still doesn't parse as YAML, or
    matches none of the three shapes.
    """
    cleaned = _clean_pasted_yaml(content)
    try:
        parsed = yaml.safe_load(cleaned)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"invalid YAML: {exc}")

    if isinstance(parsed, dict) and isinstance(parsed.get("adapters"), list):
        return cleaned

    if isinstance(parsed, list):
        # Already list-item-shaped (starts with "- "); just nest it under `adapters:`.
        reindented = "\n".join("  " + line if line.strip() else line for line in cleaned.splitlines())
        return f"adapters:\n{reindented}\n"

    if isinstance(parsed, dict) and parsed.get("name"):
        # A bare mapping, no list marker — re-serialize rather than guess indentation.
        return yaml.safe_dump({"adapters": [parsed]}, sort_keys=False)

    raise HTTPException(
        status_code=422,
        detail="Content must be a single adapter: either a full 'adapters:' document "
               "(as produced by Export), a bare '- name: ...' list entry, or a mapping "
               "starting with 'name: ...'."
    )


@router.post("/adapters/import/format", dependencies=[adapters_auth])
async def format_import_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Normalize pasted/uploaded adapter YAML into the canonical `adapters:` document
    shape, without writing anything. Lets the import panel offer a 'Format' action that
    reuses the same PyYAML-based normalization import itself applies, instead of
    duplicating a YAML formatter in the browser."""
    content = body.get("content")
    if not content:
        raise HTTPException(status_code=422, detail="Missing 'content' field")
    normalized = _normalize_import_document(content)
    errors = validate_yaml_text(normalized)
    return {"yaml": normalized, "errors": errors}


@router.post("/adapters/import", dependencies=[adapters_auth])
async def import_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Import a single-adapter YAML document exported from another environment
    (or hand-written to the same shape). Applies the same collision rules as
    create: a same-named file is waivable with `overwrite`, but a name already
    owned by a *different* file never is — otherwise import would be a way to
    create the duplicate-name situation that guard exists to prevent."""
    raw_content = body.get("content")
    if not raw_content:
        raise HTTPException(status_code=422, detail="Missing 'content' field")
    register = body.get("register", True)
    overwrite = bool(body.get("overwrite"))

    content = _normalize_import_document(raw_content)

    errors = validate_yaml_text(content)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    parsed = yaml.safe_load(content) or {}
    entries = parsed.get("adapters") or []
    if len(entries) != 1:
        raise HTTPException(
            status_code=422,
            detail="Import accepts exactly one adapter per file — the writer is "
                   "one-file-per-adapter. Split the bundle and import each adapter separately."
        )
    entry = entries[0]

    name = entry.get("name")
    try:
        adapter_writer.validate_adapter_name(name)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    provider_errors = validate_providers(entry, _enabled_inference_providers(request.app.state.config))
    if provider_errors:
        raise HTTPException(status_code=422, detail="; ".join(provider_errors))

    adapters_dir, adapters_yaml = _adapter_sdk_paths(request)
    if not adapters_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Adapters directory not found: {adapters_dir}")

    filename = f"{name}.yaml"
    if (adapters_dir / filename).exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"Adapter file '{filename}' already exists")

    existing_file, _ = _find_adapter_file(adapters_dir, name)
    if existing_file and existing_file.name != filename:
        raise HTTPException(
            status_code=409,
            detail=f"Adapter '{name}' already exists in {existing_file.name}"
        )

    skill_name = (entry.get("capabilities") or {}).get("skill_name")
    if skill_name:
        owner = _find_skill_name_owner(adapters_dir, skill_name, exclude_name=name)
        if owner:
            raise HTTPException(
                status_code=409,
                detail=f"Skill name '{skill_name}' is already used by adapter '{owner}'; "
                       "skill routing would be ambiguous between the two."
            )

    try:
        path = adapter_writer.write_adapter(
            name, content,
            register=register,
            overwrite=overwrite,
            adapters_dir=adapters_dir,
            adapters_yaml=adapters_yaml,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Adapter file was written to {adapters_dir / filename} but could not be "
                   f"registered: {exc}"
        )

    from config.config_manager import clear_config_cache
    clear_config_cache()

    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config, name)
            apply_mcp_auth_policy(request.app.state, new_config)
        except Exception as e:
            logger.error(f"Adapter '{name}' was imported but runtime reload failed: {e}", exc_info=True)
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"

    await _propagate_adapter_generation(request, "import")

    if reload_error:
        message = (
            f"Adapter '{name}' imported, but runtime reload failed ({reload_error}). "
            "Use 'Reload Adapters' to apply."
        )
    else:
        message = f"Adapter '{name}' imported and applied."

    return {
        "message": message,
        "name": name,
        "filename": filename,
        "path": str(path),
        "registered": bool(register),
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


@router.post("/adapters", dependencies=[adapters_auth])
async def create_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Generate an adapter from a spec, write + register it, and apply it live."""
    answers = body.get("answers") or {}
    register = body.get("register", True)
    overwrite = bool(body.get("overwrite"))

    spec_key = body.get("spec")
    yaml_text = _render_from_spec(spec_key, answers)
    # The form enforces the same bounds, but this endpoint is reachable without it.
    errors = validate_answers(get_spec(spec_key), answers) + validate_yaml_text(yaml_text)
    rendered_entry = (yaml.safe_load(yaml_text) or {}).get("adapters", [{}])[0]
    errors += validate_providers(rendered_entry, _enabled_inference_providers(request.app.state.config))
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    name = answers.get("name")
    if not name:
        raise HTTPException(status_code=422, detail="Missing 'name' in answers")
    try:
        adapter_writer.validate_adapter_name(name)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    adapters_dir, adapters_yaml = _adapter_sdk_paths(request)
    if not adapters_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Adapters directory not found: {adapters_dir}")

    filename = f"{name}.yaml"
    if (adapters_dir / filename).exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"Adapter file '{filename}' already exists")

    # The writer only guards the filename; an adapter of the same name living in a
    # different file would silently shadow this one at load time. `overwrite` waives
    # the target-file check above, never this one — otherwise it would be a way to
    # create exactly the duplicate definition this guard exists to prevent.
    existing_file, _ = _find_adapter_file(adapters_dir, name)
    if existing_file and existing_file.name != filename:
        raise HTTPException(
            status_code=409,
            detail=f"Adapter '{name}' already exists in {existing_file.name}"
        )

    skill_name = (rendered_entry.get("capabilities") or {}).get("skill_name")
    if skill_name:
        owner = _find_skill_name_owner(adapters_dir, skill_name, exclude_name=name)
        if owner:
            raise HTTPException(
                status_code=409,
                detail=f"Skill name '{skill_name}' is already used by adapter '{owner}'; "
                       "skill routing would be ambiguous between the two."
            )

    try:
        path = adapter_writer.write_adapter(
            name, yaml_text,
            register=register,
            overwrite=overwrite,
            adapters_dir=adapters_dir,
            adapters_yaml=adapters_yaml,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        # register_import found no import list — the file itself is already written.
        raise HTTPException(
            status_code=500,
            detail=f"Adapter file was written to {adapters_dir / filename} but could not be "
                   f"registered: {exc}"
        )

    from config.config_manager import clear_config_cache
    clear_config_cache()

    # Apply immediately, same contract as the enable/disable toggle.
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config, name)
            apply_mcp_auth_policy(request.app.state, new_config)
        except Exception as e:
            logger.error(f"Adapter '{name}' was created but runtime reload failed: {e}", exc_info=True)
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"

    await _propagate_adapter_generation(request, "creation")

    if reload_error:
        message = (
            f"Adapter '{name}' created, but runtime reload failed ({reload_error}). "
            "Use 'Reload Adapters' to apply."
        )
    else:
        message = f"Adapter '{name}' created and applied."

    return {
        "message": message,
        "name": name,
        "filename": filename,
        "path": str(path),
        "registered": bool(register),
        "yaml": yaml_text,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


# Config keys through which one adapter names another. These are resolved through the
# adapter manager at runtime, so a dangling name breaks the referring adapter rather
# than the deleted one: composite adapters fail to initialize, realtime adapters lose
# grounding. Skill lists are the third way and live under `capabilities`.
_ADAPTER_REF_LIST_KEYS = ("child_adapters",)
_ADAPTER_REF_SCALAR_KEYS = ("grounding_adapter",)


def _adapter_reference_kinds(entry: dict, name: str) -> list[str]:
    """Which of `entry`'s reference fields point at `name`."""
    kinds = []

    caps = entry.get("capabilities") or {}
    if name in (caps.get("available_skills") or []) or name in (caps.get("auto_routable_skills") or []):
        kinds.append("skills")

    config = entry.get("config") or {}
    if not isinstance(config, dict):
        return kinds
    for key in _ADAPTER_REF_LIST_KEYS:
        if name in (config.get(key) or []):
            kinds.append(key)
    for key in _ADAPTER_REF_SCALAR_KEYS:
        if config.get(key) == name:
            kinds.append(key)

    return kinds


async def _find_adapter_referrers(request: Request, adapters_dir: Path, name: str) -> list[str]:
    """Things that would break if `name` disappeared: API keys bound to it, and other
    adapters that name it — as a skill or as a runtime dependency."""
    referrers: list[str] = []

    api_key_service = getattr(request.app.state, "api_key_service", None)
    if api_key_service is not None:
        try:
            if not api_key_service._initialized:
                await api_key_service.initialize()
            keys = await api_key_service.database.find_many(
                api_key_service.collection_name, {"adapter_name": name}
            )
            for key in keys or []:
                label = key.get("client_name") or key.get("name") or str(key.get("_id"))
                referrers.append(f"API key '{label}'")
        except Exception as exc:
            # A referrer check that cannot run must not silently report "no referrers".
            logger.error(f"Referrer check for adapter '{name}' failed: {exc}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=f"Could not check whether adapter '{name}' is still referenced: {exc}"
            )

    for yaml_file in sorted(adapters_dir.glob("*.yaml")):
        try:
            parsed = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(parsed, dict):
            continue
        for entry in parsed.get("adapters", []) or []:
            if not isinstance(entry, dict) or entry.get("name") == name:
                continue
            for kind in _adapter_reference_kinds(entry, name):
                referrers.append(f"adapter '{entry.get('name')}' ({kind})")

    return referrers


@router.delete("/adapters/{adapter_name}", dependencies=[adapters_auth])
async def delete_adapter(
    request: Request,
    adapter_name: str,
    force: bool = Query(False, description="Delete even if the adapter is still referenced"),
):
    """Remove an adapter's definition, drop its import line, and evict it from the server."""
    try:
        adapter_writer.validate_adapter_name(adapter_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    adapters_dir, adapters_yaml = _adapter_sdk_paths(request)
    if not adapters_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Adapters directory not found: {adapters_dir}")

    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    if not force:
        referrers = await _find_adapter_referrers(request, adapters_dir, adapter_name)
        if referrers:
            raise HTTPException(
                status_code=409,
                detail=f"Adapter '{adapter_name}' is still referenced by: "
                       + ", ".join(referrers)
                       + ". Delete it anyway with force=true (referrers are not updated)."
            )

    parsed = yaml.safe_load(content) or {}
    siblings = [
        a for a in (parsed.get("adapters") or [])
        if isinstance(a, dict) and a.get("name") != adapter_name
    ]

    file_removed = False
    unregistered = False
    if siblings:
        # The file owns other adapters, so splice out just this block and keep both the
        # file and its import line — same line-splicing discipline as the PUT route.
        lines = content.split("\n")
        start, end = _find_adapter_block(lines, adapter_name)
        if start == -1:
            raise HTTPException(
                status_code=500,
                detail=f"Adapter '{adapter_name}' is defined in {file_path.name} but its block "
                       "could not be located; edit the file directly."
            )
        _write_adapter_config(file_path, "\n".join(lines[:start] + lines[end:]))
    else:
        try:
            unregistered = adapter_writer.delete_adapter(
                file_path.stem,
                adapters_dir=adapters_dir,
                adapters_yaml=adapters_yaml,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        file_removed = True

    from config.config_manager import clear_config_cache
    clear_config_cache()

    # The removal branch lives in reload_all_adapters only — the scoped path raises
    # because the name is (correctly) gone from the config file.
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config)
            apply_mcp_auth_policy(request.app.state, new_config)
        except Exception as e:
            logger.error(f"Adapter '{adapter_name}' was deleted but runtime reload failed: {e}", exc_info=True)
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"

    # reload_all_adapters' removal branch does not touch the capability registry, so a
    # deleted adapter would keep showing up in GET /adapters/capabilities.
    try:
        from adapters.capabilities import get_capability_registry
        get_capability_registry().unregister(adapter_name)
    except Exception as exc:
        logger.warning(f"Could not unregister capabilities for '{adapter_name}': {exc}")

    await _propagate_adapter_generation(request, "deletion")

    if reload_error:
        message = (
            f"Adapter '{adapter_name}' deleted, but runtime reload failed ({reload_error}). "
            "Use 'Reload Adapters' to apply."
        )
    else:
        message = f"Adapter '{adapter_name}' deleted and removed from the running server."

    return {
        "message": message,
        "name": adapter_name,
        "filename": file_path.name,
        "file_removed": file_removed,
        "unregistered": unregistered,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


# Adapter Hot Reload
@router.post("/reload-adapters", response_model=AdapterReloadResponse, dependencies=[adapters_auth])
async def reload_adapters(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
):
    """
    Reload adapter configurations from adapters.yaml without server restart.

    This endpoint performs hot-swap of adapters:
    - If adapter_name is None: reloads all adapters
    - If adapter_name is provided: reloads only that specific adapter

    For all adapters:
    - Adds new adapters
    - Removes disabled adapters
    - Updates changed adapter configurations
    - Preserves in-flight requests on old adapters

    For specific adapter:
    - Updates only the named adapter configuration
    - Returns error if adapter not found in config

    Requires admin authentication.

    Query Parameters:
        adapter_name: Optional name of specific adapter to reload

    Returns:
        AdapterReloadResponse with reload summary

    Raises:
        HTTPException: If adapter manager is unavailable, config loading fails,
                      or specific adapter is not found
    """
    # Get adapter manager from app state
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(
            status_code=503,
            detail="Adapter manager is not available"
        )

    # Get config path from app state
    config_path = getattr(request.app.state, 'config_path', None)
    if not config_path:
        raise HTTPException(
            status_code=500,
            detail="Config path is not available in app state"
        )

    try:
        # Reload the configuration from disk
        new_config = reload_adapters_config(config_path)

        # Reload adapters using the adapter manager
        summary = await adapter_manager.reload_adapter_configs(new_config, adapter_name)
        apply_mcp_auth_policy(request.app.state, new_config)

        # Under performance.workers > 1, this only reloaded the worker that
        # served this request - bump the durable generation counter so
        # sibling workers pick up the change on their next poll tick (see
        # services/adapter_reload_state.py). No-op in single-process mode.
        import os
        if os.environ.get('ORBIT_SUPERVISOR_PID'):
            from services import adapter_reload_state
            new_generation = await adapter_reload_state.bump_generation(request.app.state, "adapter_config")
            if new_generation is not None:
                last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
                if last_seen is not None:
                    # Avoid this same worker redundantly reloading itself again
                    # on its own next poll tick.
                    last_seen["adapter_config"] = new_generation
            else:
                logger.warning("Failed to propagate adapter reload to other workers")

        # Generate appropriate message
        if adapter_name:
            action = summary.get('action', 'reloaded')
            message = f"Adapter '{adapter_name}' {action} successfully"
        else:
            added = summary.get('added', 0)
            removed = summary.get('removed', 0)
            updated = summary.get('updated', 0)
            total = summary.get('total', 0)
            message = f"Adapters reloaded: {added} added, {removed} removed, {updated} updated, {total} total"

        logger.info(f"Adapter reload completed: {message}")

        return AdapterReloadResponse(
            status="success",
            message=message,
            summary=summary,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    except FileNotFoundError as e:
        logger.error(f"Config file not found: {str(e)}")
        raise HTTPException(status_code=500, detail="Config file not found")
    except ValueError as e:
        logger.error(f"Adapter reload error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during adapter reload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reload adapters")


@router.post("/reload-adapters/async", dependencies=[adapters_auth])
async def reload_adapters_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
):
    """Start adapter reload as a background admin job."""
    job = _create_admin_job(request, "reload_adapters", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading adapters")
        try:
            result = await reload_adapters(request=request, adapter_name=adapter_name)
            _update_admin_job(
                request,
                job["job_id"],
                status="completed",
                message=result.message,
                result=result.model_dump() if hasattr(result, "model_dump") else result,
            )
        except HTTPException as exc:
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc.detail), error=str(exc.detail))
        except Exception as exc:
            logger.error(f"Async adapter reload failed: {exc}", exc_info=True)
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc), error=str(exc))

    asyncio.create_task(run_job())
    return {
      "status": "accepted",
      "job_id": job["job_id"],
      "message": "Adapter reload started in background"
    }


# Template Hot Reload
@router.post("/reload-templates", response_model=TemplateReloadResponse, dependencies=[adapters_auth])
async def reload_templates(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
):
    """
    Reload intent templates from template library files without server restart.

    This endpoint reloads templates for intent-based adapters:
    - If adapter_name is None: reloads templates for all cached intent adapters
    - If adapter_name is provided: reloads templates only for that adapter

    The adapter must already be loaded (cached). This does not reload adapter
    configuration, only re-reads template YAML files and re-indexes in vector store.

    This is useful for:
    - Updating template definitions without restarting the server
    - Adding new templates to an existing adapter
    - Modifying template NL examples or descriptions
    - Iterating on template development

    Requires admin authentication.

    Query Parameters:
        adapter_name: Optional name of specific adapter to reload templates for

    Returns:
        TemplateReloadResponse with reload summary including:
        - templates_loaded: Number of templates loaded
        - adapters_updated: List of adapters that were updated
        - errors: Any errors encountered during reload

    Raises:
        HTTPException 404: If adapter not found or doesn't support template reloading
        HTTPException 503: If adapter manager is unavailable
        HTTPException 500: If reload fails unexpectedly
    """
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(
            status_code=503,
            detail="Adapter manager is not available"
        )

    try:
        summary = await adapter_manager.reload_templates(adapter_name)

        # Under performance.workers > 1, this only reloaded the worker that
        # served this request - bump the durable generation counter so
        # sibling workers pick up the change on their next poll tick (see
        # services/adapter_reload_state.py). No-op in single-process mode.
        import os
        if os.environ.get('ORBIT_SUPERVISOR_PID'):
            from services import adapter_reload_state
            new_generation = await adapter_reload_state.bump_generation(request.app.state, "templates")
            if new_generation is not None:
                last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
                if last_seen is not None:
                    last_seen["templates"] = new_generation
            else:
                logger.warning("Failed to propagate template reload to other workers")

        # Generate appropriate message
        if adapter_name:
            message = f"Templates for adapter '{adapter_name}' reloaded: {summary.get('templates_loaded', 0)} templates"
        else:
            adapters_count = len(summary.get('adapters_updated', []))
            message = f"Templates reloaded for {adapters_count} adapter(s): {summary.get('templates_loaded', 0)} total templates"

        if summary.get('errors'):
            message += f" ({len(summary['errors'])} error(s))"

        logger.info(f"Template reload completed: {message}")

        return TemplateReloadResponse(
            status="success",
            message=message,
            summary=summary,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    except ValueError as e:
        logger.error(f"Template reload error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during template reload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reload templates")


@router.post("/reload-templates/async", dependencies=[adapters_auth])
async def reload_templates_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
):
    """Start template reload as a background admin job."""
    job = _create_admin_job(request, "reload_templates", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading templates")
        try:
            result = await reload_templates(request=request, adapter_name=adapter_name)
            _update_admin_job(
                request,
                job["job_id"],
                status="completed",
                message=result.message,
                result=result.model_dump() if hasattr(result, "model_dump") else result,
            )
        except HTTPException as exc:
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc.detail), error=str(exc.detail))
        except Exception as exc:
            logger.error(f"Async template reload failed: {exc}", exc_info=True)
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc), error=str(exc))

    asyncio.create_task(run_job())
    return {
      "status": "accepted",
      "job_id": job["job_id"],
      "message": "Template reload started in background"
    }


@router.post("/adapters/{adapter_name}/test-query", dependencies=[Depends(require_permission("adapters.manage"))])
async def test_adapter_query(
    adapter_name: str,
    body: TemplateTestRequest,
    request: Request,
):
    """
    Test a natural language query against an intent adapter's templates
    without running the full LLM inference pipeline.

    Returns detailed diagnostics: template matching scores, parameter extraction,
    rendered query, and raw datasource results.
    """
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    try:
        adapter = await adapter_manager.get_adapter(adapter_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found: {e}")

    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    # Verify adapter is an intent or composite retriever
    from retrievers.base.intent_sql_base import IntentSQLRetriever
    from retrievers.base.intent_http_base import IntentHTTPRetriever
    from retrievers.base.intent_composite_base import CompositeIntentRetriever

    if not isinstance(adapter, (IntentSQLRetriever, IntentHTTPRetriever, CompositeIntentRetriever)):
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{adapter_name}' is type '{type(adapter).__name__}', not an intent retriever. "
                   f"test-query only works with intent-based adapters."
        )

    from utils.template_diagnostics import diagnose_template_query

    try:
        result = await diagnose_template_query(
            retriever=adapter,
            query=body.query,
            max_templates=body.max_templates,
            execute=body.execute,
            include_all_candidates=body.include_all_candidates,
            verbose=body.verbose,
        )
        return result
    except Exception as e:
        logger.error(f"Template test-query failed for '{adapter_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Test query failed")
