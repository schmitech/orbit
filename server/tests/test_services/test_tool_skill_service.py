#!/usr/bin/env python3
"""
Unit tests for the tool-skill registry (server/services/tool_skill_service.py).

Phase 1 of docs/roadmap/mcp-tool-skills.md — file-based SKILL.md loading,
frontmatter validation, glob matching, and priority/name ordering.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from services.tool_skill_service import (
    MAX_SKILL_BODY_BYTES,
    SURFACED_SET_CAP,
    ToolSkill,
    ToolSkillRegistry,
    get_tool_skill_registry,
    reload_tool_skill_registry,
    warn_catalog_overflow,
)


def _write_skill(tmp_path, dirname, frontmatter_lines, body="Some procedural guidance."):
    skill_dir = tmp_path / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body + "\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


class TestToolSkillRegistryLoading:
    def test_missing_directory_yields_empty_registry(self, tmp_path):
        registry = ToolSkillRegistry(tmp_path / "does-not-exist")
        assert registry.all_skills() == []

    def test_empty_directory_yields_empty_registry(self, tmp_path):
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_loads_a_valid_skill(self, tmp_path):
        _write_skill(tmp_path, "crm", [
            "name: crm-pipeline-playbook",
            "description: How to use the CRM tools.",
            "mcp_tools:",
            '  - "business-sample__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        skills = registry.all_skills()
        assert len(skills) == 1
        skill = skills[0]
        assert skill.name == "crm-pipeline-playbook"
        assert skill.description == "How to use the CRM tools."
        assert skill.mcp_tools == ["business-sample__*"]
        assert skill.enabled is True
        assert skill.priority == 0
        assert "procedural guidance" in skill.body

    def test_missing_frontmatter_is_skipped(self, tmp_path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Just a body, no frontmatter.", encoding="utf-8")
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_invalid_yaml_frontmatter_is_skipped(self, tmp_path):
        skill_dir = tmp_path / "bad"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: [unterminated\n---\nbody\n", encoding="utf-8"
        )
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_missing_name_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "description: no name here",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_invalid_name_slug_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: Not_A_Valid_Slug!",
            "description: bad name",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_reserved_orbit_prefix_on_name_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: orbit__sneaky",
            "description: reserved prefix",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_reserved_orbit_prefix_in_mcp_tools_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: sneaky-binding",
            "description: reserved prefix in binding",
            "mcp_tools:",
            '  - "orbit__load_tool_skill"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_missing_description_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: no-description",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_missing_mcp_tools_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: no-binding",
            "description: has no mcp_tools",
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_empty_body_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "bad", [
            "name: empty-body",
            "description: has an empty body",
            "mcp_tools:",
            '  - "foo__*"',
        ], body="")
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_oversize_body_is_skipped(self, tmp_path):
        _write_skill(tmp_path, "big", [
            "name: too-big",
            "description: exceeds the body cap",
            "mcp_tools:",
            '  - "foo__*"',
        ], body="x" * (MAX_SKILL_BODY_BYTES + 1))
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_disabled_skill_is_excluded(self, tmp_path):
        _write_skill(tmp_path, "off", [
            "name: disabled-skill",
            "description: should not load",
            "mcp_tools:",
            '  - "foo__*"',
            "enabled: false",
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []

    def test_duplicate_name_keeps_first_loaded(self, tmp_path):
        _write_skill(tmp_path, "aaa-first", [
            "name: dup",
            "description: first one wins",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        _write_skill(tmp_path, "zzz-second", [
            "name: dup",
            "description: should be dropped",
            "mcp_tools:",
            '  - "bar__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        skills = registry.all_skills()
        assert len(skills) == 1
        assert skills[0].description == "first one wins"

    def test_reload_picks_up_a_new_file(self, tmp_path):
        registry = ToolSkillRegistry(tmp_path)
        assert registry.all_skills() == []
        _write_skill(tmp_path, "new", [
            "name: newly-added",
            "description: added after construction",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        registry.reload()
        assert len(registry.all_skills()) == 1


class TestToolSkillRegistryMatching:
    def test_glob_matches_server_wildcard(self, tmp_path):
        _write_skill(tmp_path, "crm", [
            "name: crm-playbook",
            "description: CRM tools",
            "mcp_tools:",
            '  - "business-sample__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        matched = registry.matched_for(["business-sample__search_opportunities", "github__search_issues"])
        assert [s.name for s in matched] == ["crm-playbook"]

    def test_glob_matches_exact_tool_name(self, tmp_path):
        _write_skill(tmp_path, "gh", [
            "name: gh-playbook",
            "description: GitHub issue search guidance",
            "mcp_tools:",
            '  - "github__search_issues"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert [s.name for s in registry.matched_for(["github__search_issues"])] == ["gh-playbook"]
        assert registry.matched_for(["github__list_prs"]) == []

    def test_no_match_returns_empty(self, tmp_path):
        _write_skill(tmp_path, "crm", [
            "name: crm-playbook",
            "description: CRM tools",
            "mcp_tools:",
            '  - "business-sample__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.matched_for(["filesystem__read_file"]) == []

    def test_matching_is_case_sensitive(self, tmp_path):
        _write_skill(tmp_path, "crm", [
            "name: crm-playbook",
            "description: CRM tools",
            "mcp_tools:",
            '  - "Business-Sample__*"',
        ])
        registry = ToolSkillRegistry(tmp_path)
        assert registry.matched_for(["business-sample__search_opportunities"]) == []
        assert registry.matched_for(["Business-Sample__search_opportunities"]) != []

    def test_priority_then_name_sort_order_is_deterministic(self, tmp_path):
        _write_skill(tmp_path, "b-skill", [
            "name: b-skill",
            "description: priority 0",
            "mcp_tools:",
            '  - "foo__*"',
        ])
        _write_skill(tmp_path, "a-skill", [
            "name: a-skill",
            "description: priority 5",
            "mcp_tools:",
            '  - "foo__*"',
            "priority: 5",
        ])
        _write_skill(tmp_path, "c-skill", [
            "name: c-skill",
            "description: priority 5 too, alphabetically after a-skill",
            "mcp_tools:",
            '  - "foo__*"',
            "priority: 5",
        ])
        registry = ToolSkillRegistry(tmp_path)
        matched = registry.matched_for(["foo__bar"])
        # Higher priority first; ties broken by name.
        assert [s.name for s in matched] == ["a-skill", "c-skill", "b-skill"]

    def test_matched_set_is_unbounded_by_the_registry_itself(self, tmp_path):
        for i in range(15):
            _write_skill(tmp_path, f"skill-{i:02d}", [
                f"name: skill-{i:02d}",
                "description: one of many",
                "mcp_tools:",
                '  - "foo__*"',
            ])
        registry = ToolSkillRegistry(tmp_path)
        # The registry itself does not cap; callers truncate to the surfaced set.
        assert len(registry.matched_for(["foo__bar"])) == 15


class TestGetToolSkillRegistrySingleton:
    def test_get_returns_same_instance_for_same_config(self, tmp_path, monkeypatch):
        import services.tool_skill_service as mod
        monkeypatch.setattr(mod, "_registry_instance", None)
        monkeypatch.setattr(mod, "_registry_dir", None)

        config = {"tool_skills": {"directory": str(tmp_path)}}
        first = get_tool_skill_registry(config)
        second = get_tool_skill_registry(config)
        assert first is second

    def test_reload_forces_a_fresh_instance(self, tmp_path, monkeypatch):
        import services.tool_skill_service as mod
        monkeypatch.setattr(mod, "_registry_instance", None)
        monkeypatch.setattr(mod, "_registry_dir", None)

        config = {"tool_skills": {"directory": str(tmp_path)}}
        first = get_tool_skill_registry(config)
        second = reload_tool_skill_registry(config)
        assert first is not second


class TestCatalogOverflowWarning:
    class _Manager:
        _tools_cache = {
            "business-sample": [
                {"function": {"name": "business-sample__list_customers"}},
            ],
            "private": [
                {"function": {"name": "private__secret"}},
            ],
        }

        @staticmethod
        def setting(server_name, key):
            return server_name == "business-sample" and key == "allow_opportunistic"

    def test_warns_with_priority_ordered_drops_for_reachable_tools(self, caplog, tmp_path):
        skills = [
            ToolSkill(
                name=f"skill-{i:02d}",
                description="procedure",
                mcp_tools=["business-sample__*"],
                body="body",
                priority=20 - i,
            )
            for i in range(SURFACED_SET_CAP + 2)
        ]
        registry = ToolSkillRegistry(tmp_path, db_skills=skills)
        config = {
            "adapters": [{
                "name": "mcp-agent-chat",
                "type": "mcp_agent",
                "enabled": True,
                "capabilities": {"mcp_servers": ["business-sample"]},
            }],
        }

        warn_catalog_overflow(config, registry, self._Manager())

        assert "matches 12 tool skills" in caplog.text
        assert "skill-10, skill-11" in caplog.text

    def test_respects_tool_skill_allowlist(self, caplog, tmp_path):
        skills = [
            ToolSkill(
                name=f"skill-{i:02d}", description="procedure",
                mcp_tools=["business-sample__*"], body="body",
            )
            for i in range(SURFACED_SET_CAP + 2)
        ]
        registry = ToolSkillRegistry(tmp_path, db_skills=skills)
        config = {
            "adapters": [{
                "name": "inline",
                "type": "conversational",
                "enabled": True,
                "capabilities": {
                    "mcp_tools": True,
                    "mcp_servers": ["business-sample"],
                    "tool_skills": ["skill-00"],
                },
            }],
        }

        warn_catalog_overflow(config, registry, self._Manager())

        assert "surfaced-set cap" not in caplog.text

    def test_warns_when_one_tool_exceeds_injection_budget(self, caplog, tmp_path):
        skills = [
            ToolSkill(
                name=f"skill-{i:02d}", description="procedure",
                mcp_tools=["business-sample__list_customers"], body="body",
                priority=10 - i,
            )
            for i in range(4)
        ]
        registry = ToolSkillRegistry(tmp_path, db_skills=skills)
        config = {
            "adapters": [{
                "name": "mcp-agent-chat",
                "type": "mcp_agent",
                "enabled": True,
                "capabilities": {"mcp_servers": ["business-sample"]},
            }],
        }

        warn_catalog_overflow(config, registry, self._Manager())

        assert "shared injection budget of 3 skills/24576 bytes" in caplog.text
        assert "skill-03" in caplog.text
