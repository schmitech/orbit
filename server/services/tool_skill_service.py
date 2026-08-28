"""
Tool Skill Registry — Phase 1 (file-based)

Loads admin-authored SKILL.md documents from disk and indexes them by the
namespaced MCP tool names (``<server>__<tool>``) they are bound to via their
``mcp_tools`` glob list.

This is a *procedural playbook* mechanism, not the ORBIT skill/adapter-swap
routing mechanism (``capabilities.expose_as_skill``) — see
docs/roadmap/mcp-tool-skills.md §1 for the terminology split. A "tool skill"
here is a markdown document with YAML frontmatter that the model can load via
the synthetic ``orbit__load_tool_skill`` tool (see
inference/pipeline/steps/mcp_agent.py), never an adapter and never routed via
``skill: "..."``.

See docs/roadmap/mcp-tool-skills.md for the full design (§2.1, §2.2, §2.5).
"""

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Matches the lowercase-slug convention MCP server names already use
# (routes/admin/mcp.py) — kept consistent so a skill name never surprises an
# author familiar with that convention.
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

# Reserved for the synthetic loader tool (orbit__load_tool_skill) — no skill
# may claim this namespace (docs/roadmap/mcp-tool-skills.md §2.1).
_RESERVED_PREFIX = "orbit__"

_FRONTMATTER_DELIM = "---"

# Per-skill body cap (docs/roadmap/mcp-tool-skills.md §3, §8 Q5).
MAX_SKILL_BODY_BYTES = 32 * 1024

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
    mcp_tools: List[str]
    body: str
    enabled: bool = True
    version: Optional[str] = None
    priority: int = 0
    source_path: Optional[str] = None

    def matches(self, tool_name: str) -> bool:
        """Whether this skill's mcp_tools glob list covers ``tool_name``.

        fnmatch-style globbing (not pathlib path-matching — the namespaced
        tool name is a flat ``<server>__<tool>`` string, not a path), case
        sensitive to match the already-lowercase server/tool name convention.
        """
        return any(fnmatch.fnmatchcase(tool_name, pattern) for pattern in self.mcp_tools)


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

    name = frontmatter.get("name")
    if not isinstance(name, str) or not _SKILL_NAME_PATTERN.match(name):
        logger.warning("Skill file %s has a missing/invalid 'name' (must be a lowercase slug); skipped.", path)
        return None
    if name.startswith(_RESERVED_PREFIX):
        logger.warning(
            "Skill '%s' in %s uses the reserved '%s' prefix (the synthetic loader's own "
            "namespace); skipped.", name, path, _RESERVED_PREFIX,
        )
        return None

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        logger.warning("Skill '%s' in %s is missing a non-empty 'description'; skipped.", name, path)
        return None

    mcp_tools = frontmatter.get("mcp_tools")
    if not isinstance(mcp_tools, list) or not mcp_tools or not all(
        isinstance(t, str) and t.strip() for t in mcp_tools
    ):
        logger.warning("Skill '%s' in %s has a missing/invalid 'mcp_tools' list; skipped.", name, path)
        return None
    for pattern in mcp_tools:
        if pattern.startswith(_RESERVED_PREFIX):
            logger.warning(
                "Skill '%s' in %s binds the reserved '%s' prefix in mcp_tools; skipped.",
                name, path, _RESERVED_PREFIX,
            )
            return None

    enabled = frontmatter.get("enabled", True)
    if not isinstance(enabled, bool):
        logger.warning("Skill '%s' in %s has non-boolean 'enabled'; defaulting to true.", name, path)
        enabled = True

    version = frontmatter.get("version")
    if version is not None:
        version = str(version)

    priority = frontmatter.get("priority", 0)
    if not isinstance(priority, int) or isinstance(priority, bool):
        logger.warning("Skill '%s' in %s has non-integer 'priority'; defaulting to 0.", name, path)
        priority = 0

    if not body:
        logger.warning("Skill '%s' in %s has an empty body; skipped.", name, path)
        return None

    body_size = len(body.encode("utf-8"))
    if body_size > MAX_SKILL_BODY_BYTES:
        logger.warning(
            "Skill '%s' in %s exceeds the %d-byte body cap (%d bytes); skipped.",
            name, path, MAX_SKILL_BODY_BYTES, body_size,
        )
        return None

    return ToolSkill(
        name=name,
        description=description.strip(),
        mcp_tools=list(mcp_tools),
        body=body,
        enabled=enabled,
        version=version,
        priority=priority,
        source_path=str(path),
    )


class ToolSkillRegistry:
    """
    Loads and indexes SKILL.md documents from ``skills_dir`` (Phase 1:
    file-based only — Phase 3 layers a database source on top, database
    entries winning on a name collision; see
    docs/roadmap/mcp-tool-skills.md §2.6).

    A missing or empty directory is not an error — no skills configured is a
    valid, common state.
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self._skills: Dict[str, ToolSkill] = {}
        self._load()

    def _load(self) -> None:
        skills: Dict[str, ToolSkill] = {}
        if not self.skills_dir.is_dir():
            self._skills = skills
            return

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

        self._skills = skills

    def reload(self) -> None:
        """Re-read every SKILL.md under ``skills_dir`` from disk."""
        self._load()

    def all_skills(self) -> List[ToolSkill]:
        return list(self._skills.values())

    def get(self, name: str) -> Optional[ToolSkill]:
        return self._skills.get(name)

    def matched_for(self, tool_names: Iterable[str]) -> List[ToolSkill]:
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
    ``get_mcp_client_manager`` in services/mcp_client_service.py.
    """
    global _registry_instance, _registry_dir
    directory = _resolve_skills_dir(config)
    if _registry_instance is None or _registry_dir != directory:
        _registry_instance = ToolSkillRegistry(Path(directory))
        _registry_dir = directory
    return _registry_instance


def reload_tool_skill_registry(config: dict) -> ToolSkillRegistry:
    """Force a fresh reload from disk, discarding any cached instance."""
    global _registry_instance, _registry_dir
    directory = _resolve_skills_dir(config)
    _registry_instance = ToolSkillRegistry(Path(directory))
    _registry_dir = directory
    return _registry_instance
