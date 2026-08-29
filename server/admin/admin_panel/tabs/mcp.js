// TAB: MCP (external Model Context Protocol servers and their tools)
//
// Master-detail. "Defaults" is pinned to the head of the server list
// because it is what every server inherits from — selecting it edits the
// mcp_clients-level block. Each server's settings row states its
// provenance (inherited vs override) and lights its leading edge when it
// departs from the default, reusing the panel accent already used across
// this design system to mean "this is the thing you changed".
// ==================================================================
export function createMcpTab({
  api, endpoints, el, clear, skeleton, refreshButton, withButton,
  confirmAction, showError, showStatus, createSelect, getActiveTab
}) {
  var mcpData = null;      // { enabled, defaults, servers, settings }
  var mcpTools = null;     // { available, servers: { name: {reachable, tools} } }
  var mcpSelected = null;  // server name, or MCP_DEFAULTS_KEY
  var mcpPending = {};     // unsaved edits for the current selection only
  var mcpPinging = {};     // server name -> true while its own ping is in flight
  var mcpLastChecked = {}; // server name -> Date.now() of its last completed ping
  var mcpCheckedAtNodes = []; // {node, ts, apply} for every "Checked Xs ago" span in the current render
  var mcpCheckedAtTimer = null; // ticks mcpCheckedAtNodes so the relative text ages while the tab sits open
  var mcpRowSync = {};    // server name -> fn that repaints just that list row (dot/meta/ping button)
  var mcpDetailSync = null; // { name, sync() } for the currently open server detail's tools section, or null
  var mcpSelectSync = {}; // list key -> fn(selected) that toggles just that row's selected styling
  var mcpDetailContainer = null; // the current detail <div>, so selecting a row can rebuild just it

  var MCP_DEFAULTS_KEY = "__defaults__";
  var MCP_CREATE_KEY = "__create__";

  var MCP_SETTING_LABELS = {
    allow_opportunistic: {
      label: "Opportunistic tools",
      hint: "Offer this server's tools on ordinary turns, with no skill requested",
    },
    tool_timeout: { label: "Tool timeout", hint: "Seconds before a tool call is abandoned", unit: "s" },
    max_tool_iterations: { label: "Max tool rounds", hint: "Tool-calling rounds allowed per request" },
    tool_result_max_chars: { label: "Result cap", hint: "Characters of tool output kept in model context" },
    discovery_timeout: { label: "Discovery timeout", hint: "Seconds to wait when listing this server's tools", unit: "s" },
    discovery_retry_interval: { label: "Discovery retry", hint: "Seconds before retrying a server that failed", unit: "s" },
  };

  var MCP_TRANSPORT_LABELS = { stdio: "Subprocess", http: "Streamable HTTP" };
  var MCP_CONNECTION_URL_MAX_LENGTH = 2048;
  var MCP_CONNECTION_COMMAND_MAX_LENGTH = 512;
  var MCP_CONNECTION_ARG_MAX_LENGTH = 2048;
  var MCP_CONNECTION_ARGS_MAX_COUNT = 64;
  // env and headers share the same key/value caps as their backend
  // counterparts (_MCP_CONNECTION_ENV_*/_MCP_CONNECTION_HEADER_* in
  // admin_routes.py) so the UI can't accept input the server will reject.
  var MCP_CONNECTION_ENV_KEY_MAX_LENGTH = 256;
  var MCP_CONNECTION_ENV_VALUE_MAX_LENGTH = 8192;
  var MCP_CONNECTION_ENV_MAX_ENTRIES = 64;
  var MCP_CONNECTION_HEADER_KEY_MAX_LENGTH = 256;
  var MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH = 8192;
  var MCP_CONNECTION_HEADER_MAX_ENTRIES = 32;

  function mcpEndpointUrlError(value) {
    if (!value || value.length > MCP_CONNECTION_URL_MAX_LENGTH) {
      return "URL must be between 1 and " + MCP_CONNECTION_URL_MAX_LENGTH + " characters.";
    }
    if (value !== value.trim() || /[\x00-\x20]/.test(value)) {
      return "URL must not contain whitespace or control characters.";
    }
    try {
      var parsed = new URL(value);
      if ((parsed.protocol !== "http:" && parsed.protocol !== "https:") || !parsed.hostname || parsed.hash) {
        return "URL must be an absolute HTTP(S) endpoint without a fragment.";
      }
    } catch (_err) {
      return "Enter a valid HTTP(S) endpoint URL.";
    }
    return null;
  }

  // Everything that reflects unsaved state — the save button, the override
  // summary, each row's accent and provenance, the server list — registers a
  // listener here. Edits then update those parts in place instead of
  // re-rendering the tab, which would rebuild the very input being typed into
  // and drop the caret.
  //
  // Split into two arrays so the two get reset independently: mcpListDirty
  // holds only the list's enabled-toggle rebuild listener and lives for the
  // whole tab render, while mcpDetailDirty holds every control the current
  // detail pane registers and must be cleared whenever that pane is
  // replaced (a fresh detail render or mcpSelectServer's fast path) — else
  // switching rows piles up listeners for detached controls indefinitely.
  var mcpListDirty = [];
  var mcpDetailDirty = [];

  function mcpSyncDirty() {
    mcpListDirty.forEach(function (fn) { fn(); });
    mcpDetailDirty.forEach(function (fn) { fn(); });
  }

  function mcpHasPendingEdits() {
    return Object.keys(mcpPending).length > 0;
  }

  function mcpSettingMeta(key) {
    return MCP_SETTING_LABELS[key] || { label: key, hint: "" };
  }

  function mcpFormatValue(key, value) {
    if (typeof value === "boolean") return value ? "on" : "off";
    var unit = mcpSettingMeta(key).unit || "";
    return String(value) + unit;
  }

  function mcpRelativeTime(ts) {
    var s = Math.round(Math.max(0, Date.now() - ts) / 1000);
    if (s < 5) return "just now";
    if (s < 60) return s + "s ago";
    var m = Math.round(s / 60);
    if (m < 60) return m + (m === 1 ? " min ago" : " mins ago");
    var h = Math.round(m / 60);
    return h + (h === 1 ? " hr ago" : " hrs ago");
  }

  // A "Checked Xs ago" span whose text keeps aging via mcpCheckedAtTimer
  // instead of freezing at whatever it read during the render that created
  // it — otherwise every timestamp reads "just now" until some unrelated
  // interaction happens to rerender the tab. `ts` may be null (nothing
  // checked yet); the span then hides itself until setTs gives it one.
  function mcpCheckedAtSpan(ts, className) {
    var span = el("span", { className: className || "mcp-checked-at" });
    var entry = { node: span, ts: ts };
    entry.apply = function () {
      if (entry.ts == null) {
        span.style.display = "none";
        span.textContent = "";
      } else {
        span.style.display = "";
        span.textContent = "Checked " + mcpRelativeTime(entry.ts);
      }
    };
    entry.apply();
    mcpCheckedAtNodes.push(entry);
    return {
      node: span,
      setTs: function (ts) { entry.ts = ts; entry.apply(); },
    };
  }

  function mcpStartCheckedAtTimer() {
    if (mcpCheckedAtTimer) return;
    mcpCheckedAtTimer = setInterval(function () {
      // A list-only rebuild (see the `enabled` dirty-listener below) swaps
      // in a fresh listSlot without resetting mcpCheckedAtNodes, so the old
      // rows' entries are left pointing at now-detached nodes. Drop them
      // here rather than letting them accumulate on every toggle.
      mcpCheckedAtNodes = mcpCheckedAtNodes.filter(function (entry) {
        if (!entry.node.isConnected) return false;
        entry.apply();
        return true;
      });
    }, 1000);
  }

  // Repaints only the pieces that a ping can change — this row's dot/meta/
  // ping button, and the open detail pane's tools section if it's this same
  // server — instead of a full mcpRerender(), which would tear down and
  // rebuild the whole master-detail layout on every click and read as a
  // flicker.
  function mcpApplyPingState(name) {
    if (mcpRowSync[name]) mcpRowSync[name]();
    if (mcpDetailSync && mcpDetailSync.name === name) mcpDetailSync.sync();
  }

  // Re-dials a single server via GET /mcp/tools?server=<name>, merging its
  // result into the shared mcpTools cache rather than replacing it — a ping
  // of one server must never blank out what's already known about the rest.
  async function mcpPingServer(name) {
    if (mcpPinging[name]) return;
    mcpPinging[name] = true;
    mcpApplyPingState(name);
    try {
      var result = await api("GET", endpoints.mcpTools + "?server=" + encodeURIComponent(name));
      if (!mcpTools) mcpTools = { available: result.available, servers: {} };
      mcpTools.available = result.available;
      mcpTools.reason = result.reason;
      if (result.available && result.servers) {
        mcpTools.servers = mcpTools.servers || {};
        Object.assign(mcpTools.servers, result.servers);
      }
      mcpLastChecked[name] = Date.now();
    } catch (err) {
      showError(err.message);
    } finally {
      mcpPinging[name] = false;
      mcpApplyPingState(name);
    }
  }

  // Reflects an unsaved enable/disable of `key` (a server name, or
  // MCP_DEFAULTS_KEY) for whichever entry is currently selected — used for
  // display everywhere except ping eligibility, which must stay pinned to
  // the persisted value the live MCPClientManager actually has.
  function mcpPendingToggleValue(key, saved) {
    return (mcpSelected === key && mcpPending.enabled != null) ? mcpPending.enabled : saved;
  }

  // Derives a server row's dot state / meta text / checked-at from current
  // state — used for both the initial render and mcpRowSync's repaint, so
  // the two can never drift out of sync with each other.
  function mcpServerRowStatus(server) {
    var discovery = (mcpTools && mcpTools.servers && mcpTools.servers[server.name]) || null;
    var pinging = !!mcpPinging[server.name];
    var displayEnabled = mcpPendingToggleValue(server.name, server.enabled);
    if (!displayEnabled) return { state: "off", meta: "Disabled", pinging: pinging, checkedAt: null };
    if (pinging) return { state: "checking", meta: "Pinging…", pinging: pinging, checkedAt: null };
    var checkedAt = mcpLastChecked[server.name] || null;
    if (discovery) {
      if (discovery.reachable) {
        return {
          state: "up",
          meta: discovery.tools.length + (discovery.tools.length === 1 ? " tool" : " tools"),
          pinging: pinging,
          checkedAt: checkedAt,
        };
      }
      return { state: "down", meta: "Unreachable", pinging: pinging, checkedAt: checkedAt };
    }
    // Nothing pinged this session yet — fall back to what the backend
    // already knows from its startup warm-up (or a previous admin session),
    // so the dot doesn't sit blank until someone clicks Ping. There's no
    // timestamp for that discovery, so checkedAt stays null.
    if (server.status) {
      if (server.status.reachable) {
        return {
          state: "up",
          meta: server.status.tool_count + (server.status.tool_count === 1 ? " tool" : " tools"),
          pinging: pinging,
          checkedAt: null,
        };
      }
      return { state: "down", meta: "Unreachable", pinging: pinging, checkedAt: null };
    }
    return { state: "unknown", meta: "Not checked", pinging: pinging, checkedAt: checkedAt };
  }

  async function renderMcp(container) {
    clear(container);

    if (!mcpData) {
      container.appendChild(skeleton());
      try {
        mcpData = await api("GET", endpoints.mcpServers);
      } catch (err) {
        clear(container);
        container.appendChild(el("div", { className: "panel empty-state" },
          el("strong", null, "Could not read the MCP configuration"),
          el("p", null, err.message)
        ));
        return;
      }
      if (getActiveTab() === "mcp") renderMcp(container);
      return;
    }

    if (mcpSelected === null) {
      mcpSelected = MCP_DEFAULTS_KEY;
    }

    mcpListDirty = [];
    mcpDetailDirty = [];
    mcpCheckedAtNodes = [];
    mcpRowSync = {};
    mcpDetailSync = null;
    mcpSelectSync = {};
    mcpStartCheckedAtTimer();

    var layout = el("div", { className: "mcp-layout" });
    container.appendChild(layout);

    var listSlot = mcpRenderList();
    layout.appendChild(listSlot);
    // `enabled` is the only pending edit the list reflects, so rebuild only
    // when it changes rather than on every keystroke. Focus lives in the
    // detail pane, so replacing the list is safe.
    var lastEnabled = mcpPending.enabled;
    mcpListDirty.push(function () {
      if (mcpPending.enabled === lastEnabled) return;
      lastEnabled = mcpPending.enabled;
      var fresh = mcpRenderList();
      layout.replaceChild(fresh, listSlot);
      listSlot = fresh;
    });

    var detail = el("div", { className: "panel mcp-detail" });
    layout.appendChild(detail);
    mcpDetailContainer = detail;
    mcpRenderDetail(detail);
  }

  function mcpRerender() {
    var c = document.getElementById("tab-content");
    if (c && getActiveTab() === "mcp") renderMcp(c);
  }

  // Selecting a row never changes anything about the list itself (dot,
  // meta, overrides) — only which row is highlighted and what the detail
  // pane shows. Repaint just those two things instead of routing through
  // mcpRerender(), which tears down and rebuilds the whole master-detail
  // layout and reads as a flicker on every click.
  function mcpSelectServer(key) {
    if (mcpSelected === key) return;
    if (mcpHasPendingEdits()) {
      confirmAction({
        title: "Unsaved Changes",
        message: "You have unsaved changes here. Discard them?",
        confirmLabel: "Discard",
        isDanger: true,
        onConfirm: function () {
          mcpPending = {};
          mcpSelected = key;
          mcpRerender();
        }
      });
      return;
    }
    var previous = mcpSelected;
    mcpSelected = key;
    if (mcpSelectSync[previous]) mcpSelectSync[previous](false);
    if (mcpSelectSync[key]) mcpSelectSync[key](true);
    if (mcpDetailContainer) {
      mcpDetailSync = null;
      // Every control the outgoing detail pane registered is about to be
      // detached — drop them so mcpSyncDirty() doesn't keep invoking
      // callbacks for DOM that no longer exists.
      mcpDetailDirty = [];
      clear(mcpDetailContainer);
      mcpRenderDetail(mcpDetailContainer);
    } else {
      mcpRerender();
    }
  }

  // ----- Server list (master) -----

  function mcpRenderList() {
    var panel = el("div", { className: "panel mcp-list-panel" });

    var header = el("div", { className: "panel-header-row" },
      el("h2", null, "MCP servers"),
      el("div", { className: "mcp-list-actions" },
        el("button", {
          type: "button", className: "btn btn--neutral btn--icon", "aria-label": "Add server", title: "Add server",
          onclick: function () {
            if (mcpHasPendingEdits()) {
              confirmAction({ title: "Unsaved Changes", message: "Discard changes and add a server?", confirmLabel: "Discard", isDanger: true,
                onConfirm: function () { mcpPending = {}; mcpSelected = MCP_CREATE_KEY; mcpRerender(); } });
              return;
            }
            mcpSelected = MCP_CREATE_KEY;
            mcpRerender();
          }
        }, mcpPlusIcon()),
        refreshButton("Refresh servers and tools", function () {
          mcpData = null;
          mcpTools = null;
          mcpPending = {};
          mcpRerender();
        })
      )
    );
    panel.appendChild(header);

    var list = el("div", { className: "mcp-list", role: "listbox", "aria-label": "MCP servers" });

    var globalEnabled = mcpPendingToggleValue(MCP_DEFAULTS_KEY, mcpData.enabled);
    list.appendChild(mcpListItem({
      key: MCP_DEFAULTS_KEY,
      name: "Defaults",
      meta: globalEnabled ? "MCP enabled" : "MCP disabled",
      state: globalEnabled ? "on" : "off",
      isDefaults: true,
    }));
    list.appendChild(el("div", { className: "mcp-list-rule", role: "presentation" }));

    var servers = mcpData.servers || [];
    if (!servers.length) {
      list.appendChild(el("p", { className: "muted mcp-list-empty" },
        "No servers defined. Add one to connect tools from an HTTP endpoint or local subprocess."
      ));
    }

    servers.forEach(function (server) {
      var status = mcpServerRowStatus(server);
      list.appendChild(mcpListItem({
        key: server.name,
        name: server.name,
        transport: server.transport,
        meta: status.meta,
        state: status.state,
        overrides: Object.keys(server.overrides || {}).length,
        checkedAt: status.checkedAt,
        pinging: status.pinging,
        // Gate on the saved `enabled` flag, not the pending toggle: the live
        // MCPClientManager only knows about servers that are enabled on
        // disk, so a server that's disabled-but-pending-enabled (or was
        // never enabled) can't be resolved by GET /mcp/tools?server=<name>
        // yet, and would just 404.
        onPing: server.enabled ? function () { mcpPingServer(server.name); } : null,
        server: server,
      }));
    });

    panel.appendChild(list);
    return panel;
  }

  function mcpListItem(opts) {
    var isSelected = mcpSelected === opts.key;
    var dot = el("span", {
      className: "mcp-dot mcp-dot--" + opts.state,
      "aria-hidden": "true",
    });

    var lines = [el("span", { className: "mcp-list-name" }, opts.name)];
    var metaTextSpan = el("span", null, opts.meta);
    var metaParts = [];
    if (opts.transport) {
      metaParts.push(el("span", { className: "mcp-transport" }, opts.transport));
    }
    metaParts.push(metaTextSpan);
    // Always create the checked-at span, even with no timestamp yet, so a
    // ping completing later can reveal it via setTs() rather than needing
    // to splice a new node into an already-rendered meta line.
    var checkedAtCtl = mcpCheckedAtSpan(opts.checkedAt || null);
    metaParts.push(checkedAtCtl.node);
    if (opts.overrides) {
      metaParts.push(el("span", { className: "mcp-override-count" },
        opts.overrides + (opts.overrides === 1 ? " override" : " overrides")
      ));
    }
    lines.push(el("span", { className: "mcp-list-meta" }, metaParts));

    var item = el("button", {
      type: "button",
      role: "option",
      "aria-selected": String(isSelected),
      className: "mcp-list-item"
        + (isSelected ? " is-selected" : "")
        + (opts.isDefaults ? " is-defaults" : ""),
    }, dot, el("span", { className: "mcp-list-copy" }, lines));

    item.addEventListener("click", function () {
      mcpSelectServer(opts.key);
    });

    // Repaint just this row's selected styling when another row is picked —
    // see mcpSelectServer.
    mcpSelectSync[opts.key] = function (selected) {
      item.classList.toggle("is-selected", selected);
      item.setAttribute("aria-selected", String(selected));
    };

    // The select button and the ping button must be siblings, not nested —
    // a <button> can't contain another interactive <button>.
    var row = el("div", { className: "mcp-list-row" }, item);
    var pingBtn = null;
    var pingIcon = null;
    if (opts.onPing) {
      pingIcon = mcpPingIcon(opts.pinging);
      pingBtn = el("button", {
        type: "button",
        className: "mcp-list-ping" + (opts.pinging ? " is-pinging" : ""),
        "aria-label": "Ping " + opts.name,
        title: "Ping " + opts.name,
      }, pingIcon);
      pingBtn.disabled = !!opts.pinging;
      pingBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        opts.onPing();
      });
      row.appendChild(pingBtn);
    }

    // Repaint just this row on a ping, in place — see mcpApplyPingState.
    if (opts.server) {
      mcpRowSync[opts.key] = function () {
        var status = mcpServerRowStatus(opts.server);
        dot.className = "mcp-dot mcp-dot--" + status.state;
        metaTextSpan.textContent = status.meta;
        checkedAtCtl.setTs(status.checkedAt);
        if (pingBtn) {
          pingBtn.disabled = !!status.pinging;
          pingBtn.classList.toggle("is-pinging", !!status.pinging);
        }
        if (pingIcon) pingIcon.classList.toggle("is-spinning", !!status.pinging);
      };
    }
    return row;
  }

  // ----- Detail -----

  function mcpRenderDetail(detail) {
    if (mcpSelected === MCP_CREATE_KEY) {
      mcpRenderCreateDetail(detail);
      return;
    }
    if (mcpSelected === MCP_DEFAULTS_KEY) {
      mcpRenderDefaultsDetail(detail);
      return;
    }
    var server = (mcpData.servers || []).filter(function (s) {
      return s.name === mcpSelected;
    })[0];
    if (!server) {
      mcpSelected = MCP_DEFAULTS_KEY;
      mcpRenderDefaultsDetail(detail);
      return;
    }
    mcpRenderServerDetail(detail, server);
  }

  function mcpRenderCreateDetail(detail) {
    var draft = { name: "", transport: "http", url: "", headers: {}, command: "", args: [], env: {} };
    var mapEditor = null;
    function render() {
      clear(detail);
      detail.appendChild(el("div", { className: "mcp-detail-head" },
        el("div", { className: "mcp-detail-title" }, el("h2", null, "Add MCP server"),
          el("p", { className: "muted" }, "New servers are enabled and checked for tools immediately."))
      ));
      var ledger = el("div", { className: "mcp-ledger" });
      var nameRow = mcpConnectionRow("Name", "Unique lowercase identifier", draft.name, function (next) { draft.name = next; },
        { maxLength: 64, autocomplete: "off" });
      ledger.appendChild(nameRow);
      var transport = createSelect({
        className: "mcp-text",
        ariaLabel: "Transport",
        options: [
          { value: "http", label: "Streamable HTTP" },
          { value: "stdio", label: "Subprocess (stdio)" },
        ],
        value: draft.transport
      });
      transport.addEventListener("change", function () { draft.transport = transport.value; render(); });
      ledger.appendChild(el("div", { className: "mcp-setting-row mcp-connection-row" },
        el("span", { className: "mcp-setting-copy" }, el("span", { className: "mcp-setting-label" }, "Transport"),
          el("span", { className: "mcp-setting-hint" }, "How ORBIT connects to this server")),
        el("span", { className: "mcp-setting-control" }, transport)
      ));
      if (draft.transport === "http") {
        ledger.appendChild(mcpConnectionRow("URL", "Streamable HTTP endpoint", draft.url, function (next) { draft.url = next; },
          { type: "url", maxLength: MCP_CONNECTION_URL_MAX_LENGTH, validate: mcpEndpointUrlError }));
        mapEditor = mcpKeyValueRows("Headers", "HTTP headers; declare ${VAR} values in .env or export them before use", draft.headers, function (next) { draft.headers = next; },
          { keyMaxLength: MCP_CONNECTION_HEADER_KEY_MAX_LENGTH, valueMaxLength: MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH, maxEntries: MCP_CONNECTION_HEADER_MAX_ENTRIES, keyPattern: /^[A-Za-z0-9_-]+$/ });
        ledger.appendChild(mapEditor);
      } else {
        ledger.appendChild(mcpConnectionRow("Command", "Executable launched for this server", draft.command, function (next) { draft.command = next; }, { maxLength: MCP_CONNECTION_COMMAND_MAX_LENGTH }));
        ledger.appendChild(mcpArgsTextEditor("Args", "One argument per line", draft.args, function (next) { draft.args = next; }, { argMaxLength: MCP_CONNECTION_ARG_MAX_LENGTH, maxCount: MCP_CONNECTION_ARGS_MAX_COUNT }));
        mapEditor = mcpKeyValueRows("Env", "Environment variables passed to the server process", draft.env, function (next) { draft.env = next; },
          { keyMaxLength: MCP_CONNECTION_ENV_KEY_MAX_LENGTH, valueMaxLength: MCP_CONNECTION_ENV_VALUE_MAX_LENGTH, maxEntries: MCP_CONNECTION_ENV_MAX_ENTRIES, keyPattern: /^[A-Za-z_][A-Za-z0-9_]*$/ });
        ledger.appendChild(mapEditor);
      }
      detail.appendChild(ledger);
      var createBtn = el("button", { type: "button", className: "btn btn--primary" }, "Create server");
      createBtn.addEventListener("click", function () {
        withButton(createBtn, async function () {
          if (!/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(draft.name)) {
            throw new Error("Name must be a 1–64 character lowercase slug.");
          }
          if (mapEditor && !mapEditor.commitPending()) {
            var pendingHeader = mapEditor.pendingKey();
            if (pendingHeader) {
              throw new Error(
                draft.transport === "http"
                  ? "Header names may contain only letters, numbers, hyphens, and underscores."
                  : "Environment variable names must start with a letter or underscore and contain only letters, numbers, and underscores."
              );
            }
          }
          var connection = draft.transport === "http"
            ? { url: draft.url, headers: draft.headers }
            : { command: draft.command, args: draft.args, env: draft.env };
          if (draft.transport === "http") {
            var error = mcpEndpointUrlError(draft.url);
            if (error) throw new Error(error);
          }
          var res = await api("POST", endpoints.mcpServers, { name: draft.name, transport: draft.transport, connection: connection });
          mcpSelected = draft.name;
          mcpData = null;
          mcpTools = null;
          showStatus(res.message || "Server created.");
          mcpRerender();
        });
      });
      detail.appendChild(el("div", { className: "mcp-save-row" },
        el("button", { type: "button", className: "btn btn--neutral", onclick: function () { mcpSelected = MCP_DEFAULTS_KEY; mcpRerender(); } }, "Cancel"),
        createBtn
      ));
    }
    render();
  }

  function mcpSaveRow(onSave) {
    var saveBtn = el("button", { type: "button", className: "btn btn--primary" }, "Save changes");
    saveBtn.disabled = !mcpHasPendingEdits();
    mcpDetailDirty.push(function () {
      saveBtn.disabled = !mcpHasPendingEdits();
    });
    saveBtn.addEventListener("click", function () {
      withButton(saveBtn, onSave);
    });
    var row = el("div", { className: "mcp-save-row" }, saveBtn);
    return row;
  }

  function mcpRenderDefaultsDetail(detail) {
    var head = el("div", { className: "mcp-detail-head" },
      el("div", { className: "mcp-detail-title" },
        el("h2", null, "Defaults"),
        el("p", { className: "muted" },
          "Every server inherits these values unless it sets its own."
        )
      ),
      mcpToggle({
        on: mcpPending.enabled != null ? mcpPending.enabled : mcpData.enabled,
        label: "MCP tool calling",
        onChange: function (next) {
          if (next === mcpData.enabled) delete mcpPending.enabled;
          else mcpPending.enabled = next;
          mcpSyncDirty();
        }
      })
    );
    detail.appendChild(head);

    if (!mcpData.enabled) {
      detail.appendChild(el("div", { className: "mcp-notice" },
        "MCP tool calling is off. No server is contacted and no tools reach the model."
      ));
    }

    detail.appendChild(el("h3", null, "Default settings"));
    var ledger = el("div", { className: "mcp-ledger" });
    (mcpData.settings || []).forEach(function (spec) {
      var saved = mcpData.defaults[spec.key];
      var row = mcpSettingRow(spec, {
        value: mcpPending[spec.key] != null ? mcpPending[spec.key] : saved,
        isDefaults: true,
        inheritedValue: saved,
        isOverridden: function () { return false; },
        currentValue: function () {
          return mcpPending[spec.key] != null ? mcpPending[spec.key] : saved;
        },
        onChange: function (next) {
          if (next === saved) delete mcpPending[spec.key];
          else mcpPending[spec.key] = next;
          mcpSyncDirty();
        }
      });
      mcpDetailDirty.push(row.sync);
      ledger.appendChild(row);
    });
    detail.appendChild(ledger);

    detail.appendChild(mcpSaveRow(async function () {
      var body = { settings: {} };
      Object.keys(mcpPending).forEach(function (key) {
        if (key === "enabled") body.enabled = mcpPending[key];
        else body.settings[key] = mcpPending[key];
      });
      var res = await api("PATCH", endpoints.mcpDefaults, body);
      mcpPending = {};
      mcpData = null;
      mcpTools = null;
      showStatus(res.message || "Defaults saved.");
      mcpRerender();
    }));
  }

  function mcpRenderServerDetail(detail, server) {
    var enabled = mcpPending.enabled != null ? mcpPending.enabled : server.enabled;

    var head = el("div", { className: "mcp-detail-head" },
      el("div", { className: "mcp-detail-title" },
        el("h2", { className: "mcp-server-name" }, server.name),
        el("p", { className: "muted" },
          MCP_TRANSPORT_LABELS[server.transport] || server.transport
        )
      ),
      el("div", { className: "mcp-detail-actions" },
        mcpToggle({
          on: enabled,
          label: "Server " + server.name,
          onChange: function (next) {
            if (next === server.enabled) delete mcpPending.enabled;
            else mcpPending.enabled = next;
            mcpSyncDirty();
          }
        }),
        el("button", {
          type: "button", className: "btn danger", onclick: function () {
            confirmAction({
              title: "Remove MCP Server",
              message: "Remove '" + server.name + "' and its available tools? This deletes its configuration immediately. Environment variables and the external server are not changed.",
              confirmLabel: "Remove server",
              loadingLabel: "Removing…",
              isDanger: true,
              onConfirm: async function () {
                var res = await api("DELETE", endpoints.mcpServers + "/" + encodeURIComponent(server.name));
                mcpPending = {};
                mcpSelected = MCP_DEFAULTS_KEY;
                mcpData = null;
                mcpTools = null;
                showStatus(res.message || "Server removed.");
                mcpRerender();
              }
            });
          }
        }, "Remove server")
      )
    );
    detail.appendChild(head);

    if (server.connection) {
      detail.appendChild(el("h3", null, "Connection"));
      var connLedger = el("div", { className: "mcp-ledger" });

      if (server.transport === "stdio") {
        var commandRow = mcpConnectionRow(
          "Command",
          "Executable launched for this server",
          Object.prototype.hasOwnProperty.call(mcpPending, "connection.command")
            ? mcpPending["connection.command"] : server.connection.command,
          function (next) {
            if (next === server.connection.command) delete mcpPending["connection.command"];
            else mcpPending["connection.command"] = next;
            mcpSyncDirty();
          },
          { maxLength: MCP_CONNECTION_COMMAND_MAX_LENGTH }
        );
        connLedger.appendChild(commandRow);
        mcpDetailDirty.push(function () {
          commandRow.sync(Object.prototype.hasOwnProperty.call(mcpPending, "connection.command"));
        });

        var argsRow = mcpArgsTextEditor(
          "Args",
          "One argument per line",
          Object.prototype.hasOwnProperty.call(mcpPending, "connection.args")
            ? mcpPending["connection.args"] : server.connection.args,
          function (next) { mcpPending["connection.args"] = next; mcpSyncDirty(); },
          {
            argMaxLength: MCP_CONNECTION_ARG_MAX_LENGTH,
            maxCount: MCP_CONNECTION_ARGS_MAX_COUNT,
          }
        );
        connLedger.appendChild(argsRow);

        var envRow = mcpKeyValueRows(
          "Env",
          "Environment variables passed to the server process",
          Object.prototype.hasOwnProperty.call(mcpPending, "connection.env")
            ? mcpPending["connection.env"] : server.connection.env,
          function (next) { mcpPending["connection.env"] = next; mcpSyncDirty(); },
          {
            keyMaxLength: MCP_CONNECTION_ENV_KEY_MAX_LENGTH,
            valueMaxLength: MCP_CONNECTION_ENV_VALUE_MAX_LENGTH,
            maxEntries: MCP_CONNECTION_ENV_MAX_ENTRIES,
          }
        );
        connLedger.appendChild(envRow);
      } else {
        var urlRow = mcpConnectionRow(
          "URL",
          "Streamable HTTP endpoint",
          Object.prototype.hasOwnProperty.call(mcpPending, "connection.url")
            ? mcpPending["connection.url"] : server.connection.url,
          function (next) {
            if (next === server.connection.url) delete mcpPending["connection.url"];
            else mcpPending["connection.url"] = next;
            mcpSyncDirty();
          },
          { type: "url", maxLength: MCP_CONNECTION_URL_MAX_LENGTH, validate: mcpEndpointUrlError }
        );
        connLedger.appendChild(urlRow);
        mcpDetailDirty.push(function () {
          urlRow.sync(Object.prototype.hasOwnProperty.call(mcpPending, "connection.url"));
        });

        // headers is http-only: the stdio transport never reads it (see
        // MCPClientManager._open_session), so it isn't editable there.
        var headersRow = mcpKeyValueRows(
          "Headers",
          "HTTP headers; declare ${VAR} values in .env or export them before use",
          Object.prototype.hasOwnProperty.call(mcpPending, "connection.headers")
            ? mcpPending["connection.headers"] : server.connection.headers,
          function (next) { mcpPending["connection.headers"] = next; mcpSyncDirty(); },
          {
            keyMaxLength: MCP_CONNECTION_HEADER_KEY_MAX_LENGTH,
            valueMaxLength: MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH,
            maxEntries: MCP_CONNECTION_HEADER_MAX_ENTRIES,
          }
        );
        connLedger.appendChild(headersRow);
      }

      detail.appendChild(connLedger);
    } else if (server.endpoint) {
      detail.appendChild(el("p", { className: "mcp-endpoint" }, server.endpoint));
    }

    // ----- Tools -----
    // Pinging is scoped to this one server (GET /mcp/tools?server=<name>) so
    // checking it never re-dials, or disturbs the known status of, every
    // other configured server. The checked-at span, ping button and tools
    // list below are built once and repainted in place by mcpDetailSync, so
    // a ping only ever touches this section — never the whole detail pane.
    var toolsCheckedAtCtl = mcpCheckedAtSpan(mcpLastChecked[server.name] || null, "mcp-last-checked");
    var toolsPingIcon = mcpPingIcon(!!mcpPinging[server.name]);
    var toolsPingLabel = el("span", null, mcpPinging[server.name] ? "Pinging…" : "Ping server");
    var toolsPingBtn = el("button", {
      type: "button",
      className: "btn btn--neutral mcp-ping-btn",
    }, toolsPingIcon, toolsPingLabel);
    toolsPingBtn.addEventListener("click", function () { mcpPingServer(server.name); });

    // Gate on the saved `enabled` flag, not the pending toggle — see the
    // matching comment in mcpRenderList. A newly-enabled-but-unsaved server
    // isn't in the live manager yet, so pinging it would just 404.
    function syncToolsHeader() {
      var pinging = !!mcpPinging[server.name];
      var canPing = server.enabled;
      toolsCheckedAtCtl.setTs(mcpLastChecked[server.name] || null);
      toolsPingIcon.classList.toggle("is-spinning", pinging);
      toolsPingLabel.textContent = pinging ? "Pinging…" : "Ping server";
      toolsPingBtn.disabled = pinging || !canPing;
      toolsPingBtn.title = canPing ? "" : "Save this server as enabled before pinging it.";
    }
    syncToolsHeader();

    var toolsHeader = el("div", { className: "panel-header-row mcp-tools-header" },
      el("h3", null, "Tools"),
      el("div", { className: "mcp-tools-header-actions" }, toolsCheckedAtCtl.node, toolsPingBtn)
    );
    detail.appendChild(toolsHeader);

    var toolsBody = el("div", { className: "mcp-tools-body" });
    function syncToolsBody() {
      clear(toolsBody);
      var stillEnabled = mcpPending.enabled != null ? mcpPending.enabled : server.enabled;
      toolsBody.appendChild(mcpRenderTools(server, stillEnabled));
    }
    syncToolsBody();
    detail.appendChild(toolsBody);

    // ----- Playbooks (read-only) -----
    // Tool skills (docs/roadmap/mcp-tool-skills.md, "Tool Skills" tab) are
    // bound to namespaced tool names via an mcp_tools glob, independently of
    // this server's own definition. This is a read-only cross-reference so
    // an author can see, from the server side, which playbooks already cover
    // its tools — editing happens on the Tool Skills tab, not here.
    var playbooksBody = el("div", { className: "mcp-tools-body" });
    detail.appendChild(el("h3", null, "Playbooks"));
    detail.appendChild(playbooksBody);
    syncPlaybooks(server, playbooksBody);

    mcpDetailSync = {
      name: server.name,
      sync: function () { syncToolsHeader(); syncToolsBody(); syncPlaybooks(server, playbooksBody); },
    };

    // ----- Settings ledger -----
    // Name the override count up front, so the accent bar on individual rows
    // is explained on arrival rather than only by the provenance text sitting
    // at the far right of each row.
    var specs = mcpData.settings || [];
    var summary = el("span", { className: "mcp-settings-summary" });
    function syncSummary() {
      var n = specs.filter(function (spec) {
        return Object.prototype.hasOwnProperty.call(mcpPending, spec.key)
          ? mcpPending[spec.key] !== null
          : Object.prototype.hasOwnProperty.call(server.overrides, spec.key);
      }).length;
      summary.classList.toggle("has-overrides", n > 0);
      summary.textContent = n
        ? n + " of " + specs.length + (n === 1 ? " overrides" : " override") + " the defaults"
        : "All inherited from the defaults";
    }
    syncSummary();
    mcpDetailDirty.push(syncSummary);

    // A first-time visitor has no way to know the left-edge accent means
    // "overridden" — the row's own title only surfaces on hover. Spell it
    // out once here instead of repeating an "override" label on every row.
    var overrideLegend = el("span", {
      className: "mcp-override-legend",
      tabIndex: "0",
      "aria-label": "Blue marks a setting that overrides the default",
      title: "Blue marks a setting that overrides the default",
    }, el("span", { className: "mcp-override-legend-swatch", "aria-hidden": "true" }), "= overrides default");

    detail.appendChild(el("div", { className: "panel-header-row mcp-settings-header" },
      el("h3", null, "Settings"),
      el("div", { className: "mcp-settings-header-meta" }, overrideLegend, summary)
    ));

    var ledger = el("div", { className: "mcp-ledger" });
    (mcpData.settings || []).forEach(function (spec) {
      var hasOverride = Object.prototype.hasOwnProperty.call(server.overrides, spec.key);
      var inherited = mcpData.defaults[spec.key];

      // A pending null means "revert to inherited", so provenance follows the
      // pending edit rather than what is currently on disk.
      function isOverridden() {
        return Object.prototype.hasOwnProperty.call(mcpPending, spec.key)
          ? mcpPending[spec.key] !== null
          : hasOverride;
      }
      function currentValue() {
        if (!Object.prototype.hasOwnProperty.call(mcpPending, spec.key)) {
          return server.effective[spec.key];
        }
        return mcpPending[spec.key] === null ? inherited : mcpPending[spec.key];
      }

      var row = mcpSettingRow(spec, {
        value: currentValue(),
        inheritedValue: inherited,
        isOverridden: isOverridden,
        currentValue: currentValue,
        onChange: function (next) {
          // Only a value that differs from what is on disk is worth saving:
          // typing a changed number back to its original clears the edit and
          // disables Save again.
          var saved = hasOverride ? server.overrides[spec.key] : inherited;
          if (next === saved) delete mcpPending[spec.key];
          else mcpPending[spec.key] = next;
          mcpSyncDirty();
        },
        onRevert: function () {
          // Deleting a stored override is itself a change; dropping a pending
          // one merely restores what is already saved.
          if (hasOverride) mcpPending[spec.key] = null;
          else delete mcpPending[spec.key];
        }
      });
      mcpDetailDirty.push(row.sync);
      ledger.appendChild(row);
    });
    detail.appendChild(ledger);

    detail.appendChild(mcpSaveRow(async function () {
      var body = { settings: {}, connection: {} };
      var CONNECTION_FIELDS = ["url", "command", "args", "env", "headers"];
      Object.keys(mcpPending).forEach(function (key) {
        if (key === "enabled") { body.enabled = mcpPending[key]; return; }
        var connField = CONNECTION_FIELDS.find(function (f) { return key === "connection." + f; });
        if (connField) { body.connection[connField] = mcpPending[key]; return; }
        body.settings[key] = mcpPending[key];
      });
      if (body.connection.url != null) {
        var urlError = mcpEndpointUrlError(body.connection.url);
        if (urlError) { showError(urlError); return; }
      }
      if (!Object.keys(body.connection).length) delete body.connection;
      var res = await api(
        "PATCH",
        endpoints.mcpServers + "/" + encodeURIComponent(server.name),
        body
      );
      mcpPending = {};
      mcpData = null;
      mcpTools = null;
      showStatus(res.message || "Saved.");
      mcpRerender();
    }));
  }

  function mcpUnreachableNotice(server) {
    return el("div", { className: "mcp-unreachable" },
      el("strong", null, "Could not reach this server"),
      el("p", null,
        server.transport === "stdio"
          ? "Check the command runs and is on PATH. Startup logs record the underlying error."
          : "Check the URL is reachable and required headers are set. Startup logs record the underlying error."
      )
    );
  }

  var mcpSkillsCache = null; // fetched lazily, once per tab session
  function mcpSimpleGlobMatch(name, pattern) {
    // "*" only — enough for the mcp_tools convention (business-sample__*,
    // github__search_issues); not a full fnmatch implementation.
    var escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
    return new RegExp("^" + escaped + "$").test(name);
  }

  function syncPlaybooks(server, container) {
    clear(container);
    var discovery = (mcpTools && mcpTools.servers) ? mcpTools.servers[server.name] : null;
    if (!discovery || !discovery.reachable || !discovery.tools || !discovery.tools.length) {
      container.appendChild(el("p", { className: "muted mcp-tools-empty" },
        "Ping this server to see which tool-skill playbooks are bound to its tools."
      ));
      return;
    }
    var toolNames = discovery.tools.map(function (t) { return server.name + "__" + t.name; });

    var render = function (skills) {
      clear(container);
      var matches = (skills || []).filter(function (s) {
        return s.enabled && (s.mcp_tools || []).some(function (pattern) {
          return toolNames.some(function (n) { return mcpSimpleGlobMatch(n, pattern); });
        });
      });
      if (!matches.length) {
        container.appendChild(el("p", { className: "muted mcp-tools-empty" },
          "No database-authored tool-skill playbooks are bound to this server's tools yet. " +
          "File-authored config/skills playbooks may still be active at runtime; author a database playbook on the Tool Skills tab to list it here."
        ));
        return;
      }
      var list = el("div", { className: "mcp-tools" });
      matches.forEach(function (s) {
        list.appendChild(el("div", { className: "mcp-tool" },
          el("p", { className: "mcp-tool-name" }, s.name),
          el("p", { className: "mcp-tool-desc" }, s.description)
        ));
      });
      container.appendChild(list);
    };

    if (mcpSkillsCache) {
      render(mcpSkillsCache);
      return;
    }
    container.appendChild(el("p", { className: "muted mcp-tools-empty" }, "Loading playbooks…"));
    api("GET", endpoints.skills).then(function (skills) {
      mcpSkillsCache = skills || [];
      render(mcpSkillsCache);
    }).catch(function () {
      container.appendChild(el("p", { className: "muted mcp-tools-empty" }, "Failed to load tool-skill playbooks."));
    });
  }

  function mcpRenderTools(server, enabled) {
    if (!enabled) {
      return el("p", { className: "muted mcp-tools-empty" },
        "This server is disabled, so none of its tools reach the model."
      );
    }
    if (mcpPinging[server.name]) {
      return el("p", { className: "muted mcp-tools-empty" }, "Pinging " + server.name + "…");
    }
    if (!mcpTools) {
      return el("p", { className: "muted mcp-tools-empty" },
        "Select Ping server to dial this server and list what it exposes."
      );
    }
    if (!mcpTools.available) {
      return el("p", { className: "muted mcp-tools-empty" }, mcpTools.reason);
    }
    var discovery = (mcpTools.servers || {})[server.name];
    if (!discovery) {
      // No ping this session, but the backend's startup warm-up (or a
      // previous admin session) may already know whether this server is
      // reachable — surface that instead of a blanket "not checked" when
      // it's available. The tool list itself still needs an actual ping.
      if (server.status) {
        if (!server.status.reachable) return mcpUnreachableNotice(server);
        return el("p", { className: "muted mcp-tools-empty" },
          "Reachable — " + server.status.tool_count
            + (server.status.tool_count === 1 ? " tool" : " tools")
            + " available. Select Ping server to list them."
        );
      }
      return el("p", { className: "muted mcp-tools-empty" },
        "This server hasn't been pinged yet. Select Ping server to dial it and list what it exposes."
      );
    }
    if (!discovery.reachable) return mcpUnreachableNotice(server);
    if (!discovery.tools.length) {
      return el("p", { className: "muted mcp-tools-empty" },
        "Connected, but this server exposes no tools."
      );
    }

    var list = el("div", { className: "mcp-tools" });
    discovery.tools.forEach(function (tool) {
      var entry = el("div", { className: "mcp-tool" },
        el("p", { className: "mcp-tool-name" }, tool.name)
      );
      if (tool.description) {
        entry.appendChild(el("p", { className: "mcp-tool-desc" }, tool.description));
      }
      if (tool.parameters.length) {
        var params = el("p", { className: "mcp-tool-params" });
        tool.parameters.forEach(function (p, i) {
          if (i) params.appendChild(document.createTextNode("  "));
          params.appendChild(el("span", {
            className: "mcp-param" + (p.required ? " is-required" : ""),
            title: p.description || "",
          }, p.name + (p.required ? "*" : "") + " " + p.type));
        });
        entry.appendChild(params);
      }
      list.appendChild(entry);
    });
    return list;
  }

  // ----- Controls -----

  // Owns its own on/off state so a click never needs a re-render, which would
  // rebuild the button and drop keyboard focus mid-interaction.
  function mcpToggle(opts) {
    var on = !!opts.on;
    var track = el("button", {
      type: "button",
      className: "adapter-toggle" + (on ? " on" : ""),
      "aria-pressed": String(on),
      "aria-label": (on ? "Disable " : "Enable ") + opts.label,
    }, el("span", { className: "adapter-toggle-knob" }));

    track.setState = function (next) {
      on = !!next;
      track.classList.toggle("on", on);
      track.setAttribute("aria-pressed", String(on));
      track.setAttribute("aria-label", (on ? "Disable " : "Enable ") + opts.label);
    };
    track.addEventListener("click", function () {
      track.setState(!on);
      opts.onChange(on);
    });
    return track;
  }

  // A plain editable text field for a server's scalar connection details.
  // Unlike mcpSettingRow there is no mcp_clients-level default to
  // fall back to or revert against — the row just tracks "changed vs. what's
  // on disk", reported by the caller via row.sync(isChanged).
  function mcpConnectionRow(label, hint, value, onChange, opts) {
    opts = opts || {};
    var control = el("input", {
      type: opts.type || "text",
      className: "mcp-text",
      value: value || "",
      "aria-label": label,
    });
    if (opts.maxLength) control.maxLength = opts.maxLength;
    if (opts.validate) {
      function validate() {
        control.setCustomValidity(opts.validate(control.value) || "");
      }
      control.addEventListener("input", validate);
      validate();
    }
    control.addEventListener("input", function () {
      onChange(control.value);
    });

    var provenance = el("span", { className: "mcp-provenance" });
    var row = el("div", { className: "mcp-setting-row mcp-connection-row" },
      el("span", { className: "mcp-setting-copy" },
        el("span", { className: "mcp-setting-label" }, label),
        el("span", { className: "mcp-setting-hint" }, hint)
      ),
      el("span", { className: "mcp-setting-control" }, control),
      provenance
    );

    row.sync = function (isChanged) {
      row.classList.toggle("is-override", isChanged);
      clear(provenance);
      provenance.classList.toggle("is-override", isChanged);
      if (isChanged) provenance.appendChild(document.createTextNode("changed"));
    };
    row.sync(false);
    return row;
  }

  // Inline SVGs (not text glyphs) so the plus/minus render at a crisp,
  // consistent weight across platforms instead of relying on font glyph
  // metrics for "+"/"-".
  function mcpIconSvg(pathD) {
    var wrapper = el("span", { className: "mcp-kv-icon", "aria-hidden": "true" });
    wrapper.innerHTML =
      '<svg viewBox="0 0 16 16" width="16" height="16" fill="none">' +
      '<path d="' + pathD + '" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>' +
      "</svg>";
    return wrapper;
  }

  function mcpPlusIcon() {
    return mcpIconSvg("M8 3v10M3 8h10");
  }

  function mcpMinusIcon() {
    return mcpIconSvg("M3 8h10");
  }

  // Circular-arrow "retry" glyph, reused for both the per-row ping button
  // and the detail pane's ping button. Spins in place while a ping for its
  // server is in flight.
  function mcpPingIcon(spinning) {
    var icon = mcpIconSvg("M13 8a5 5 0 1 1-1.6-3.6M13 3.2V6.6H9.6");
    icon.classList.add("mcp-ping-icon");
    icon.classList.toggle("is-spinning", !!spinning);
    return icon;
  }

  // A small "current/max" counter for a value field, since a single-line
  // input scrolls rather than wraps — there's no other visible sign of how
  // close a long value is to its cap.
  function mcpKvCounter(length, max) {
    var counter = el("span", { className: "mcp-kv-counter", "aria-hidden": "true" });
    mcpKvCounterUpdate(counter, length, max);
    return counter;
  }

  function mcpKvCounterUpdate(counter, length, max) {
    counter.textContent = length + " / " + max;
    counter.classList.toggle("is-near-limit", length >= max);
  }

  // A key/value list editor for a server's env or headers map. Unlike
  // mcpConnectionRow's single scalar, onChange always reports the full
  // resulting map — the save handler sends it as a complete replacement,
  // not a diff, matching the backend's full-replace contract.
  function mcpKeyValueRows(label, hint, valueMap, onChange, opts) {
    opts = opts || {};
    var keyMaxLength = opts.keyMaxLength || MCP_CONNECTION_ENV_KEY_MAX_LENGTH;
    var valueMaxLength = opts.valueMaxLength || MCP_CONNECTION_ENV_VALUE_MAX_LENGTH;
    var maxEntries = opts.maxEntries || MCP_CONNECTION_ENV_MAX_ENTRIES;
    var keyPattern = opts.keyPattern || null;
    var current = Object.assign({}, valueMap || {});
    var pristineJson = JSON.stringify(current);
    var commitPending = function () { return false; };
    var rowsEl = el("div", { className: "mcp-kv-rows" });
    var provenance = el("span", { className: "mcp-provenance" });

    function renderRows() {
      clear(rowsEl);
      Object.keys(current).forEach(function (mapKey) {
        var keyInput = el("input", {
          type: "text", className: "mcp-text mcp-kv-key", maxLength: keyMaxLength,
          value: mapKey, "aria-label": label + " key",
        });
        var valueInput = el("input", {
          type: "text", className: "mcp-text mcp-kv-value", maxLength: valueMaxLength,
          value: current[mapKey], "aria-label": label + " value for " + mapKey,
        });
        // A single-line input scrolls instead of wrapping, so there's no
        // visual sign a long value is anywhere near its cap — surface the
        // count explicitly rather than relying on the field "feeling" full.
        var valueCounter = mcpKvCounter(valueInput.value.length, valueMaxLength);
        valueInput.addEventListener("input", function () {
          // Belt-and-suspenders: the `maxlength` attribute above already
          // stops typing/pasting past the cap in every modern browser, but
          // truncate here too rather than trust that alone — this is the
          // same value that gets sent to the server-side cap, so a paste
          // that somehow lands past it should never reach onChange.
          if (valueInput.value.length > valueMaxLength) {
            var pos = valueInput.selectionStart;
            valueInput.value = valueInput.value.slice(0, valueMaxLength);
            valueInput.selectionStart = valueInput.selectionEnd = Math.min(pos, valueMaxLength);
          }
          mcpKvCounterUpdate(valueCounter, valueInput.value.length, valueMaxLength);
          current[mapKey] = valueInput.value;
          onChange(Object.assign({}, current));
          sync();
        });
        var valueCell = el("span", { className: "mcp-kv-value-cell" }, valueInput, valueCounter);
        var removeBtn = el("button", {
          type: "button", className: "mcp-kv-btn mcp-kv-btn--remove",
          "aria-label": "Remove " + (mapKey || "entry"),
          onclick: function () {
            delete current[mapKey];
            onChange(Object.assign({}, current));
            renderRows();
            sync();
          }
        }, mcpMinusIcon());
        keyInput.addEventListener("change", function () {
          var nextKey = keyInput.value.trim().slice(0, keyMaxLength);
          if (!nextKey || nextKey === mapKey) { keyInput.value = mapKey; return; }
          if (Object.prototype.hasOwnProperty.call(current, nextKey)) {
            keyInput.value = mapKey;
            return;
          }
          var value = current[mapKey];
          delete current[mapKey];
          current[nextKey] = value;
          onChange(Object.assign({}, current));
          renderRows();
          sync();
        });
        var keyCell = el("span", { className: "mcp-kv-key-cell" }, keyInput,
          el("span", { className: "mcp-kv-counter-spacer", "aria-hidden": "true" }));
        var removeBtnCell = el("span", { className: "mcp-kv-btn-cell" }, removeBtn,
          el("span", { className: "mcp-kv-counter-spacer", "aria-hidden": "true" }));
        rowsEl.appendChild(el("div", { className: "mcp-kv-row" }, keyCell, valueCell, removeBtnCell));
      });

      var atLimit = Object.keys(current).length >= maxEntries;
      var newKeyInput = el("input", {
        type: "text", className: "mcp-text mcp-kv-key", placeholder: "key",
        maxLength: keyMaxLength,
      });
      var newValueInput = el("input", {
        type: "text", className: "mcp-text mcp-kv-value", placeholder: "value",
        maxLength: valueMaxLength,
      });
      var addBtn = el("button", {
        type: "button", className: "mcp-kv-btn mcp-kv-btn--add",
        "aria-label": "Add " + label.toLowerCase() + " entry",
        onclick: function () {
          commitPending();
        }
      }, mcpPlusIcon());
      commitPending = function () {
          var newKey = newKeyInput.value.trim().slice(0, keyMaxLength);
          if (!newKey || Object.prototype.hasOwnProperty.call(current, newKey)) return false;
          if (keyPattern && !keyPattern.test(newKey)) return false;
          if (Object.keys(current).length >= maxEntries) return false;
          current[newKey] = newValueInput.value.slice(0, valueMaxLength);
          onChange(Object.assign({}, current));
          renderRows();
          sync();
          return true;
        };
      var newValueCounter = mcpKvCounter(0, valueMaxLength);
      newKeyInput.addEventListener("input", function () {
        if (newKeyInput.value.length > keyMaxLength) newKeyInput.value = newKeyInput.value.slice(0, keyMaxLength);
      });
      newValueInput.addEventListener("input", function () {
        if (newValueInput.value.length > valueMaxLength) newValueInput.value = newValueInput.value.slice(0, valueMaxLength);
        mcpKvCounterUpdate(newValueCounter, newValueInput.value.length, valueMaxLength);
      });
      newKeyInput.disabled = atLimit;
      newValueInput.disabled = atLimit;
      addBtn.disabled = atLimit;
      var newValueCell = el("span", { className: "mcp-kv-value-cell" }, newValueInput, newValueCounter);
      var newKeyCell = el("span", { className: "mcp-kv-key-cell" }, newKeyInput,
        el("span", { className: "mcp-kv-counter-spacer", "aria-hidden": "true" }));
      var addBtnCell = el("span", { className: "mcp-kv-btn-cell" }, addBtn,
        el("span", { className: "mcp-kv-counter-spacer", "aria-hidden": "true" }));
      rowsEl.appendChild(el("div", { className: "mcp-kv-row mcp-kv-add-row" }, newKeyCell, newValueCell, addBtnCell));
      if (atLimit) {
        rowsEl.appendChild(el("p", { className: "mcp-kv-limit-hint" },
          "Limit of " + maxEntries + " entries reached."));
      }
    }

    function sync() {
      var isChanged = JSON.stringify(current) !== pristineJson;
      row.classList.toggle("is-override", isChanged);
      clear(provenance);
      provenance.classList.toggle("is-override", isChanged);
      if (isChanged) provenance.appendChild(document.createTextNode("changed"));
    }

    renderRows();
    var row = el("div", { className: "mcp-setting-row mcp-connection-row mcp-kv-editor" },
      el("span", { className: "mcp-setting-copy" },
        el("span", { className: "mcp-setting-label" }, label),
        el("span", { className: "mcp-setting-hint" }, hint)
      ),
      el("span", { className: "mcp-setting-control" }, rowsEl),
      provenance
    );
    row.sync = sync;
    row.commitPending = function () { return commitPending(); };
    row.pendingKey = function () {
      var input = rowsEl.querySelector(".mcp-kv-add-row .mcp-kv-key");
      return input ? input.value.trim() : "";
    };
    sync();
    return row;
  }

  // A one-arg-per-line textarea for a stdio server's args list. Bounded to
  // the same per-arg length and entry count as the backend's `args`
  // validation (_MCP_CONNECTION_ARG_MAX_LENGTH/_MCP_CONNECTION_ARGS_MAX_COUNT
  // in admin_routes.py) — enforced by trimming on input rather than a
  // hard textarea maxlength, since a single maxlength can't distinguish
  // "one huge line" from "many short lines".
  function mcpArgsTextEditor(label, hint, argsList, onChange, opts) {
    opts = opts || {};
    var argMaxLength = opts.argMaxLength || MCP_CONNECTION_ARG_MAX_LENGTH;
    var maxCount = opts.maxCount || MCP_CONNECTION_ARGS_MAX_COUNT;
    var pristineText = (argsList || []).join("\n");
    var control = el("textarea", {
      className: "mcp-text mcp-args-textarea", rows: 4, "aria-label": label,
    });
    control.value = pristineText;
    control.addEventListener("input", function () {
      var lines = control.value.split("\n");
      if (lines.length > maxCount) lines = lines.slice(0, maxCount);
      lines = lines.map(function (line) {
        return line.length > argMaxLength ? line.slice(0, argMaxLength) : line;
      });
      var truncatedText = lines.join("\n");
      if (truncatedText !== control.value) {
        var cursor = control.selectionStart;
        control.value = truncatedText;
        control.selectionStart = control.selectionEnd = Math.min(cursor, truncatedText.length);
      }
      var next = truncatedText.split("\n");
      while (next.length && next[0].trim() === "") next.shift();
      while (next.length && next[next.length - 1].trim() === "") next.pop();
      onChange(next);
      row.sync(control.value !== pristineText);
    });

    var provenance = el("span", { className: "mcp-provenance" });
    var row = el("div", { className: "mcp-setting-row mcp-connection-row" },
      el("span", { className: "mcp-setting-copy" },
        el("span", { className: "mcp-setting-label" }, label),
        el("span", { className: "mcp-setting-hint" }, hint)
      ),
      el("span", { className: "mcp-setting-control" }, control),
      provenance
    );
    row.sync = function (isChanged) {
      row.classList.toggle("is-override", isChanged);
      clear(provenance);
      provenance.classList.toggle("is-override", isChanged);
      if (isChanged) provenance.appendChild(document.createTextNode("changed"));
    };
    row.sync(false);
    return row;
  }

  function mcpSettingRow(spec, opts) {
    var meta = mcpSettingMeta(spec.key);
    var control;

    if (spec.type === "boolean") {
      control = mcpToggle({
        on: !!opts.value,
        label: meta.label,
        onChange: opts.onChange,
      });
    } else {
      // Bounds come from the server so the input and the endpoint's own
      // validation cannot disagree.
      var lo = typeof spec.min === "number" ? spec.min : 0;
      var hi = typeof spec.max === "number" && spec.max > 0 ? spec.max : 2147483647;
      var maxDigits = String(hi).length;

      control = el("input", {
        type: "text",
        inputmode: "numeric",
        maxlength: String(maxDigits),
        size: String(maxDigits),
        value: String(opts.value),
        className: "mcp-number",
        "aria-label": meta.label,
        title: "Between " + lo + " and " + hi,
      });

      // type="text" + inputmode rather than type="number": number inputs still
      // accept "e", "+" and ".", ignore maxlength entirely, and report an empty
      // string for junk input, which makes the digit cap impossible to enforce.
      control.addEventListener("input", function () {
        var digits = control.value.replace(/\D+/g, "").slice(0, maxDigits);
        if (digits !== control.value) {
          var caret = control.selectionStart - (control.value.length - digits.length);
          control.value = digits;
          try { control.setSelectionRange(caret, caret); } catch (e) { /* detached */ }
        }
      });

      // Report on every keystroke so Save enables as soon as the value
      // genuinely differs, and disables again the moment it is typed back.
      // Only digits can be present by this point, so parsing is safe.
      control.addEventListener("input", function () {
        if (control.value === "") return; // mid-edit; wait for commit
        opts.onChange(parseInt(control.value, 10));
      });

      // Clamping is deferred to commit: doing it per keystroke would rewrite
      // "6" to the minimum before the user can finish typing "60".
      var commit = function () {
        var next = parseInt(control.value, 10);
        if (isNaN(next)) {
          // Emptied and left. Restore what the row currently holds; the
          // pending state already matches, so nothing needs committing.
          control.value = String(opts.currentValue());
          return;
        }
        var clamped = Math.min(hi, Math.max(lo, next));
        if (clamped !== next) {
          control.value = String(clamped);
          showError(meta.label + " must be between " + lo + " and " + hi + ".");
        }
        // Only commit a value that actually differs from the row's current
        // state. After "Use default" the pending edit is an explicit null,
        // meaning "delete this override"; blurring the field would otherwise
        // re-commit the displayed number as a plain value and resurrect the
        // override the user just cleared.
        if (clamped !== opts.currentValue()) opts.onChange(clamped);
      };
      control.addEventListener("change", commit);
      control.addEventListener("blur", commit);
    }

    var provenance = el("span", { className: "mcp-provenance" });
    var row = el("div", { className: "mcp-setting-row" },
      el("span", { className: "mcp-setting-copy" },
        el("span", { className: "mcp-setting-label" }, meta.label),
        el("span", { className: "mcp-setting-hint" }, meta.hint)
      ),
      el("span", { className: "mcp-setting-control" }, control),
      provenance
    );

    // Recomputes only the accent and the provenance cell. It deliberately does
    // not touch the control's value, which would fight the user mid-keystroke;
    // the revert path sets that explicitly.
    row.sync = function () {
      var isOverride = !opts.isDefaults && opts.isOverridden();
      row.classList.toggle("is-override", isOverride);
      // The accent bar already says "overridden" at a glance; the row's own
      // title makes that legible on hover/focus without a text label eating
      // space next to "Use default" on every overridden row.
      row.title = isOverride ? "Blue marks a setting that overrides the default" : "";
      clear(provenance);
      provenance.classList.toggle("is-override", isOverride);

      if (opts.isDefaults) {
        provenance.appendChild(document.createTextNode("default"));
        return;
      }
      if (isOverride) {
        var revert = el("button", {
          type: "button",
          className: "mcp-revert",
          title: "Use the default of " + mcpFormatValue(spec.key, opts.inheritedValue),
        }, "Use default");
        revert.addEventListener("click", function () {
          opts.onRevert();
          if (control.setState) control.setState(opts.inheritedValue);
          else control.value = String(opts.inheritedValue);
          mcpSyncDirty();
          control.focus(); // the button that had focus is about to be removed
        });
        provenance.appendChild(revert);
        return;
      }
      provenance.appendChild(
        document.createTextNode("inherited " + mcpFormatValue(spec.key, opts.inheritedValue))
      );
    };

    row.sync();
    return row;
  }

  function hasPendingEdits() {
    return mcpHasPendingEdits();
  }

  function clearPendingEdits() {
    mcpPending = {};
  }

  function dispose() {
    if (mcpCheckedAtTimer) {
      clearInterval(mcpCheckedAtTimer);
      mcpCheckedAtTimer = null;
    }
    mcpCheckedAtNodes = [];
  }

  function invalidatePlaybooksCache() { mcpSkillsCache = null; }

  return {
    render: renderMcp, dispose: dispose, hasPendingEdits: hasPendingEdits, clearPendingEdits: clearPendingEdits,
    invalidatePlaybooksCache: invalidatePlaybooksCache,
  };
}
