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
  let cachedKeys = null;

  // Selection state per tab
  let selectedUser = null;
  let selectedKey = null;
  let selectedPrompt = null;
  let messageCounter = 0;
  let opsLogPollTimer = null;

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

  function clearOpsLogPolling() {
    if (opsLogPollTimer) {
      clearTimeout(opsLogPollTimer);
      opsLogPollTimer = null;
    }
  }

  function maskSecret(value) {
    if (!value) return "";
    if (value.length <= 8) return "••••••••";
    return value.slice(0, 4) + "••••••••" + value.slice(-4);
  }

  function promptIdentifier(prompt) {
    return (prompt && (prompt.id || prompt._id)) || "";
  }

  function markSelectedRow(tableBody, activeRow) {
    tableBody.querySelectorAll("tr").forEach(function (row) {
      var isActive = row === activeRow;
      row.classList.toggle("selected-row", isActive);
      row.setAttribute("aria-selected", isActive ? "true" : "false");
    });
  }

  function field(labelText, input, hintText, control) {
    var target = control || input;
    var id = target.id || "field-" + Math.random().toString(36).slice(2, 9);
    target.id = id;
    var children = [el("span", null, labelText)];
    if (hintText) children.push(el("span", { className: "muted" }, hintText));
    children.push(input);
    return el("label", { htmlFor: id, className: "stack" }, children);
  }

  function passwordField(labelText, input, hintText) {
    input.type = "password";
    var wrapper = el("div", { className: "password-field" }, input);
    var toggleBtn = el("button", {
      type: "button",
      className: "password-toggle",
      "aria-label": "Show password",
      title: "Show password",
    }, "👁");
    toggleBtn.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      toggleBtn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      toggleBtn.setAttribute("title", showing ? "Show password" : "Hide password");
    });
    wrapper.appendChild(toggleBtn);
    return field(labelText, wrapper, hintText, input);
  }

  function wrapTable(table) {
    return el("div", { className: "table-wrap" }, table);
  }

  function debounce(fn, delay) {
    var timer = null;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(null, args);
      }, delay);
    };
  }

  function trapFocus(e, root) {
    var focusable = root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  // ------------------------------------------------------------------
  // Status / Error messages
  // ------------------------------------------------------------------
  function showStatus(msg) {
    pushMessage("status", msg, true);
  }

  function showError(msg) {
    pushMessage("error", msg, false);
  }

  function pushMessage(kind, msg, autoDismiss) {
    var region = document.getElementById("toast-region");
    if (!region) return;
    var dismissBtn = el("button", {
      type: "button",
      className: "message-dismiss",
      "aria-label": "Dismiss notification",
    }, "×");
    var node = el("div", {
      id: "message-" + (++messageCounter),
      className: kind,
      role: kind === "error" ? "alert" : "status",
    },
      el("div", { className: "message-body" }, msg),
      dismissBtn
    );
    dismissBtn.addEventListener("click", function () { node.remove(); });
    region.prepend(node);
    if (autoDismiss) {
      setTimeout(function () {
        if (node.parentNode) node.remove();
      }, 5000);
    }
  }

  // ------------------------------------------------------------------
  // Confirm dialog
  // ------------------------------------------------------------------
  function confirmDialog(title, message, onConfirm, confirmLabel, isDanger, extraContent) {
    var previousFocus = document.activeElement;
    var titleId = "dialog-title-" + Date.now();
    var descId = "dialog-desc-" + Date.now();
    var backdrop = el("div", { className: "dialog-backdrop" });
    var cancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var confirmBtn = el("button", { className: isDanger ? "danger" : "", type: "button" }, confirmLabel || "Confirm");
    var bodyChildren = [
      el("h2", { id: titleId }, title),
      el("p", { id: descId }, message),
    ];
    if (extraContent) bodyChildren.push(extraContent);
    bodyChildren.push(el("div", { className: "dialog-actions" }, cancelBtn, confirmBtn));
    var dialog = el("div", {
      className: "confirm-dialog",
      role: "dialog",
      "aria-modal": "true",
      "aria-labelledby": titleId,
      "aria-describedby": descId,
    }, el("div", { className: "dialog-body" }, bodyChildren));
    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);
    (isDanger ? cancelBtn : confirmBtn).focus();

    function close() {
      document.removeEventListener("keydown", handler);
      backdrop.remove();
      if (previousFocus && previousFocus.focus) previousFocus.focus();
    }
    cancelBtn.addEventListener("click", close);
    confirmBtn.addEventListener("click", async function () {
      try {
        await onConfirm();
        close();
      } catch (err) {
        showError(err.message);
      }
    });
    backdrop.addEventListener("click", function (e) { if (e.target === backdrop) close(); });
    function handler(e) {
      if (e.key === "Escape") close();
      if (e.key === "Tab") trapFocus(e, dialog);
    }
    document.addEventListener("keydown", handler);
  }

  function confirmAction(options) {
    confirmDialog(options.title, options.message, options.onConfirm, options.confirmLabel, !!options.isDanger);
  }

  function requireTypedConfirmation(options) {
    var input = el("input", {
      type: "text",
      maxlength: "100",
      "aria-label": "Type " + options.expectedText + " to confirm"
    });
    var extra = el("label", { className: "dialog-field" },
      el("span", null, 'Type "' + options.expectedText + '" to continue'),
      input
    );
    confirmDialog(options.title, options.message, async function () {
      if (input.value.trim() !== options.expectedText) {
        throw new Error("Confirmation text did not match.");
      }
      await options.onConfirm();
    }, options.confirmLabel, options.isDanger !== false, extra);
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
    var controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, 30000);
    var opts = {
      method: method,
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
    };
    if (authToken) opts.headers["Authorization"] = "Bearer " + authToken;
    if (body !== undefined) opts.body = JSON.stringify(body);
    var resp;
    try {
      resp = await fetch(path, opts);
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") throw new Error("Request timed out");
      throw err;
    }
    clearTimeout(timeoutId);
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
    var topbar = el("header", { className: "topbar", role: "banner" },
      el("div", { className: "brand-block" },
        el("img", {
          src: "/static/orbit-logo-dark.png",
          alt: "",
          className: "brand-logo",
        })
      ),
      el("div", { className: "topbar-actions" },
        el("span", null, currentUser ? currentUser.role : ""),
        logoutBtn
      )
    );

    // Tabs
    var tabBar = el("div", { className: "tabs", role: "tablist", "aria-label": "Admin sections" });
    TABS.forEach(function (t) {
      var isSelected = t.id === activeTab;
      var btn = el("button", {
        id: "tab-" + t.id,
        type: "button",
        role: "tab",
        "aria-selected": String(isSelected),
        "aria-controls": "tab-content",
        tabindex: isSelected ? "0" : "-1",
        className: t.id === activeTab ? "active" : "",
        dataset: { tab: t.id },
      }, t.label);
      btn.addEventListener("click", function () { switchTab(t.id); });
      btn.addEventListener("keydown", function (e) {
        var currentIndex = TABS.findIndex(function (tab) { return tab.id === t.id; });
        if (e.key === "ArrowRight") {
          e.preventDefault();
          switchTab(TABS[(currentIndex + 1) % TABS.length].id);
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          switchTab(TABS[(currentIndex - 1 + TABS.length) % TABS.length].id);
        }
      });
      tabBar.appendChild(btn);
    });

    // Content
    var toastRegion = el("div", {
      id: "toast-region",
      className: "toast-region",
      "aria-live": "polite",
      "aria-atomic": "true",
    });
    var content = el("main", {
      id: "tab-content",
      className: "app-main",
      role: "tabpanel",
      tabindex: "-1",
      "aria-labelledby": "tab-" + activeTab,
    });

    var shell = el("div", { className: "app-shell" }, topbar, el("nav", null, tabBar), toastRegion, content);
    app.appendChild(shell);

    renderTab();
  }

  function switchTab(id) {
    activeTab = id;
    document.querySelectorAll(".tabs button").forEach(function (b) {
      var isActive = b.dataset.tab === id;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-selected", String(isActive));
      b.setAttribute("tabindex", isActive ? "0" : "-1");
      if (isActive) b.focus();
    });
    var panel = document.getElementById("tab-content");
    if (panel) panel.setAttribute("aria-labelledby", "tab-" + id);
    renderTab();
  }

  function renderTab() {
    clearOpsLogPolling();
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
      showError("Failed to load overview: " + err.message);
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
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    // Create user form
    left.appendChild(el("h2", null, "Users"));
    var usernameInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var passwordInput = el("input", { type: "password", required: "true", maxlength: "100" });
    var roleSelect = el("select", null,
      el("option", { value: "user" }, "user"),
      el("option", { value: "admin" }, "admin")
    );
    var createBtn = el("button", { type: "button" }, "Create User");

    var form = el("div", { className: "inline-form" },
      field("Username", usernameInput),
      passwordField("Password", passwordInput),
      field("Role", roleSelect),
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
        showStatus("User created");
        loadUsers();
      } catch (err) {
        showError(err.message);
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
    var curPwInput = el("input", { type: "password", placeholder: "Current password", maxlength: "100" });
    var newPwInput = el("input", { type: "password", placeholder: "New password", maxlength: "100" });
    var confirmPwInput = el("input", { type: "password", placeholder: "Confirm new password", maxlength: "100" });
    var changeBtn = el("button", { type: "button" }, "Change Password");

    changeBtn.addEventListener("click", async function () {
      var cur = curPwInput.value;
      var nw = newPwInput.value;
      var conf = confirmPwInput.value;
      if (!cur || !nw) return;
      if (nw !== conf) { showError("Passwords do not match"); return; }
      changeBtn.disabled = true;
      try {
        await api("POST", "/auth/change-password", { current_password: cur, new_password: nw });
        curPwInput.value = "";
        newPwInput.value = "";
        confirmPwInput.value = "";
        showStatus("Password changed successfully");
      } catch (err) {
        showError(err.message);
      } finally {
        changeBtn.disabled = false;
      }
    });

    panel.appendChild(el("div", { className: "stack" },
      passwordField("Current Password", curPwInput),
      passwordField("New Password", newPwInput),
      passwordField("Confirm Password", confirmPwInput),
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
      var isSelected = selectedUser && selectedUser.id === u.id;
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", null, u.username),
        el("td", null, u.role || ""),
        el("td", null,
          el("span", { className: u.active !== false ? "status-active" : "status-inactive" },
            u.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", function () {
        selectedUser = u;
        markSelectedRow(tbody, tr);
        renderUserDetail(rightPanel, u, function () {
          selectedUser = null;
          renderTab();
        });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          tr.click();
        }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(wrapTable(table));
  }

  function renderUserDetail(panel, user, onRefresh) {
    clear(panel);
    panel.appendChild(el("h2", null, "Manage: " + user.username));

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
      var action = user.active !== false ? "deactivate" : "activate";
      confirmAction({
        title: (action === "deactivate" ? "Deactivate" : "Activate") + " User",
        message: "Are you sure you want to " + action + " " + user.username + "?",
        confirmLabel: action === "deactivate" ? "Deactivate" : "Activate",
        onConfirm: async function () {
          toggleBtn.disabled = true;
          try {
            await api("POST", "/auth/users/" + encodeURIComponent(user.id) + "/" + action);
            showStatus("User " + action + "d");
            onRefresh();
          } finally {
            toggleBtn.disabled = false;
          }
        }
      });
    });
    panel.appendChild(toggleBtn);

    // Reset password
    panel.appendChild(el("h3", null, "Reset Password"));
    var newPwInput = el("input", { type: "password", maxlength: "100" });
    var resetBtn = el("button", { type: "button" }, "Reset Password");
    resetBtn.addEventListener("click", function () {
      var pw = newPwInput.value.trim();
      if (!pw) return;
      confirmAction({
        title: "Reset Password",
        message: "Reset the password for " + user.username + "?",
        confirmLabel: "Reset",
        onConfirm: async function () {
          resetBtn.disabled = true;
          try {
            await api("POST", "/auth/reset-password", { user_id: user.id, new_password: pw });
            newPwInput.value = "";
            showStatus("Password reset");
          } finally {
            resetBtn.disabled = false;
          }
        }
      });
    });
    panel.appendChild(el("div", { className: "inline-form" }, passwordField("New password", newPwInput), resetBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete User");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete User",
        message: 'Delete user "' + user.username + '"? This cannot be undone.',
        expectedText: user.username,
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", "/auth/users/" + encodeURIComponent(user.id));
          showStatus("User deleted");
          onRefresh();
        }
      });
    });
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Destructive actions affect account access immediately."),
      deleteBtn
    ));
  }

  // ==================================================================
  // TAB: API Keys
  // ==================================================================
  async function renderKeys(container) {
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
    var clientInput = el("input", { type: "text", required: "true", maxlength: "100" });
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
        promptSelect.appendChild(el("option", { value: promptIdentifier(p) }, p.name + " (v" + (p.version || "1.0") + ")"));
      });
    }
    var notesInput = el("input", { type: "text", maxlength: "100" });
    var createBtn = el("button", { type: "button" }, "Create Key");

    var form = el("div", { className: "inline-form" },
      field("Client", clientInput),
      field("Adapter", adapterSelect),
      field("Prompt", promptSelect),
      field("Notes", notesInput),
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
        showStatus("API key created");
        loadKeys();
      } catch (err) {
        showError(err.message);
      } finally {
        createBtn.disabled = false;
      }
    });

    async function loadKeys() {
      try {
        var keys = await api("GET", "/admin/api-keys");
        cachedKeys = keys;
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

  async function loadAvailableKeys() {
    try {
      cachedKeys = await api("GET", "/admin/api-keys");
    } catch (_) {
      cachedKeys = [];
    }
    return cachedKeys;
  }

  function fillKeySelect(select, keys, selectedKeyId) {
    clear(select);
    select.appendChild(el("option", { value: "" }, keys && keys.length ? "Select an API key" : "No API keys available"));
    (keys || []).forEach(function (key) {
      var keyVal = key.api_key || key.key || "";
      var label = (key.client_name || "Unnamed key") + " (" + maskSecret(keyVal) + ")";
      var option = el("option", { value: key._id || "" }, label);
      if (selectedKeyId && key._id === selectedKeyId) option.selected = true;
      select.appendChild(option);
    });
    select.disabled = !keys || keys.length === 0;
  }

  function fillPromptSelect(select, prompts, selectedPromptId) {
    clear(select);
    select.appendChild(el("option", { value: "" }, prompts && prompts.length ? "Select a prompt" : "No prompts available"));
    (prompts || []).forEach(function (prompt) {
      var promptId = promptIdentifier(prompt);
      var option = el("option", { value: promptId }, prompt.name + " (v" + (prompt.version || "1.0") + ")");
      if (selectedPromptId && promptId === selectedPromptId) option.selected = true;
      select.appendChild(option);
    });
    select.disabled = !prompts || prompts.length === 0;
  }

  async function loadKeyDetail(keyId) {
    return api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/detail");
  }

  function createMarkdownPreview(textarea) {
    var frame = el("div", { className: "markdown-preview-shell" },
      el("div", { className: "markdown-preview-header" }, "Preview"),
      el("div", { className: "markdown-preview is-empty", "aria-live": "polite" },
        el("p", { className: "muted" }, "Nothing to preview yet.")
      )
    );
    var body = frame.querySelector(".markdown-preview");
    var requestToken = 0;

    async function renderPreview() {
      var text = textarea.value.trim();
      if (!text) {
        body.className = "markdown-preview is-empty";
        body.innerHTML = '<p class="muted">Nothing to preview yet.</p>';
        return;
      }

      var token = ++requestToken;
      body.className = "markdown-preview is-loading";
      body.innerHTML = '<p class="muted">Rendering preview...</p>';

      try {
        var result = await api("POST", "/admin/render-markdown", { markdown: text });
        if (token !== requestToken) return;
        body.className = "markdown-preview";
        body.innerHTML = result && result.html ? result.html : "<p></p>";
      } catch (err) {
        if (token !== requestToken) return;
        body.className = "markdown-preview is-error";
        body.textContent = "Preview unavailable: " + err.message;
      }
    }

    textarea.addEventListener("input", debounce(renderPreview, 220));
    renderPreview();
    return frame;
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
        el("th", null, "Client"),
        el("th", null, "Adapter"),
        el("th", null, "Prompt"),
        el("th", null, "Active")
      )
    );
    var tbody = el("tbody");
    keys.forEach(function (k) {
      var isSelected = selectedKey && selectedKey._id && k._id && selectedKey._id === k._id;
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", null, k.client_name || ""),
        el("td", null, k.adapter_name || "default"),
        el("td", null, k.system_prompt_name || "None"),
        el("td", null,
          el("span", { className: k.active !== false ? "status-active" : "status-inactive" },
            k.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", async function () {
        selectedKey = { _id: k._id };
        markSelectedRow(tbody, tr);
        clear(rightPanel);
        rightPanel.appendChild(el("p", { className: "muted" }, "Loading key details..."));
        try {
          var detail = await loadKeyDetail(k._id);
          selectedKey = detail;
          renderKeyDetail(rightPanel, detail, function () {
            selectedKey = null;
            renderTab();
          });
        } catch (err) {
          selectedKey = null;
          clear(rightPanel);
          rightPanel.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Unable to load key details."),
            el("p", { className: "muted" }, err.message || "Unknown error")
          ));
          showError(err.message);
        }
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          tr.click();
        }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(wrapTable(table));
  }

  function renderKeyDetail(panel, key, onRefresh) {
    clear(panel);
    var keyId = key._id || "";
    var keyVal = key.api_key || key.key || "";
    panel.appendChild(el("h2", null, "Key: " + (key.client_name || keyVal)));
    var revealSecret = false;
    var keyCode = el("code", null, maskSecret(keyVal));
    var revealBtn = el("button", {
      type: "button",
      className: "password-toggle",
      "aria-label": "Show API key",
      title: "Show API key",
    }, "👁");
    revealBtn.addEventListener("click", function () {
      revealSecret = !revealSecret;
      keyCode.textContent = revealSecret ? keyVal : maskSecret(keyVal);
      revealBtn.setAttribute("aria-label", revealSecret ? "Hide API key" : "Show API key");
      revealBtn.setAttribute("title", revealSecret ? "Hide API key" : "Show API key");
    });
    var keyField = el("div", { className: "secret-field" }, keyCode, revealBtn);

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Key:"), " ", keyField),
      el("p", null, el("strong", null, "Client:"), " " + (key.client_name || "N/A")),
      el("p", null, el("strong", null, "Adapter:"), " " + (key.adapter_name || "default")),
      el("p", null, el("strong", null, "Prompt:"), " " + (key.system_prompt_name || "None")),
      el("p", null, el("strong", null, "Active:"), " ",
        el("span", { className: key.active !== false ? "status-active" : "status-inactive" },
          key.active !== false ? "Active" : "Inactive"
        )
      )
    );
    panel.appendChild(summary);

    // Test key
    var testBtn = el("button", { className: "secondary", type: "button" }, "Test Key");
    var testResult = el("div", {
      className: "test-result",
      "aria-live": "polite",
      "aria-atomic": "true"
    });
    testBtn.addEventListener("click", async function () {
      testBtn.disabled = true;
      clear(testResult);
      testResult.className = "test-result";
      testResult.appendChild(el("span", { className: "muted" }, "Checking key status..."));
      try {
        await api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/status");
        testResult.className = "test-result test-result-ok";
        testResult.appendChild(el("span", { className: "test-result-icon", "aria-hidden": "true" }, "✓"));
        testResult.appendChild(el("div", { className: "test-result-copy" },
          el("strong", null, "Key verified"),
          el("span", null, "Authentication succeeded and this key is accepted by the server.")
        ));
      } catch (err) {
        testResult.className = "test-result test-result-fail";
        testResult.appendChild(el("span", { className: "test-result-icon", "aria-hidden": "true" }, "!"));
        testResult.appendChild(el("div", { className: "test-result-copy" },
          el("strong", null, "Verification failed"),
          el("span", null, "The server rejected this key. Check whether it is active and correctly configured.")
        ));
      } finally {
        testBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form", style: "margin-top:var(--sp-3)" }, testBtn, testResult));

    // Rename
    panel.appendChild(el("h3", null, "Rename Key"));
    var renameInput = el("input", { type: "text", maxlength: "100" });
    var renameBtn = el("button", { type: "button" }, "Rename");
    renameBtn.addEventListener("click", async function () {
      var nk = renameInput.value.trim();
      if (!nk) return;
      renameBtn.disabled = true;
      try {
        await api("PATCH", "/admin/api-keys/" + encodeURIComponent(keyId) + "/rename?new_api_key=" + encodeURIComponent(nk));
        showStatus("Key renamed");
        onRefresh();
      } catch (err) {
        showError(err.message);
      } finally {
        renameBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, field("New key value", renameInput), renameBtn));

    // Quota section
    panel.appendChild(el("h3", null, "Quota Management"));
    var quotaWrap = el("div", { className: "quota-section" });
    panel.appendChild(quotaWrap);

    var loadQuotaBtn = el("button", { className: "secondary", type: "button" }, "Load Quota");
    quotaWrap.appendChild(loadQuotaBtn);

    loadQuotaBtn.addEventListener("click", async function () {
      loadQuotaBtn.disabled = true;
      try {
        var quota = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/quota");
        renderQuotaDetail(quotaWrap, keyId, quota);
      } catch (err) {
        showError(err.message);
      } finally {
        loadQuotaBtn.disabled = false;
      }
    });

    // Associate prompt
    panel.appendChild(el("h3", null, "Associate Prompt"));
    var promptSelect = el("select", null, el("option", { value: "" }, "Loading prompts..."));
    var assocBtn = el("button", { type: "button" }, "Associate");
    fillPromptSelect(promptSelect, cachedPrompts, key.system_prompt_id);
    assocBtn.disabled = !cachedPrompts || !cachedPrompts.length;
    if (!cachedPrompts) {
      loadAdaptersAndPrompts().then(function () {
        fillPromptSelect(promptSelect, cachedPrompts, key.system_prompt_id);
        assocBtn.disabled = !cachedPrompts || !cachedPrompts.length;
      });
    }
    assocBtn.addEventListener("click", async function () {
      var pid = promptSelect.value;
      if (!pid) return;
      assocBtn.disabled = true;
      try {
        await api("POST", "/admin/api-keys/" + encodeURIComponent(keyId) + "/prompt", { prompt_id: pid });
        key.system_prompt_id = pid;
        var matchedPrompt = (cachedPrompts || []).find(function (prompt) {
          return promptIdentifier(prompt) === pid;
        });
        key.system_prompt_name = matchedPrompt ? matchedPrompt.name : key.system_prompt_name;
        showStatus("Prompt associated");
        onRefresh();
      } catch (err) {
        showError(err.message);
      } finally {
        assocBtn.disabled = false;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, field("Prompt", promptSelect), assocBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var dangerActions = el("div", { className: "inline-form" });
    if (key.active !== false) {
      var deactivateBtn = el("button", { className: "secondary", type: "button" }, "Deactivate Key");
      deactivateBtn.addEventListener("click", function () {
        confirmAction({
          title: "Deactivate Key",
          message: "Deactivate this API key? Existing integrations will stop authenticating.",
          confirmLabel: "Deactivate",
          onConfirm: async function () {
            deactivateBtn.disabled = true;
            try {
              await api("POST", "/admin/api-keys/" + encodeURIComponent(keyId) + "/deactivate");
              showStatus("Key deactivated");
              onRefresh();
            } finally {
              deactivateBtn.disabled = false;
            }
          }
        });
      });
      dangerActions.appendChild(deactivateBtn);
    }
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Key");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete API Key",
        message: "Delete this API key? This cannot be undone.",
        expectedText: key.client_name || "DELETE",
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", "/admin/api-keys/" + encodeURIComponent(keyId));
          showStatus("Key deleted");
          onRefresh();
        }
      });
    });
    dangerActions.appendChild(deleteBtn);
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Deleting a key immediately revokes access for downstream clients."),
      dangerActions
    ));

    // Raw status
    panel.appendChild(el("h3", null, "Raw Status"));
    var rawWrap = el("div");
    var rawBtn = el("button", { className: "secondary", type: "button" }, "Load Status");
    rawWrap.appendChild(rawBtn);
    rawBtn.addEventListener("click", async function () {
      rawBtn.disabled = true;
      try {
        var status = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/status");
        clear(rawWrap);
        rawWrap.appendChild(el("pre", null, JSON.stringify(status, null, 2)));
      } catch (err) {
        showError(err.message);
      } finally {
        rawBtn.disabled = false;
      }
    });
    panel.appendChild(rawWrap);
  }

  function renderQuotaDetail(wrap, keyId, quota) {
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
      btn.addEventListener("click", function () {
        confirmAction({
          title: "Reset Quota",
          message: "Reset the " + period + " quota counters for this key?",
          confirmLabel: "Reset",
          onConfirm: async function () {
            btn.disabled = true;
            try {
              await api("POST", "/admin/api-keys/" + encodeURIComponent(keyId) + "/quota/reset?period=" + period);
              showStatus("Quota " + period + " reset");
              var updated = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/quota");
              renderQuotaDetail(wrap, keyId, updated);
            } finally {
              btn.disabled = false;
            }
          }
        });
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
        await api("PUT", "/admin/api-keys/" + encodeURIComponent(keyId) + "/quota", body);
        showStatus("Quota updated");
        var updated = await api("GET", "/admin/api-keys/" + encodeURIComponent(keyId) + "/quota");
        renderQuotaDetail(wrap, keyId, updated);
      } catch (err) {
        showError(err.message);
      } finally {
        saveBtn.disabled = false;
      }
    });

    editForm.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-2)" },
      field("Daily Limit", dailyInput, "Leave blank for unlimited"),
      field("Monthly Limit", monthlyInput, "Leave blank for unlimited"),
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
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    left.appendChild(el("h2", null, "System Prompts"));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var versionInput = el("input", { type: "text", value: "1.0", maxlength: "100" });
    var textArea = el("textarea", { rows: "5", required: "true", maxlength: "50000" });
    var createBtn = el("button", { type: "button" }, "Create Prompt");

    var form = el("div", { className: "stack" },
      el("div", { className: "inline-form" },
        field("Name", nameInput),
        field("Version", versionInput)
      ),
      field("Prompt", textArea),
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
        showStatus("Prompt created");
        loadPrompts();
      } catch (err) {
        showError(err.message);
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
        el("th", null, "ID"),
        el("th", null, "Name"),
        el("th", null, "Version")
      )
    );
    var tbody = el("tbody");
    prompts.forEach(function (p) {
      var promptId = promptIdentifier(p);
      var isSelected = selectedPrompt && promptIdentifier(selectedPrompt) === promptId;
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", null, el("code", null, promptId)),
        el("td", null, p.name),
        el("td", null, p.version || "")
      );
      tr.addEventListener("click", function () {
        selectedPrompt = p;
        markSelectedRow(tbody, tr);
        renderPromptDetail(rightPanel, p, function () {
          selectedPrompt = null;
          renderTab();
        });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          tr.click();
        }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(wrapTable(table));
  }

  function renderPromptDetail(panel, prompt, onRefresh) {
    clear(panel);
    var promptId = promptIdentifier(prompt);
    panel.appendChild(el("h2", null, "Edit: " + prompt.name));

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Name:"), " " + prompt.name),
      el("p", null, el("strong", null, "ID:"), " ", el("code", null, promptId))
    );
    panel.appendChild(summary);

    // Edit
    var originalVersion = prompt.version || "1.0";
    var originalPromptText = prompt.prompt || "";
    var isEditingPrompt = false;
    var vInput = el("input", { type: "text", value: prompt.version || "1.0", maxlength: "100" });
    var tArea = el("textarea", { rows: "8", maxlength: "50000" }, prompt.prompt || "");
    var saveBtn = el("button", { type: "button" }, "Save Changes");
    saveBtn.addEventListener("click", async function () {
      if (saveBtn.disabled) return;
      saveBtn.disabled = true;
      try {
        await api("PUT", "/admin/prompts/" + encodeURIComponent(promptId), {
          prompt: tArea.value,
          version: vInput.value.trim(),
        });
        showStatus("Prompt updated");
        onRefresh();
      } catch (err) {
        showError(err.message);
      } finally {
        saveBtn.disabled = false;
      }
    });
    
    var editPreview = createMarkdownPreview(tArea);
    var editorWrap = el("div", { className: "prompt-editor-pane", style: "display:none" },
      field("Prompt Text", tArea)
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Prompt Text");
    var cancelBtn = el("button", { className: "secondary", type: "button", style: "display:none" }, "Cancel");
    function promptHasChanges() {
      return vInput.value.trim() !== originalVersion || tArea.value !== originalPromptText;
    }
    function syncPromptSaveState() {
      saveBtn.disabled = !isEditingPrompt || !promptHasChanges();
    }
    function setPromptEditMode(editing) {
      isEditingPrompt = editing;
      editorWrap.style.display = editing ? "block" : "none";
      previewWrap.style.display = editing ? "none" : "block";
      editToggle.style.display = editing ? "none" : "inline-flex";
      cancelBtn.style.display = editing ? "inline-flex" : "none";
      syncPromptSaveState();
    }
    editToggle.addEventListener("click", function () {
      setPromptEditMode(true);
    });
    cancelBtn.addEventListener("click", function () {
      vInput.value = originalVersion;
      tArea.value = originalPromptText;
      tArea.dispatchEvent(new Event("input"));
      setPromptEditMode(false);
    });
    vInput.addEventListener("input", syncPromptSaveState);
    tArea.addEventListener("input", syncPromptSaveState);
    syncPromptSaveState();
    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      field("Version", vInput),
      el("div", { className: "inline-form" }, editToggle, cancelBtn),
      previewWrap,
      editorWrap,
      saveBtn
    ));

    // Associate to API key
    panel.appendChild(el("h3", null, "Associate to API Key"));
    var keySelect = el("select", null, el("option", { value: "" }, "Loading API keys..."));
    var assocBtn = el("button", { type: "button" }, "Associate");
    var selectedPromptKeyId = null;
    if (cachedKeys && cachedKeys.length) {
      var selectedPromptKey = cachedKeys.find(function (key) {
        return key.system_prompt_id && String(key.system_prompt_id) === String(promptId);
      });
      selectedPromptKeyId = selectedPromptKey ? selectedPromptKey._id : null;
    }
    fillKeySelect(keySelect, cachedKeys, selectedPromptKeyId);
    assocBtn.disabled = !cachedKeys || !cachedKeys.length;
    if (!cachedKeys) {
      loadAvailableKeys().then(function (keys) {
        var matchedKey = keys.find(function (key) {
          return key.system_prompt_id && String(key.system_prompt_id) === String(promptId);
        });
        fillKeySelect(keySelect, keys, matchedKey ? matchedKey._id : null);
        assocBtn.disabled = !keys.length;
      });
    }
    assocBtn.addEventListener("click", async function () {
      var k = keySelect.value;
      if (!k || !promptId) return;
      assocBtn.disabled = true;
      try {
        await api("POST", "/admin/api-keys/" + encodeURIComponent(k) + "/prompt", { prompt_id: promptId });
        showStatus("Prompt associated with key");
      } catch (err) {
        showError(err.message);
      } finally {
        assocBtn.disabled = keySelect.disabled;
      }
    });
    panel.appendChild(el("div", { className: "inline-form" }, field("API Key", keySelect), assocBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Prompt");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete Prompt",
        message: 'Delete prompt "' + prompt.name + '"? This cannot be undone.',
        expectedText: prompt.name,
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", "/admin/prompts/" + encodeURIComponent(promptId));
          showStatus("Prompt deleted");
          onRefresh();
        }
      });
    });
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Deleting a prompt breaks future associations that depend on it."),
      deleteBtn
    ));
  }

  // ==================================================================
  // TAB: Ops
  // ==================================================================
  function renderOps(container) {
    if (!cachedAdapters) {
      clear(container);
      container.appendChild(el("div", { className: "panel" }, el("h2", null, "Ops"), skeleton()));
      loadAdaptersAndPrompts().then(function () {
        if (document.body.contains(container)) renderOps(container);
      });
      return;
    }

    var grid = el("div", { className: "panel-grid" });
    container.appendChild(grid);

    // Reload panel
    var reloadPanel = el("div", { className: "panel action-panel" });
    reloadPanel.appendChild(el("h2", null, "Reload Configuration"));
    var filterSelect = el("select", null, el("option", { value: "" }, "All adapters"));
    if (cachedAdapters && cachedAdapters.length) {
      cachedAdapters.forEach(function (adapterName) {
        filterSelect.appendChild(el("option", { value: adapterName }, adapterName));
      });
    }
    reloadPanel.appendChild(el("div", { className: "stack" }, field("Adapter filter", filterSelect, "Optional scope for a targeted reload")));

    var reloadAdaptersBtn = el("button", { type: "button" }, "Reload Adapters");
    reloadAdaptersBtn.addEventListener("click", function () {
      confirmAction({
        title: "Reload Adapters",
        message: "Reload adapter configuration" + (filterSelect.value ? " for " + filterSelect.value : "") + "?",
        confirmLabel: "Reload",
        onConfirm: async function () {
          reloadAdaptersBtn.disabled = true;
          try {
            var path = "/admin/reload-adapters";
            var f = filterSelect.value;
            if (f) path += "?adapter_name=" + encodeURIComponent(f);
            var result = await api("POST", path);
            showStatus("Adapters reloaded: " + (result.message || "OK"));
          } finally {
            reloadAdaptersBtn.disabled = false;
          }
        }
      });
    });

    var reloadTemplatesBtn = el("button", { type: "button" }, "Reload Templates");
    reloadTemplatesBtn.addEventListener("click", function () {
      confirmAction({
        title: "Reload Templates",
        message: "Reload templates" + (filterSelect.value ? " for " + filterSelect.value : "") + "?",
        confirmLabel: "Reload",
        onConfirm: async function () {
          reloadTemplatesBtn.disabled = true;
          try {
            var path = "/admin/reload-templates";
            var f = filterSelect.value;
            if (f) path += "?adapter_name=" + encodeURIComponent(f);
            var result = await api("POST", path);
            showStatus("Templates reloaded: " + (result.message || "OK"));
          } finally {
            reloadTemplatesBtn.disabled = false;
          }
        }
      });
    });

    reloadPanel.appendChild(el("div", { className: "inline-form", style: "margin-top:var(--sp-3)" },
      reloadAdaptersBtn, reloadTemplatesBtn
    ));

    grid.appendChild(reloadPanel);

    // Log viewer panel
    var logPanel = el("div", { className: "panel log-panel" });
    logPanel.appendChild(el("h2", null, "Server Logs"));
    var logFilename = el("div", { className: "muted" }, "Loading latest log...");
    var logUpdated = el("div", { className: "muted" }, "");
    var autoRefreshInput = el("input", { type: "checkbox" });
    autoRefreshInput.checked = true;
    var refreshLogsBtn = el("button", { className: "secondary", type: "button" }, "Refresh Logs");
    var logOutput = el("pre", { className: "log-viewer" }, "Loading logs...");

    var logsInFlight = false;

    function scheduleLogRefresh() {
      clearOpsLogPolling();
      if (activeTab !== "ops" || !autoRefreshInput.checked) return;
      if (document.hidden) return;
      opsLogPollTimer = setTimeout(function () {
        loadLogs(true);
      }, 3000);
    }

    async function loadLogs(silent) {
      if (logsInFlight) return;
      logsInFlight = true;
      refreshLogsBtn.disabled = true;
      try {
        var result = await api("GET", "/admin/logs/tail?lines=200");
        logFilename.textContent = result.filename || "orbit.log";
        logUpdated.textContent = result.updated_at ? "Updated " + result.updated_at : "";
        logOutput.textContent = (result.lines || []).join("\n") || "No log lines available.";
      } catch (err) {
        if (!silent) showError(err.message);
        logOutput.textContent = "Failed to load logs.";
      } finally {
        logsInFlight = false;
        refreshLogsBtn.disabled = false;
        scheduleLogRefresh();
      }
    }

    refreshLogsBtn.addEventListener("click", function () { loadLogs(false); });
    autoRefreshInput.addEventListener("change", function () {
      scheduleLogRefresh();
    });

    logPanel.appendChild(el("div", { className: "log-toolbar" },
      el("div", { className: "log-meta" }, logFilename, logUpdated),
      el("div", { className: "log-controls" },
        el("label", { className: "check-row" }, autoRefreshInput, "Auto-refresh"),
        refreshLogsBtn
      )
    ));
    logPanel.appendChild(logOutput);
    grid.appendChild(logPanel);

    // Server control panel
    var controlPanel = el("div", { className: "panel action-panel" });
    controlPanel.appendChild(el("h2", null, "Server Control"));
    controlPanel.appendChild(el("p", { className: "muted" },
      "Restart applies the current runtime command again. Shutdown terminates the ORBIT process until it is started externally."
    ));

    var restartBtn = el("button", { className: "secondary", type: "button" }, "Restart");
    restartBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Restart Server",
        message: "Type RESTART to restart the ORBIT server process in place.",
        expectedText: "RESTART",
        confirmLabel: "Restart",
        isDanger: false,
        onConfirm: async function () {
          restartBtn.disabled = true;
          try {
            await api("POST", "/admin/restart");
            showStatus("Server restart initiated");
          } finally {
            restartBtn.disabled = false;
          }
        }
      });
    });

    var shutdownBtn = el("button", { className: "danger", type: "button" }, "Shutdown");
    shutdownBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Shutdown Server",
        message: "Type SHUTDOWN to terminate the ORBIT server process.",
        expectedText: "SHUTDOWN",
        confirmLabel: "Shutdown",
        onConfirm: async function () {
          shutdownBtn.disabled = true;
          try {
            await api("POST", "/admin/shutdown");
            showStatus("Server shutdown initiated");
          } finally {
            shutdownBtn.disabled = false;
          }
        }
      });
    });

    controlPanel.appendChild(el("div", { className: "inline-form", style: "margin-top:var(--sp-3)" }, restartBtn, shutdownBtn));
    grid.appendChild(controlPanel);

    loadLogs(false);
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
