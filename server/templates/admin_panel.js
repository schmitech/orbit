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
  let cachedAdapterCapabilities = null;
  let cachedPrompts = null;
  let cachedKeys = null;

  // Selection state per tab
  let selectedUser = null;
  let selectedKey = null;
  let selectedPrompt = null;
  let messageCounter = 0;
  let opsLogPollTimer = null;

  // Monitoring state
  let metricsWs = null;
  let metricsReconnectTimer = null;
  let selectedWindowMinutes = 5;
  let lastMetricsSnapshot = null;
  let lastAdapters = {};
  let adapterSearchFilter = "";
  let adapterStateFilter = "all";
  let overviewCharts = {};
  let monitoringThresholds = { cpu: 90, memory: 85, error_rate: 5, response_time_ms: 5000 };

  // ------------------------------------------------------------------
  // API endpoint paths
  // ------------------------------------------------------------------
  var ENDPOINTS = {
    token: "/admin/api/token",
    logout: "/admin/logout",
    health: "/health",
    healthAdapters: "/health/adapters",
    register: "/auth/register",
    users: "/auth/users",
    changePassword: "/auth/change-password",
    resetPassword: "/auth/reset-password",
    apiKeys: "/admin/api-keys",
    prompts: "/admin/prompts",
    adapterCapabilities: "/admin/adapters/capabilities",
    jobs: "/admin/jobs",
    logsTail: "/admin/logs/tail",
    renderMarkdown: "/admin/render-markdown",
    reloadAdapters: "/admin/reload-adapters",
    reloadTemplates: "/admin/reload-templates",
    restart: "/admin/restart",
    shutdown: "/admin/shutdown",
    adminExport: "/admin/export",
    login: "/admin/login",
  };

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

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
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
  // Server lifecycle overlay
  // ------------------------------------------------------------------
  function showServerOverlay(opts) {
    // opts: { title, detail, mode: "restart"|"shutdown" }
    var existing = document.getElementById("server-overlay");
    if (existing) existing.remove();

    var overlay = el("div", { id: "server-overlay", className: "server-overlay" });
    var card = el("div", { className: "server-overlay-card" });

    var spinner = el("div", { className: "server-overlay-spinner" });
    var title = el("h2", { className: "server-overlay-title" }, opts.title);
    var detail = el("p", { className: "server-overlay-detail", id: "server-overlay-detail" }, opts.detail || "");
    var elapsed = el("p", { className: "server-overlay-elapsed", id: "server-overlay-elapsed" }, "");

    card.appendChild(spinner);
    card.appendChild(title);
    card.appendChild(detail);
    card.appendChild(elapsed);

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    // Disconnect live connections
    disconnectMetricsWs();
    clearOpsLogPolling();

    // Track elapsed time
    var startTime = Date.now();
    var elapsedTimer = setInterval(function () {
      var secs = Math.floor((Date.now() - startTime) / 1000);
      var elEl = document.getElementById("server-overlay-elapsed");
      if (elEl) elEl.textContent = secs + "s elapsed";
    }, 1000);

    if (opts.mode === "restart") {
      // Wait a moment for server to go down, then start polling
      setTimeout(function () {
        pollServerHealth();
      }, 2000);
    } else {
      // Shutdown mode: show terminated message, then keep polling in background
      setTimeout(function () {
        var detail2 = document.getElementById("server-overlay-detail");
        if (detail2) detail2.textContent = "The server process has been terminated. Start it with 'orbit start' \u2014 this page will reload automatically.";
        var spinner2 = overlay.querySelector(".server-overlay-spinner");
        if (spinner2) spinner2.classList.add("stopped");
        // Start background polling — auto-reload when someone starts the server
        pollServerHealth();
      }, 3000);
    }

    function pollServerHealth() {
      // Use an <img> probe to avoid console network errors from fetch.
      // Browsers don't log ERR_CONNECTION_REFUSED for image loads.
      function probe() {
        var img = new Image();
        var done = false;
        var timer = setTimeout(function () {
          if (done) return;
          done = true;
          setTimeout(probe, 3000);
        }, 2500);

        img.onload = function () {
          if (done) return;
          done = true;
          clearTimeout(timer);
          // Image loaded means server is up — verify with a real fetch
          fetch(ENDPOINTS.health, { method: "GET", credentials: "same-origin" })
            .then(function (r) {
              if (r.ok) {
                clearInterval(elapsedTimer);
                var detailEl = document.getElementById("server-overlay-detail");
                if (detailEl) detailEl.textContent = "Server is back online. Reloading...";
                var spinner3 = document.querySelector(".server-overlay-spinner");
                if (spinner3) { spinner3.classList.remove("stopped"); spinner3.classList.add("done"); }
                setTimeout(function () { window.location.reload(); }, 800);
              } else {
                setTimeout(probe, 3000);
              }
            })
            .catch(function () { setTimeout(probe, 3000); });
        };
        img.onerror = function () {
          if (done) return;
          done = true;
          clearTimeout(timer);
          setTimeout(probe, 3000);
        };
        // Probe the favicon — any static asset works
        img.src = "/static/favicon.svg?_t=" + Date.now();
      }

      probe();
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
    var inFlight = false;
    var backdrop = el("div", { className: "dialog-backdrop" });
    var cancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var confirmBtn = el("button", { className: isDanger ? "danger" : "", type: "button" }, confirmLabel || "Confirm");
    var defaultConfirmContent = confirmBtn.textContent;
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
      if (inFlight) return;
      document.removeEventListener("keydown", handler);
      backdrop.remove();
      if (previousFocus && previousFocus.focus) previousFocus.focus();
    }
    cancelBtn.addEventListener("click", close);
    confirmBtn.addEventListener("click", async function () {
      if (inFlight) return;
      inFlight = true;
      confirmBtn.disabled = true;
      cancelBtn.disabled = true;
      if (confirmBtn.dataset.loadingLabel) {
        clear(confirmBtn);
        confirmBtn.appendChild(el("span", { className: "button-spinner", "aria-hidden": "true" }));
        confirmBtn.appendChild(el("span", null, confirmBtn.dataset.loadingLabel));
      }
      try {
        await onConfirm();
        inFlight = false;
        close();
      } catch (err) {
        inFlight = false;
        confirmBtn.disabled = false;
        cancelBtn.disabled = false;
        clear(confirmBtn);
        confirmBtn.appendChild(document.createTextNode(defaultConfirmContent));
        showError(err.message);
      }
    });
    backdrop.addEventListener("click", function (e) {
      if (inFlight) return;
      if (e.target === backdrop) close();
    });
    function handler(e) {
      if (e.key === "Escape" && !inFlight) close();
      if (e.key === "Tab") trapFocus(e, dialog);
    }
    document.addEventListener("keydown", handler);
  }

  function confirmAction(options) {
    confirmDialog(options.title, options.message, options.onConfirm, options.confirmLabel, !!options.isDanger);
    var dialogs = document.querySelectorAll(".confirm-dialog .dialog-actions button:last-child");
    var confirmBtn = dialogs[dialogs.length - 1];
    if (confirmBtn && options.loadingLabel) {
      confirmBtn.dataset.loadingLabel = options.loadingLabel;
    }
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
  // Button action helper — eliminates repeated try/catch/finally/disable
  // ------------------------------------------------------------------
  async function withButton(btn, fn, successMsg) {
    btn.disabled = true;
    try {
      await fn();
      if (successMsg) showStatus(successMsg);
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
    }
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
      window.location.href = ENDPOINTS.login + "?next=/admin";
      throw new Error("Session expired");
    }
    var text = await resp.text();
    var data;
    try { data = JSON.parse(text); } catch (_) { data = text; }
    if (!resp.ok) {
      var msg = text || resp.statusText;
      if (data && typeof data === "object") {
        if (Array.isArray(data.detail)) {
          msg = data.detail.map(function (item) {
            if (item && typeof item === "object") {
              return item.msg || JSON.stringify(item);
            }
            return String(item);
          }).join("; ");
        } else if (data.detail && typeof data.detail === "object") {
          msg = data.detail.msg || JSON.stringify(data.detail);
        } else if (data.detail) {
          msg = String(data.detail);
        } else if (data.message) {
          msg = String(data.message);
        } else {
          msg = JSON.stringify(data);
        }
      }
      throw new Error(msg);
    }
    return data;
  }

  // ------------------------------------------------------------------
  // Init
  // ------------------------------------------------------------------
  async function init() {
    try {
      var resp = await fetch(ENDPOINTS.token);
      if (!resp.ok) {
        window.location.href = ENDPOINTS.login + "?next=/admin";
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
    { id: "prompts", label: "Personas" },
    { id: "ops", label: "Ops" },
  ];

  function renderShell() {
    var app = document.getElementById("app");
    clear(app);

    // Topbar with inline nav
    var logoutBtn = el("button", { type: "button", className: "topbar-logout" }, "Logout");
    logoutBtn.addEventListener("click", doLogout);

    var nav = el("nav", { className: "topbar-nav", role: "tablist", "aria-label": "Admin sections" });
    TABS.forEach(function (t) {
      var isSelected = t.id === activeTab;
      var btn = el("a", {
        id: "tab-" + t.id,
        role: "tab",
        href: "#",
        "aria-selected": String(isSelected),
        "aria-controls": "tab-content",
        tabindex: isSelected ? "0" : "-1",
        className: "topbar-nav-link" + (isSelected ? " active" : ""),
        dataset: { tab: t.id },
      }, t.label);
      btn.addEventListener("click", function (e) { e.preventDefault(); switchTab(t.id); });
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
      nav.appendChild(btn);
    });

    var topbar = el("header", { className: "topbar", role: "banner" },
      el("div", { className: "brand-block" },
        el("img", {
          src: "/static/orbit-logo-dark.png",
          alt: "",
          className: "brand-logo",
        })
      ),
      nav,
      el("div", { className: "topbar-actions" },
        el("span", null, currentUser ? currentUser.role : ""),
        logoutBtn
      )
    );

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

    var shell = el("div", { className: "app-shell" }, topbar, toastRegion, content);
    app.appendChild(shell);

    renderTab();
  }

  function switchTab(id) {
    // Disconnect monitoring when leaving overview
    if (activeTab === "overview" && id !== "overview") {
      disconnectMetricsWs();
      destroyOverviewCharts();
    }
    activeTab = id;
    document.querySelectorAll(".topbar-nav-link").forEach(function (b) {
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
      await fetch(ENDPOINTS.logout, { method: "POST" });
    } catch (_) {}
    authToken = null;
    currentUser = null;
    window.location.href = ENDPOINTS.login + "?next=/admin";
  }

  // ==================================================================
  // TAB: Overview (with integrated monitoring)
  // ==================================================================

  // --- Monitoring utility functions ---

  function clampPercentage(v) {
    if (typeof v !== "number" || isNaN(v)) return 0;
    return Math.min(100, Math.max(0, v));
  }

  function formatNum(value, frac) {
    var n = Number(value);
    if (Number.isNaN(n)) return value != null ? String(value) : "0";
    if (frac == null) return n.toLocaleString();
    return n.toLocaleString(undefined, { minimumFractionDigits: frac, maximumFractionDigits: frac });
  }

  function escapeHtml(value) {
    if (value == null) return "";
    var lookup = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(value).replace(/[&<>"']/g, function (c) { return lookup[c] || c; });
  }

  function getChartDensityConfig() {
    if (selectedWindowMinutes <= 5) return { targetPoints: 60, maxTicks: 6 };
    if (selectedWindowMinutes <= 15) return { targetPoints: 45, maxTicks: 7 };
    if (selectedWindowMinutes <= 30) return { targetPoints: 36, maxTicks: 7 };
    return { targetPoints: 24, maxTicks: 8 };
  }

  function aggregateSeries(labels, seriesList) {
    if (!labels.length) return { labels: labels, seriesList: seriesList };
    var density = getChartDensityConfig();
    if (labels.length <= density.targetPoints) return { labels: labels, seriesList: seriesList };
    var bucketSize = Math.ceil(labels.length / density.targetPoints);
    var aggLabels = [];
    var aggSeries = seriesList.map(function () { return []; });
    for (var start = 0; start < labels.length; start += bucketSize) {
      var end = Math.min(start + bucketSize, labels.length);
      aggLabels.push(labels[end - 1]);
      seriesList.forEach(function (series, idx) {
        var bucket = series.slice(start, end).filter(function (v) { return typeof v === "number" && !isNaN(v); });
        aggSeries[idx].push(bucket.length ? bucket.reduce(function (s, v) { return s + v; }, 0) / bucket.length : null);
      });
    }
    return { labels: aggLabels, seriesList: aggSeries };
  }

  function getMaxPoints(timestamps) {
    if (!Array.isArray(timestamps) || timestamps.length < 2) return Math.ceil((selectedWindowMinutes * 60) / 5);
    var intervals = [];
    for (var i = 1; i < timestamps.length; i++) {
      var d = (new Date(timestamps[i]).getTime() - new Date(timestamps[i - 1]).getTime()) / 1000;
      if (isFinite(d) && d > 0) intervals.push(d);
    }
    if (!intervals.length) return Math.ceil((selectedWindowMinutes * 60) / 5);
    var avg = intervals.reduce(function (s, v) { return s + v; }, 0) / intervals.length;
    return Math.max(1, Math.ceil((selectedWindowMinutes * 60) / avg));
  }

  function updateChartWithActiveTooltip(chart, labels, datasetValues) {
    var active = chart.getActiveElements();
    chart.data.labels = labels;
    chart.data.datasets.forEach(function (ds, idx) { ds.data = datasetValues[idx] || []; });
    chart.update("none");
    if (!labels.length) { chart.setActiveElements([]); return; }
    if (active.length) {
      var reactivated = active.map(function (a) {
        return { datasetIndex: a.datasetIndex, index: Math.min(labels.length - 1, Math.max(0, a.index)) };
      }).filter(function (a) { var m = chart.getDatasetMeta(a.datasetIndex); return m && m.data && m.data[a.index]; });
      if (reactivated.length) {
        chart.setActiveElements(reactivated);
        var first = reactivated[0];
        var elem = chart.getDatasetMeta(first.datasetIndex).data[first.index];
        if (elem && chart.tooltip) { chart.tooltip.setActiveElements(reactivated, { x: elem.x, y: elem.y }); chart.tooltip.update(); }
        chart.draw();
      }
    }
  }

  function destroyOverviewCharts() {
    Object.keys(overviewCharts).forEach(function (k) {
      try { overviewCharts[k].destroy(); } catch (_) {}
    });
    overviewCharts = {};
  }

  function disconnectMetricsWs() {
    if (metricsReconnectTimer) { clearInterval(metricsReconnectTimer); metricsReconnectTimer = null; }
    if (metricsWs) { try { metricsWs.close(); } catch (_) {} metricsWs = null; }
  }

  function connectMetricsWs() {
    disconnectMetricsWs();
    var protocol = location.protocol === "https:" ? "wss:" : "ws:";
    var ws = new WebSocket(protocol + "//" + location.host + "/ws/metrics");
    metricsWs = ws;

    ws.onopen = function () {
      if (metricsReconnectTimer) { clearInterval(metricsReconnectTimer); metricsReconnectTimer = null; }
      var dot = document.getElementById("mon-status-dot");
      var txt = document.getElementById("mon-status-text");
      if (dot) { dot.className = "status-dot connected pulse"; }
      if (txt) { txt.textContent = "Connected"; }
    };

    ws.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        if (data.metrics) updateMonitoringMetrics(data.metrics);
        updateMonitoringAdapters(data.adapters || {});
        if (data.thread_pools) updateMonitoringThreadPools(data.thread_pools);
        if (data.datasource_pool) updateMonitoringDatasourcePool(data.datasource_pool);
        if (data.redis_health) updateMonitoringRedisHealth(data.redis_health);
        if (data.pipeline_steps) updateMonitoringPipeline(data.pipeline_steps, data.pipeline_summary);
        if (data.connections) updateMonitoringConnections(data.connections);
      } catch (e) { console.error("Metrics parse error:", e); }
    };

    ws.onclose = function () {
      var dot = document.getElementById("mon-status-dot");
      var txt = document.getElementById("mon-status-text");
      if (dot) { dot.className = "status-dot disconnected"; }
      if (txt) { txt.textContent = "Reconnecting..."; }
      if (!metricsReconnectTimer && activeTab === "overview") {
        metricsReconnectTimer = setInterval(function () { connectMetricsWs(); }, 5000);
      }
    };

    ws.onerror = function () { console.error("Metrics WebSocket error"); };
  }

  // --- Light-theme chart options ---
  var monitoringChartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false, axis: "x" },
    elements: { point: { radius: 0, hoverRadius: 5, hitRadius: 18 } },
    scales: {
      y: { beginAtZero: true, grid: { color: "rgba(15,29,51,0.06)" }, ticks: { color: "#6b7a96" } },
      x: { grid: { color: "rgba(15,29,51,0.06)" }, ticks: { color: "#6b7a96", maxRotation: 0, minRotation: 0 } }
    },
    plugins: { legend: { labels: { color: "#0f1d33" } } }
  };

  function initOverviewCharts() {
    destroyOverviewCharts();
    var ids = ["mon-system-chart", "mon-request-chart", "mon-response-chart", "mon-percentile-chart"];
    var configs = [
      { datasets: [{ label: "CPU %", borderColor: "#2b6cb0", backgroundColor: "rgba(43,108,176,0.1)", tension: 0.25, fill: true, data: [] },
                    { label: "Memory %", borderColor: "#059669", backgroundColor: "rgba(5,150,105,0.1)", tension: 0.25, fill: true, data: [] }] },
      { datasets: [{ label: "Requests/sec", borderColor: "#d97706", backgroundColor: "rgba(217,119,6,0.1)", tension: 0.25, fill: true, data: [] },
                    { label: "Error Rate %", borderColor: "#e11d48", backgroundColor: "rgba(225,29,72,0.1)", tension: 0.25, fill: true, data: [] }] },
      { datasets: [{ label: "Avg Response Time", borderColor: "#7c3aed", backgroundColor: "rgba(124,58,237,0.1)", tension: 0.25, fill: true, data: [] }] },
      { datasets: [{ label: "P50", borderColor: "#059669", fill: false, tension: 0.25, data: [] },
                    { label: "P95", borderColor: "#d97706", fill: false, tension: 0.25, data: [] },
                    { label: "P99", borderColor: "#e11d48", fill: false, tension: 0.25, data: [] }] }
    ];

    ids.forEach(function (id, i) {
      var canvas = document.getElementById(id);
      if (!canvas) return;
      overviewCharts[id] = new Chart(canvas, {
        type: "line",
        data: { labels: [], datasets: configs[i].datasets.map(function (d) { return Object.assign({}, d, { pointRadius: 0, pointHoverRadius: 5, pointHitRadius: 18 }); }) },
        options: i === 1
          ? Object.assign({}, monitoringChartOpts, { scales: Object.assign({}, monitoringChartOpts.scales, { y: Object.assign({}, monitoringChartOpts.scales.y, { ticks: Object.assign({}, monitoringChartOpts.scales.y.ticks, { stepSize: 1, precision: 0 }), min: 0 }) }) })
          : monitoringChartOpts
      });
    });
  }

  // --- Update functions ---

  function updateMonitoringMetrics(data) {
    lastMetricsSnapshot = data;
    if (data.thresholds) monitoringThresholds = Object.assign({}, monitoringThresholds, data.thresholds);

    var cpu = clampPercentage(data.system.cpu_percent);
    var mem = clampPercentage(data.system.memory_percent);
    var errRate = clampPercentage(data.requests.error_rate);
    var reliability = clampPercentage(100 - errRate);

    setText("mon-cpu-value", formatNum(cpu, 1));
    setProgressBar("mon-cpu-bar", cpu, cpu >= monitoringThresholds.cpu ? "red" : cpu >= monitoringThresholds.cpu * 0.82 ? "amber" : "sky");
    setText("mon-cpu-sub", formatNum(cpu, 1) + "% utilization");

    setText("mon-mem-value", formatNum(data.system.memory_gb, 2));
    setProgressBar("mon-mem-bar", mem, mem >= monitoringThresholds.memory ? "red" : mem >= monitoringThresholds.memory * 0.82 ? "amber" : "green");
    setText("mon-mem-sub", formatNum(mem, 1) + "% of system");

    setText("mon-rps-value", formatNum(data.requests.per_second, 1));
    setText("mon-rps-sub", formatNum(data.requests.total) + " total");

    setText("mon-rel-value", formatNum(reliability, 2));
    setProgressBar("mon-rel-bar", reliability, errRate >= monitoringThresholds.error_rate ? "red" : errRate > 0 ? "amber" : "green");
    setText("mon-rel-sub", errRate > 0 ? formatNum(errRate, 2) + "% error rate" : "No errors");

    setText("mon-last-update", new Date().toLocaleTimeString());

    // Endpoint stats
    if (data.endpoint_stats && data.endpoint_stats.length > 0) {
      updateMonitoringEndpoints(data.endpoint_stats);
    }

    // Charts
    if (data.time_series && data.time_series.timestamps && data.time_series.timestamps.length > 0) {
      var labels = data.time_series.timestamps.map(function (t) { return new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); });
      var maxPts = getMaxPoints(data.time_series.timestamps);
      var startIdx = Math.max(0, labels.length - maxPts);
      var trimmed = labels.slice(startIdx);

      var charts = [
        { key: "mon-system-chart", series: [data.time_series.cpu.slice(startIdx), data.time_series.memory.slice(startIdx)] },
        { key: "mon-request-chart", series: [data.time_series.requests_per_second.slice(startIdx), data.time_series.error_rate.slice(startIdx)] },
        { key: "mon-response-chart", series: [data.time_series.response_time.slice(startIdx)] },
        { key: "mon-percentile-chart", series: [data.time_series.response_time_p50.slice(startIdx), data.time_series.response_time_p95.slice(startIdx), data.time_series.response_time_p99.slice(startIdx)] }
      ];

      charts.forEach(function (c) {
        var chart = overviewCharts[c.key];
        if (!chart) return;
        var density = getChartDensityConfig();
        if (chart.options && chart.options.scales && chart.options.scales.x && chart.options.scales.x.ticks) {
          chart.options.scales.x.ticks.maxTicksLimit = density.maxTicks;
        }
        var agg = aggregateSeries(trimmed, c.series);
        updateChartWithActiveTooltip(chart, agg.labels, agg.seriesList);
      });
    }
  }

  function setText(id, text) {
    var e = document.getElementById(id);
    if (e) e.textContent = text;
  }

  function setProgressBar(id, pct, color) {
    var bar = document.getElementById(id);
    if (!bar) return;
    bar.style.width = clampPercentage(pct).toFixed(1) + "%";
    bar.className = "monitoring-progress-bar " + color;
  }

  function updateMonitoringEndpoints(endpoints) {
    var section = document.getElementById("mon-endpoint-section");
    var tbody = document.getElementById("mon-endpoint-tbody");
    if (!section || !tbody) return;
    if (!endpoints || !endpoints.length) { section.style.display = "none"; return; }
    section.style.display = "";
    var methodColors = { GET: "method-get", POST: "method-post", PUT: "method-put", DELETE: "method-delete" };
    clear(tbody);
    endpoints.forEach(function (ep) {
      var method = (ep.method || "GET").toUpperCase();
      tbody.appendChild(el("tr", null,
        el("td", null, el("span", { className: "method-badge " + (methodColors[method] || "method-get") }, method)),
        el("td", { style: "font-family:var(--font-mono);font-size:var(--text-xs)" }, ep.endpoint),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.total_requests)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.avg_latency_ms, 1) + " ms"),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.error_rate, 2) + "%")
      ));
    });
  }

  function monitoringStatCell(label, value) {
    return el("div", null,
      el("div", { style: "text-transform:uppercase;letter-spacing:0.1em;font-size:0.65rem" }, label),
      el("div", { style: "font-weight:700;color:var(--ink)" }, value)
    );
  }

  function monitoringSummaryCard(label, value, hint) {
    var children = [
      el("p", { className: "label" }, label),
      el("p", { className: "value" }, value)
    ];
    if (hint) children.push(el("p", { className: "hint" }, hint));
    return el("div", { className: "monitoring-summary-card" }, children);
  }

  function updateMonitoringPipeline(steps, summary) {
    var section = document.getElementById("mon-pipeline-section");
    if (!section) return;
    if (!steps || !Object.keys(steps).length) { section.style.display = "none"; return; }
    section.style.display = "";
    var summaryEl = document.getElementById("mon-pipeline-summary");
    if (summaryEl && summary) {
      clear(summaryEl);
      summaryEl.appendChild(monitoringSummaryCard("Total Executions", formatNum(summary.total_executions)));
      summaryEl.appendChild(monitoringSummaryCard("Success Rate", formatNum((summary.success_rate * 100), 1) + "%"));
      summaryEl.appendChild(monitoringSummaryCard("Avg Pipeline Time", formatNum(summary.avg_time_ms, 1) + " ms"));
    }
    var container = document.getElementById("mon-pipeline-steps");
    if (!container) return;
    var entries = Object.entries(steps).sort(function (a, b) { return b[1].total_executions - a[1].total_executions; });
    clear(container);
    entries.forEach(function (pair) {
      var name = pair[0], s = pair[1];
      var pct = s.success_rate * 100;
      var badgeCls = pct < 80 ? "red" : pct < 95 ? "amber" : "green";
      container.appendChild(el("div", { className: "monitoring-adapter-card" },
        el("div", { style: "display:flex;justify-content:space-between;align-items:center" },
          el("span", { style: "font-weight:700;font-size:var(--text-sm)" }, name),
          el("span", { className: "monitoring-badge " + badgeCls }, formatNum(pct, 1) + "%")
        ),
        el("div", { style: "display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--sp-2);font-size:var(--text-xs);color:var(--ink-muted)" },
          monitoringStatCell("Avg", formatNum(s.avg_time_ms, 1) + " ms"),
          monitoringStatCell("Min", formatNum(s.min_time_ms, 1) + " ms"),
          monitoringStatCell("Max", formatNum(s.max_time_ms, 1) + " ms")
        ),
        el("div", { style: "font-size:var(--text-xs);color:var(--ink-muted)" }, formatNum(s.total_executions) + " executions")
      ));
    });
  }

  function updateMonitoringAdapters(adapters) {
    lastAdapters = adapters || {};
    var section = document.getElementById("mon-adapter-section");
    if (!section) return;
    var entries = Object.entries(lastAdapters);
    if (!entries.length) { section.style.display = "none"; return; }
    section.style.display = "";
    renderMonitoringAdapterList(lastAdapters);
  }

  function renderMonitoringAdapterList(adapters) {
    var summaryEl = document.getElementById("mon-adapter-summary");
    var container = document.getElementById("mon-adapter-list");
    if (!summaryEl || !container) return;
    var entries = Object.entries(adapters || {});
    if (!entries.length) {
      clear(summaryEl);
      summaryEl.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, "No adapter telemetry available"));
      clear(container);
      return;
    }
    var counts = entries.reduce(function (acc, pair) {
      var state = (pair[1] && pair[1].state || "unknown").toLowerCase();
      acc[state] = (acc[state] || 0) + 1; acc.total += 1; return acc;
    }, { total: 0, open: 0, half_open: 0, closed: 0, unknown: 0 });
    clear(summaryEl);
    [
      { label: "Total", key: "total", hint: "Monitored" },
      { label: "Open", key: "open", hint: "Tripped" },
      { label: "Half-open", key: "half_open", hint: "Testing" },
      { label: "Closed", key: "closed", hint: "Healthy" }
    ].forEach(function (c) {
      summaryEl.appendChild(monitoringSummaryCard(c.label, String(counts[c.key] || 0), c.hint));
    });

    var stateOrder = { open: 0, half_open: 1, closed: 2, unknown: 3 };
    var filtered = entries.filter(function (pair) {
      var st = (pair[1] && pair[1].state || "unknown").toLowerCase();
      var matchState = adapterStateFilter === "all" || adapterStateFilter === st;
      var matchSearch = !adapterSearchFilter || pair[0].toLowerCase().includes(adapterSearchFilter);
      return matchState && matchSearch;
    }).sort(function (a, b) {
      var sa = (a[1] && a[1].state || "unknown").toLowerCase();
      var sb = (b[1] && b[1].state || "unknown").toLowerCase();
      var d = (stateOrder[sa] || 3) - (stateOrder[sb] || 3);
      return d !== 0 ? d : a[0].localeCompare(b[0]);
    });

    clear(container);
    if (!filtered.length) {
      container.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, "No adapters match the current filters."));
      return;
    }
    var badgeMap = { closed: "green", open: "red", half_open: "amber", unknown: "muted" };
    filtered.forEach(function (pair) {
      var name = pair[0], status = pair[1];
      var state = (status && status.state || "unknown").toLowerCase();
      var failures = (status && status.failure_count) || 0;
      var reqs = (status && (status.request_count || status.success_count)) || 0;
      var latency = status && status.average_latency_ms;
      var latencyStr = typeof latency === "number" ? formatNum(latency, latency >= 100 ? 0 : 1) + " ms" : "\u2014";
      container.appendChild(el("div", { className: "monitoring-adapter-card" },
        el("div", { style: "display:flex;justify-content:space-between;align-items:start;gap:var(--sp-2)" },
          el("div", { style: "min-width:0" },
            el("p", { style: "font-weight:700;font-size:var(--text-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap", title: name }, name),
            el("p", { style: "font-size:var(--text-xs);color:var(--ink-muted)" }, "Failures: " + formatNum(failures))
          ),
          el("span", { className: "monitoring-badge " + (badgeMap[state] || "muted") }, state.replace("_", " "))
        ),
        el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-2);font-size:var(--text-xs);color:var(--ink-muted)" },
          monitoringStatCell("Requests", formatNum(reqs)),
          monitoringStatCell("Latency", latencyStr)
        )
      ));
    });
  }

  function updateMonitoringThreadPools(pools) {
    var section = document.getElementById("mon-threadpool-section");
    if (!section) return;
    var entries = Object.entries(pools || {});
    if (!entries.length) { section.style.display = "none"; return; }
    section.style.display = "";
    var container = document.getElementById("mon-threadpool-list");
    if (!container) return;
    clear(container);
    entries.forEach(function (pair) {
      var name = pair[0], pool = pair[1];
      var util = pool.max_workers > 0 ? clampPercentage((pool.active_threads / pool.max_workers) * 100) : 0;
      var isIdle = pool.active_threads === 0 && pool.queued_tasks === 0;
      var barColor = isIdle ? "muted" : util >= 90 ? "red" : util >= 75 ? "amber" : "green";
      var badgeCls = isIdle ? "muted" : util >= 90 ? "red" : util >= 75 ? "amber" : "green";
      var card = el("div", { className: "thread-pool-card" },
        el("div", { style: "display:flex;justify-content:space-between;align-items:center" },
          el("h4", null, name),
          el("span", { className: "monitoring-badge " + badgeCls }, util.toFixed(1) + "%")
        ),
        el("div", { className: "monitoring-stats-row" },
          el("span", { className: "stats-label" }, "Active Threads"),
          el("span", { className: "stats-value" }, pool.active_threads + " / " + pool.max_workers)
        ),
        el("div", { className: "monitoring-stats-row" },
          el("span", { className: "stats-label" }, "Queued Tasks"),
          el("span", { className: "stats-value" }, String(pool.queued_tasks === "N/A" ? "0" : pool.queued_tasks))
        ),
        el("div", { className: "monitoring-progress-track" },
          el("div", { id: "tp-bar-" + name, className: "monitoring-progress-bar " + barColor, style: "width:" + Math.max(util, 2).toFixed(1) + "%" })
        ),
        isIdle ? el("div", { style: "font-size:var(--text-xs);color:var(--ink-muted);margin-top:var(--sp-1)" }, "Pool idle \u2014 threads spawn on demand") : null
      );
      container.appendChild(card);
    });
  }

  function updateMonitoringRedisHealth(data) {
    var section = document.getElementById("mon-redis-section");
    if (!section) return;
    if (!data || !data.enabled) { section.style.display = "none"; return; }
    section.style.display = "";
    var statusEl = document.getElementById("mon-redis-status");
    if (statusEl) {
      statusEl.textContent = data.initialized ? "Connected" : "Disconnected";
      statusEl.style.color = data.initialized ? "var(--success-text)" : "var(--danger-text)";
    }
    var cb = data.circuit_breaker || {};
    setText("mon-redis-cb", (cb.state || "unknown").replace("_", "-"));
    setText("mon-redis-failures", (cb.failure_count || 0) + " / " + (cb.max_failures || 5));
    var pool = data.pool || {};
    var inUse = pool.in_use_connections || 0;
    var maxC = pool.max_connections || 0;
    setText("mon-redis-pool", inUse + " / " + maxC);
    var util = maxC > 0 ? clampPercentage((inUse / maxC) * 100) : 0;
    setProgressBar("mon-redis-bar", util, util >= 90 ? "red" : util >= 70 ? "amber" : "green");
  }

  function updateMonitoringDatasourcePool(data) {
    var section = document.getElementById("mon-datasource-section");
    if (!section) return;
    if (!data || !(data.total_cached_datasources > 0)) { section.style.display = "none"; return; }
    section.style.display = "";
    setText("mon-ds-total", formatNum(data.total_cached_datasources || 0));
    setText("mon-ds-refs", formatNum(data.total_references || 0));
    var eff = data.total_references > 0 ? ((data.total_references - data.total_cached_datasources) / data.total_references * 100) : 0;
    setText("mon-ds-efficiency", formatNum(Math.max(0, eff), 1) + "%");
    var container = document.getElementById("mon-ds-list");
    if (!container || !data.datasource_keys) return;
    clear(container);
    data.datasource_keys.forEach(function (key) {
      var refCount = (data.reference_counts && data.reference_counts[key]) || 0;
      var parts = key.split(":");
      var dsType = parts[0] || "unknown";
      var connInfo = parts.slice(1).join(":") || "default";
      var badgeCls = refCount >= 5 ? "green" : refCount >= 3 ? "green" : refCount === 2 ? "amber" : "muted";
      container.appendChild(el("div", { className: "monitoring-adapter-card" },
        el("div", { style: "display:flex;justify-content:space-between;align-items:center" },
          el("div", null,
            el("p", { style: "font-weight:700;font-size:var(--text-sm)" }, dsType),
            el("p", { style: "font-size:var(--text-xs);color:var(--ink-muted);font-family:var(--font-mono)" }, connInfo)
          ),
          el("span", { className: "monitoring-badge " + badgeCls }, refCount + " ref" + (refCount !== 1 ? "s" : ""))
        )
      ));
    });
  }

  function updateMonitoringConnections(conn) {
    setText("mon-ws-clients", (conn.websocket_clients || 0).toString());
    setText("mon-active-sessions", (conn.active_sessions || 0).toString());
  }

  // --- Render Overview ---
  async function renderOverview(container) {
    // 1. Toolbar
    var toolbar = el("div", { className: "monitoring-toolbar" },
      el("div", { className: "monitoring-toolbar-left" },
        el("div", { id: "mon-status-dot", className: "status-dot disconnected" }),
        el("span", { id: "mon-status-text", style: "font-size:var(--text-sm);color:var(--ink-muted)" }, "Connecting..."),
        el("span", { style: "font-size:var(--text-xs);color:var(--ink-muted)" }, "Last update: "),
        el("span", { id: "mon-last-update", style: "font-size:var(--text-xs);font-family:var(--font-mono);color:var(--ink-muted)" }, "—")
      ),
      el("div", { className: "monitoring-toolbar-right" },
        [1, 5, 15, 30, 60].map(function (m) {
          var btn = el("button", {
            className: "time-window-btn",
            "aria-pressed": m === selectedWindowMinutes ? "true" : "false",
            dataset: { window: String(m) }
          }, m + "m");
          btn.addEventListener("click", function () {
            if (m === selectedWindowMinutes) return;
            selectedWindowMinutes = m;
            document.querySelectorAll(".time-window-btn").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.window === String(m)); });
            if (lastMetricsSnapshot) updateMonitoringMetrics(lastMetricsSnapshot);
          });
          return btn;
        }),
        el("button", { className: "monitoring-export-btn", onClick: function () { window.open(ENDPOINTS.adminExport, "_blank"); } }, "Export")
      )
    );
    container.appendChild(toolbar);

    // 2. Metric cards
    function metricCard(id, label, unit) {
      return el("div", { className: "metric-card" },
        el("div", null, el("span", { id: id + "-value", className: "metric-value" }, "—"), unit ? el("span", { className: "metric-unit" }, unit) : null),
        el("div", { className: "metric-label" }, label),
        el("div", { id: id + "-sub", className: "metric-sub" }, ""),
        el("div", { className: "monitoring-progress-track" }, el("div", { id: id + "-bar", className: "monitoring-progress-bar muted", style: "width:0%" }))
      );
    }
    var metricsGrid = el("div", { className: "metric-cards-grid" },
      metricCard("mon-cpu", "CPU", "%"),
      metricCard("mon-mem", "Memory", "GB"),
      metricCard("mon-rps", "Throughput", "req/s"),
      metricCard("mon-rel", "Reliability", "%")
    );
    container.appendChild(metricsGrid);

    // 4. Charts
    var chartsGrid = el("div", { className: "charts-grid" });
    [["mon-system-chart", "System Resources"], ["mon-request-chart", "Request Metrics"],
     ["mon-response-chart", "Response Time (ms)"], ["mon-percentile-chart", "Percentiles (ms)"]
    ].forEach(function (pair) {
      var card = el("div", { className: "chart-card" },
        el("h3", null, pair[1]),
        el("canvas", { id: pair[0] })
      );
      chartsGrid.appendChild(card);
    });
    container.appendChild(chartsGrid);

    // 5. Endpoint latency table
    var endpointSection = el("div", { id: "mon-endpoint-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Endpoint Latency"),
      el("div", { className: "endpoint-table-wrap" },
        el("table", { className: "endpoint-table" },
          el("thead", null, el("tr", null,
            el("th", null, "Method"), el("th", null, "Endpoint"), el("th", { style: "text-align:right" }, "Requests"),
            el("th", { style: "text-align:right" }, "Avg Latency"), el("th", { style: "text-align:right" }, "Error Rate")
          )),
          el("tbody", { id: "mon-endpoint-tbody" })
        )
      )
    );
    container.appendChild(endpointSection);

    // 6. Pipeline steps
    var pipelineSection = el("div", { id: "mon-pipeline-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Pipeline Steps"),
      el("div", { id: "mon-pipeline-summary", style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2);margin-bottom:var(--sp-3)" }),
      el("div", { id: "mon-pipeline-steps", className: "adapter-health-grid" })
    );
    container.appendChild(pipelineSection);

    // 7. Adapter Health
    var adapterToolbar = el("div", { className: "adapter-health-toolbar" });
    var searchWrap = el("div", { className: "monitoring-search-field" });
    var searchInput = el("input", { type: "text", placeholder: "Search adapters...", "aria-label": "Search adapters" });
    searchInput.addEventListener("input", function (e) {
      adapterSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (lastMetricsSnapshot) renderMonitoringAdapterList(lastAdapters);
    });
    searchWrap.appendChild(searchInput);
    adapterToolbar.appendChild(searchWrap);
    ["all", "closed", "half_open", "open"].forEach(function (state) {
      var btn = el("button", { className: "state-filter" + (state === adapterStateFilter ? " active" : ""), "aria-pressed": state === adapterStateFilter ? "true" : "false" }, state === "all" ? "All" : state.replace("_", " "));
      btn.addEventListener("click", function () {
        adapterStateFilter = state;
        adapterToolbar.querySelectorAll(".state-filter").forEach(function (b) {
          var isActive = b === btn;
          b.classList.toggle("active", isActive);
          b.setAttribute("aria-pressed", isActive);
        });
        renderMonitoringAdapterList(lastAdapters);
      });
      adapterToolbar.appendChild(btn);
    });

    var adapterSection = el("div", { id: "mon-adapter-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Adapter Health"),
      adapterToolbar,
      el("div", { id: "mon-adapter-summary", style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2);margin:var(--sp-3) 0" }),
      el("div", { id: "mon-adapter-list", className: "adapter-health-grid" })
    );
    container.appendChild(adapterSection);

    // 8. Datasource Pool
    var dsSection = el("div", { id: "mon-datasource-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Datasource Pool"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2);margin-bottom:var(--sp-3)" },
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Cached"), el("p", { id: "mon-ds-total", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "References"), el("p", { id: "mon-ds-refs", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Reuse Rate"), el("p", { id: "mon-ds-efficiency", className: "value" }, "0%"))
      ),
      el("div", { id: "mon-ds-list", className: "adapter-health-grid" })
    );
    container.appendChild(dsSection);

    // 9. Redis Health
    var redisSection = el("div", { id: "mon-redis-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Redis Health"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2)" },
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Status"), el("p", { id: "mon-redis-status", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Circuit Breaker"), el("p", { id: "mon-redis-cb", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Failures"), el("p", { id: "mon-redis-failures", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Pool"), el("p", { id: "mon-redis-pool", className: "value" }, "—"))
      ),
      el("div", { className: "monitoring-progress-track", style: "margin-top:var(--sp-2)" }, el("div", { id: "mon-redis-bar", className: "monitoring-progress-bar muted", style: "width:0%" }))
    );
    container.appendChild(redisSection);

    // 10. Thread Pools
    var threadSection = el("div", { id: "mon-threadpool-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Thread Pools"),
      el("div", { id: "mon-threadpool-list", className: "thread-pool-grid" })
    );
    container.appendChild(threadSection);

    // Initialize charts after DOM insertion
    initOverviewCharts();

    // Connect WebSocket for live monitoring
    connectMetricsWs();
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
    var right = el("div", { className: "stack" });
    var accountPanel = el("div", { className: "panel" });
    var detailPanel = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    right.appendChild(accountPanel);
    right.appendChild(detailPanel);
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

    // Right sidebar — persistent account panel plus selected user workspace
    accountPanel.appendChild(el("h2", null, "My Account"));
    renderChangeMyPassword(accountPanel);
    renderSelectedUserPlaceholder(detailPanel);

    createBtn.addEventListener("click", function () {
      var u = usernameInput.value.trim();
      var p = passwordInput.value.trim();
      if (!u || !p) return;
      withButton(createBtn, async function () {
        await api("POST", ENDPOINTS.register, { username: u, password: p, role: roleSelect.value });
        usernameInput.value = "";
        passwordInput.value = "";
        loadUsers();
      }, "User created");
    });

    async function loadUsers() {
      try {
        var users = await api("GET", ENDPOINTS.users);
        renderUserTable(tableWrap, users, detailPanel);
        if (selectedUser && selectedUser.id) {
          var refreshedSelection = users.find(function (user) {
            return user.id === selectedUser.id;
          });
          if (refreshedSelection) {
            selectedUser = refreshedSelection;
            renderUserDetail(detailPanel, refreshedSelection, function () {
              selectedUser = null;
              renderTab();
            });
          } else {
            selectedUser = null;
            renderSelectedUserPlaceholder(detailPanel);
          }
        } else {
          renderSelectedUserPlaceholder(detailPanel);
        }
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

    changeBtn.addEventListener("click", function () {
      var cur = curPwInput.value;
      var nw = newPwInput.value;
      var conf = confirmPwInput.value;
      if (!cur || !nw) return;
      if (nw !== conf) { showError("Passwords do not match"); return; }
      withButton(changeBtn, async function () {
        await api("POST", ENDPOINTS.changePassword, { current_password: cur, new_password: nw });
        curPwInput.value = "";
        newPwInput.value = "";
        confirmPwInput.value = "";
      }, "Password changed successfully");
    });

    panel.appendChild(el("div", { className: "stack" },
      passwordField("Current Password", curPwInput),
      passwordField("New Password", newPwInput),
      passwordField("Confirm Password", confirmPwInput),
      changeBtn
    ));
  }

  function renderSelectedUserPlaceholder(panel) {
    clear(panel);
    panel.appendChild(el("h2", null, "Selected User"));
    panel.appendChild(el("p", { className: "muted" }, "Select a user from the list to view account status, reset credentials, or manage access."));
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
    panel.appendChild(el("h2", null, "Selected User"));
    panel.appendChild(el("p", { className: "muted" }, "Managing " + user.username));
    var isCurrentUser = !!(currentUser && currentUser.id && user && user.id && currentUser.id === user.id);

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
    if (isCurrentUser) {
      panel.appendChild(el("div", { className: "danger-zone" },
        el("p", null, "The account currently used for this admin session cannot be deactivated or deleted here."),
        el("p", { className: "muted" }, "Use My Account to change your own password.")
      ));
    } else {
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
              await api("POST", ENDPOINTS.users + "/" + encodeURIComponent(user.id) + "/" + action);
              showStatus("User " + action + "d");
              onRefresh();
            } finally {
              toggleBtn.disabled = false;
            }
          }
        });
      });
      panel.appendChild(toggleBtn);
    }

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
            await api("POST", ENDPOINTS.resetPassword, { user_id: user.id, new_password: pw });
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
    if (!isCurrentUser) {
      panel.appendChild(el("h3", null, "Danger Zone"));
      var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete User");
      deleteBtn.addEventListener("click", function () {
        requireTypedConfirmation({
          title: "Delete User",
          message: 'Delete user "' + user.username + '"? This cannot be undone.',
          expectedText: user.username,
          confirmLabel: "Delete",
          onConfirm: async function () {
            await api("DELETE", ENDPOINTS.users + "/" + encodeURIComponent(user.id));
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
  }

  // ==================================================================
  // TAB: API Keys
  // ==================================================================
  async function renderKeys(container) {
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "stack" });
    var createPanel = el("div", { className: "panel" });
    var detailPanel = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    right.appendChild(createPanel);
    right.appendChild(detailPanel);
    container.appendChild(layout);

    left.appendChild(el("h2", null, "API Keys"));

    // Fetch adapters and prompts for dropdowns
    await loadAdaptersAndPrompts();

    // Create key form
    var clientInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var adapterSelect = el("select");
    var availableAdapterNames = [];
    if (cachedAdapters) {
      cachedAdapters.forEach(function (a) {
        var name = typeof a === "string" ? a : (a.name || a.adapter_name || "");
        if (name) availableAdapterNames.push(name);
      });
    }
    if (availableAdapterNames.length) {
      availableAdapterNames.forEach(function (name, index) {
        var option = el("option", { value: name }, name);
        if (index === 0) option.selected = true;
        adapterSelect.appendChild(option);
      });
    } else {
      adapterSelect.appendChild(el("option", { value: "" }, "No adapters available"));
      adapterSelect.disabled = true;
    }
    var promptSelect = el("select", null, el("option", { value: "" }, "No persona"));
    if (cachedPrompts) {
      cachedPrompts.forEach(function (p) {
        promptSelect.appendChild(el("option", { value: promptIdentifier(p) }, p.name + " (v" + (p.version || "1.0") + ")"));
      });
    }
    var notesInput = el("textarea", { rows: "4", maxlength: "500" });
    var createBtn = el("button", { type: "button" }, "Create Key");

    createPanel.appendChild(el("h2", null, "Create API Key"));
    var form = el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid" },
        field("Client", clientInput),
        field("Adapter", adapterSelect),
        field("Persona", promptSelect)
      ),
      field("Notes", notesInput),
      el("div", { className: "admin-create-form-actions" },
        createBtn
      )
    );
    createPanel.appendChild(form);

    var tableWrap = el("div", null, skeleton());
    left.appendChild(tableWrap);

    detailPanel.appendChild(el("h2", null, "Key Details"));
    detailPanel.appendChild(el("p", { className: "muted" }, "Select an API key to manage"));

    createBtn.addEventListener("click", function () {
      var cn = clientInput.value.trim();
      if (!cn) return;
      if (!adapterSelect.value) {
        showError("Select an adapter before creating the API key.");
        return;
      }
      withButton(createBtn, async function () {
        var body = { client_name: cn, adapter_name: adapterSelect.value };
        if (promptSelect.value) body.system_prompt_id = promptSelect.value;
        if (notesInput.value.trim()) body.notes = notesInput.value.trim();
        await api("POST", ENDPOINTS.apiKeys, body);
        clientInput.value = "";
        notesInput.value = "";
        loadKeys();
      }, "API key created");
    });

    async function loadKeys() {
      try {
        var keys = await api("GET", ENDPOINTS.apiKeys);
        cachedKeys = keys;
        renderKeyTable(tableWrap, keys, detailPanel);
        if (selectedKey && selectedKey._id) {
          var refreshedSelection = keys.find(function (key) {
            return key._id === selectedKey._id;
          });
          if (refreshedSelection) {
            selectedKey = refreshedSelection;
            clear(detailPanel);
            detailPanel.appendChild(el("p", { className: "muted" }, "Loading key details..."));
            try {
              var detail = await loadKeyDetail(refreshedSelection._id);
              selectedKey = detail;
              renderKeyDetail(detailPanel, detail, function () {
                selectedKey = null;
                renderTab();
              });
            } catch (detailErr) {
              selectedKey = null;
              clear(detailPanel);
              detailPanel.appendChild(el("div", { className: "empty-state" },
                el("p", null, "Unable to load key details."),
                el("p", { className: "muted" }, detailErr.message || "Unknown error")
              ));
              showError(detailErr.message);
            }
          } else {
            selectedKey = null;
            clear(detailPanel);
            detailPanel.appendChild(el("h2", null, "Key Details"));
            detailPanel.appendChild(el("p", { className: "muted" }, "Select an API key to manage"));
          }
        }
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load API keys"));
      }
    }

    loadKeys();
  }

  async function loadAdaptersAndPrompts() {
    try {
      var healthData = await api("GET", ENDPOINTS.healthAdapters).catch(function () { return null; });
      if (healthData) {
        var adapters = healthData.adapters || healthData.circuit_breakers || healthData;
        if (Array.isArray(adapters)) {
          cachedAdapters = adapters;
        } else if (typeof adapters === "object" && adapters !== null) {
          cachedAdapters = Object.keys(adapters);
        }
      }
    } catch (_) {}
    // Ensure cachedAdapters is always set so callers don't retry indefinitely
    if (!cachedAdapters) cachedAdapters = [];
    try {
      cachedPrompts = await api("GET", ENDPOINTS.prompts);
    } catch (_) {
      cachedPrompts = [];
    }
  }

  async function loadAvailableKeys() {
    try {
      cachedKeys = await api("GET", ENDPOINTS.apiKeys);
    } catch (_) {
      cachedKeys = [];
    }
    return cachedKeys;
  }

  async function loadAdapterCapabilities() {
    try {
      var result = await api("GET", ENDPOINTS.adapterCapabilities);
      cachedAdapterCapabilities = (result && result.adapters) || [];
    } catch (_) {
      cachedAdapterCapabilities = [];
    }
    return cachedAdapterCapabilities;
  }

  async function waitForAdminJob(jobId, startedMessage) {
    if (startedMessage) showStatus(startedMessage);
    var attempts = 0;
    while (attempts < 240) {
      attempts += 1;
      var job = await api("GET", ENDPOINTS.jobs + "/" + encodeURIComponent(jobId));
      if (job.status === "completed") {
        return job;
      }
      if (job.status === "failed") {
        throw new Error(job.error || job.message || "Background job failed");
      }
      await sleep(1500);
    }
    throw new Error("Background job timed out");
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
    select.appendChild(el("option", { value: "" }, prompts && prompts.length ? "Select a persona" : "No personas available"));
    (prompts || []).forEach(function (prompt) {
      var promptId = promptIdentifier(prompt);
      var option = el("option", { value: promptId }, prompt.name + " (v" + (prompt.version || "1.0") + ")");
      if (selectedPromptId && promptId === selectedPromptId) option.selected = true;
      select.appendChild(option);
    });
    select.disabled = !prompts || prompts.length === 0;
  }

  async function loadKeyDetail(keyId) {
    return api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/detail");
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
        var result = await api("POST", ENDPOINTS.renderMarkdown, { markdown: text });
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
        el("th", null, "Persona"),
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
      el("p", null, el("strong", null, "Persona:"), " " + (key.system_prompt_name || "None")),
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
        await api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/status");
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
    renameBtn.addEventListener("click", function () {
      var nk = renameInput.value.trim();
      if (!nk) return;
      withButton(renameBtn, async function () {
        await api("PATCH", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/rename?new_api_key=" + encodeURIComponent(nk));
        onRefresh();
      }, "Key renamed");
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
        var quota = await api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/quota");
        renderQuotaDetail(quotaWrap, keyId, quota);
      } catch (err) {
        showError(err.message);
      } finally {
        loadQuotaBtn.disabled = false;
      }
    });

    // Associate persona
    panel.appendChild(el("h3", null, "Associate Persona"));
    var promptSelect = el("select", null, el("option", { value: "" }, "Loading personas..."));
    var assocBtn = el("button", { type: "button" }, "Associate");
    fillPromptSelect(promptSelect, cachedPrompts, key.system_prompt_id);
    assocBtn.disabled = !cachedPrompts || !cachedPrompts.length;
    if (!cachedPrompts) {
      loadAdaptersAndPrompts().then(function () {
        fillPromptSelect(promptSelect, cachedPrompts, key.system_prompt_id);
        assocBtn.disabled = !cachedPrompts || !cachedPrompts.length;
      });
    }
    assocBtn.addEventListener("click", function () {
      var pid = promptSelect.value;
      if (!pid) return;
      withButton(assocBtn, async function () {
        await api("POST", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/prompt", { prompt_id: pid });
        key.system_prompt_id = pid;
        var matchedPrompt = (cachedPrompts || []).find(function (prompt) {
          return promptIdentifier(prompt) === pid;
        });
        key.system_prompt_name = matchedPrompt ? matchedPrompt.name : key.system_prompt_name;
        onRefresh();
      }, "Persona associated");
    });
    panel.appendChild(el("div", { className: "inline-form" }, field("Persona", promptSelect), assocBtn));

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
              await api("POST", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/deactivate");
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
          await api("DELETE", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId));
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
        var status = await api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/status");
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
              await api("POST", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/quota/reset?period=" + period);
              showStatus("Quota " + period + " reset");
              var updated = await api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/quota");
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
        await api("PUT", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/quota", body);
        showStatus("Quota updated");
        var updated = await api("GET", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + "/quota");
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
  // TAB: Personas
  // ==================================================================
  async function renderPrompts(container) {
    var layout = el("div", { className: "split-layout" });
    var left = el("div", { className: "panel" });
    var right = el("div", { className: "panel" });
    layout.appendChild(left);
    layout.appendChild(right);
    container.appendChild(layout);

    left.appendChild(el("h2", null, "Personas"));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var versionInput = el("input", { type: "text", value: "1.0", maxlength: "100" });
    var textArea = el("textarea", { rows: "5", required: "true", maxlength: "50000" });
    var createKeySelect = el("select", null, el("option", { value: "" }, "Loading API keys..."));
    var createBtn = el("button", { type: "button" }, "Create Persona");

    function fillCreatePersonaKeySelect(keys) {
      fillKeySelect(createKeySelect, keys);
      if (createKeySelect.options.length) {
        createKeySelect.options[0].textContent = "No API key";
      }
    }

    fillCreatePersonaKeySelect(cachedKeys);
    if (!cachedKeys) {
      loadAvailableKeys().then(function (keys) {
        fillCreatePersonaKeySelect(keys);
      });
    }

    var form = el("div", { className: "stack" },
      el("div", { className: "inline-form" },
        field("Name", nameInput),
        field("Version", versionInput),
        field("API Key", createKeySelect)
      ),
      field("Persona", textArea),
      createBtn
    );
    left.appendChild(form);

    var tableWrap = el("div", null, skeleton());
    left.appendChild(tableWrap);

    right.appendChild(el("h2", null, "Persona Details"));
    right.appendChild(el("p", { className: "muted" }, "Select a persona to edit"));

    createBtn.addEventListener("click", function () {
      var n = nameInput.value.trim();
      var t = textArea.value.trim();
      if (!n || !t) return;
      withButton(createBtn, async function () {
        var createdPrompt = await api("POST", ENDPOINTS.prompts, { name: n, prompt: t, version: versionInput.value.trim() || "1.0" });
        if (createKeySelect.value && createdPrompt && promptIdentifier(createdPrompt)) {
          await api("POST", ENDPOINTS.apiKeys + "/" + encodeURIComponent(createKeySelect.value) + "/prompt", {
            prompt_id: promptIdentifier(createdPrompt)
          });
        }
        nameInput.value = "";
        textArea.value = "";
        versionInput.value = "1.0";
        createKeySelect.value = "";
        loadPrompts();
      }, "Persona created");
    });

    async function loadPrompts() {
      try {
        var prompts = await api("GET", ENDPOINTS.prompts);
        cachedPrompts = prompts;
        renderPromptTable(tableWrap, prompts, right);
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load personas"));
      }
    }

    loadPrompts();
  }

  function renderPromptTable(wrap, prompts, rightPanel) {
    clear(wrap);
    if (!prompts || prompts.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F4DD}"),
        el("p", null, "No personas found")
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
        el("td", null, el("code", { className: "plain-code" }, promptId)),
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
      el("p", null, el("strong", null, "ID:"), " ", el("code", { className: "plain-code" }, promptId))
    );
    panel.appendChild(summary);

    // Edit
    var originalVersion = prompt.version || "1.0";
    var originalPromptText = prompt.prompt || "";
    var isEditingPrompt = false;
    var vInput = el("input", { type: "text", value: prompt.version || "1.0", maxlength: "100", readonly: "true", "aria-readonly": "true" });
    var tArea = el("textarea", { rows: "8", maxlength: "50000", readonly: "true", "aria-readonly": "true" }, prompt.prompt || "");
    var saveBtn = el("button", { type: "button" }, "Save Changes");
    saveBtn.addEventListener("click", function () {
      if (saveBtn.disabled) return;
      withButton(saveBtn, async function () {
        await api("PUT", ENDPOINTS.prompts + "/" + encodeURIComponent(promptId), {
          prompt: tArea.value,
          version: vInput.value.trim(),
        });
        onRefresh();
      }, "Persona updated");
    });
    
    var editPreview = createMarkdownPreview(tArea);
    var editorWrap = el("div", { className: "prompt-editor-pane", style: "display:none" },
      field("Persona Text", tArea)
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Persona");
    var cancelBtn = el("button", { className: "secondary", type: "button", style: "display:none" }, "Cancel");
    function promptHasChanges() {
      return vInput.value.trim() !== originalVersion || tArea.value !== originalPromptText;
    }
    function syncPromptSaveState() {
      saveBtn.disabled = !isEditingPrompt || !promptHasChanges();
    }
    function setPromptEditMode(editing) {
      isEditingPrompt = editing;
      vInput.readOnly = !editing;
      vInput.setAttribute("aria-readonly", editing ? "false" : "true");
      if (editing) vInput.removeAttribute("readonly");
      else vInput.setAttribute("readonly", "true");
      tArea.readOnly = !editing;
      tArea.setAttribute("aria-readonly", editing ? "false" : "true");
      if (editing) tArea.removeAttribute("readonly");
      else tArea.setAttribute("readonly", "true");
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
    assocBtn.addEventListener("click", function () {
      var k = keySelect.value;
      if (!k || !promptId) return;
      withButton(assocBtn, async function () {
        await api("POST", ENDPOINTS.apiKeys + "/" + encodeURIComponent(k) + "/prompt", { prompt_id: promptId });
        var refreshedKeys = await loadAvailableKeys();
        var matchedKey = refreshedKeys.find(function (key) {
          return key.system_prompt_id && String(key.system_prompt_id) === String(promptId);
        });
        fillKeySelect(keySelect, refreshedKeys, matchedKey ? matchedKey._id : null);
      }, "Persona associated with key");
    });
    panel.appendChild(el("div", { className: "inline-form" }, field("API Key", keySelect), assocBtn));

    // Delete
    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Persona");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete Persona",
        message: 'Delete persona "' + prompt.name + '"? This cannot be undone.',
        expectedText: prompt.name,
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", ENDPOINTS.prompts + "/" + encodeURIComponent(promptId));
          showStatus("Persona deleted");
          onRefresh();
        }
      });
    });
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Deleting a persona breaks future associations that depend on it."),
      deleteBtn
    ));
  }

  // ==================================================================
  // TAB: Ops
  // ==================================================================
  function renderOps(container) {
    if (!cachedAdapterCapabilities) {
      clear(container);
      container.appendChild(el("div", { className: "panel" }, el("h2", null, "Ops"), skeleton()));
      loadAdapterCapabilities().then(function () {
        if (document.body.contains(container)) renderOps(container);
      });
      return;
    }

    clear(container);

    // --- Action bar: Reload + Server Control in a compact row ---
    var actionBar = el("div", { className: "ops-action-bar" });

    // Reload section
    var filterSelect = el("select", null, el("option", { value: "" }, "All adapters"));
    if (cachedAdapterCapabilities && cachedAdapterCapabilities.length) {
      cachedAdapterCapabilities.forEach(function (adapterInfo) {
        filterSelect.appendChild(el("option", { value: adapterInfo.name }, adapterInfo.name));
      });
    }
    var reloadHint = el("p", { className: "muted" }, "Template reload applies only to cached adapters that support template libraries.");

    function selectedAdapterCapability() {
      if (!filterSelect.value) return null;
      return (cachedAdapterCapabilities || []).find(function (adapterInfo) {
        return adapterInfo.name === filterSelect.value;
      }) || null;
    }

    function syncReloadControls() {
      var selectedAdapter = selectedAdapterCapability();
      reloadAdaptersBtn.textContent = selectedAdapter ? "Reload Adapter" : "Reload Adapters";
      if (!selectedAdapter) {
        reloadTemplatesBtn.disabled = false;
        reloadHint.textContent = "Template reload applies only to cached adapters that support template libraries.";
        return;
      }
      var templatesAvailable = !!selectedAdapter.supports_template_reload;
      reloadTemplatesBtn.disabled = !templatesAvailable;
      if (!selectedAdapter.cached) {
        reloadHint.textContent = "Template reload is unavailable because this adapter is not currently cached.";
      } else if (!templatesAvailable) {
        reloadHint.textContent = "Template reload is unavailable for this adapter type.";
      } else {
        reloadHint.textContent = "Reload templates only for " + selectedAdapter.name + ".";
      }
    }

    var reloadAdaptersBtn = el("button", { className: "secondary", type: "button" }, "Reload Adapters");
    reloadAdaptersBtn.addEventListener("click", function () {
      confirmAction({
        title: "Reload Adapters",
        message: "Reload adapter configuration" + (filterSelect.value ? " for " + filterSelect.value : "") + "?",
        confirmLabel: "Reload",
        loadingLabel: filterSelect.value ? "Reloading Adapter..." : "Reloading Adapters...",
        onConfirm: async function () {
          reloadAdaptersBtn.disabled = true;
          try {
            var path = ENDPOINTS.reloadAdapters;
            var f = filterSelect.value;
            path += "/async";
            if (f) path += "?adapter_name=" + encodeURIComponent(f);
            var started = await api("POST", path);
            var job = await waitForAdminJob(started.job_id, started.message);
            var result = job.result || {};
            await loadAdapterCapabilities();
            syncReloadControls();
            showStatus("Adapters reloaded: " + (result.message || "OK"));
          } finally {
            reloadAdaptersBtn.disabled = false;
          }
        }
      });
    });

    var reloadTemplatesBtn = el("button", { className: "secondary", type: "button" }, "Reload Templates");
    reloadTemplatesBtn.addEventListener("click", function () {
      confirmAction({
        title: "Reload Templates",
        message: "Reload templates" + (filterSelect.value ? " for " + filterSelect.value : "") + "?",
        confirmLabel: "Reload",
        loadingLabel: filterSelect.value ? "Reloading Templates..." : "Reloading Templates...",
        onConfirm: async function () {
          reloadTemplatesBtn.disabled = true;
          try {
            var path = ENDPOINTS.reloadTemplates;
            var f = filterSelect.value;
            path += "/async";
            if (f) path += "?adapter_name=" + encodeURIComponent(f);
            var started = await api("POST", path);
            var job = await waitForAdminJob(started.job_id, started.message);
            var result = job.result || {};
            await loadAdapterCapabilities();
            syncReloadControls();
            showStatus("Templates reloaded: " + (result.message || "OK"));
          } finally {
            reloadTemplatesBtn.disabled = false;
          }
        }
      });
    });
    filterSelect.addEventListener("change", syncReloadControls);
    syncReloadControls();

    // Server control
    var restartBtn = el("button", { className: "secondary", type: "button" }, "Restart Server");
    restartBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Restart Server",
        message: "Type RESTART to restart the ORBIT server process in place. The page will automatically reload once the server is back online.",
        expectedText: "RESTART",
        confirmLabel: "Restart",
        isDanger: false,
        onConfirm: async function () {
          restartBtn.disabled = true;
          try {
            await api("POST", ENDPOINTS.restart);
            showServerOverlay({
              title: "Restarting Server",
              detail: "The server process is restarting...",
              mode: "restart"
            });
          } catch (err) {
            restartBtn.disabled = false;
            showError("Failed to initiate restart: " + err.message);
          }
        }
      });
    });

    var shutdownBtn = el("button", { className: "danger", type: "button" }, "Shutdown");
    shutdownBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Shutdown Server",
        message: "Type SHUTDOWN to terminate the ORBIT server process. You will need to restart it manually from the command line using 'orbit start'.",
        expectedText: "SHUTDOWN",
        confirmLabel: "Shutdown",
        onConfirm: async function () {
          shutdownBtn.disabled = true;
          try {
            await api("POST", ENDPOINTS.shutdown);
            showServerOverlay({
              title: "Server Shutting Down",
              detail: "Terminating the server process...",
              mode: "shutdown"
            });
          } catch (err) {
            shutdownBtn.disabled = false;
            showError("Failed to initiate shutdown: " + err.message);
          }
        }
      });
    });

    actionBar.appendChild(filterSelect);
    actionBar.appendChild(reloadAdaptersBtn);
    actionBar.appendChild(reloadTemplatesBtn);
    actionBar.appendChild(el("div", { className: "ops-action-divider" }));
    actionBar.appendChild(restartBtn);
    actionBar.appendChild(shutdownBtn);
    container.appendChild(actionBar);
    container.appendChild(reloadHint);

    // --- Log viewer: full-width terminal-style panel ---
    var logLevelFilter = "all";
    var logSearchTerm = "";
    var rawLogLines = [];
    var userNearBottom = true;
    var pendingNewLines = 0;

    var logFilename = el("span", { className: "log-filename" }, "orbit.log");
    var logUpdated = el("span", { className: "log-updated" }, "");
    var logCount = el("span", { className: "log-count" }, "");

    // "Jump to bottom" banner shown when new lines arrive while scrolled up
    var jumpBanner = el("button", { className: "log-jump-banner hidden", type: "button" });
    jumpBanner.addEventListener("click", function () {
      userNearBottom = true;
      pendingNewLines = 0;
      jumpBanner.classList.add("hidden");
      logScrollAnchor.scrollIntoView({ behavior: "smooth", block: "end" });
    });

    // Level filter buttons
    var levels = ["all", "error", "warning", "info", "debug"];
    var levelBar = el("div", { className: "log-level-bar" });
    levels.forEach(function (lvl) {
      var btn = el("button", {
        className: "log-level-btn" + (lvl === logLevelFilter ? " active" : ""),
        dataset: { level: lvl },
        type: "button"
      }, lvl === "all" ? "All" : lvl.charAt(0).toUpperCase() + lvl.slice(1));
      btn.addEventListener("click", function () {
        logLevelFilter = lvl;
        levelBar.querySelectorAll(".log-level-btn").forEach(function (b) {
          b.classList.toggle("active", b.dataset.level === lvl);
        });
        fullRenderLogLines();
      });
      levelBar.appendChild(btn);
    });

    // Search input
    var logSearch = el("input", { type: "text", placeholder: "Filter logs...", className: "log-search-input", "aria-label": "Filter logs" });
    logSearch.addEventListener("input", function (e) {
      logSearchTerm = (e.target.value || "").toLowerCase();
      fullRenderLogLines();
    });

    var logBody = el("div", { className: "log-terminal" });
    var logScrollAnchor = el("div", { className: "log-scroll-anchor" });
    logBody.appendChild(logScrollAnchor);

    // Track scroll position to decide auto-scroll
    logBody.addEventListener("scroll", function () {
      var threshold = 60; // pixels from bottom
      var atBottom = logBody.scrollHeight - logBody.scrollTop - logBody.clientHeight < threshold;
      userNearBottom = atBottom;
      if (atBottom && pendingNewLines > 0) {
        pendingNewLines = 0;
        jumpBanner.classList.add("hidden");
      }
    });

    function detectLevel(line) {
      var upper = line.toUpperCase();
      if (upper.includes(" ERROR ") || upper.includes("[ERROR]") || upper.includes("ERROR:") || upper.startsWith("ERROR ")) return "error";
      if (upper.includes(" WARNING ") || upper.includes("[WARNING]") || upper.includes("WARNING:") || upper.startsWith("WARNING ")) return "warning";
      if (upper.includes(" DEBUG ") || upper.includes("[DEBUG]") || upper.includes("DEBUG:") || upper.startsWith("DEBUG ")) return "debug";
      if (upper.includes(" INFO ") || upper.includes("[INFO]") || upper.includes("INFO:") || upper.startsWith("INFO ")) return "info";
      return "info";
    }

    function matchesFilter(line) {
      if (!line.trim()) return false;
      var level = detectLevel(line);
      if (logLevelFilter !== "all" && level !== logLevelFilter) return false;
      if (logSearchTerm && line.toLowerCase().indexOf(logSearchTerm) === -1) return false;
      return true;
    }

    function buildLogRow(line, lineNo) {
      var level = detectLevel(line);
      var row = el("div", { className: "log-line log-level-" + level });
      row.appendChild(el("span", { className: "log-lineno" }, String(lineNo)));
      var badgeText = level === "warning" ? "WARN" : level.toUpperCase();
      row.appendChild(el("span", { className: "log-badge log-badge-" + level }, badgeText));

      if (logSearchTerm) {
        var lower = line.toLowerCase();
        var idx = lower.indexOf(logSearchTerm);
        if (idx >= 0) {
          var textSpan = el("span", { className: "log-text" });
          textSpan.appendChild(document.createTextNode(line.substring(0, idx)));
          textSpan.appendChild(el("mark", { className: "log-highlight" }, line.substring(idx, idx + logSearchTerm.length)));
          textSpan.appendChild(document.createTextNode(line.substring(idx + logSearchTerm.length)));
          row.appendChild(textSpan);
        } else {
          row.appendChild(el("span", { className: "log-text" }, line));
        }
      } else {
        row.appendChild(el("span", { className: "log-text" }, line));
      }
      return row;
    }

    function updateLogCount() {
      var visible = logBody.querySelectorAll(".log-line").length;
      logCount.textContent = visible + " / " + rawLogLines.length + " lines";
    }

    /** Full re-render — used for filter/search changes. */
    function fullRenderLogLines() {
      while (logBody.firstChild !== logScrollAnchor) {
        logBody.removeChild(logBody.firstChild);
      }
      var frag = document.createDocumentFragment();
      var lineNo = 0;
      rawLogLines.forEach(function (line) {
        if (!matchesFilter(line)) return;
        lineNo++;
        frag.appendChild(buildLogRow(line, lineNo));
      });
      logBody.insertBefore(frag, logScrollAnchor);
      updateLogCount();
      if (userNearBottom) {
        logScrollAnchor.scrollIntoView({ block: "end" });
      }
    }

    /** Append only new lines — used during tailing. */
    function appendNewLogLines(newLines) {
      if (!newLines.length) return;
      var currentLineNo = logBody.querySelectorAll(".log-line").length;
      var frag = document.createDocumentFragment();
      var added = 0;
      newLines.forEach(function (line) {
        if (!matchesFilter(line)) return;
        currentLineNo++;
        added++;
        frag.appendChild(buildLogRow(line, currentLineNo));
      });
      logBody.insertBefore(frag, logScrollAnchor);
      updateLogCount();

      if (added > 0) {
        if (userNearBottom) {
          logScrollAnchor.scrollIntoView({ block: "end" });
        } else {
          pendingNewLines += added;
          jumpBanner.textContent = pendingNewLines + " new line" + (pendingNewLines !== 1 ? "s" : "") + " below \u2193";
          jumpBanner.classList.remove("hidden");
        }
      }
    }

    var logsInFlight = false;

    function scheduleLogRefresh() {
      clearOpsLogPolling();
      if (activeTab !== "ops") return;
      if (document.hidden) return;
      opsLogPollTimer = setTimeout(function () {
        loadLogs(true);
      }, 3000);
    }

    async function loadLogs(silent) {
      if (logsInFlight) return;
      logsInFlight = true;
      try {
        var result = await api("GET", ENDPOINTS.logsTail + "?lines=500");
        logFilename.textContent = result.filename || "orbit.log";
        logUpdated.textContent = result.updated_at ? "Updated " + result.updated_at : "";
        var incoming = result.lines || [];

        if (rawLogLines.length === 0) {
          // First load — full render
          rawLogLines = incoming;
          fullRenderLogLines();
          // Start scrolled to bottom
          userNearBottom = true;
          logScrollAnchor.scrollIntoView({ block: "end" });
        } else {
          // Diff: find new lines appended at the end.
          // The server returns the last N lines of the file. If the file grew,
          // the tail end of `incoming` contains new lines not in `rawLogLines`.
          var overlap = findOverlap(rawLogLines, incoming);
          var newLines = incoming.slice(overlap);
          rawLogLines = incoming;
          if (newLines.length > 0) {
            appendNewLogLines(newLines);
          }
        }
      } catch (err) {
        if (!silent) showError(err.message);
      } finally {
        logsInFlight = false;
        scheduleLogRefresh();
      }
    }

    /**
     * Find how many lines from the end of `prev` overlap with the start of `next`.
     * Returns the index in `next` where new content begins.
     */
    function findOverlap(prev, next) {
      if (!prev.length || !next.length) return 0;
      // Use the last few lines of prev as a fingerprint to find where next diverges
      var matchLen = Math.min(prev.length, next.length, 20);
      var tail = prev.slice(-matchLen);
      // Search for this tail sequence in next
      outer:
      for (var start = 0; start <= next.length - matchLen; start++) {
        for (var j = 0; j < matchLen; j++) {
          if (next[start + j] !== tail[j]) continue outer;
        }
        // Found the tail at position `start` in next — new content starts after it
        return start + matchLen;
      }
      // No overlap found — treat entire next as new (log rotated or drastically changed)
      return 0;
    }

    // Visibility change: resume polling when tab becomes visible
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && activeTab === "ops") {
        scheduleLogRefresh();
      }
    });

    var logPanel = el("div", { className: "panel log-panel-v2" });

    var logHeader = el("div", { className: "log-header" },
      el("div", { className: "log-header-left" },
        el("h2", { style: "margin:0;font-size:var(--text-md)" }, "Server Logs"),
        logFilename,
        logUpdated,
        logCount
      ),
      el("div", { className: "log-header-right" },
        logSearch,
        levelBar
      )
    );

    logPanel.appendChild(logHeader);
    logPanel.appendChild(logBody);
    logPanel.appendChild(jumpBanner);
    container.appendChild(logPanel);

    loadLogs(false);
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  window.addEventListener("beforeunload", function () {
    disconnectMetricsWs();
    destroyOverviewCharts();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
