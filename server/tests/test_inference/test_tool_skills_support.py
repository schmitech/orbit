#!/usr/bin/env python3
"""
Unit tests for the shared tool-skill support module
(server/inference/pipeline/tool_skills_support.py) — docs/roadmap/mcp-tool-skills.md
Phase 2 (§4): InjectionBudget and resolve_surfaced_skills, isolated from
either pipeline step.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

import types
if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from inference.pipeline.tool_skills_support import (
    TOOL_SKILL_LOADER_NAME,
    InjectionBudget,
    resolve_surfaced_skills,
)


class _FakeSkill:
    def __init__(self, name, body="x", priority=0):
        self.name = name
        self.body = body
        self.priority = priority

    def matches(self, tool_name):
        return True


class _FakeRegistry:
    def __init__(self, skills):
        self._skills = skills

    def matched_for(self, tool_names):
        return list(self._skills)


_TOOLS = [{"type": "function", "function": {"name": "filesystem__read_file"}}]


class TestInjectionBudget:
    def test_reserves_up_to_the_skill_count_cap(self):
        a, b, c = _FakeSkill("a"), _FakeSkill("b"), _FakeSkill("c")
        budget = InjectionBudget([a, b, c], max_skills=2, max_bytes=10_000)

        assert budget.try_reserve(a) is True
        assert budget.try_reserve(b) is True
        assert budget.try_reserve(c) is False  # 3rd exceeds the skill-count cap

    def test_reserves_up_to_the_byte_cap(self):
        small = _FakeSkill("small", body="12345")
        big = _FakeSkill("big", body="1234567890123")
        budget = InjectionBudget([small, big], max_skills=10, max_bytes=10)

        assert budget.try_reserve(small) is True
        assert budget.try_reserve(big) is False  # would exceed the byte cap

    def test_a_skill_cannot_be_reserved_twice(self):
        skill = _FakeSkill("a")
        budget = InjectionBudget([skill], max_skills=10, max_bytes=10_000)

        assert budget.try_reserve(skill) is True
        assert budget.try_reserve(skill) is False
        assert budget.already_loaded("a") is True

    def test_priority_admission_is_independent_of_reservation_order(self):
        """
        Regression: eligibility must be decided from the full candidate set
        up front, not first-come-first-served at try_reserve time — three
        low-priority skills reserved before a high-priority one must not
        permanently exhaust the budget and lock the high-priority skill out.
        candidate_skills mirrors ToolSkillRegistry.matched_for's sort
        (priority desc, name), so "h" here is the highest-priority skill even
        though it is reserved last.
        """
        h = _FakeSkill("h", priority=10)
        l0, l1, l2 = _FakeSkill("l0"), _FakeSkill("l1"), _FakeSkill("l2")
        budget = InjectionBudget([h, l0, l1, l2], max_skills=3, max_bytes=10_000)

        # Calls arrive in an order the model controls, not priority order.
        assert budget.try_reserve(l0) is True
        assert budget.try_reserve(l1) is True
        assert budget.try_reserve(l2) is False  # not in the eligible set (4th by priority)
        assert budget.try_reserve(h) is True    # still admitted — eligibility precomputed


class TestResolveSurfacedSkills:
    def test_collision_disables_tool_skills_for_the_turn(self):
        colliding_tools = [{"type": "function", "function": {"name": TOOL_SKILL_LOADER_NAME}}]
        registry = _FakeRegistry([_FakeSkill("s1")])

        surfaced, matched, collided = resolve_surfaced_skills(colliding_tools, registry, allowlist=None)

        assert collided is True
        assert surfaced == []
        assert matched == []

    def test_allowlist_filters_the_matched_set_before_truncation(self):
        registry = _FakeRegistry([_FakeSkill("allowed"), _FakeSkill("excluded")])

        surfaced, matched, collided = resolve_surfaced_skills(_TOOLS, registry, allowlist=["allowed"])

        assert collided is False
        assert [s.name for s in matched] == ["allowed"]
        assert [s.name for s in surfaced] == ["allowed"]

    def test_no_allowlist_means_every_matched_skill(self):
        registry = _FakeRegistry([_FakeSkill("a"), _FakeSkill("b")])

        surfaced, matched, collided = resolve_surfaced_skills(_TOOLS, registry, allowlist=None)

        assert [s.name for s in matched] == ["a", "b"]
        assert [s.name for s in surfaced] == ["a", "b"]

    def test_surfaced_set_is_truncated_but_matched_set_is_not(self):
        skills = [_FakeSkill(f"s{i}") for i in range(15)]
        registry = _FakeRegistry(skills)

        surfaced, matched, collided = resolve_surfaced_skills(_TOOLS, registry, allowlist=None)

        assert len(matched) == 15
        assert len(surfaced) == 10
