"""Case schema and ${binding} template resolution.

A case never stores expected *values* — only the recipe for computing them
(`ground_truth`) and the rules the agent must obey (`checks`). See
ground_truth.py for why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ${binding.path.to[0].field} — dotted keys with optional [n] indexing.
TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")
_SEGMENT_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def deep_get(root: Any, path: str) -> Any:
    """Walk a dotted/indexed path, e.g. 'top.customers[0].id'."""
    current = root
    for name, index in _SEGMENT_RE.findall(path):
        if name:
            if not isinstance(current, dict) or name not in current:
                raise KeyError(f"{path!r}: no key {name!r} at {type(current).__name__}")
            current = current[name]
        else:
            position = int(index)
            if not isinstance(current, list) or position >= len(current):
                raise KeyError(f"{path!r}: index {position} out of range")
            current = current[position]
    return current


def resolve_templates(value: Any, bindings: dict[str, Any]) -> Any:
    """Substitute ${...} references recursively.

    A string that is exactly one reference keeps the referenced value's type
    (so an int stays an int); an embedded reference is stringified.
    """
    if isinstance(value, str):
        match = TEMPLATE_RE.fullmatch(value.strip())
        if match:
            return deep_get(bindings, match.group(1).strip())
        return TEMPLATE_RE.sub(lambda m: str(deep_get(bindings, m.group(1).strip())), value)
    if isinstance(value, dict):
        return {key: resolve_templates(item, bindings) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_templates(item, bindings) for item in value]
    return value


@dataclass(frozen=True)
class GroundTruthStep:
    """One ground-truth step, bound to a name.

    Either a read-only tool call (`tool` + `args`) or a derivation (`derive`)
    that post-processes an earlier binding — needed because some expectations
    are orderings or filters the server does not return directly.
    """

    as_: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    derive: str | None = None
    from_: str | None = None


@dataclass(frozen=True)
class Check:
    type: str
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass(frozen=True)
class Case:
    id: str
    query: str
    suite: str
    playbook: str | None
    checks: tuple[Check, ...]
    ground_truth: tuple[GroundTruthStep, ...] = ()
    setup: tuple[dict[str, Any], ...] = ()
    tags: tuple[str, ...] = ()
    mutating: bool = False
    max_tool_calls: int = 8


@dataclass(frozen=True)
class Suite:
    name: str
    playbook: str | None
    cases: tuple[Case, ...]


def _parse_case(raw: dict[str, Any], suite: str, playbook: str | None) -> Case:
    return Case(
        id=raw["id"],
        query=raw["query"],
        suite=suite,
        playbook=playbook,
        checks=tuple(Check(type=c.pop("type"), params=c) for c in (raw.get("checks") or [])),
        ground_truth=tuple(
            GroundTruthStep(
                as_=s["as"],
                tool=s.get("tool"),
                args=s.get("args") or {},
                derive=s.get("derive"),
                from_=s.get("from"),
            )
            for s in (raw.get("ground_truth") or [])
        ),
        setup=tuple(raw.get("setup") or []),
        tags=tuple(raw.get("tags") or []),
        mutating=bool(raw.get("mutating", False)),
        max_tool_calls=int(raw.get("max_tool_calls", 8)),
    )


def load_suite(path: Path) -> Suite:
    raw = yaml.safe_load(path.read_text())
    name = raw["suite"]
    playbook = raw.get("playbook")
    cases = tuple(_parse_case(case, name, playbook) for case in raw["cases"])
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: duplicate case ids")
    return Suite(name=name, playbook=playbook, cases=cases)


def load_suites(cases_dir: Path) -> list[Suite]:
    return [load_suite(path) for path in sorted(cases_dir.glob("*.yaml"))]
