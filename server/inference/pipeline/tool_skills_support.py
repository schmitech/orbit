"""
Shared tool-skill support for both MCP tool-calling call sites — the explicit
``mcp_agent`` adapter (inference/pipeline/steps/mcp_agent.py) and the
opportunistic path (inference/pipeline/steps/llm_inference.py). Extracted so
Level 1/2/3 disclosure, per-adapter scoping, and the per-turn injection budget
are implemented once. See docs/roadmap/mcp-tool-skills.md §2, §3, §4 (Phase 2).
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .mcp_tool_loop import ToolDispatchResult, TrustedContext
from services.tool_skill_service import ToolSkill, ToolSkillRegistry, SURFACED_SET_CAP

logger = logging.getLogger(__name__)

# Reserved namespace for the synthetic tool-skill loader.
TOOL_SKILL_LOADER_NAME = "orbit__load_tool_skill"

# Per-turn injection budget shared across Level 2 (explicit load) and Level 3
# (JIT auto-injection) — docs/roadmap/mcp-tool-skills.md §3/§8 Q5. A skill
# already counted toward this budget (via either level) cannot be loaded a
# second time in the same turn, and the two levels draw from one shared pool.
INJECTION_BUDGET_MAX_SKILLS = 3
INJECTION_BUDGET_MAX_BYTES = 24 * 1024


def tool_names(tools: Sequence[Dict[str, Any]]) -> List[str]:
    return [t.get("function", {}).get("name", "") for t in tools]


def tool_skill_loader_schema(surfaced_skills: Sequence[ToolSkill]) -> Dict[str, Any]:
    """
    The synthetic ``orbit__load_tool_skill`` tool. Its ``name`` enum is built
    from exactly the turn's *surfaced set* (§2.2) — never the full matched
    set, and never the whole registry. The enum is a UX aid only; the
    dispatcher independently re-checks the requested name against this same
    surfaced set server-side.
    """
    return {
        "type": "function",
        "function": {
            "name": TOOL_SKILL_LOADER_NAME,
            "description": "Read the full procedural playbook for using a set of tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": [skill.name for skill in surfaced_skills],
                        "description": "The skill name to load, from the tool playbook catalog.",
                    },
                },
                "required": ["name"],
            },
        },
    }


def tool_skill_catalog_text(surfaced_skills: Sequence[ToolSkill]) -> str:
    """Level 1 catalog block appended to the system message (§2.2) — one
    line per surfaced skill, cheap enough to send on every turn."""
    lines = "\n".join(f"- {skill.name}: {skill.description}" for skill in surfaced_skills)
    return (
        "Available tool playbooks (call "
        f"{TOOL_SKILL_LOADER_NAME} to read one in full):\n{lines}"
    )


def resolve_surfaced_skills(
    tools: Sequence[Dict[str, Any]],
    registry: ToolSkillRegistry,
    allowlist: Optional[Sequence[str]],
) -> Tuple[List[ToolSkill], List[ToolSkill], bool]:
    """
    Resolve this turn's matched and surfaced skill sets against ``tools``
    (the already relevance-filtered MCP tool list), applying the adapter's
    ``capabilities.tool_skills`` allowlist (§2.7) — ``None`` means every
    matching skill, matching ``mcp_servers``' own default.

    Returns ``(surfaced_skills, matched_skills, loader_name_collides)``.

    ``matched_skills`` is the full matched set, filtered by the allowlist —
    Level 3 (§2.2) deliberately consults this rather than the capped
    surfaced set. ``surfaced_skills`` is ``matched_skills`` truncated to
    ``SURFACED_SET_CAP``, and is what drives the Level 1 catalog, the Level 2
    loader's enum, and Level 2 dispatch authorization (§2.2).

    On a namespace collision — a real MCP tool literally named
    ``orbit__load_tool_skill`` — tool skills are disabled entirely for this
    turn (empty sets, collision flag set) so the real tool always wins the
    name (§4 Phase 1 post-review fix).
    """
    names = tool_names(tools)
    if TOOL_SKILL_LOADER_NAME in set(names):
        logger.warning(
            "An MCP tool named '%s' is already exposed this turn; tool skills "
            "are disabled for it so the real tool stays reachable.",
            TOOL_SKILL_LOADER_NAME,
        )
        return [], [], True

    matched = registry.matched_for(names)
    if allowlist is not None:
        allowed = set(allowlist)
        matched = [skill for skill in matched if skill.name in allowed]
    surfaced = matched[:SURFACED_SET_CAP]
    return surfaced, matched, False


class InjectionBudget:
    """
    Per-turn budget and idempotence tracker shared across Level 2 (explicit
    ``orbit__load_tool_skill`` calls) and Level 3 (JIT auto-injection) —
    docs/roadmap/mcp-tool-skills.md §2.2/§3. One instance is built per turn
    and threaded through the dispatcher closure built by :func:`build_dispatch`.

    Eligibility is decided **once, up front**, from ``candidate_skills`` — the
    turn's full matched set, already sorted (priority desc, name) by
    ``ToolSkillRegistry.matched_for`` — rather than reactively as each
    dispatch call arrives. This is required, not a simplification: which
    tools a model happens to invoke first, and in what order, is not
    controllable, and Level 3 skills are only discovered as those calls
    happen. A first-come-first-served budget would let three low-priority
    bound-tool calls exhaust the budget before a higher-priority tool is
    ever invoked later in the same turn — silently inverting the documented
    "drop lowest-priority skills first" rule (§2.1, §3). Precomputing
    eligibility from the full sorted candidate set makes the outcome depend
    only on priority/name, never on call order.
    """

    def __init__(
        self,
        candidate_skills: List[ToolSkill],
        max_skills: int = INJECTION_BUDGET_MAX_SKILLS,
        max_bytes: int = INJECTION_BUDGET_MAX_BYTES,
    ):
        self.loaded: set = set()
        self._eligible = self._select_eligible(candidate_skills, max_skills, max_bytes)

    @staticmethod
    def _select_eligible(candidate_skills: List[ToolSkill], max_skills: int, max_bytes: int) -> set:
        """
        Greedily admit skills from ``candidate_skills`` in the order given
        (priority desc, name) until either cap is hit. A skill too large to
        fit the remaining byte budget is skipped rather than stopping the
        scan, so a later, smaller, lower-priority skill can still be
        admitted within the same byte budget.
        """
        eligible: set = set()
        bytes_used = 0
        for skill in candidate_skills:
            if len(eligible) >= max_skills:
                break
            size = len(skill.body.encode("utf-8"))
            if bytes_used + size > max_bytes:
                continue
            eligible.add(skill.name)
            bytes_used += size
        return eligible

    def already_loaded(self, name: str) -> bool:
        return name in self.loaded

    def try_reserve(self, skill: ToolSkill) -> bool:
        """
        Attempt to count ``skill`` against the shared budget. Returns False
        (without side effects) if the skill was already loaded this turn, or
        if it was never in the precomputed eligible set (dropped for the
        turn regardless of call order) — callers distinguish "already
        loaded" (idempotent repeat) from "budget exhausted" (dropped)
        themselves via ``already_loaded``.
        """
        if skill.name in self.loaded:
            return False
        if skill.name not in self._eligible:
            return False
        self.loaded.add(skill.name)
        return True


def build_dispatch(mcp_manager, surfaced_skills: Sequence[ToolSkill], matched_skills: Sequence[ToolSkill], budget: InjectionBudget):
    """
    Build this turn's dispatcher, combining:

    - **Level 2** — ``orbit__load_tool_skill`` routes to a local skill load,
      authorized against ``surfaced_skills`` only (§2.2). Interception is
      itself gated on ``surfaced_skills`` being non-empty — defense in depth
      alongside the collision guard in :func:`resolve_surfaced_skills`, so an
      empty surfaced set (nothing matched, or a namespace collision) never
      swallows a same-named real MCP tool call.
    - **Level 3** — the first time a tool bound to a matched skill is
      actually invoked this turn, its body rides along as trusted context on
      that same dispatch (§2.2), drawn from the full ``matched_skills`` set
      (not just the surfaced set — §2.2's stated exception). Sibling calls
      requested in the same assistant turn are unaffected, since each
      dispatch only ever attaches skills bound to its own ``tool_name``.

    Both levels draw from the one shared ``budget``: a skill already loaded
    via either level is idempotent on any further request (Level 2 returns a
    fixed "already loaded" result; Level 3 silently skips it), and a skill
    that would exceed the per-turn skill-count or byte budget is dropped —
    logged for Level 3, returned as a rejection result for Level 2.
    """
    surfaced_by_name = {skill.name: skill for skill in surfaced_skills}

    async def dispatch(tool_name: str, arguments: Dict[str, Any]) -> ToolDispatchResult:
        if tool_name == TOOL_SKILL_LOADER_NAME and surfaced_by_name:
            requested = arguments.get("name") if isinstance(arguments, dict) else None
            skill = surfaced_by_name.get(requested)
            if skill is None:
                return ToolDispatchResult(
                    content=f"Unknown or unavailable tool skill '{requested}'.",
                    source_type="tool_skill_load",
                )
            if budget.already_loaded(requested):
                return ToolDispatchResult(
                    content=f"'{requested}' already loaded this turn.",
                    source_type="tool_skill_load",
                )
            if not budget.try_reserve(skill):
                return ToolDispatchResult(
                    content=f"'{requested}' could not be loaded (per-turn tool-skill budget reached).",
                    source_type="tool_skill_load",
                )
            return ToolDispatchResult(
                content="",
                source_type="tool_skill_load",
                trusted_context=[TrustedContext(name=skill.name, body=skill.body, version=skill.version)],
            )

        content = await mcp_manager.call_tool(tool_name, arguments)
        result = ToolDispatchResult(content=content, source_type="mcp_tool_call")

        for skill in matched_skills:
            if budget.already_loaded(skill.name):
                continue
            if not skill.matches(tool_name):
                continue
            if not budget.try_reserve(skill):
                logger.info(
                    "Tool skill '%s' dropped from just-in-time injection: "
                    "per-turn tool-skill budget reached.", skill.name,
                )
                continue
            result.trusted_context.append(
                TrustedContext(name=skill.name, body=skill.body, version=skill.version)
            )
        return result

    return dispatch
