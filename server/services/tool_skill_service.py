"""
Tool Skill Registry — Phase 1 (file-based) + Phase 3 (database-backed)

Loads admin-authored SKILL.md documents from disk and/or the database and
indexes them by the namespaced MCP tool names (``<server>__<tool>``) they are
bound to via their ``mcp_tools`` glob list.

This is a *procedural playbook* mechanism, not the ORBIT skill/adapter-swap
routing mechanism (``capabilities.expose_as_skill``) — see
docs/roadmap/mcp-tool-skills.md §1 for the terminology split. A "tool skill"
here is a markdown document with YAML frontmatter that the model can load via
the synthetic ``orbit__load_tool_skill`` tool (see
inference/pipeline/steps/mcp_agent.py), never an adapter and never routed via
``skill: "..."``.

See docs/roadmap/mcp-tool-skills.md for the full design (§2.1, §2.2, §2.5,
§2.6 for the file-vs-database precedence this module implements).
"""

import fnmatch
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional, Union
from collections.abc import Iterable

import yaml
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Matches the lowercase-slug convention MCP server names already use
# (routes/admin/mcp.py) — kept consistent so a skill name never surprises an
# author familiar with that convention.
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SKILL_VERSION_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")

# Reserved for the synthetic loader tool (orbit__load_tool_skill) — no skill
# may claim this namespace (docs/roadmap/mcp-tool-skills.md §2.1).
_RESERVED_PREFIX = "orbit__"

_FRONTMATTER_DELIM = "---"

# Authoring/storage guardrails. The body cap intentionally equals the per-turn
# byte budget: accepting a larger body would create a valid-looking skill that
# can never be injected.
MAX_SKILL_NAME_CHARS = 64
MAX_SKILL_DESCRIPTION_CHARS = 500
MAX_SKILL_VERSION_CHARS = 25
MIN_SKILL_PRIORITY = -1
MAX_SKILL_PRIORITY = 99
MAX_MCP_TOOL_PATTERNS = 64
MAX_MCP_TOOL_PATTERN_CHARS = 256
MAX_SKILL_BODY_BYTES = 24 * 1024
MAX_ACTIVE_DB_SKILLS = 10_000

# Per-turn injection budget shared by Level 2 and Level 3.
INJECTION_BUDGET_MAX_SKILLS = 3
INJECTION_BUDGET_MAX_BYTES = 24 * 1024

# Level 1 catalog / Level 2 enum cap — the "surfaced set" (§2.2, §8 Q5). Any
# skill beyond this, sorted by (priority desc, name), is present in the
# matched set but never surfaced to the model this turn.
SURFACED_SET_CAP = 10

# Default location, relative to the working directory ORBIT was started from
# (matches the `stores_config_path`-style convention in service_factory.py,
# and the same caveat as `ORBIT_DOCS_DIR` in config/mcp_clients.yaml: a
# relative path resolves against the launch directory, not this file).
DEFAULT_SKILLS_DIR = "config/skills"


@dataclass
class ToolSkill:
    """A parsed, validated SKILL.md document."""

    name: str
    description: str
    mcp_tools: list[str]
    body: str
    enabled: bool = True
    version: Optional[str] = None
    priority: int = 0
    source_path: Optional[str] = None
    # "file" (config/skills/*/SKILL.md) or "db" (admin-authored, Phase 3).
    # Database entries win on a name collision (docs/roadmap/mcp-tool-skills.md
    # §2.6) — the panel shows the file version as the "on-disk default".
    source: str = "file"
    db_id: Optional[str] = None

    def matches(self, tool_name: str) -> bool:
        """Whether this skill's mcp_tools glob list covers ``tool_name``.

        fnmatch-style globbing (not pathlib path-matching — the namespaced
        tool name is a flat ``<server>__<tool>`` string, not a path), case
        sensitive to match the already-lowercase server/tool name convention.
        """
        return any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in self.mcp_tools)


class SkillValidationError(ValueError):
    """A skill's fields fail the shared validation rules.

    Raised by ``_validate_skill_fields`` (used at request time, e.g.
    ``ToolSkillService.create``/``update``, where a bad document must be
    rejected with a clear error) — as opposed to file parsing, which logs a
    warning and skips instead, since a malformed file on disk must never
    break the loop for every other adapter (see ``_parse_skill_file``).
    """


def _validate_skill_fields(
    *,
    name: Any,
    description: Any,
    mcp_tools: Any,
    body: Any,
    enabled: Any = True,
    version: Any = None,
    priority: Any = 0,
    label: str,
) -> dict[str, Any]:
    """Validate one skill's fields against the shared rules (name slug,
    reserved ``orbit__`` prefix, non-empty description/mcp_tools/body, body
    size cap, enabled/priority types). ``label`` is used in error/log
    messages only (a file path, or a DB skill's name). Returns a dict of
    normalized field values on success; raises ``SkillValidationError`` on
    any problem — callers that want log-and-skip instead of raise/reject
    (file loading) catch this and log a warning.
    """
    if not isinstance(name, str) or not _SKILL_NAME_PATTERN.match(name):
        raise SkillValidationError(
            f"{label}: missing/invalid 'name' (must be a lowercase slug)"
        )
    if len(name) > MAX_SKILL_NAME_CHARS:
        raise SkillValidationError(
            f"{label}: skill name exceeds {MAX_SKILL_NAME_CHARS} characters"
        )
    if name.startswith(_RESERVED_PREFIX):
        raise SkillValidationError(
            f"{label}: skill '{name}' uses the reserved '{_RESERVED_PREFIX}' prefix "
            "(the synthetic loader's own namespace)"
        )

    if not isinstance(description, str) or not description.strip():
        raise SkillValidationError(f"{label}: skill '{name}' is missing a non-empty 'description'")
    if len(description.strip()) > MAX_SKILL_DESCRIPTION_CHARS:
        raise SkillValidationError(
            f"{label}: skill '{name}' description exceeds "
            f"{MAX_SKILL_DESCRIPTION_CHARS} characters"
        )

    if not isinstance(mcp_tools, list) or not mcp_tools or not all(
        isinstance(t, str) and t.strip() for t in mcp_tools
    ):
        raise SkillValidationError(f"{label}: skill '{name}' has a missing/invalid 'mcp_tools' list")
    if len(mcp_tools) > MAX_MCP_TOOL_PATTERNS:
        raise SkillValidationError(
            f"{label}: skill '{name}' has more than "
            f"{MAX_MCP_TOOL_PATTERNS} mcp_tools patterns"
        )
    for pattern in mcp_tools:
        if len(pattern) > MAX_MCP_TOOL_PATTERN_CHARS:
            raise SkillValidationError(
                f"{label}: skill '{name}' has an mcp_tools pattern longer than "
                f"{MAX_MCP_TOOL_PATTERN_CHARS} characters"
            )
        if pattern.startswith(_RESERVED_PREFIX):
            raise SkillValidationError(
                f"{label}: skill '{name}' binds the reserved '{_RESERVED_PREFIX}' prefix in mcp_tools"
            )

    if not isinstance(enabled, bool):
        logger.warning("%s: skill '%s' has non-boolean 'enabled'; defaulting to true.", label, name)
        enabled = True

    if version is not None:
        version = str(version).strip()
        if len(version) > MAX_SKILL_VERSION_CHARS:
            raise SkillValidationError(
                f"{label}: skill '{name}' version exceeds {MAX_SKILL_VERSION_CHARS} characters"
            )
        if not _SKILL_VERSION_PATTERN.fullmatch(version):
            raise SkillValidationError(
                f"{label}: skill '{name}' version must contain only numbers separated by dots"
            )

    if not isinstance(priority, int) or isinstance(priority, bool):
        logger.warning("%s: skill '%s' has non-integer 'priority'; defaulting to 0.", label, name)
        priority = 0
    elif not MIN_SKILL_PRIORITY <= priority <= MAX_SKILL_PRIORITY:
        raise SkillValidationError(
            f"{label}: skill '{name}' priority must be between {MIN_SKILL_PRIORITY} and {MAX_SKILL_PRIORITY}"
        )

    if not isinstance(body, str) or not body.strip():
        raise SkillValidationError(f"{label}: skill '{name}' has an empty body")
    body = body.strip()

    body_size = len(body.encode("utf-8"))
    if body_size > MAX_SKILL_BODY_BYTES:
        raise SkillValidationError(
            f"{label}: skill '{name}' exceeds the {MAX_SKILL_BODY_BYTES}-byte body cap ({body_size} bytes)"
        )

    return {
        "name": name,
        "description": description.strip(),
        "mcp_tools": list(mcp_tools),
        "body": body,
        "enabled": enabled,
        "version": version,
        "priority": priority,
    }


def select_injection_eligible(
    candidate_skills: Iterable[ToolSkill],
    max_skills: int = INJECTION_BUDGET_MAX_SKILLS,
    max_bytes: int = INJECTION_BUDGET_MAX_BYTES,
) -> list[ToolSkill]:
    """Select the priority-ordered skills that fit the shared turn budget."""
    eligible: list[ToolSkill] = []
    bytes_used = 0
    for skill in candidate_skills:
        if len(eligible) >= max_skills:
            break
        size = len(skill.body.encode("utf-8"))
        if bytes_used + size > max_bytes:
            continue
        eligible.append(skill)
        bytes_used += size
    return eligible


def _parse_skill_file(path: Path) -> Optional[ToolSkill]:
    """Parse and validate one SKILL.md file. Returns None (with a warning
    logged) for any structural problem — a malformed skill must never break
    the tool-calling loop for every other adapter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read skill file %s: %s", path, exc)
        return None

    if not text.startswith(_FRONTMATTER_DELIM):
        logger.warning("Skill file %s is missing YAML frontmatter; skipped.", path)
        return None

    parts = text.split(_FRONTMATTER_DELIM, 2)
    if len(parts) < 3:
        logger.warning("Skill file %s has malformed frontmatter (no closing '---'); skipped.", path)
        return None

    _, frontmatter_text, body_text = parts
    body = body_text.lstrip("\n").strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        logger.warning("Skill file %s has invalid YAML frontmatter: %s", path, exc)
        return None
    if not isinstance(frontmatter, dict):
        logger.warning("Skill file %s frontmatter is not a mapping; skipped.", path)
        return None

    try:
        fields = _validate_skill_fields(
            name=frontmatter.get("name"),
            description=frontmatter.get("description"),
            mcp_tools=frontmatter.get("mcp_tools"),
            body=body,
            enabled=frontmatter.get("enabled", True),
            version=frontmatter.get("version"),
            priority=frontmatter.get("priority", 0),
            label=f"Skill file {path}",
        )
    except SkillValidationError as exc:
        logger.warning("%s; skipped.", exc)
        return None

    return ToolSkill(
        **fields,
        source_path=str(path),
        source="file",
    )


class ToolSkillRegistry:
    """
    Loads and indexes SKILL.md documents from ``skills_dir`` (files) and,
    when supplied, admin-authored skills from the database (Phase 3) —
    database entries win on a name collision; see
    docs/roadmap/mcp-tool-skills.md §2.6. The file version of a collided
    name is kept out of the served index but is still retrievable via
    ``file_default_for`` so the admin panel can show it as the "on-disk
    default" the DB entry overrides.

    A missing or empty directory (and no DB skills) is not an error — no
    skills configured is a valid, common state.
    """

    def __init__(self, skills_dir: Path, db_skills: Optional[list[ToolSkill]] = None):
        self.skills_dir = Path(skills_dir)
        self._file_skills: dict[str, ToolSkill] = {}
        self._db_skills: dict[str, ToolSkill] = {}
        self._skills: dict[str, ToolSkill] = {}
        self._load_files()
        if db_skills:
            self.set_db_skills(db_skills)
        else:
            self._recompute()

    def _load_files(self) -> None:
        skills: dict[str, ToolSkill] = {}
        if self.skills_dir.is_dir():
            for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
                skill = _parse_skill_file(skill_file)
                if skill is None:
                    continue
                if not skill.enabled:
                    continue
                existing = skills.get(skill.name)
                if existing is not None:
                    logger.warning(
                        "Duplicate tool skill name '%s' (%s); keeping the first one loaded (%s).",
                        skill.name, skill_file, existing.source_path,
                    )
                    continue
                skills[skill.name] = skill

        self._file_skills = skills

    def _recompute(self) -> None:
        merged: dict[str, ToolSkill] = dict(self._file_skills)
        for name, skill in self._db_skills.items():
            if name in merged:
                logger.info(
                    "Tool skill '%s': database entry overrides the on-disk default (%s).",
                    name, merged[name].source_path,
                )
            merged[name] = skill
        self._skills = merged

    def set_db_skills(self, db_skills: Iterable[ToolSkill]) -> None:
        """Replace the database-sourced skill set and re-merge (DB wins on a
        name collision with a file skill). Called after Phase 3 CRUD writes
        and on the periodic cross-worker reload poll."""
        self._db_skills = {skill.name: skill for skill in db_skills if skill.enabled}
        self._recompute()

    def reload(self) -> None:
        """Re-read every SKILL.md under ``skills_dir`` from disk. Database
        skills already loaded are kept as-is — call ``set_db_skills`` again
        to refresh those."""
        self._load_files()
        self._recompute()

    def all_skills(self) -> list[ToolSkill]:
        return list(self._skills.values())

    def get(self, name: str) -> Optional[ToolSkill]:
        return self._skills.get(name)

    def file_default_for(self, name: str) -> Optional[ToolSkill]:
        """The on-disk version of ``name``, if a database entry overrides it
        (or if it isn't overridden at all) — used by the admin panel to show
        "on-disk default" (§2.6)."""
        return self._file_skills.get(name)

    def matched_for(self, tool_names: Iterable[str]) -> list[ToolSkill]:
        """
        The *matched set* (docs/roadmap/mcp-tool-skills.md §2.2): every
        enabled skill whose ``mcp_tools`` glob matches at least one name in
        ``tool_names``, sorted by (priority desc, name) for deterministic
        ordering across requests and workers. Unbounded — callers wanting the
        *surfaced set* truncate to ``SURFACED_SET_CAP`` themselves.
        """
        names = list(tool_names)
        matched = [
            skill for skill in self._skills.values()
            if any(skill.matches(name) for name in names)
        ]
        matched.sort(key=lambda s: (-s.priority, s.name))
        return matched


_registry_instance: Optional[ToolSkillRegistry] = None
_registry_dir: Optional[str] = None


def _resolve_skills_dir(config: dict) -> str:
    return (config or {}).get("tool_skills", {}).get("directory", DEFAULT_SKILLS_DIR)


def get_tool_skill_registry(config: dict) -> ToolSkillRegistry:
    """
    Return the process-wide ``ToolSkillRegistry``, building it on first use
    (or rebuilding it if the configured directory changed) — mirrors
    ``get_mcp_client_manager`` in services/mcp_client_service.py. Rebuilding
    here re-reads files only; any previously-loaded DB skills are lost, so
    callers that own a DB source should re-apply ``refresh_tool_skill_registry_db``
    afterward (this mirrors how a directory change is a rare/manual event,
    unlike the DB refresh, which is driven by admin writes and the reload poll).
    """
    global _registry_instance, _registry_dir
    directory = _resolve_skills_dir(config)
    if _registry_instance is None or _registry_dir != directory:
        _registry_instance = ToolSkillRegistry(Path(directory))
        _registry_dir = directory
    return _registry_instance


def reload_tool_skill_registry(config: dict) -> ToolSkillRegistry:
    """Force a fresh reload from disk, discarding any cached instance
    (including any previously-loaded DB skills — see ``get_tool_skill_registry``)."""
    global _registry_instance, _registry_dir
    directory = _resolve_skills_dir(config)
    _registry_instance = ToolSkillRegistry(Path(directory))
    _registry_dir = directory
    return _registry_instance


def warn_catalog_overflow(
    config: dict,
    registry: ToolSkillRegistry,
    mcp_manager: Any,
) -> None:
    """Warn when statically reachable matches exceed catalog/injection caps.

    This is intentionally called from discovery/registry-refresh paths, not
    request resolution, so varied user queries cannot create log volume. The
    check is conservative: it considers every currently cached tool the
    adapter may reach at once, then applies the adapter's tool-skill allowlist.
    Level 3 still uses the full matched set and is unaffected by this cap.
    """
    if mcp_manager is None:
        return

    cached_by_server = getattr(mcp_manager, "_tools_cache", {}) or {}
    for adapter in (config or {}).get("adapters", []) or []:
        if not isinstance(adapter, dict) or not adapter.get("enabled", True):
            continue
        capabilities = adapter.get("capabilities") or {}
        is_mcp_agent = adapter.get("type") == "mcp_agent"
        is_opportunistic = bool(capabilities.get("mcp_tools"))
        if not is_mcp_agent and not is_opportunistic:
            continue

        allowed_servers = capabilities.get("mcp_servers")
        tool_names: list[str] = []
        for server_name, tools in cached_by_server.items():
            if allowed_servers and server_name not in allowed_servers:
                continue
            if is_opportunistic and not mcp_manager.setting(server_name, "allow_opportunistic"):
                continue
            tool_names.extend(
                tool.get("function", {}).get("name", "") for tool in tools
            )

        tool_names = sorted(set(filter(None, tool_names)))
        matched = registry.matched_for(tool_names)
        skill_allowlist = capabilities.get("tool_skills")
        if skill_allowlist is not None:
            allowed_skills = set(skill_allowlist)
            matched = [skill for skill in matched if skill.name in allowed_skills]
        adapter_name = adapter.get("name", "<unnamed>")
        if len(matched) > SURFACED_SET_CAP:
            dropped = [skill.name for skill in matched[SURFACED_SET_CAP:]]
            logger.warning(
                "Adapter '%s' matches %d tool skills across its statically reachable "
                "MCP tools; the Level 1/2 surfaced-set cap is %d, so these "
                "lower-priority skills are omitted from the catalog and loader: %s",
                adapter_name,
                len(matched),
                SURFACED_SET_CAP,
                ", ".join(dropped),
            )

        for tool_name in tool_names:
            tool_matches = registry.matched_for([tool_name])
            if skill_allowlist is not None:
                tool_matches = [
                    skill for skill in tool_matches if skill.name in allowed_skills
                ]
            if len(tool_matches) > SURFACED_SET_CAP:
                logger.warning(
                    "Adapter '%s' tool '%s' matches %d tool skills; only the first "
                    "%d by priority/name can appear in the catalog and loader.",
                    adapter_name,
                    tool_name,
                    len(tool_matches),
                    SURFACED_SET_CAP,
                )

            eligible_names = {
                skill.name for skill in select_injection_eligible(tool_matches)
            }
            injection_dropped = [
                skill.name for skill in tool_matches
                if skill.name not in eligible_names
            ]
            if injection_dropped:
                logger.warning(
                    "Adapter '%s' tool '%s' matches %d tool skills, exceeding the "
                    "shared injection budget of %d skills/%d bytes; dropped by "
                    "priority and size: %s",
                    adapter_name,
                    tool_name,
                    len(tool_matches),
                    INJECTION_BUDGET_MAX_SKILLS,
                    INJECTION_BUDGET_MAX_BYTES,
                    ", ".join(injection_dropped),
                )


def _db_doc_to_skill(doc: dict[str, Any]) -> Optional[ToolSkill]:
    """Validate one ``tool_skills`` DB document into a ``ToolSkill``. Returns
    None (with a warning logged) on any validation failure — mirrors
    ``_parse_skill_file``'s log-and-skip behavior so one malformed DB row
    can't break the registry for every other adapter."""
    name = doc.get("name")
    try:
        fields = _validate_skill_fields(
            name=name,
            description=doc.get("description"),
            mcp_tools=doc.get("mcp_tools"),
            body=doc.get("body"),
            enabled=doc.get("enabled", True),
            version=doc.get("version"),
            priority=doc.get("priority", 0),
            label=f"DB tool skill '{name}'",
        )
    except SkillValidationError as exc:
        logger.warning("%s; skipped.", exc)
        return None

    return ToolSkill(
        **fields,
        source_path=None,
        source="db",
        db_id=str(doc.get("_id")) if doc.get("_id") is not None else None,
    )


async def refresh_tool_skill_registry_db(config: dict, tool_skill_service: "ToolSkillService") -> ToolSkillRegistry:
    """Query every enabled database skill and merge it into the process-wide
    registry (DB wins on a name collision with a file skill, §2.6). Called
    at startup once ``ToolSkillService`` is initialized, after any admin CRUD
    write, and from the cross-worker reload poll (services/adapter_reload_state.py)."""
    registry = get_tool_skill_registry(config)
    docs = await tool_skill_service.list_skills(
        enabled_only=True,
        limit=MAX_ACTIVE_DB_SKILLS + 1,
        sort=[("priority", -1), ("name", 1)],
    )
    if len(docs) > MAX_ACTIVE_DB_SKILLS:
        logger.error(
            "Database contains more than the supported %d active tool skills; "
            "loading the deterministic highest-priority subset.",
            MAX_ACTIVE_DB_SKILLS,
        )
        docs = docs[:MAX_ACTIVE_DB_SKILLS]
    db_skills = [s for s in (_db_doc_to_skill(doc) for doc in docs) if s is not None]
    registry.set_db_skills(db_skills)
    try:
        from services.mcp_client_service import get_current_mcp_client_manager
        warn_catalog_overflow(config, registry, get_current_mcp_client_manager())
    except Exception as exc:
        # Diagnostics must never make a successful registry refresh fail.
        logger.debug("Could not evaluate tool-skill catalog overflow: %s", exc)
    return registry


class ToolSkillService:
    """
    Database-backed CRUD for admin-authored tool skills (Phase 3), modeled on
    ``PromptService`` (server/services/prompt_service.py). Persists to the
    same multi-backend ``DatabaseService`` abstraction (Mongo/SQLite/Postgres)
    — never a direct driver import — so it works unchanged across backends.

    This service owns *storage and validation* only; merging its documents
    into the live, per-process ``ToolSkillRegistry`` that the tool-calling
    loop actually reads is the caller's job (``refresh_tool_skill_registry_db``),
    same separation ``PromptService`` has from its own runtime cache callers.
    """

    def __init__(self, config: dict[str, Any], database_service=None):
        self.config = config
        if database_service is None:
            from services.database_service import create_database_service
            database_service = create_database_service(config)
        self.database = database_service

        self.backend_type = config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')
        if self.backend_type == 'mongodb':
            mongodb_config = config.get('internal_services', {}).get('mongodb', {})
            self.collection_name = mongodb_config.get('tool_skills_collection', 'tool_skills')
        else:
            self.collection_name = 'tool_skills'

    async def initialize(self) -> None:
        await self.database.initialize()
        await self.database.create_index(self.collection_name, "name", unique=True)
        logger.info("Tool Skill Service initialized successfully (collection: %s)", self.collection_name)

    def _encode_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """SQLite/Postgres have no native array column type — unlike
        ``users.roles``/``api_keys.allowed_*``, ``tool_skills`` is a
        dynamically-created table (no predefined schema), so this encodes
        ``mcp_tools`` at the service layer rather than adding another
        collection-specific hack to sqlite_service.py/postgres_service.py.
        MongoDB stores the list natively and is left untouched."""
        if self.backend_type == 'mongodb':
            return doc
        encoded = dict(doc)
        if isinstance(encoded.get("mcp_tools"), list):
            encoded["mcp_tools"] = json.dumps(encoded["mcp_tools"])
        return encoded

    def _decode_doc(self, doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if doc is None or self.backend_type == 'mongodb':
            return doc
        if isinstance(doc.get("mcp_tools"), str):
            try:
                doc["mcp_tools"] = json.loads(doc["mcp_tools"])
            except json.JSONDecodeError:
                doc["mcp_tools"] = []
        return doc

    async def create_skill(
        self,
        *,
        name: str,
        description: str,
        mcp_tools: list[str],
        body: str,
        enabled: bool = True,
        version: Optional[str] = None,
        priority: int = 0,
    ) -> Any:
        """Create a new database-authored tool skill. Raises ``HTTPException``
        (400) on validation failure, (409) if the name already exists."""
        fields = self._validate(
            name=name, description=description, mcp_tools=mcp_tools, body=body,
            enabled=enabled, version=version, priority=priority,
        )

        existing = await self.database.find_one(self.collection_name, {"name": fields["name"]})
        if existing:
            raise HTTPException(status_code=409, detail=f"Tool skill '{fields['name']}' already exists")
        if fields["enabled"]:
            await self._assert_active_capacity()

        now = datetime.now(UTC)
        doc = self._encode_doc({**fields, "created_at": now, "updated_at": now})
        try:
            skill_id = await self.database.insert_one(self.collection_name, doc)
        except Exception as exc:
            logger.error("Error creating tool skill '%s': %s", fields["name"], exc)
            raise HTTPException(status_code=500, detail=f"Error creating tool skill: {exc}")
        return skill_id

    async def get_skill_by_id(self, skill_id: Union[str, Any]) -> Optional[dict[str, Any]]:
        try:
            doc = await self.database.find_one(self.collection_name, {"_id": skill_id})
            return self._decode_doc(doc)
        except Exception as exc:
            logger.error("Error retrieving tool skill %s: %s", skill_id, exc)
            return None

    async def list_skills(
        self,
        name_filter: Optional[str] = None,
        enabled_only: bool = False,
        limit: int = 100,
        offset: int = 0,
        sort: Optional[list[tuple[str, int]]] = None,
    ) -> list[dict[str, Any]]:
        filter_query: dict[str, Any] = {}
        if name_filter:
            filter_query["name"] = {"$regex": re.escape(name_filter), "$options": "i"}
        if enabled_only:
            filter_query["enabled"] = True

        try:
            docs = await self.database.find_many(
                self.collection_name, filter_query, sort=sort, limit=limit, skip=offset,
            )
        except Exception as exc:
            logger.error("Error listing tool skills: %s", exc)
            raise HTTPException(status_code=500, detail=f"Error listing tool skills: {exc}")

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            self._decode_doc(doc)
        return docs

    async def update_skill(
        self,
        skill_id: Union[str, Any],
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mcp_tools: Optional[list[str]] = None,
        body: Optional[str] = None,
        enabled: Optional[bool] = None,
        version: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> bool:
        """Update an existing skill, including a validated rename."""
        current = await self.get_skill_by_id(skill_id)
        if not current:
            return False

        fields = self._validate(
            name=name if name is not None else current["name"],
            description=description if description is not None else current["description"],
            mcp_tools=mcp_tools if mcp_tools is not None else current["mcp_tools"],
            body=body if body is not None else current["body"],
            enabled=enabled if enabled is not None else current.get("enabled", True),
            version=version if version is not None else current.get("version"),
            priority=priority if priority is not None else current.get("priority", 0),
        )
        if fields["enabled"] and not current.get("enabled", True):
            await self._assert_active_capacity()
        if fields["name"] != current["name"]:
            existing = await self.database.find_one(self.collection_name, {"name": fields["name"]})
            if existing:
                raise HTTPException(status_code=409, detail=f"Tool skill '{fields['name']}' already exists")
        update_doc = self._encode_doc(fields)
        update_doc["updated_at"] = datetime.now(UTC)

        try:
            return await self.database.update_one(
                self.collection_name, {"_id": skill_id}, {"$set": update_doc},
            )
        except Exception as exc:
            logger.error("Error updating tool skill %s: %s", skill_id, exc)
            return False

    async def delete_skill(self, skill_id: Union[str, Any]) -> bool:
        try:
            return await self.database.delete_one(self.collection_name, {"_id": skill_id})
        except Exception as exc:
            logger.error("Error deleting tool skill %s: %s", skill_id, exc)
            return False

    async def _assert_active_capacity(self) -> None:
        active_count = await self.database.count(
            self.collection_name, {"enabled": True}
        )
        if active_count >= MAX_ACTIVE_DB_SKILLS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Active tool-skill limit ({MAX_ACTIVE_DB_SKILLS}) reached; "
                    "disable or delete an active skill before enabling another"
                ),
            )

    @staticmethod
    def _validate(
        *, name, description, mcp_tools, body, enabled, version, priority,
    ) -> dict[str, Any]:
        """Run the shared field validation, translating a ``SkillValidationError``
        into an HTTP 400 — the admin API's request-time equivalent of
        ``_parse_skill_file``'s log-and-skip for a bad file on disk."""
        try:
            return _validate_skill_fields(
                name=name, description=description, mcp_tools=mcp_tools, body=body,
                enabled=enabled, version=version, priority=priority,
                label="Tool skill",
            )
        except SkillValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
