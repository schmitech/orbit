"""Static smoke checks for the browser-native admin panel module graph."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_ops_log_autoscroll_stays_inside_terminal():
    """Loading/tailing logs must not scroll the page past server controls."""
    source = (ADMIN_DIR / "admin_panel" / "tabs" / "ops.js").read_text()

    assert "function scrollLogsToBottom" in source
    assert "logBody.scrollTop = logBody.scrollHeight" in source
    assert "logScrollAnchor.scrollIntoView" not in source


def test_persona_api_key_names_use_safe_display_metadata():
    module_url = json.dumps((ADMIN_DIR / "admin_panel" / "tabs" / "prompts.js").resolve().as_uri())
    script = f"""
import {{ associatedApiKeyNames }} from {module_url};

var keys = [
  {{ client_name: "Zeta client", api_key: "***secret-z", system_prompt_id: "persona-1" }},
  {{ client_name: "Alpha client", api_key: "***secret-a", system_prompt_id: "persona-1" }},
  {{ client_name: "Other client", api_key: "***secret-o", system_prompt_id: "persona-2" }},
];
var names = associatedApiKeyNames("persona-1", keys);
if (names.join(",") !== "Alpha client,Zeta client") throw new Error("associated key names should be matched and sorted");
if (names.join(" ").includes("secret")) throw new Error("key values must never appear in persona associations");
"""
    _run_node_module_assertions(script)


def _run_node_module_assertions(script: str) -> None:
    """Run an ES-module script with node and fail the test on any assertion
    failure it reports (via a non-zero exit code)."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    result = subprocess.run(
        [node, "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_keys_expiration_helpers():
    """Exercise the pure expiration helpers exported by api-keys.js — display
    categorization, sort ordering, request-payload construction, and the
    multi-page loading algorithm — per the API key expiration admin-panel
    plan's testing section.
    """
    module_url = json.dumps((ADMIN_DIR / "admin_panel" / "tabs" / "api-keys.js").resolve().as_uri())
    script = f"""
import {{
  expirationState, expirationSortValue, formatExpiration, accessState,
  buildExpirationRequest, collectAllKeyPages
}} from {module_url};

var failures = [];
function assert(cond, msg) {{ if (!cond) failures.push(msg); }}

var now = Math.floor(Date.now() / 1000);
var daySec = 86400;

// --- display categories ---------------------------------------------
var managedKey = {{ expires_at: now + 10 * daySec, expiration_policy: "managed", expired: false, days_remaining: 10, active: true }};
var legacyKey = {{ expires_at: now + 90 * daySec, expiration_policy: "legacy_migration", expired: false, days_remaining: 90, active: true }};
var expiredKey = {{ expires_at: now - daySec, expiration_policy: "managed", expired: true, days_remaining: -1, active: true }};
var nonExpiringKey = {{ expires_at: null, expiration_policy: "non_expiring_exception", expired: false, days_remaining: null, active: true }};
var missingKey = {{ expires_at: null, expiration_policy: null, expired: false, days_remaining: null, active: true }};

assert(expirationState(managedKey) === "managed", "managed key should classify as managed");
assert(expirationState(legacyKey) === "legacy_migration", "legacy migration key should classify as legacy_migration");
assert(expirationState(expiredKey) === "expired", "expired key should classify as expired");
assert(expirationState(nonExpiringKey) === "non_expiring", "non-expiring exception should classify as non_expiring");
assert(expirationState(missingKey) === "missing", "key with no policy/expires_at should classify as missing (migration pending)");

// Server `expired` must win even when expires_at looks like it is still in
// the future (simulated browser/server clock skew).
var skewedKey = {{ expires_at: now + 10 * daySec, expiration_policy: "managed", expired: true, days_remaining: -0.01, active: true }};
assert(expirationState(skewedKey) === "expired", "server expired=true must win over a future-looking expires_at");

// --- access precedence: Inactive, Expired, Active --------------------
assert(accessState({{ active: false, expired: true }}) === "inactive", "inactive beats expired in access precedence");
assert(accessState({{ active: true, expired: true }}) === "expired", "expired beats active in access precedence");
assert(accessState({{ active: true, expired: false }}) === "active", "active key with no expiration issue is active");

// --- sort ordering, including missing/non-expiring ---------------------
var soonKey = {{ expires_at: now + daySec, expiration_policy: "managed", expired: false, days_remaining: 1 }};
var laterKey = {{ expires_at: now + 5 * daySec, expiration_policy: "managed", expired: false, days_remaining: 5 }};
var unordered = [missingKey, nonExpiringKey, laterKey, soonKey];
var sorted = unordered.slice().sort(function (a, b) {{ return expirationSortValue(a) - expirationSortValue(b); }});
assert(sorted[0] === soonKey && sorted[1] === laterKey && sorted[2] === nonExpiringKey && sorted[3] === missingKey,
  "finite timestamps should sort chronologically before non-expiring, which sorts before missing metadata");

// --- expiring-soon threshold uses the server-supplied warning days -----
var tenDayKey = {{ expires_at: now + 10 * daySec, expiration_policy: "managed", expired: false, days_remaining: 10 }};
assert(formatExpiration(tenDayKey, 14).badge === "warning", "10 days remaining should be 'expiring soon' at a 14-day threshold");
assert(formatExpiration(tenDayKey, 7).badge !== "warning", "10 days remaining should not be 'expiring soon' at a 7-day threshold");
assert(formatExpiration(expiredKey, 14).badge === "error", "expired key should carry the error badge regardless of threshold");
assert(formatExpiration(nonExpiringKey, 14).badge === "success", "non-expiring exception should carry a success (green) badge");
assert(!formatExpiration(expiredKey, 14).label.startsWith("Expired"), "expired timestamp should not repeat the badge text");
assert(formatExpiration(nonExpiringKey, 14).label === "", "non-expiring exception should be represented by one self-contained badge");

// --- create default: no expiration properties ---------------------------
var defaultResult = buildExpirationRequest("default", "", "");
assert(defaultResult.ok && Object.keys(defaultResult.body).length === 0, "server-default choice must send no expiration fields");

// --- custom expiration: only a valid ISO expires_at ----------------------
var future = new Date(Date.now() + 30 * 60 * 1000);
var futureLocal = future.getFullYear() + "-" + String(future.getMonth() + 1).padStart(2, "0") + "-" + String(future.getDate()).padStart(2, "0")
  + "T" + String(future.getHours()).padStart(2, "0") + ":" + String(future.getMinutes()).padStart(2, "0");
var customResult = buildExpirationRequest("custom", futureLocal, "");
assert(customResult.ok, "a valid future custom date should be accepted");
assert(Object.keys(customResult.body).join(",") === "expires_at", "custom choice must send only expires_at");
assert(!isNaN(new Date(customResult.body.expires_at).getTime()), "expires_at must be a valid ISO timestamp");

// --- non-expiring: only non_expiring + trimmed justification -------------
var nonExpResult = buildExpirationRequest("non_expiring", "", "  needed for a service account  ");
assert(nonExpResult.ok, "a non-empty justification should be accepted");
assert(Object.keys(nonExpResult.body).sort().join(",") === "expiration_justification,non_expiring", "non-expiring choice must send only non_expiring and expiration_justification");
assert(nonExpResult.body.non_expiring === true, "non_expiring must be true");
assert(nonExpResult.body.expiration_justification === "needed for a service account", "justification must be trimmed");

// --- rejections ------------------------------------------------------
assert(!buildExpirationRequest("non_expiring", "", "").ok, "empty justification must be rejected");
assert(!buildExpirationRequest("non_expiring", "", "   ").ok, "whitespace-only justification must be rejected");
assert(!buildExpirationRequest("custom", "", "").ok, "missing custom date must be rejected");
assert(!buildExpirationRequest("custom", "not-a-date", "").ok, "invalid custom date must be rejected");
var past = new Date(Date.now() - 60 * 60 * 1000);
var pastLocal = past.getFullYear() + "-01-01T00:00";
assert(!buildExpirationRequest("custom", pastLocal, "").ok, "a past custom date must be rejected");
assert(!buildExpirationRequest("bogus-choice", "", "").ok, "an unrecognized/conflicting choice must be rejected");

// --- multi-page loading: 1000-record offsets, stop on a short page -------
(async function () {{
  var calls = [];
  function makePage(count, warningDays) {{
    var keys = [];
    for (var i = 0; i < count; i++) keys.push({{ _id: "k" + i }});
    var page = {{ keys: keys }};
    if (warningDays !== undefined) page.expiration_warning_days = warningDays;
    return page;
  }}
  var pages = [makePage(1000, 21), makePage(1000), makePage(500)];
  var result = await collectAllKeyPages(function (limit, offset) {{
    calls.push([limit, offset]);
    return Promise.resolve(pages.shift());
  }});
  assert(result.keys.length === 2500, "should concatenate all pages into 2500 keys");
  assert(calls.length === 3, "should stop after the short (< limit) page");
  assert(JSON.stringify(calls) === JSON.stringify([[1000, 0], [1000, 1000], [1000, 2000]]), "should page with limit=1000 and increasing offsets");
  assert(result.expirationWarningDays === 21, "should capture expiration_warning_days from the first page that has it");
  assert(result.usedFallbackWarningDays === false, "should not report a fallback when a page carried expiration_warning_days");

  var noWarningDaysResult = await collectAllKeyPages(function () {{
    return Promise.resolve({{ keys: [] }});
  }});
  assert(noWarningDaysResult.usedFallbackWarningDays === true, "should report a fallback when no page carries expiration_warning_days");
  assert(noWarningDaysResult.expirationWarningDays === 14, "should fall back to a 14-day default");

  if (failures.length) {{
    console.error(failures.join("\\n"));
    process.exit(1);
  }}
}})();
"""
    _run_node_module_assertions(script)
