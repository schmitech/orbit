/* ============================================================
   ORBIT Admin Panel — Single-file vanilla JS client
   ============================================================ */
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let authToken = null;
  let currentUser = null;
  let activeTab = "overview";

  // Cached data
  let cachedAdapters = null;
  let cachedPrompts = null;

  // Selection state per tab
  let selectedUser = null;
  let selectedKey = null;
  let selectedPrompt = null;

  // ------------------------------------------------------------------
  // DOM helpers
  // ------------------------------------------------------------------
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "className") node.className = v;
        else if (k === "htmlFor") node.setAttribute("for", v);
        else if (k.startsWith("on") && typeof v === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (k === "dataset") {
          for (const [dk, dv] of Object.entries(v)) node.dataset[dk] = dv;
        } else {
          node.setAttribute(k, v);
        }
      }
    }
    for (const child of children) {
      if (child == null || child === false) continue;
      if (typeof child === "string" || typeof child === "number") {
        node.appendChild(document.createTextNode(String(child)));
      } else if (Array.isArray(child)) {
        child.forEach(function (c) { if (c) node.appendChild(c); });
      } else {
        node.appendChild(child);
      }
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  // ------------------------------------------------------------------
  // Status / Error messages
  // ------------------------------------------------------------------
  let _statusTimer = null;
  function showStatus(msg, container) {
    _clearMsg(container);
    var d = el("div", { className: "status", role: "status" }, msg);
    container.prepend(d);
    _statusTimer = setTimeout(function () { d.remove(); }, 4000);
  }

  function showError(msg, container) {
    _clearMsg(container);
    var d = el("div", { className: "error", role: "alert" }, msg);
    container.prepend(d);
    _statusTimer = setTimeout(function () { d.remove(); }, 6000);
  }

  function _clearMsg(container) {
    if (_statusTimer) clearTimeout(_statusTimer);
    container.querySelectorAll(".status, .error").forEach(function (n) { n.remove(); });
  }

  // ------------------------------------------------------------------
  // Confirm dialog
  // ------------------------------------------------------------------
  function confirmDialog(title, message, onConfirm, dangerLabel) {
    var backdrop = el("div", { className: "dialog-backdrop" });
    var cancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var confirmBtn = el("button", { className: dangerLabel ? "danger" : "", type: "button" }, dangerLabel || "Confirm");
    var dialog = el("div", { className: "confirm-dialog" },
      el("h2", null, title),
      el("p", null, message),
      el("div", { className: "dialog-actions" }, cancelBtn, confirmBtn)
    );
    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);
    confirmBtn.focus();

    function close() { backdrop.remove(); }
    cancelBtn.addEventListener("click", close);
    confirmBtn.addEventListener("click", function () { close(); onConfirm(); });
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) close(); });
    document.addEventListener("keydown", function handler(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", handler); }
    });
  }

  // ------------------------------------------------------------------
  // Skeleton loader
  // ------------------------------------------------------------------
  function skeleton() {
    return el("div", { className: "skeleton" },
      el("div", { className: "skeleton-line" }),
      el("div", { className: "skeleton-line" }),
      el("div", { className: "skeleton-line" })
    );
  }

  // ------------------------------------------------------------------
  // API helper
  // ------------------------------------------------------------------
  async function api(method, path, body) {
    var opts = {
      method: method,
      headers: { "Content-Type": "application/json" },
    };
    if (authToken) opts.headers["Authorization"] = "Bearer " + authToken;
    if (body !== undefined) opts.body = JSON.stringify(body);
    var resp = await fetch(path, opts);
    if (resp.status === 401) {
      authToken = null;
      currentUser = null;
      window.location.href = "/dashboard/login?next=/admin";
      throw new Error("Session expired");
    }
    var text = await resp.text();
    var data;
    try { data = JSON.parse(text); } catch (_) { data = text; }
    if (!resp.ok) {
      var msg = (data && data.detail) || (data && data.message) || text || resp.statusText;
      throw new Error(msg);
    }
    return data;
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------
  async function init() {
    try {
      var resp = await fetch("/admin/api/token");
      if (!resp.ok) {
        window.location.href = "/dashboard/login?next=/admin";
        return;
      }
      var data = await resp.json();
      authToken = data.token;
      currentUser = data.user;
      renderShell();
    } catch (err) {
      document.getElementById("app").textContent = "Failed to initialize: " + err.message;
    }
  }

  // ------------------------------------------------------------------
  // Shell: topbar + tabs + content area
  // ------------------------------------------------------------------
  var TABS = [
    { id: "overview", label: "Overview" },
    { id: "users", label: "Users" },
    { id: "keys", label: "API Keys" },
    { id: "prompts", label: "Prompts" },
    { id: "ops", label: "Ops" },
  ];

  function renderShell() {
    var app = document.getElementById("app");
    clear(app);

    // Topbar
    var logoutBtn = el("button", { type: "button" }, "Logout");
    logoutBtn.addEventListener("click", doLogout);
    var topbar = el("div", { className: "topbar" },
      el("div", null,
        el("h1", null, "ORBIT Admin Panel"),
        el("p", null, currentUser ? currentUser.username : "")
      ),
      el("div", { className: "topbar-actions" },
        el("span", null, currentUser ? currentUser.role : ""),
        logoutBtn
      )
    );

    // Tabs
    var tabBar = el("div", { className: "tabs" });
    TABS.forEach(function (t) {
      var btn = el("button", {
        type: "button",
        className: t.id === activeTab ? "active" : "",
        dataset: { tab: t.id },
      }, t.label);
      btn.addEventListener("click", function () { switchTab(t.id); });
      tabBar.appendChild(btn);
    });

    // Content
    var content = el("div", { id: "tab-content" });

    var shell = el("div", { className: "app-shell" }, topbar, tabBar, content);
    app.appendChild(shell);

    renderTab();
  }

  function switchTab(id) {
    activeTab = id;
    document.querySelectorAll(".tabs button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === id);
    });
    renderTab();
  }

  function renderTab() {
    var c = document.getElementById("tab-content");
    if (!c) return;
    clear(c);
    switch (activeTab) {
      case "overview": renderOverview(c); break;
      case "users": renderUsers(c); break;
      case "keys": renderKeys(c); break;
      case "prompts": renderPrompts(c); break;
      case "ops": renderOps(c); break;
    }
  }

  // ------------------------------------------------------------------
  // Logout
  // ------------------------------------------------------------------
  async function doLogout() {
    try {
      await fetch("/admin/logout", { method: "POST" });
    } catch (_) {}
    authToken = null;
    currentUser = null;
    window.location.href = "/dashboard/login?next=/admin";
  }

  // ==================================================================
  // TAB: Overview
  // ==================================================================
  async function renderOverview(container) {
    var grid = el("div", { className: "panel-grid" });
    var serverPanel = el("div", { className: "panel" }, el("h2", null, "Server Info"), skeleton());
    var healthPanel = el("div", { className: "panel" }, el("h2", null, "Health"), skeleton());
    grid.appendChild(serverPanel);
    grid.appendChild(healthPanel);

    var refreshBtn = el("button", { className: "secondary", type: "button" }, "Refresh Status");
    refreshBtn.addEventListener("click", function () { renderOverview(container); });
    container.appendChild(refreshBtn);
    container.appendChild(grid);

    // Fetch data in parallel
    try {
      var [info, health] = await Promise.all([
        api("GET", "/admin/info"),
        api("GET", "/health/").catch(function () { return { status: "unknown" }; }),
      ]);
      renderInfoCard(serverPanel, "Server Info", info);
      renderInfoCard(healthPanel, "Health", health);
    } catch (err) {
      showError("Failed to load overview: " + err.message, container);
    }
  }

  function renderInfoCard(panel, title, data) {
    clear(panel);
    panel.appendChild(el("h2", null, title));
    var grid = el("div", { className: "info-grid" });
    if (data && typeof data === "object") {
      for (var key of Object.keys(data)) {
        var val = data[key];
        var valStr = typeof val === "object" ? JSON.stringify(val) : String(val);
        var cls = "info-value";
        if (/running|healthy|ok/i.test(valStr)) cls += " status-ok";
        else if (/degraded|warn/i.test(valStr)) cls += " status-warn";
        grid.appendChild(
          el("div", { className: "info-row" },
            el("span", { className: "info-label" }, key),
            el("span", { className: cls }, valStr)
          )
        );
      }
    }
    panel.appendChild(grid);
  }

  // ==================================================================
  // TAB: Users
  // ==================================================================
  async function renderUsers(container) {
    selectedUser = null;
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    // Create user form
    left.appendChild(el("h2", null, "Users"));
    var usernameInput = el("input", { type: "text", placeholder: "Username", required: "true" });
    var passwordInput = el("input", { type: "password", placeholder: "Password", required: "true" });
    var roleSelect = el("select", null,
      el("option", { value: "user" }, "user"),
      el("option", { value: "admin" }, "admin")
    );
    var createBtn = el("button", { type: "button" }, "Create User");

    var form = el("div", { className: "inline-form" },
      el("label", null, "Username", usernameInput),
      el("label", null, "Password", passwordInput),
      el("label", null, "Role", roleSelect),
      createBtn
    );
    left.appendChild(form);

    var tableWrap = el("div", null, skeleton());
    left.appendChild(tableWrap);

    // Right panel — change own password + placeholder
    right.appendChild(el("h2", null, "My Account"));
    renderChangeMyPassword(right);
    right.appendChild(el("h3", null, "Selected User"));
    right.appendChild(el("p", { className: "muted" }, "Select a user from the list to manage"));

    createBtn.addEventListener("click", async function () {
      var u = usernameInput.value.trim();
      var p = passwordInput.value.trim();
      if (!u || !p) return;
      createBtn.disabled = true;
      try {
        await api("POST", "/auth/register", { username: u, password: p, role: roleSelect.value });
        usernameInput.value = "";
        passwordInput.value = "";
        showStatus("User created", left);
        loadUsers();
      } catch (err) {
        showError(err.message, left);
      } finally {
        createBtn.disabled = false;
      }
    });

    async function loadUsers() {
      try {
        var users = await api("GET", "/auth/users");
        renderUserTable(tableWrap, users, right);
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load users"));
      }
    }

    loadUsers();
  }

  function renderChangeMyPassword(panel) {
    var curPwInput = el("input", { type: "password", placeholder: "Current password" });
    var newPwInput = el("input", { type: "password", placeholder: "New password" });
    var confirmPwInput = el("input", { type: "password", placeholder: "Confirm new password" });
    var changeBtn = el("button", { type: "button" }, "Change Password");

    changeBtn.addEventListener("click", async function () {
      var cur = curPwInput.value;
      var nw = newPwInput.value;
      var conf = confirmPwInput.value;
      if (!cur || !nw) return;
      if (nw !== conf) { showError("Passwords do not match", panel); return; }
      changeBtn.disabled = true;
      try {
        await api("POST", "/auth/change-password", { current_password: cur, new_password: nw });
        curPwInput.value = "";
        newPwInput.value = "";
        confirmPwInput.value = "";
        showStatus("Password changed successfully", panel);
      } catch (err) {
        showError(err.message, panel);
      } finally {
        changeBtn.disabled = false;
      }
    });

    panel.appendChild(el("div", { className: "stack" },
      el("label", null, "Current Password", curPwInput),
      el("label", null, "New Password", newPwInput),
      el("label", null, "Confirm Password", confirmPwInput),
      changeBtn
    ));
  }

  function renderUserTable(wrap, users, rightPanel) {
    clear(wrap);
    if (!users || users.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F464}"),
        el("p", null, "No users found")
      ));
      return;
    }
    var table = el("table");
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Username"),
        el("th", null, "Role"),
        el("th", null, "Active")
      )
    );
    var tbody = el("tbody");
    users.forEach(function (u) {
      var tr = el("tr", {
        className: "selectable-row" + (selectedUser && selectedUser.id === u.id ? " selected-row" : ""),
        tabindex: "0",
      },
        el("td", { dataset: { label: "Username" } }, u.username),
        el("td", { dataset: { label: "Role" } }, u.role || ""),
        el("td", { dataset: { label: "Active" } },
          el("span", { className: u.active !== false ? "status-active" : "status-inactive" },
            u.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", function () {
        selectedUser = u;
        wrap.querySelectorAll("tr").forEach(function (r) { r.classList.remove("selected-row"); });
        tr.classList.add("selected-row");
        renderUserDetail(rightPanel, u, function () {
          selectedUser = null;
          renderTab();
        });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderUserDetail(panel, user, onRefresh) {
    clear(panel);
    panel.appendChild(el("h2", null, "Manage: " + escapeHtml(user.username)));

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "ID:"), " " + (user.id || "N/A")),
      el("p", null, el("strong", null, "Role:"), " " + (user.role || "N/A")),
      el("p", null, el("strong", null, "Active:"), " ",
        el("span", { className: user.active !== false ? "status-active" : "status-inactive" },
          user.active !== false ? "Active" : "Inactive"
        )
      )
    );
    panel.appendChild(summary);

    // Activate / Deactivate
    var toggleBtn = el("button", { className: "secondary", type: "button" },
      user.active !== false ? "Deactivate User" : "Activate User"
    );
    toggleBtn.addEventListener("click", async function () {
      toggleBtn.disabled = true;
      try {
        var action = user.active !== false ? "deactivate" : "activate";
        await api("POST", "/auth/users/" + encodeURIComponent(user.id) + "/" + action);
        showStatus("User " + action + "d", panel);
        onRefresh();
      } catch (err) {
        showError(err.message, panel);
      } finally {
        toggleBtn.disabled = false;
      }
    });
    panel.appendChild(toggleBtn);

    // Reset password
    panel.appendChild(el("h3", null, "Reset Password"));
    var newPwInput = el("input", { type: "password", placeholder: "New password" });
    var resetBtn = el("button", { type: "button" }, "Reset Password");
    resetBtn.addEventListener("click", async function () {
      var pw = newPwInput.value.trim();
      if (!pw) return;
      resetBtn.disabled = true;
      try {
        await api("POST", "/auth/reset-password", { user_id: user.id, new_password: pw });
        newPwInput.value = "";
        showStatus("Password reset", panel);
      } catch (err) {
        showError(err.message, panel);
      } finally {
        resetBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, newPwInput, resetBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete User");
    deleteBtn.addEventListener("click", function () {
      confirmDialog(
        "Delete User",
        "Are you sure you want to delete user \"" + escapeHtml(user.username) + "\"? This cannot be undone.",
        async function () {
          try {
            await api("DELETE", "/auth/users/" + encodeURIComponent(user.id));
            showStatus("User deleted", panel);
            onRefresh();
          } catch (err) {
            showError(err.message, panel);
          }
        },
        "Delete"
      );
    });
    panel.appendChild(deleteBtn);
  }

  // ==================================================================
  // TAB: API Keys
  // ==================================================================
  async function renderKeys(container) {
    selectedKey = null;
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    left.appendChild(el("h2", null, "API Keys"));

    // Fetch adapters and prompts for dropdowns
    await loadAdaptersAndPrompts();

    // Create key form
    var clientInput = el("input", { type: "text", placeholder: "Client name", required: "true" });
    var adapterSelect = el("select", null, el("option", { value: "" }, "Default adapter"));
    if (cachedAdapters) {
      cachedAdapters.forEach(function (a) {
        var name = typeof a === "string" ? a : (a.name || a.adapter_name || "");
        if (name) adapterSelect.appendChild(el("option", { value: name }, name));
      });
    }
    var promptSelect = el("select", null, el("option", { value: "" }, "No prompt"));
    if (cachedPrompts) {
      cachedPrompts.forEach(function (p) {
        promptSelect.appendChild(el("option", { value: p.id }, p.name + " (v" + (p.version || "1.0") + ")"));
      });
    }
    var notesInput = el("input", { type: "text", placeholder: "Notes (optional)" });
    var createBtn = el("button", { type: "button" }, "Create Key");

    var form = el("div", { className: "inline-form" },
      el("label", null, "Client", clientInput),
      el("label", null, "Adapter", adapterSelect),
      el("label", null, "Prompt", promptSelect),
      el("label", null, "Notes", notesInput),
      createBtn
    );
    left.appendChild(form);

    var tableWrap = el("div", null, skeleton());
    left.appendChild(tableWrap);

    right.appendChild(el("h2", null, "Key Details"));
    right.appendChild(el("p", { className: "muted" }, "Select an API key to manage"));

    createBtn.addEventListener("click", async function () {
      var cn = clientInput.value.trim();
      if (!cn) return;
      createBtn.disabled = true;
      try {
        var body = { client_name: cn, adapter_name: adapterSelect.value || undefined };
        if (promptSelect.value) body.system_prompt_id = promptSelect.value;
        if (notesInput.value.trim()) body.notes = notesInput.value.trim();
        await api("POST", "/admin/api-keys", body);
        clientInput.value = "";
        notesInput.value = "";
        showStatus("API key created", left);
        loadKeys();
      } catch (err) {
        showError(err.message, left);
      } finally {
        createBtn.disabled = false;
      }
    });

    async function loadKeys() {
      try {
        var keys = await api("GET", "/admin/api-keys");
        renderKeyTable(tableWrap, keys, right);
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load API keys"));
      }
    }

    loadKeys();
  }

  async function loadAdaptersAndPrompts() {
    try {
      var healthData = await api("GET", "/health/adapters").catch(function () { return null; });
      if (healthData) {
        var adapters = healthData.adapters || healthData.circuit_breakers || healthData;
        if (typeof adapters === "object" && !Array.isArray(adapters)) {
          cachedAdapters = Object.keys(adapters);
        }
      }
    } catch (_) {}
    try {
      cachedPrompts = await api("GET", "/admin/prompts");
    } catch (_) {
      cachedPrompts = [];
    }
  }

  function renderKeyTable(wrap, keys, rightPanel) {
    clear(wrap);
    if (!keys || keys.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F511}"),
        el("p", null, "No API keys found")
      ));
      return;
    }
    var table = el("table");
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Key"),
        el("th", null, "Client"),
        el("th", null, "Adapter"),
        el("th", null, "Active")
      )
    );
    var tbody = el("tbody");
    keys.forEach(function (k) {
      var keyVal = k.api_key || k.key || "";
      var tr = el("tr", {
        className: "selectable-row" + (selectedKey && selectedKey.api_key === k.api_key ? " selected-row" : ""),
        tabindex: "0",
      },
        el("td", { dataset: { label: "Key" } }, el("code", null, keyVal)),
        el("td", { dataset: { label: "Client" } }, k.client_name || ""),
        el("td", { dataset: { label: "Adapter" } }, k.adapter_name || "default"),
        el("td", { dataset: { label: "Active" } },
          el("span", { className: k.active !== false ? "status-active" : "status-inactive" },
            k.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", function () {
        selectedKey = k;
        wrap.querySelectorAll("tr").forEach(function (r) { r.classList.remove("selected-row"); });
        tr.classList.add("selected-row");
        renderKeyDetail(rightPanel, k, function () {
          selectedKey = null;
          renderTab();
        });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderKeyDetail(panel, key, onRefresh) {
    clear(panel);
    var keyVal = key.api_key || key.key || "";
    panel.appendChild(el("h2", null, "Key: " + escapeHtml(key.client_name || keyVal)));

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Key:"), " ", el("code", null, keyVal)),
      el("p", null, el("strong", null, "Client:"), " " + (key.client_name || "N/A")),
      el("p", null, el("strong", null, "Adapter:"), " " + (key.adapter_name || "default")),
      el("p", null, el("strong", null, "Active:"), " ",
        el("span", { className: key.active !== false ? "status-active" : "status-inactive" },
          key.active !== false ? "Active" : "Inactive"
        )
      )
    );
    panel.appendChild(summary);

    // Test key
    var testBtn = el("button", { className: "secondary", type: "button" }, "Test Key");
    var testResult = el("span");
    testBtn.addEventListener("click", async function () {
      testBtn.disabled = true;
      testResult.textContent = "";
      try {
        var resp = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/status");
        testResult.className = "badge-ok";
        testResult.textContent = "Valid";
      } catch (err) {
        testResult.className = "badge-fail";
        testResult.textContent = "Invalid";
      } finally {
        testBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form", style: "margin-top:var(--sp-3)" }, testBtn, testResult));

    // Rename
    panel.appendChild(el("h3", null, "Rename Key"));
    var renameInput = el("input", { type: "text", placeholder: "New key value" });
    var renameBtn = el("button", { type: "button" }, "Rename");
    renameBtn.addEventListener("click", async function () {
      var nk = renameInput.value.trim();
      if (!nk) return;
      renameBtn.disabled = true;
      try {
        await api("PATCH", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/rename?new_api_key=" + encodeURIComponent(nk));
        showStatus("Key renamed", panel);
        onRefresh();
      } catch (err) {
        showError(err.message, panel);
      } finally {
        renameBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, renameInput, renameBtn));

    // Deactivate
    if (key.active !== false) {
      var deactivateBtn = el("button", { className: "secondary", type: "button" }, "Deactivate Key");
      deactivateBtn.addEventListener("click", async function () {
        deactivateBtn.disabled = true;
        try {
          await api("POST", "/admin/api-keys/deactivate", { api_key: keyVal });
          showStatus("Key deactivated", panel);
          onRefresh();
        } catch (err) {
          showError(err.message, panel);
        } finally {
          deactivateBtn.disabled = false;
        }
      });
      panel.appendChild(deactivateBtn);
    }

    // Quota section
    panel.appendChild(el("h3", null, "Quota Management"));
    var quotaWrap = el("div", { className: "quota-section" });
    panel.appendChild(quotaWrap);

    var loadQuotaBtn = el("button", { className: "secondary", type: "button" }, "Load Quota");
    quotaWrap.appendChild(loadQuotaBtn);

    loadQuotaBtn.addEventListener("click", async function () {
      loadQuotaBtn.disabled = true;
      try {
        var quota = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/quota");
        renderQuotaDetail(quotaWrap, keyVal, quota);
      } catch (err) {
        showError(err.message, panel);
      } finally {
        loadQuotaBtn.disabled = false;
      }
    });

    // Associate prompt
    panel.appendChild(el("h3", null, "Associate Prompt"));
    var promptIdInput = el("input", { type: "text", placeholder: "Prompt ID" });
    var assocBtn = el("button", { type: "button" }, "Associate");
    assocBtn.addEventListener("click", async function () {
      var pid = promptIdInput.value.trim();
      if (!pid) return;
      assocBtn.disabled = true;
      try {
        await api("POST", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/prompt", { prompt_id: pid });
        promptIdInput.value = "";
        showStatus("Prompt associated", panel);
      } catch (err) {
        showError(err.message, panel);
      } finally {
        assocBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, promptIdInput, assocBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Key");
    deleteBtn.addEventListener("click", function () {
      confirmDialog(
        "Delete API Key",
        "Are you sure you want to delete this API key? This cannot be undone.",
        async function () {
          try {
            await api("DELETE", "/admin/api-keys/" + encodeURIComponent(keyVal));
            showStatus("Key deleted", panel);
            onRefresh();
          } catch (err) {
            showError(err.message, panel);
          }
        },
        "Delete"
      );
    });
    panel.appendChild(deleteBtn);

    // Raw status
    panel.appendChild(el("h3", null, "Raw Status"));
    var rawWrap = el("div");
    var rawBtn = el("button", { className: "secondary", type: "button" }, "Load Status");
    rawWrap.appendChild(rawBtn);
    rawBtn.addEventListener("click", async function () {
      rawBtn.disabled = true;
      try {
        var status = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/status");
        clear(rawWrap);
        rawWrap.appendChild(el("pre", null, JSON.stringify(status, null, 2)));
      } catch (err) {
        showError(err.message, panel);
      } finally {
        rawBtn.disabled = false;
      }
    });
    panel.appendChild(rawWrap);
  }

  function renderQuotaDetail(wrap, keyVal, quota) {
    clear(wrap);
    // Display
    var usage = quota.usage || {};
    var config = quota.quota || {};
    var info = el("div", { className: "info-grid" },
      infoRow("Daily Used", usage.daily_used != null ? usage.daily_used : "N/A"),
      infoRow("Daily Limit", config.daily_limit != null ? config.daily_limit : "Unlimited"),
      infoRow("Daily Remaining", quota.daily_remaining != null ? quota.daily_remaining : "N/A"),
      infoRow("Monthly Used", usage.monthly_used != null ? usage.monthly_used : "N/A"),
      infoRow("Monthly Limit", config.monthly_limit != null ? config.monthly_limit : "Unlimited"),
      infoRow("Monthly Remaining", quota.monthly_remaining != null ? quota.monthly_remaining : "N/A"),
      infoRow("Throttle", config.throttle_enabled ? "Enabled (priority " + (config.throttle_priority || 5) + ")" : "Disabled")
    );
    wrap.appendChild(info);

    // Reset buttons
    var resetRow = el("div", { className: "inline-form", style: "margin-top:var(--sp-2)" });
    ["daily", "monthly", "all"].forEach(function (period) {
      var btn = el("button", { className: "secondary", type: "button" }, "Reset " + period);
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        try {
          await api("POST", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/quota/reset?period=" + period);
          showStatus("Quota " + period + " reset", wrap);
          var updated = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/quota");
          renderQuotaDetail(wrap, keyVal, updated);
        } catch (err) {
          showError(err.message, wrap);
        } finally {
          btn.disabled = false;
        }
      });
      resetRow.appendChild(btn);
    });
    wrap.appendChild(resetRow);

    // Edit form
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Quota");
    var editForm = el("div", { style: "display:none" });

    var dailyInput = el("input", { type: "number", placeholder: "Daily limit (blank=unlimited)", value: config.daily_limit != null ? config.daily_limit : "" });
    var monthlyInput = el("input", { type: "number", placeholder: "Monthly limit (blank=unlimited)", value: config.monthly_limit != null ? config.monthly_limit : "" });
    var throttleCheck = el("input", { type: "checkbox" });
    if (config.throttle_enabled) throttleCheck.checked = true;
    var priorityInput = el("input", { type: "range", min: "1", max: "10", value: config.throttle_priority || 5 });
    var priorityLabel = el("span", null, "Priority: " + (config.throttle_priority || 5));
    priorityInput.addEventListener("input", function () { priorityLabel.textContent = "Priority: " + priorityInput.value; });

    var saveBtn = el("button", { type: "button" }, "Save Quota");
    saveBtn.addEventListener("click", async function () {
      saveBtn.disabled = true;
      try {
        var body = {
          throttle_enabled: throttleCheck.checked,
          throttle_priority: parseInt(priorityInput.value),
        };
        if (dailyInput.value !== "") body.daily_limit = parseInt(dailyInput.value);
        else body.daily_limit = null;
        if (monthlyInput.value !== "") body.monthly_limit = parseInt(monthlyInput.value);
        else body.monthly_limit = null;
        await api("PUT", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/quota", body);
        showStatus("Quota updated", wrap);
        var updated = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyVal) + "/quota");
        renderQuotaDetail(wrap, keyVal, updated);
      } catch (err) {
        showError(err.message, wrap);
      } finally {
        saveBtn.disabled = false;
      }
    });

    editForm.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-2)" },
      el("label", null, "Daily Limit", dailyInput),
      el("label", null, "Monthly Limit", monthlyInput),
      el("label", { className: "check-row" }, throttleCheck, "Throttle Enabled"),
      el("div", null, priorityLabel, priorityInput),
      saveBtn
    ));

    editToggle.addEventListener("click", function () {
      var hidden = editForm.style.display === "none";
      editForm.style.display = hidden ? "block" : "none";
      editToggle.textContent = hidden ? "Cancel Edit" : "Edit Quota";
    });

    wrap.appendChild(el("div", { style: "margin-top:var(--sp-2)" }, editToggle));
    wrap.appendChild(editForm);
  }

  function infoRow(label, value) {
    return el("div", { className: "info-row" },
      el("span", { className: "info-label" }, label),
      el("span", { className: "info-value" }, String(value))
    );
  }

  // ==================================================================
  // TAB: Prompts
  // ==================================================================
  async function renderPrompts(container) {
    selectedPrompt = null;
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    left.appendChild(el("h2", null, "System Prompts"));

    var nameInput = el("input", { type: "text", placeholder: "Prompt name", required: "true" });
    var versionInput = el("input", { type: "text", placeholder: "Version", value: "1.0" });
    var textArea = el("textarea", { placeholder: "Prompt text", rows: "5", required: "true" });
    var createBtn = el("button", { type: "button" }, "Create Prompt");

    var form = el("div", { className: "stack" },
      el("div", { className: "inline-form" },
        el("label", null, "Name", nameInput),
        el("label", null, "Version", versionInput)
      ),
      el("label", null, "Prompt", textArea),
      createBtn
    );
    left.appendChild(form);

    var tableWrap = el("div", null, skeleton());
    left.appendChild(tableWrap);

    right.appendChild(el("h2", null, "Prompt Details"));
    right.appendChild(el("p", { className: "muted" }, "Select a prompt to edit"));

    createBtn.addEventListener("click", async function () {
      var n = nameInput.value.trim();
      var t = textArea.value.trim();
      if (!n || !t) return;
      createBtn.disabled = true;
      try {
        await api("POST", "/admin/prompts", { name: n, prompt: t, version: versionInput.value.trim() || "1.0" });
        nameInput.value = "";
        textArea.value = "";
        versionInput.value = "1.0";
        showStatus("Prompt created", left);
        loadPrompts();
      } catch (err) {
        showError(err.message, left);
      } finally {
        createBtn.disabled = false;
      }
    });

    async function loadPrompts() {
      try {
        var prompts = await api("GET", "/admin/prompts");
        cachedPrompts = prompts;
        renderPromptTable(tableWrap, prompts, right);
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load prompts"));
      }
    }

    loadPrompts();
  }

  function renderPromptTable(wrap, prompts, rightPanel) {
    clear(wrap);
    if (!prompts || prompts.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F4DD}"),
        el("p", null, "No prompts found")
      ));
      return;
    }
    var table = el("table");
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Name"),
        el("th", null, "Version"),
        el("th", null, "ID")
      )
    );
    var tbody = el("tbody");
    prompts.forEach(function (p) {
      var tr = el("tr", {
        className: "selectable-row" + (selectedPrompt && selectedPrompt.id === p.id ? " selected-row" : ""),
        tabindex: "0",
      },
        el("td", { dataset: { label: "Name" } }, p.name),
        el("td", { dataset: { label: "Version" } }, p.version || ""),
        el("td", { dataset: { label: "ID" } }, el("code", null, p.id || ""))
      );
      tr.addEventListener("click", function () {
        selectedPrompt = p;
        wrap.querySelectorAll("tr").forEach(function (r) { r.classList.remove("selected-row"); });
        tr.classList.add("selected-row");
        renderPromptDetail(rightPanel, p, function () {
          selectedPrompt = null;
          renderTab();
        });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderPromptDetail(panel, prompt, onRefresh) {
    clear(panel);
    panel.appendChild(el("h2", null, "Edit: " + escapeHtml(prompt.name)));

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Name:"), " " + prompt.name),
      el("p", null, el("strong", null, "ID:"), " ", el("code", null, prompt.id || ""))
    );
    panel.appendChild(summary);

    // Edit
    var vInput = el("input", { type: "text", value: prompt.version || "1.0" });
    var tArea = el("textarea", { rows: "8" }, prompt.prompt || "");
    var saveBtn = el("button", { type: "button" }, "Save Changes");
    saveBtn.addEventListener("click", async function () {
      saveBtn.disabled = true;
      try {
        await api("PUT", "/admin/prompts/" + encodeURIComponent(prompt.id), {
          prompt: tArea.value,
          version: vInput.value.trim(),
        });
        showStatus("Prompt updated", panel);
        onRefresh();
      } catch (err) {
        showError(err.message, panel);
      } finally {
        saveBtn.disabled = false;
      }
    });

    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      el("label", null, "Version", vInput),
      el("label", null, "Prompt Text", tArea),
      saveBtn
    ));

    // Associate to API key
    panel.appendChild(el("h3", null, "Associate to API Key"));
    var keyInput = el("input", { type: "text", placeholder: "Full API key value" });
    var assocBtn = el("button", { type: "button" }, "Associate");
    assocBtn.addEventListener("click", async function () {
      var k = keyInput.value.trim();
      if (!k) return;
      assocBtn.disabled = true;
      try {
        await api("POST", "/admin/api-keys/" + encodeURIComponent(k) + "/prompt", { prompt_id: prompt.id });
        keyInput.value = "";
        showStatus("Prompt associated with key", panel);
      } catch (err) {
        showError(err.message, panel);
      } finally {
        assocBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, keyInput, assocBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Prompt");
    deleteBtn.addEventListener("click", function () {
      confirmDialog(
        "Delete Prompt",
        "Are you sure you want to delete prompt \"" + escapeHtml(prompt.name) + "\"? This cannot be undone.",
        async function () {
          try {
            await api("DELETE", "/admin/prompts/" + encodeURIComponent(prompt.id));
            showStatus("Prompt deleted", panel);
            onRefresh();
          } catch (err) {
            showError(err.message, panel);
          }
        },
        "Delete"
      );
    });
    panel.appendChild(deleteBtn);
  }

  // ==================================================================
  // TAB: Ops
  // ==================================================================
  function renderOps(container) {
    var grid = el("div", { className: "panel-grid" });
    container.appendChild(grid);

    // Reload panel
    var reloadPanel = el("div", { className: "panel action-panel" });
    reloadPanel.appendChild(el("h2", null, "Reload Configuration"));
    var filterInput = el("input", { type: "text", placeholder: "Adapter filter (optional)" });
    reloadPanel.appendChild(el("div", { className: "stack" }, filterInput));

    var reloadAdaptersBtn = el("button", { type: "button" }, "Reload Adapters");
    reloadAdaptersBtn.addEventListener("click", async function () {
      reloadAdaptersBtn.disabled = true;
      try {
        var path = "/admin/reload-adapters";
        var f = filterInput.value.trim();
        if (f) path += "?adapter_name=" + encodeURIComponent(f);
        var result = await api("POST", path);
        showStatus("Adapters reloaded: " + (result.message || "OK"), reloadPanel);
      } catch (err) {
        showError(err.message, reloadPanel);
      } finally {
        reloadAdaptersBtn.disabled = false;
      }
    });

    var reloadTemplatesBtn = el("button", { type: "button" }, "Reload Templates");
    reloadTemplatesBtn.addEventListener("click", async function () {
      reloadTemplatesBtn.disabled = true;
      try {
        var path = "/admin/reload-templates";
        var f = filterInput.value.trim();
        if (f) path += "?adapter_name=" + encodeURIComponent(f);
        var result = await api("POST", path);
        showStatus("Templates reloaded: " + (result.message || "OK"), reloadPanel);
      } catch (err) {
        showError(err.message, reloadPanel);
      } finally {
        reloadTemplatesBtn.disabled = false;
      }
    });

    reloadPanel.appendChild(el("div", { className: "inline-form", style: "margin-top:var(--sp-3)" },
      reloadAdaptersBtn, reloadTemplatesBtn
    ));

    grid.appendChild(reloadPanel);

    // Server control panel
    var controlPanel = el("div", { className: "panel action-panel" });
    controlPanel.appendChild(el("h2", null, "Server Control"));
    controlPanel.appendChild(el("p", { className: "muted" },
      "Shut down the ORBIT server process. This action cannot be undone from the admin UI."
    ));

    var shutdownBtn = el("button", { className: "danger", type: "button" }, "Shutdown Server");
    shutdownBtn.addEventListener("click", function () {
      confirmDialog(
        "Shutdown Server",
        "Are you sure you want to shut down the server? This will terminate the ORBIT process and cannot be reversed from this UI.",
        async function () {
          shutdownBtn.disabled = true;
          try {
            await api("POST", "/admin/shutdown");
            showStatus("Server shutdown initiated", controlPanel);
          } catch (err) {
            showError(err.message, controlPanel);
          }
        },
        "Shutdown"
      );
    });

    controlPanel.appendChild(shutdownBtn);
    grid.appendChild(controlPanel);
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
