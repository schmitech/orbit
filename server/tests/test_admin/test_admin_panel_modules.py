"""Static smoke checks for the browser-native admin panel module graph."""

import re
import shutil
import subprocess
from pathlib import Path


ADMIN_DIR = Path(__file__).resolve().parents[2] / "admin"
IMPORT_RE = re.compile(r'from\s+["\']([^"\']+)["\']')


def test_admin_panel_uses_a_module_entrypoint():
    html = (ADMIN_DIR / "admin_panel.html").read_text()

    assert '<script type="module" src="/static/admin_panel.js?' in html


def test_admin_panel_module_imports_resolve_and_parse():
    """Catch missing/malformed modules before a browser loads the panel."""
    module_files = [ADMIN_DIR / "admin_panel.js", *sorted((ADMIN_DIR / "admin_panel").rglob("*.js"))]
    node = shutil.which("node")

    for module_file in module_files:
        source = module_file.read_text()
        for specifier in IMPORT_RE.findall(source):
            if specifier.startswith("."):
                assert (module_file.parent / specifier).resolve().is_file(), (
                    f"{module_file.relative_to(ADMIN_DIR)} imports missing module {specifier}"
                )

        if node:
            result = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=source,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr


def test_mcp_playbooks_match_already_namespaced_discovered_tools():
    """The admin MCP endpoint exposes names from MCPClientManager's
    OpenAI-format cache, where every tool is already ``<server>__<tool>``.
    Guard against the UI adding the server namespace a second time, which
    makes valid database skill bindings impossible to display.
    """
    source = (ADMIN_DIR / "admin_panel" / "tabs" / "mcp.js").read_text()

    assert 'discovery.tools.map(function (t) { return t.name; })' in source
    assert 'server.name + "__" + t.name' not in source


def test_mcp_playbook_glob_matcher_covers_backend_fnmatch_shapes():
    source = (ADMIN_DIR / "admin_panel" / "tabs" / "mcp.js").read_text()
    assert "export function mcpToolSkillGlobMatch" in source
    assert 'contents[0] === "!"' in source
    assert "mcpToolSkillGlobMatch(n, pattern)" in source
