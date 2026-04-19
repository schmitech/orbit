/* ============================================================
   ORBIT Admin Portal — Single-file vanilla JS client
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
  let selectedAdapterEntry = null; // { name, filename, ... }
  let adapterEditor = null;        // Ace editor instance for Adapters tab
  let adapterOriginal = "";        // Dirty tracking baseline
  let cachedAdapterFiles = null;   // Cached adapter file listing
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
  let lastDatasourcePool = null;
  let datasourceSearchFilter = "";
  let lastThreadPools = {};
  let threadPoolSearchFilter = "";
  let overviewCharts = {};
  let monitoringThresholds = { cpu: 90, memory: 85, error_rate: 5, response_time_ms: 5000 };
  let overviewAdapterPaginator = null;
  let overviewDatasourcePaginator = null;
  let overviewThreadPoolPaginator = null;

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
    config: "/admin/config",
    adapterConfigs: "/admin/adapters/config",
    auditEvents: "/admin/audit/events",
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
        } else if (v != null) {
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

  function svgIcon(pathD, viewBox) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("viewBox", viewBox || "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    if (Array.isArray(pathD)) {
      pathD.forEach(function (d) {
        var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", d);
        svg.appendChild(p);
      });
    } else {
      var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", pathD);
      svg.appendChild(p);
    }
    return svg;
  }

  var ICON_EYE = ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"];
  var ICON_EYE_OFF = ["M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94", "M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19", "M14.12 14.12a3 3 0 1 1-4.24-4.24", "M1 1l22 22"];
  var ICON_COPY = ["M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2", "M8 2h8a1 1 0 0 1 1 1v1H7V3a1 1 0 0 1 1-1z"];
  var ICON_CHECK = ["M20 6L9 17l-5-5"];
  var ICON_PLUS = ["M12 5v14", "M5 12h14"];
  var USERNAME_MIN_LENGTH = 3;
  var USERNAME_MAX_LENGTH = 50;
  var PASSWORD_MIN_LENGTH = 8;
  var PASSWORD_MAX_LENGTH = 128;
  var USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;

  function passwordField(labelText, input, hintText) {
    input.type = "password";
    var wrapper = el("div", { className: "password-field" }, input);
    var toggleBtn = el("button", {
      type: "button",
      className: "password-toggle",
      "aria-label": "Show password",
      title: "Show password",
    });
    toggleBtn.appendChild(svgIcon(ICON_EYE));
    toggleBtn.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      toggleBtn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      toggleBtn.setAttribute("title", showing ? "Show password" : "Hide password");
      toggleBtn.innerHTML = "";
      toggleBtn.appendChild(svgIcon(showing ? ICON_EYE : ICON_EYE_OFF));
    });
    wrapper.appendChild(toggleBtn);
    return field(labelText, wrapper, hintText, input);
  }

  function validateUsername(username) {
    if (!username) return "Username is required";
    if (username !== username.trim()) return "Username cannot start or end with spaces";
    if (username.length < USERNAME_MIN_LENGTH) return "Username must be at least " + USERNAME_MIN_LENGTH + " characters";
    if (username.length > USERNAME_MAX_LENGTH) return "Username must be at most " + USERNAME_MAX_LENGTH + " characters";
    if (!USERNAME_PATTERN.test(username)) return "Username may only contain letters, numbers, periods, underscores, and hyphens";
    return "";
  }

  function validatePassword(password) {
    if (!password) return "Password is required";
    if (password.length < PASSWORD_MIN_LENGTH) return "Password must be at least " + PASSWORD_MIN_LENGTH + " characters";
    if (password.length > PASSWORD_MAX_LENGTH) return "Password must be at most " + PASSWORD_MAX_LENGTH + " characters";
    if (/\s/.test(password)) return "Password cannot contain spaces or other whitespace";
    return "";
  }

  function syncBulkActionButton(button, count, label) {
    button.disabled = count === 0;
    button.textContent = count > 0 ? "Delete " + count + " " + label : "Delete Selected";
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

  var ITEMS_PER_PAGE = 10;

  function createPaginator(opts) {
    var pageSize = opts.pageSize || ITEMS_PER_PAGE;
    var onPageChange = opts.onPageChange || function () {};
    var allItems = [];
    var currentPage = 1;
    var totalPages = 1;
    var barEl = el("div", { className: "pagination-bar" });

    function computePages() {
      totalPages = Math.max(1, Math.ceil(allItems.length / pageSize));
      if (currentPage > totalPages) currentPage = totalPages;
    }

    function getSlice() {
      var start = (currentPage - 1) * pageSize;
      return allItems.slice(start, start + pageSize);
    }

    function renderControls() {
      clear(barEl);
      if (allItems.length <= pageSize) {
        barEl.style.display = "none";
        return;
      }
      barEl.style.display = "";
      var start = (currentPage - 1) * pageSize + 1;
      var end = Math.min(currentPage * pageSize, allItems.length);
      barEl.appendChild(el("span", { className: "pagination-info" },
        "Showing " + start + "\u2013" + end + " of " + allItems.length));

      var btns = el("div", { className: "pagination-buttons" });

      var prevAttrs = { type: "button", className: "pagination-btn", "aria-label": "Previous page" };
      if (currentPage <= 1) prevAttrs.disabled = "true";
      var prevBtn = el("button", prevAttrs, "\u2039");
      prevBtn.addEventListener("click", function () { goToPage(currentPage - 1); });
      btns.appendChild(prevBtn);

      var pages = buildPageNumbers(currentPage, totalPages);
      pages.forEach(function (p) {
        if (p === "...") {
          btns.appendChild(el("span", { className: "pagination-ellipsis" }, "\u2026"));
        } else {
          var pageAttrs = {
            type: "button",
            className: "pagination-btn" + (p === currentPage ? " active" : ""),
            "aria-label": "Page " + p
          };
          if (p === currentPage) pageAttrs["aria-current"] = "page";
          var btn = el("button", pageAttrs, String(p));
          btn.addEventListener("click", function () { goToPage(p); });
          btns.appendChild(btn);
        }
      });

      var nextAttrs = { type: "button", className: "pagination-btn", "aria-label": "Next page" };
      if (currentPage >= totalPages) nextAttrs.disabled = "true";
      var nextBtn = el("button", nextAttrs, "\u203A");
      nextBtn.addEventListener("click", function () { goToPage(currentPage + 1); });
      btns.appendChild(nextBtn);

      barEl.appendChild(btns);
    }

    function buildPageNumbers(cur, total) {
      if (total <= 7) {
        var arr = [];
        for (var i = 1; i <= total; i++) arr.push(i);
        return arr;
      }
      var pages = [1];
      if (cur > 3) pages.push("...");
      for (var j = Math.max(2, cur - 1); j <= Math.min(total - 1, cur + 1); j++) pages.push(j);
      if (cur < total - 2) pages.push("...");
      pages.push(total);
      return pages;
    }

    function goToPage(n) {
      n = Math.max(1, Math.min(n, totalPages));
      if (n === currentPage && allItems.length > 0) return;
      currentPage = n;
      renderControls();
      onPageChange(getSlice(), currentPage, totalPages);
    }

    function setData(items, preservePage) {
      allItems = items || [];
      if (!preservePage) currentPage = 1;
      computePages();
      renderControls();
      onPageChange(getSlice(), currentPage, totalPages);
    }

    function ensureItemVisible(predicate) {
      for (var i = 0; i < allItems.length; i++) {
        if (predicate(allItems[i])) {
          var targetPage = Math.floor(i / pageSize) + 1;
          if (targetPage !== currentPage) {
            currentPage = targetPage;
            renderControls();
            onPageChange(getSlice(), currentPage, totalPages);
          }
          return;
        }
      }
    }

    return {
      setData: setData,
      setItems: setData,
      setPageChangeHandler: function (handler) {
        onPageChange = handler || function () {};
      },
      getControlsEl: function () { return barEl; },
      goToPage: goToPage,
      ensureItemVisible: ensureItemVisible,
      getCurrentPage: function () { return currentPage; }
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
    clearMessages("error");
    pushMessage("status", msg, true);
  }

  function showError(msg) {
    pushMessage("error", msg, false);
  }

  function clearMessages(kind) {
    var region = document.getElementById("toast-region");
    if (!region) return;
    var selector = kind ? "." + kind : ".status, .error";
    region.querySelectorAll(selector).forEach(function (node) {
      node.remove();
    });
  }

  function clearValidationErrorsOnInput() {
    clearMessages("error");
  }

  function bindValidationClear() {
    Array.prototype.slice.call(arguments).forEach(function (control) {
      if (!control || !control.addEventListener) return;
      control.addEventListener("input", clearValidationErrorsOnInput);
      control.addEventListener("change", clearValidationErrorsOnInput);
    });
  }

  function characterCount(input, maxLength) {
    var counter = el("div", { className: "character-count", "aria-live": "polite" });
    function sync() {
      var current = (input.value || "").length;
      counter.textContent = current + "/" + maxLength;
      counter.classList.toggle("near-limit", current >= maxLength * 0.9);
    }
    input.addEventListener("input", sync);
    sync();
    return counter;
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
    var inlineErrorEl = el("div", {
      className: "dialog-inline-error",
      role: "alert",
      "aria-live": "assertive",
    });
    var bodyChildren = [
      el("h2", { id: titleId }, title),
      el("p", { id: descId }, message),
    ];
    if (extraContent) bodyChildren.push(extraContent);
    bodyChildren.push(inlineErrorEl);
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
      inlineErrorEl.textContent = "";
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
        inlineErrorEl.textContent = err.message || "Something went wrong.";
        var focusField = dialog.querySelector(".dialog-body input:not([type='hidden'])");
        if (focusField && focusField.focus) focusField.focus();
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
    { id: "adapters", label: "Adapters" },
    { id: "ops", label: "Ops" },
    { id: "audit", label: "Audit" },
    { id: "settings", label: "Settings" },
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
    // Destroy adapter editor when leaving adapters tab
    if (activeTab === "adapters" && id !== "adapters") {
      if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
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
      case "adapters": renderAdapters(c); break;
      case "ops": renderOps(c); break;
      case "audit": renderAudit(c); break;
      case "settings": renderSettings(c); break;
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

  function monitoringSummaryCard(label, value, hint, extraClass) {
    var children = [
      el("p", { className: "label" }, label),
      el("p", { className: "value" }, value)
    ];
    if (hint) children.push(el("p", { className: "hint" }, hint));
    return el("div", { className: "monitoring-summary-card" + (extraClass ? " " + extraClass : "") }, children);
  }

  function monitoringStateTone(state) {
    var normalized = (state || "unknown").toLowerCase();
    if (normalized === "closed" || normalized === "connected" || normalized === "healthy") return "green";
    if (normalized === "half_open" || normalized === "warning" || normalized === "degraded") return "amber";
    if (normalized === "open" || normalized === "error" || normalized === "disconnected") return "red";
    return "muted";
  }

  function monitoringStatusCell(label, tone) {
    return el("span", { className: "monitoring-status-cell" },
      el("span", { className: "monitoring-status-icon " + (tone || "muted"), "aria-hidden": "true" }),
      el("span", { className: "monitoring-status-label" }, label)
    );
  }

  function renderMonitoringTable(container, columns, rows, emptyMessage, paginator) {
    clear(container);
    if (!rows.length) {
      container.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, emptyMessage));
      if (paginator) paginator.setItems([]);
      return;
    }
    var table = el("table", { className: "monitoring-table" });
    table.appendChild(el("thead", null, el("tr", null, columns.map(function (column) {
      return el("th", column.attrs || null, column.label);
    }))));
    var tbody = el("tbody");
    table.appendChild(tbody);
    container.appendChild(table);
    function renderPage(pageRows) {
      clear(tbody);
      pageRows.forEach(function (row) {
        tbody.appendChild(el("tr", null, row));
      });
    }
    if (paginator) {
      paginator.setPageChangeHandler(renderPage);
      paginator.setItems(rows, true);
    } else {
      renderPage(rows);
    }
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
      summaryEl.appendChild(monitoringSummaryCard(c.label, String(counts[c.key] || 0), c.hint, "monitoring-summary-card-compact"));
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
    var rows = filtered.map(function (pair) {
      var name = pair[0], status = pair[1];
      var state = (status && status.state || "unknown").toLowerCase();
      var failures = (status && status.failure_count) || 0;
      var reqs = (status && (status.request_count || status.success_count)) || 0;
      var latency = status && status.average_latency_ms;
      var latencyStr = typeof latency === "number" ? formatNum(latency, latency >= 100 ? 0 : 1) + " ms" : "\u2014";
      return [
        el("td", null, el("div", { className: "monitoring-table-primary", title: name }, name)),
        el("td", null, monitoringStatusCell(state.replace("_", " "), monitoringStateTone(state))),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(reqs)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(failures)),
        el("td", { style: "text-align:right;font-weight:600" }, latencyStr)
      ];
    });
    renderMonitoringTable(container, [
      { label: "Adapter" },
      { label: "State" },
      { label: "Requests", attrs: { style: "text-align:right" } },
      { label: "Failures", attrs: { style: "text-align:right" } },
      { label: "Avg Latency", attrs: { style: "text-align:right" } }
    ], rows, "No adapters match the current filters.", overviewAdapterPaginator);
  }

  function updateMonitoringThreadPools(pools) {
    lastThreadPools = pools || {};
    var section = document.getElementById("mon-threadpool-section");
    if (!section) return;
    var entries = Object.entries(lastThreadPools);
    if (!entries.length) { section.style.display = "none"; return; }
    section.style.display = "";
    var container = document.getElementById("mon-threadpool-list");
    if (!container) return;
    var filtered = entries.filter(function (pair) {
      if (!threadPoolSearchFilter) return true;
      return pair[0].toLowerCase().includes(threadPoolSearchFilter);
    }).sort(function (a, b) {
      return a[0].localeCompare(b[0]);
    });
    var rows = filtered.map(function (pair) {
      var name = pair[0], pool = pair[1];
      var util = pool.max_workers > 0 ? clampPercentage((pool.active_threads / pool.max_workers) * 100) : 0;
      var isIdle = pool.active_threads === 0 && pool.queued_tasks === 0;
      var tone = isIdle ? "muted" : util >= 90 ? "red" : util >= 75 ? "amber" : "green";
      var statusLabel = isIdle ? "Idle" : util >= 90 ? "Busy" : util >= 75 ? "Active" : "Healthy";
      return [
        el("td", null, el("div", { className: "monitoring-table-primary", title: name }, name)),
        el("td", null, monitoringStatusCell(statusLabel, tone)),
        el("td", { style: "text-align:right;font-weight:600" }, pool.active_threads + " / " + pool.max_workers),
        el("td", { style: "text-align:right;font-weight:600" }, String(pool.queued_tasks === "N/A" ? "0" : pool.queued_tasks)),
        el("td", { style: "text-align:right;font-weight:600" }, util.toFixed(1) + "%")
      ];
    });
    renderMonitoringTable(container, [
      { label: "Pool" },
      { label: "Status" },
      { label: "Active Threads", attrs: { style: "text-align:right" } },
      { label: "Queued", attrs: { style: "text-align:right" } },
      { label: "Utilization", attrs: { style: "text-align:right" } }
    ], rows, "No thread pools match the current filter.", overviewThreadPoolPaginator);
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
    lastDatasourcePool = data || null;
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
    var filteredKeys = data.datasource_keys.filter(function (key) {
      if (!datasourceSearchFilter) return true;
      return key.toLowerCase().includes(datasourceSearchFilter);
    }).sort();
    var rows = filteredKeys.map(function (key) {
      var refCount = (data.reference_counts && data.reference_counts[key]) || 0;
      var parts = key.split(":");
      var dsType = parts[0] || "unknown";
      var connInfo = parts.slice(1).join(":") || "default";
      var statusTone = refCount >= 3 ? "green" : refCount === 2 ? "amber" : "muted";
      var statusLabel = refCount >= 3 ? "Shared" : refCount === 2 ? "Warm" : "Idle";
      return [
        el("td", null, el("div", { className: "monitoring-table-primary" }, dsType)),
        el("td", null, el("code", { className: "monitoring-table-code", title: connInfo }, connInfo)),
        el("td", { style: "text-align:right;font-weight:600" }, refCount),
        el("td", null, monitoringStatusCell(statusLabel, statusTone))
      ];
    });
    renderMonitoringTable(container, [
      { label: "Datasource" },
      { label: "Connection" },
      { label: "References", attrs: { style: "text-align:right" } },
      { label: "Status" }
    ], rows, "No datasource pool entries match the current filter.", overviewDatasourcePaginator);
  }

  function updateMonitoringConnections(conn) {
    setText("mon-ws-clients", (conn.websocket_clients || 0).toString());
    setText("mon-active-sessions", (conn.active_sessions || 0).toString());
  }

  // --- Render Overview ---
  async function renderOverview(container) {
    overviewAdapterPaginator = createPaginator({ pageSize: ITEMS_PER_PAGE, onPageChange: function () {} });
    overviewDatasourcePaginator = createPaginator({ pageSize: ITEMS_PER_PAGE, onPageChange: function () {} });
    overviewThreadPoolPaginator = createPaginator({ pageSize: ITEMS_PER_PAGE, onPageChange: function () {} });

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
      if (overviewAdapterPaginator) overviewAdapterPaginator.goToPage(1);
      if (lastMetricsSnapshot) renderMonitoringAdapterList(lastAdapters);
    });
    searchWrap.appendChild(searchInput);
    adapterToolbar.appendChild(searchWrap);
    ["all", "closed", "half_open", "open"].forEach(function (state) {
      var btn = el("button", { className: "state-filter" + (state === adapterStateFilter ? " active" : ""), "aria-pressed": state === adapterStateFilter ? "true" : "false" }, state === "all" ? "All" : state.replace("_", " "));
      btn.addEventListener("click", function () {
        adapterStateFilter = state;
        if (overviewAdapterPaginator) overviewAdapterPaginator.goToPage(1);
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
      el("div", { id: "mon-adapter-list", className: "table-wrap monitoring-table-wrap" }),
      overviewAdapterPaginator.getControlsEl()
    );
    container.appendChild(adapterSection);

    // 8. Datasource Pool
    var dsToolbar = el("div", { className: "monitoring-table-toolbar" });
    var dsSearchWrap = el("div", { className: "monitoring-search-field" });
    var dsSearchInput = el("input", { type: "text", placeholder: "Search datasource pool...", "aria-label": "Search datasource pool" });
    dsSearchInput.addEventListener("input", function (e) {
      datasourceSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (overviewDatasourcePaginator) overviewDatasourcePaginator.goToPage(1);
      if (lastDatasourcePool) updateMonitoringDatasourcePool(lastDatasourcePool);
    });
    dsSearchWrap.appendChild(dsSearchInput);
    dsToolbar.appendChild(dsSearchWrap);
    var dsSection = el("div", { id: "mon-datasource-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Datasource Pool"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2);margin-bottom:var(--sp-3)" },
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "Cached"), el("p", { id: "mon-ds-total", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "References"), el("p", { id: "mon-ds-refs", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "Reuse Rate"), el("p", { id: "mon-ds-efficiency", className: "value" }, "0%"))
      ),
      dsToolbar,
      el("div", { id: "mon-ds-list", className: "table-wrap monitoring-table-wrap" }),
      overviewDatasourcePaginator.getControlsEl()
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
    var threadToolbar = el("div", { className: "monitoring-table-toolbar" });
    var threadSearchWrap = el("div", { className: "monitoring-search-field" });
    var threadSearchInput = el("input", { type: "text", placeholder: "Search thread pools...", "aria-label": "Search thread pools" });
    threadSearchInput.addEventListener("input", function (e) {
      threadPoolSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (overviewThreadPoolPaginator) overviewThreadPoolPaginator.goToPage(1);
      updateMonitoringThreadPools(lastThreadPools);
    });
    threadSearchWrap.appendChild(threadSearchInput);
    threadToolbar.appendChild(threadSearchWrap);
    var threadSection = el("div", { id: "mon-threadpool-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Thread Pools"),
      threadToolbar,
      el("div", { id: "mon-threadpool-list", className: "table-wrap monitoring-table-wrap" }),
      overviewThreadPoolPaginator.getControlsEl()
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
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var accountPanel = el("div", { className: "panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var userSearchFilter = "";
    var allUsers = [];
    var userFilteredEmpty = false;
    var selectedUserIds = new Set();
    var tableWrap = el("div", null, skeleton());
    var searchInput = el("input", {
      type: "text",
      placeholder: "Search users",
      "aria-label": "Search users"
    });
    var bulkDeleteBtn = el("button", { className: "danger", type: "button", disabled: "true" }, "Delete Selected");
    var userPaginator = createPaginator({
      pageSize: ITEMS_PER_PAGE,
      onPageChange: function (pageItems) {
        renderUserTable(tableWrap, pageItems, userFilteredEmpty, handleSelectUser, {
          selectedIds: selectedUserIds,
          onSelectionChange: function () {
            syncBulkActionButton(bulkDeleteBtn, selectedUserIds.size, "users");
          },
          currentUserId: currentUser && currentUser.id
        });
      }
    });

    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(accountPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    listPanel.appendChild(el("h2", null, "Users"));
    listPanel.appendChild(field("Search", searchInput));
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, bulkDeleteBtn));
    listPanel.appendChild(tableWrap);
    listPanel.appendChild(userPaginator.getControlsEl());

    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create user"
    }, svgIcon(ICON_PLUS), el("span", null, "Create User"));
    listPanel.appendChild(el("div", { className: "create-launch-row" }, createLaunchBtn));

    var usernameInput = el("input", {
      type: "text",
      required: "true",
      maxlength: String(USERNAME_MAX_LENGTH),
      placeholder: "3-50 chars. Alphanumeric and ., _, - allowed.",
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false",
      pattern: "[A-Za-z0-9._-]+"
    });
    var passwordInput = el("input", {
      type: "password",
      required: "true",
      maxlength: String(PASSWORD_MAX_LENGTH),
      placeholder: "8-128 chars. No spaces.",
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var roleSelect = el("select", null,
      el("option", { value: "user" }, "user"),
      el("option", { value: "admin" }, "admin")
    );
    var createBtn = el("button", { type: "button" }, "Create User");
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");

    function openCreatePanel() {
      createPanel.style.display = "";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function closeCreatePanel() {
      createPanel.style.display = "none";
    }

    createLaunchBtn.addEventListener("click", openCreatePanel);
    createPanelToggle.addEventListener("click", closeCreatePanel);

    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New User"),
      createPanelToggle
    ));

    var form = el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid user-create-grid" },
        field("Username", usernameInput),
        passwordField("Password", passwordInput),
        field("Role", roleSelect)
      ),
      el("div", { className: "admin-create-form-actions" }, createBtn)
    );
    createPanel.appendChild(form);
    bindValidationClear(usernameInput, passwordInput, roleSelect);

    renderSelectedUserPlaceholder(detailPanel);
    renderAccountSecurityPanel(accountPanel);

    createBtn.addEventListener("click", function () {
      var u = usernameInput.value.trim();
      var p = passwordInput.value;
      var usernameError = validateUsername(u);
      if (usernameError) { showError(usernameError); return; }
      var passwordError = validatePassword(p);
      if (passwordError) { showError(passwordError); return; }
      withButton(createBtn, async function () {
        await api("POST", ENDPOINTS.register, { username: u, password: p, role: roleSelect.value });
        usernameInput.value = "";
        passwordInput.value = "";
        roleSelect.value = "user";
        closeCreatePanel();
        loadUsers({ preferredUsername: u });
      }, "User created");
    });

    bulkDeleteBtn.addEventListener("click", function () {
      var ids = Array.from(selectedUserIds);
      if (!ids.length) return;
      confirmAction({
        title: "Delete Users",
        message: "Delete " + ids.length + " selected users? This cannot be undone.",
        confirmLabel: "Delete",
        isDanger: true,
        loadingLabel: "Deleting...",
        onConfirm: async function () {
          for (var i = 0; i < ids.length; i++) {
            await api("DELETE", ENDPOINTS.users + "/" + encodeURIComponent(ids[i]));
          }
          ids.forEach(function (id) { selectedUserIds.delete(id); });
          if (selectedUser && ids.indexOf(selectedUser.id) !== -1) selectedUser = null;
          showStatus(ids.length + " user" + (ids.length === 1 ? "" : "s") + " deleted");
          await loadUsers({ clearSelection: !selectedUser });
        }
      });
    });

    function applyUserFilter() {
      var filter = userSearchFilter;
      var filteredUsers = !filter ? allUsers : allUsers.filter(function (user) {
        return [
          user.username,
          user.role,
          user.id,
          user.active !== false ? "active" : "inactive"
        ].some(function (value) {
          return String(value || "").toLowerCase().includes(filter);
        });
      });
      userFilteredEmpty = !!allUsers.length && filteredUsers.length === 0;
      selectedUserIds.forEach(function (userId) {
        if (!allUsers.some(function (user) { return user.id === userId; })) {
          selectedUserIds.delete(userId);
        }
      });
      syncBulkActionButton(bulkDeleteBtn, selectedUserIds.size, "users");
      userPaginator.setData(filteredUsers);
    }

    function handleSelectUser(user) {
      selectedUser = user;
      renderUserDetail(detailPanel, user, function (options) {
        loadUsers(options || {});
      });
    }

    searchInput.addEventListener("input", function (e) {
      userSearchFilter = (e.target.value || "").trim().toLowerCase();
      applyUserFilter();
    });

    async function loadUsers(options) {
      options = options || {};
      try {
        var users = await api("GET", ENDPOINTS.users);
        allUsers = users;
        applyUserFilter();

        if (options.clearSelection) {
          selectedUser = null;
          renderSelectedUserPlaceholder(detailPanel);
          return;
        }

        var refreshedSelection = null;
        var preferredId = options.preferredUserId || (selectedUser && selectedUser.id);
        if (preferredId) {
          refreshedSelection = users.find(function (user) {
            return user.id === preferredId;
          });
        }
        if (!refreshedSelection && options.preferredUsername) {
          refreshedSelection = users.find(function (user) {
            return user.username === options.preferredUsername;
          });
        }

        if (refreshedSelection) {
          selectedUser = refreshedSelection;
          userPaginator.ensureItemVisible(function (user) {
            return user.id === refreshedSelection.id;
          });
          renderUserDetail(detailPanel, refreshedSelection, function (refreshOptions) {
            loadUsers(refreshOptions || {});
          });
        } else {
          selectedUser = null;
          renderSelectedUserPlaceholder(detailPanel);
        }
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load users"));
        renderSelectedUserPlaceholder(detailPanel);
      }
    }

    loadUsers();
  }

  function renderAccountSecurityPanel(panel) {
    clear(panel);
    var formWrap = el("div", { className: "collapsible-panel-body", style: "display:none" });
    var toggleBtn = el("button", { className: "secondary", type: "button" }, "Change Password");

    function openForm() {
      formWrap.style.display = "";
      toggleBtn.textContent = "Close";
    }

    function closeForm() {
      formWrap.style.display = "none";
      toggleBtn.textContent = "Change Password";
    }

    toggleBtn.addEventListener("click", function () {
      if (formWrap.style.display === "none") openForm();
      else closeForm();
    });

    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "My Account"),
      toggleBtn
    ));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Username:"), " " + ((currentUser && currentUser.username) || "N/A")),
      el("p", null, el("strong", null, "Role:"), " " + ((currentUser && currentUser.role) || "N/A"))
    ));
    renderChangeMyPassword(formWrap, closeForm);
    panel.appendChild(formWrap);
  }

  function renderChangeMyPassword(panel, onDone) {
    clear(panel);
    var curPwInput = el("input", {
      type: "password",
      placeholder: "Current password",
      maxlength: String(PASSWORD_MAX_LENGTH),
      autocomplete: "current-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var newPwInput = el("input", {
      type: "password",
      placeholder: "New password",
      maxlength: String(PASSWORD_MAX_LENGTH),
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var confirmPwInput = el("input", {
      type: "password",
      placeholder: "Confirm new password",
      maxlength: String(PASSWORD_MAX_LENGTH),
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var changeBtn = el("button", { type: "button" }, "Save Password");
    var cancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");

    cancelBtn.addEventListener("click", function () {
      curPwInput.value = "";
      newPwInput.value = "";
      confirmPwInput.value = "";
      if (onDone) onDone();
    });

    changeBtn.addEventListener("click", function () {
      var cur = curPwInput.value;
      var nw = newPwInput.value;
      var conf = confirmPwInput.value;
      if (!cur || !nw) return;
      var passwordError = validatePassword(nw);
      if (passwordError) { showError(passwordError); return; }
      if (nw !== conf) { showError("Passwords do not match"); return; }
      withButton(changeBtn, async function () {
        await api("POST", ENDPOINTS.changePassword, { current_password: cur, new_password: nw });
        curPwInput.value = "";
        newPwInput.value = "";
        confirmPwInput.value = "";
        if (onDone) onDone();
      }, "Password changed successfully");
    });

    panel.appendChild(el("div", { className: "admin-create-form" },
      el("p", { className: "muted" }, "Update the password for the account currently signed into the admin panel."),
      passwordField("Current Password", curPwInput),
      passwordField("New Password", newPwInput, "8-128 chars. No spaces."),
      passwordField("Confirm Password", confirmPwInput),
      el("div", { className: "inline-form detail-action-row" }, cancelBtn, changeBtn)
    ));
    bindValidationClear(curPwInput, newPwInput, confirmPwInput);
  }

  function renderSelectedUserPlaceholder(panel) {
    clear(panel);
    panel.style.display = "none";
  }

  function renderUserTable(wrap, users, filteredEmpty, onSelect, selection) {
    clear(wrap);
    if (!users || users.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F464}"),
        el("p", null, filteredEmpty ? "No users match the current search" : "No users found")
      ));
      return;
    }
    var table = el("table");
    var selectableUsers = users.filter(function (user) {
      return !selection.currentUserId || user.id !== selection.currentUserId;
    });
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible users"
    });
    selectAllBox.checked = selectableUsers.length > 0 && selectableUsers.every(function (user) {
      return selection.selectedIds.has(user.id);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && selectableUsers.some(function (user) {
      return selection.selectedIds.has(user.id);
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      selectableUsers.forEach(function (user) {
        if (selectAllBox.checked) selection.selectedIds.add(user.id);
        else selection.selectedIds.delete(user.id);
      });
      selection.onSelectionChange();
      renderUserTable(wrap, users, filteredEmpty, onSelect, selection);
    });
    var thead = el("thead", null,
      el("tr", null,
        el("th", { className: "selection-col" }, selectAllBox),
        el("th", null, "Username"),
        el("th", null, "Role"),
        el("th", null, "Status")
      )
    );
    var tbody = el("tbody");
    users.forEach(function (u) {
      var isSelected = selectedUser && selectedUser.id === u.id;
      var checkbox = el("input", {
        type: "checkbox",
        "aria-label": "Select user " + u.username
      });
      checkbox.checked = selection.selectedIds.has(u.id);
      if (selection.currentUserId && selection.currentUserId === u.id) {
        checkbox.disabled = true;
        checkbox.title = "You cannot bulk-delete the current admin account";
      }
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(u.id);
        else selection.selectedIds.delete(u.id);
        selection.onSelectionChange();
        renderUserTable(wrap, users, filteredEmpty, onSelect, selection);
      });
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
        el("td", null, u.username),
        el("td", null, u.role || ""),
        el("td", null,
          el("span", { className: u.active !== false ? "status-active" : "status-inactive" },
            u.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", function () {
        markSelectedRow(tbody, tr);
        onSelect(u);
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
    panel.style.display = "";
    var isCurrentUser = !!(currentUser && currentUser.id && user && user.id && currentUser.id === user.id);
    var resetPanel = el("div", { className: "collapsible-panel-body", style: "display:none" });
    var newPwInput = el("input", {
      type: "password",
      maxlength: String(PASSWORD_MAX_LENGTH),
      placeholder: "8-128 chars. No spaces.",
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var resetBtn = el("button", { type: "button" }, "Apply Reset");
    var resetCancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var resetToggle = el("button", { className: "secondary", type: "button" }, "Reset Password");

    function closeResetPanel() {
      newPwInput.value = "";
      resetPanel.style.display = "none";
      resetToggle.textContent = "Reset Password";
    }

    resetToggle.addEventListener("click", function () {
      if (resetPanel.style.display === "none") {
        resetPanel.style.display = "";
        resetToggle.textContent = "Close Reset";
      } else {
        closeResetPanel();
      }
    });

    resetCancelBtn.addEventListener("click", closeResetPanel);

    panel.appendChild(el("h2", { className: "detail-title" }, user.username || "User Details"));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "ID:"), " " + (user.id || "N/A")),
      el("p", null, el("strong", null, "Role:"), " " + (user.role || "N/A")),
      el("p", null, el("strong", null, "Status:"), " ",
        el("span", { className: user.active !== false ? "status-active" : "status-inactive" },
          user.active !== false ? "Active" : "Inactive"
        )
      )
    ));

    if (isCurrentUser) {
      panel.appendChild(el("div", { className: "danger-zone" },
        el("p", null, "The account currently used for this admin session cannot be deactivated or deleted here."),
        el("p", { className: "muted" }, "Use My Account to update your own password.")
      ));
    } else {
      var actionRow = el("div", { className: "inline-form detail-action-row" });
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
              onRefresh({ preferredUserId: user.id });
            } finally {
              toggleBtn.disabled = false;
            }
          }
        });
      });
      resetBtn.addEventListener("click", function () {
        var pw = newPwInput.value;
        if (!pw) return;
        var passwordError = validatePassword(pw);
        if (passwordError) { showError(passwordError); return; }
        confirmAction({
          title: "Reset Password",
          message: "Reset the password for " + user.username + "?",
          confirmLabel: "Reset",
          onConfirm: async function () {
            resetBtn.disabled = true;
            try {
              await api("POST", ENDPOINTS.resetPassword, { user_id: user.id, new_password: pw });
              closeResetPanel();
              showStatus("Password reset");
            } finally {
              resetBtn.disabled = false;
            }
          }
        });
      });
      actionRow.appendChild(toggleBtn);
      actionRow.appendChild(resetToggle);
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
            onRefresh({ clearSelection: true });
          }
        });
      });
      actionRow.appendChild(deleteBtn);
      panel.appendChild(actionRow);
      resetPanel.appendChild(el("div", { className: "admin-create-form user-reset-form" },
        passwordField("New Password", newPwInput),
        el("div", { className: "inline-form detail-action-row" }, resetCancelBtn, resetBtn)
      ));
      bindValidationClear(newPwInput);
      panel.appendChild(resetPanel);
    }
  }

  // ==================================================================
  // TAB: API Keys
  // ==================================================================
  async function renderKeys(container) {
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var detailPanel = el("div", { className: "panel" });
    var keySearchFilter = "";
    var selectedKeyIds = new Set();
    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    listPanel.appendChild(el("h2", null, "API Keys"));

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
    var notesInput = el("textarea", { rows: "4", maxlength: "2000" });
    var notesCounter = characterCount(notesInput, 2000);
    var createBtn = el("button", { type: "button" }, "Create Key");
    function openCreatePanel() {
      createPanel.style.display = "";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function closeCreatePanel() {
      createPanel.style.display = "none";
    }
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");
    createPanelToggle.addEventListener("click", closeCreatePanel);
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New API Key"),
      createPanelToggle
    ));
    var form = el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid api-key-create-grid" },
        field("Client", clientInput),
        field("Adapter", adapterSelect),
        field("Persona", promptSelect)
      ),
      el("div", { className: "stack" }, field("Notes", notesInput), notesCounter),
      el("div", { className: "admin-create-form-actions" },
        createBtn
      )
    );
    createPanel.appendChild(form);
    bindValidationClear(clientInput, adapterSelect, promptSelect, notesInput);

    var keySearchInput = el("input", {
      type: "text",
      placeholder: "Search API keys",
      "aria-label": "Search API keys"
    });
    listPanel.appendChild(field("Search", keySearchInput));
    var bulkDeleteBtn = el("button", { className: "danger", type: "button", disabled: "true" }, "Delete Selected");
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, bulkDeleteBtn));

    var tableWrap = el("div", null, skeleton());
    listPanel.appendChild(tableWrap);

    var keyFilteredEmpty = false;
    var keyPaginator = createPaginator({
      pageSize: ITEMS_PER_PAGE,
      onPageChange: function (pageItems) {
        renderKeyTable(tableWrap, pageItems, detailPanel, keyFilteredEmpty, {
          selectedIds: selectedKeyIds,
          onSelectionChange: function () {
            syncBulkActionButton(bulkDeleteBtn, selectedKeyIds.size, "API keys");
          }
        }, loadKeys);
      }
    });
    listPanel.appendChild(keyPaginator.getControlsEl());
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create API key"
    }, svgIcon(ICON_PLUS), el("span", null, "Create API Key"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    listPanel.appendChild(el("div", { className: "create-launch-row" }, createLaunchBtn));

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
        promptSelect.value = "";
        notesInput.value = "";
        closeCreatePanel();
        loadKeys();
      }, "API key created");
    });

    bulkDeleteBtn.addEventListener("click", function () {
      var ids = Array.from(selectedKeyIds);
      if (!ids.length) return;
      confirmAction({
        title: "Delete API Keys",
        message: "Delete " + ids.length + " selected API keys? This cannot be undone.",
        confirmLabel: "Delete",
        isDanger: true,
        loadingLabel: "Deleting...",
        onConfirm: async function () {
          for (var i = 0; i < ids.length; i++) {
            await api("DELETE", ENDPOINTS.apiKeys + "/" + encodeURIComponent(ids[i]));
          }
          ids.forEach(function (id) { selectedKeyIds.delete(id); });
          if (selectedKey && ids.indexOf(selectedKey._id) !== -1) selectedKey = null;
          showStatus(ids.length + " API key" + (ids.length === 1 ? "" : "s") + " deleted");
          await loadKeys();
        }
      });
    });

    function applyKeyFilter() {
      var keys = cachedKeys || [];
      var filter = keySearchFilter;
      var filteredKeys = !filter ? keys : keys.filter(function (key) {
        return [
          key.client_name,
          key.adapter_name,
          key.system_prompt_name,
          key.api_key
        ].some(function (value) {
          return String(value || "").toLowerCase().includes(filter);
        });
      });
      keyFilteredEmpty = !!keys.length && filteredKeys.length === 0;
      selectedKeyIds.forEach(function (keyId) {
        if (!keys.some(function (key) { return key._id === keyId; })) {
          selectedKeyIds.delete(keyId);
        }
      });
      syncBulkActionButton(bulkDeleteBtn, selectedKeyIds.size, "API keys");
      keyPaginator.setData(filteredKeys);
    }

    keySearchInput.addEventListener("input", function (e) {
      keySearchFilter = (e.target.value || "").trim().toLowerCase();
      applyKeyFilter();
    });

    async function loadKeys() {
      try {
        var keys = await api("GET", ENDPOINTS.apiKeys);
        cachedKeys = keys;
        applyKeyFilter();
        selectedKeyIds.forEach(function (keyId) {
          if (!keys.some(function (key) { return key._id === keyId; })) {
            selectedKeyIds.delete(keyId);
          }
        });
        syncBulkActionButton(bulkDeleteBtn, selectedKeyIds.size, "API keys");
        if (selectedKey && selectedKey._id) {
          var refreshedSelection = keys.find(function (key) {
            return key._id === selectedKey._id;
          });
          if (refreshedSelection) {
            selectedKey = refreshedSelection;
            keyPaginator.ensureItemVisible(function (k) { return k._id === selectedKey._id; });
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
        } else {
          clear(detailPanel);
          detailPanel.appendChild(el("h2", null, "Key Details"));
          detailPanel.appendChild(el("p", { className: "muted" }, "Select an API key to manage"));
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
      // Use adapter capabilities endpoint to get actual active adapters from the dynamic adapter manager
      if (!cachedAdapterCapabilities) {
        await loadAdapterCapabilities();
      }
      if (cachedAdapterCapabilities && cachedAdapterCapabilities.length) {
        cachedAdapters = cachedAdapterCapabilities;
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
      var label = key.client_name || "Unnamed key";
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
    var toggleBtn = el("button", {
      className: "secondary markdown-preview-toggle",
      type: "button",
      style: "display:none"
    }, "Expand");
    var frame = el("div", { className: "markdown-preview-shell" },
      el("div", { className: "markdown-preview-header" },
        el("span", null, "Preview"),
        toggleBtn
      ),
      el("div", { className: "markdown-preview markdown-preview-collapsed is-empty", "aria-live": "polite" },
        el("p", { className: "muted" }, "Nothing to preview yet.")
      )
    );
    var body = frame.querySelector(".markdown-preview");
    var requestToken = 0;
    var expanded = false;

    function syncPreviewToggle() {
      requestAnimationFrame(function () {
        var needsToggle = body.scrollHeight > 320;
        toggleBtn.style.display = needsToggle ? "inline-flex" : "none";
        if (!needsToggle) {
          expanded = false;
          body.classList.remove("markdown-preview-expanded");
          body.classList.add("markdown-preview-collapsed");
          toggleBtn.textContent = "Expand";
        }
      });
    }

    toggleBtn.addEventListener("click", function () {
      expanded = !expanded;
      body.classList.toggle("markdown-preview-expanded", expanded);
      body.classList.toggle("markdown-preview-collapsed", !expanded);
      toggleBtn.textContent = expanded ? "Collapse" : "Expand";
    });

    async function renderPreview() {
      var text = textarea.value.trim();
      if (!text) {
        expanded = false;
        body.className = "markdown-preview markdown-preview-collapsed is-empty";
        body.innerHTML = '<p class="muted">Nothing to preview yet.</p>';
        toggleBtn.style.display = "none";
        return;
      }

      var token = ++requestToken;
      body.className = "markdown-preview markdown-preview-collapsed is-loading";
      body.innerHTML = '<p class="muted">Rendering preview...</p>';
      toggleBtn.style.display = "none";

      try {
        var result = await api("POST", ENDPOINTS.renderMarkdown, { markdown: text });
        if (token !== requestToken) return;
        body.className = "markdown-preview markdown-preview-collapsed";
        body.innerHTML = result && result.html ? result.html : "<p></p>";
        syncPreviewToggle();
      } catch (err) {
        if (token !== requestToken) return;
        body.className = "markdown-preview markdown-preview-collapsed is-error";
        body.textContent = "Preview unavailable: " + err.message;
        toggleBtn.style.display = "none";
      }
    }

    textarea.addEventListener("input", debounce(renderPreview, 220));
    renderPreview();
    return frame;
  }

  function renderKeyTable(wrap, keys, rightPanel, filteredEmpty, selection, reloadKeys) {
    clear(wrap);
    if (!keys || keys.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F511}"),
        el("p", null, filteredEmpty ? "No API keys match this search" : "No API keys found")
      ));
      return;
    }
    var table = el("table");
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible API keys"
    });
    selectAllBox.checked = keys.length > 0 && keys.every(function (key) {
      return selection.selectedIds.has(key._id);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && keys.some(function (key) {
      return selection.selectedIds.has(key._id);
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      keys.forEach(function (key) {
        if (selectAllBox.checked) selection.selectedIds.add(key._id);
        else selection.selectedIds.delete(key._id);
      });
      selection.onSelectionChange();
      renderKeyTable(wrap, keys, rightPanel, filteredEmpty, selection, reloadKeys);
    });
    var thead = el("thead", null,
      el("tr", null,
        el("th", { className: "selection-col" }, selectAllBox),
        el("th", null, "Client"),
        el("th", null, "Adapter"),
        el("th", null, "Persona"),
        el("th", null, "Active")
      )
    );
    var tbody = el("tbody");
    keys.forEach(function (k) {
      var isSelected = selectedKey && selectedKey._id && k._id && selectedKey._id === k._id;
      var checkbox = el("input", {
        type: "checkbox",
        "aria-label": "Select API key " + (k.client_name || k._id || "")
      });
      checkbox.checked = selection.selectedIds.has(k._id);
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(k._id);
        else selection.selectedIds.delete(k._id);
        selection.onSelectionChange();
        renderKeyTable(wrap, keys, rightPanel, filteredEmpty, selection, reloadKeys);
      });
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
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
            reloadKeys();
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
    panel.appendChild(el("h2", { className: "detail-title" }, key.client_name || "API Key Details"));
    var revealSecret = false;
    var keyCode = el("code", null, maskSecret(keyVal));
    var revealBtn = el("button", {
      type: "button",
      className: "password-toggle",
      "aria-label": "Show API key",
      title: "Show API key",
    });
    revealBtn.appendChild(svgIcon(ICON_EYE));
    revealBtn.addEventListener("click", function () {
      revealSecret = !revealSecret;
      keyCode.textContent = revealSecret ? keyVal : maskSecret(keyVal);
      revealBtn.setAttribute("aria-label", revealSecret ? "Hide API key" : "Show API key");
      revealBtn.setAttribute("title", revealSecret ? "Hide API key" : "Show API key");
      revealBtn.innerHTML = "";
      revealBtn.appendChild(svgIcon(revealSecret ? ICON_EYE_OFF : ICON_EYE));
    });
    var copyBtn = el("button", {
      type: "button",
      className: "copy-btn",
      "aria-label": "Copy API key",
      title: "Copy API key",
    });
    copyBtn.appendChild(svgIcon(ICON_COPY));
    copyBtn.addEventListener("click", function () {
      navigator.clipboard.writeText(keyVal).then(function () {
        copyBtn.innerHTML = "";
        copyBtn.appendChild(svgIcon(ICON_CHECK));
        setTimeout(function () { copyBtn.innerHTML = ""; copyBtn.appendChild(svgIcon(ICON_COPY)); }, 1500);
      });
    });
    var keyField = el("div", { className: "secret-field" }, keyCode, revealBtn, copyBtn);
    var notesInput = el("textarea", { rows: "4", maxlength: "2000" }, key.notes || "");
    var notesCounter = characterCount(notesInput, 2000);
    var notesPreview = createMarkdownPreview(notesInput);

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Key:"), " ", keyField),
      el("p", null, el("strong", null, "Client:"), " " + (key.client_name || "N/A")),
      el("p", null, el("strong", null, "Adapter:"), " " + (key.adapter_name || "default")),
      el("p", null, el("strong", null, "Persona:"), " " + (key.system_prompt_name || "None")),
      el("p", null, el("strong", null, "Created:"), " " + (key.created_at ? new Date(key.created_at * 1000).toLocaleString() : "N/A")),
      el("p", null, el("strong", null, "Active:"), " ",
        el("span", { className: key.active !== false ? "status-active" : "status-inactive" },
          key.active !== false ? "Active" : "Inactive"
        )
      )
    );
    panel.appendChild(summary);
    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      el("h3", null, "Notes"),
      notesPreview
    ));
    var clientInput = el("input", { type: "text", maxlength: "100", value: key.client_name || "" });
    var adapterSelect = el("select");
    var availableAdapterNames = [];
    if (cachedAdapters) {
      cachedAdapters.forEach(function (a) {
        var name = typeof a === "string" ? a : (a.name || a.adapter_name || "");
        if (name && availableAdapterNames.indexOf(name) === -1) availableAdapterNames.push(name);
      });
    }
    if (key.adapter_name && availableAdapterNames.indexOf(key.adapter_name) === -1) {
      availableAdapterNames.push(key.adapter_name);
    }
    if (availableAdapterNames.length) {
      availableAdapterNames.forEach(function (name) {
        var option = el("option", { value: name }, name);
        if (name === key.adapter_name) option.selected = true;
        adapterSelect.appendChild(option);
      });
    } else {
      adapterSelect.appendChild(el("option", { value: key.adapter_name || "" }, key.adapter_name || "No adapters available"));
      adapterSelect.disabled = true;
    }
    var promptSelect = el("select", null, el("option", { value: "" }, "No persona"));
    fillPromptSelect(promptSelect, cachedPrompts, key.system_prompt_id);
    var saveBtn = el("button", { type: "button" }, "Save Details");
    var originalClientName = key.client_name || "";
    var originalAdapterName = key.adapter_name || "";
    var originalPromptId = key.system_prompt_id || "";
    var originalNotes = key.notes || "";
    var editForm = el("div", { style: "display:none" },
      el("div", { className: "admin-create-form" },
        el("div", { className: "admin-create-form-grid api-key-create-grid" },
          field("Client", clientInput),
          field("Adapter", adapterSelect),
          field("Persona", promptSelect)
        ),
        el("div", { className: "stack" }, field("Notes", notesInput), notesCounter)
      )
    );
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Details");
    var cancelBtn = el("button", { className: "secondary", type: "button", style: "display:none" }, "Cancel");
    saveBtn.style.display = "none";
    function keyDetailsChanged() {
      return clientInput.value.trim() !== originalClientName ||
        adapterSelect.value !== originalAdapterName ||
        (promptSelect.value || "") !== originalPromptId ||
        notesInput.value !== originalNotes;
    }
    function syncKeySaveState() {
      saveBtn.disabled = !keyDetailsChanged();
    }
    function setKeyEditMode(editing) {
      clientInput.readOnly = !editing;
      clientInput.setAttribute("aria-readonly", editing ? "false" : "true");
      if (editing) clientInput.removeAttribute("readonly");
      else clientInput.setAttribute("readonly", "true");
      adapterSelect.disabled = !editing;
      promptSelect.disabled = !editing;
      notesInput.readOnly = !editing;
      notesInput.setAttribute("aria-readonly", editing ? "false" : "true");
      if (editing) notesInput.removeAttribute("readonly");
      else notesInput.setAttribute("readonly", "true");
      editForm.style.display = editing ? "block" : "none";
      editToggle.style.display = editing ? "none" : "inline-flex";
      cancelBtn.style.display = editing ? "inline-flex" : "none";
      saveBtn.style.display = editing ? "inline-flex" : "none";
      syncKeySaveState();
    }
    editToggle.addEventListener("click", function () {
      setKeyEditMode(true);
    });
    cancelBtn.addEventListener("click", function () {
      clientInput.value = originalClientName;
      adapterSelect.value = originalAdapterName;
      promptSelect.value = originalPromptId;
      notesInput.value = originalNotes;
      setKeyEditMode(false);
    });
    clientInput.addEventListener("input", syncKeySaveState);
    adapterSelect.addEventListener("change", syncKeySaveState);
    promptSelect.addEventListener("change", syncKeySaveState);
    notesInput.addEventListener("input", syncKeySaveState);
    bindValidationClear(clientInput, adapterSelect, promptSelect, notesInput);
    saveBtn.addEventListener("click", function () {
      var clientName = clientInput.value.trim();
      if (!clientName) {
        showError("Client is required.");
        return;
      }
      if (!adapterSelect.value) {
        showError("Adapter is required.");
        return;
      }
      withButton(saveBtn, async function () {
        await api("PUT", ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId), {
          client_name: clientName,
          adapter_name: adapterSelect.value,
          system_prompt_id: promptSelect.value || null,
          notes: notesInput.value.trim() || null
        });
        onRefresh();
      }, "API key updated");
    });
    panel.appendChild(el("div", { className: "stack" },
      el("div", { className: "inline-form detail-action-row" }, editToggle, cancelBtn, saveBtn),
      editForm
    ));
    setKeyEditMode(false);

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
    bindValidationClear(renameInput);
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
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var promptSearchFilter = "";
    var selectedPromptIds = new Set();
    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    listPanel.appendChild(el("h2", null, "Personas"));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var versionInput = el("input", { type: "text", value: "1.0", maxlength: "25" });
    var textArea = el("textarea", { rows: "5", required: "true", maxlength: "10000" });
    var textCounter = characterCount(textArea, 10000);
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

    function openCreatePanel() {
      createPanel.style.display = "";
      if (!selectedPrompt) detailPanel.style.display = "none";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function closeCreatePanel() {
      createPanel.style.display = "none";
    }
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");
    createPanelToggle.addEventListener("click", closeCreatePanel);
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New Persona"),
      createPanelToggle
    ));
    var form = el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid persona-create-grid" },
        field("Name", nameInput),
        field("Version", versionInput),
        field("API Key", createKeySelect)
      ),
      el("div", { className: "stack" }, field("Persona", textArea), textCounter),
      el("div", { className: "admin-create-form-actions" }, createBtn)
    );
    createPanel.appendChild(form);
    bindValidationClear(nameInput, versionInput, textArea, createKeySelect);

    var promptSearchInput = el("input", {
      type: "text",
      placeholder: "Search personas",
      "aria-label": "Search personas"
    });
    listPanel.appendChild(field("Search", promptSearchInput));
    var bulkDeleteBtn = el("button", { className: "danger", type: "button", disabled: "true" }, "Delete Selected");
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, bulkDeleteBtn));

    var tableWrap = el("div", null, skeleton());
    listPanel.appendChild(tableWrap);

    var promptFilteredEmpty = false;
    var promptPaginator = createPaginator({
      pageSize: ITEMS_PER_PAGE,
      onPageChange: function (pageItems) {
        renderPromptTable(tableWrap, pageItems, detailPanel, promptFilteredEmpty, refreshPrompts, {
          selectedIds: selectedPromptIds,
          onSelectionChange: function () {
            syncBulkActionButton(bulkDeleteBtn, selectedPromptIds.size, "personas");
          }
        });
      }
    });
    listPanel.appendChild(promptPaginator.getControlsEl());
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create persona"
    }, svgIcon(ICON_PLUS), el("span", null, "Create Persona"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    listPanel.appendChild(el("div", { className: "create-launch-row" }, createLaunchBtn));

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
        closeCreatePanel();
        refreshPrompts(createdPrompt ? promptIdentifier(createdPrompt) : null, createdPrompt || null);
      }, "Persona created");
    });

    bulkDeleteBtn.addEventListener("click", function () {
      var ids = Array.from(selectedPromptIds);
      if (!ids.length) return;
      confirmAction({
        title: "Delete Personas",
        message: "Delete " + ids.length + " selected personas? This cannot be undone.",
        confirmLabel: "Delete",
        isDanger: true,
        loadingLabel: "Deleting...",
        onConfirm: async function () {
          for (var i = 0; i < ids.length; i++) {
            await api("DELETE", ENDPOINTS.prompts + "/" + encodeURIComponent(ids[i]));
          }
          ids.forEach(function (id) { selectedPromptIds.delete(id); });
          if (selectedPrompt && ids.indexOf(promptIdentifier(selectedPrompt)) !== -1) selectedPrompt = null;
          showStatus(ids.length + " persona" + (ids.length === 1 ? "" : "s") + " deleted");
          await refreshPrompts();
        }
      });
    });

    function applyPromptFilter() {
      var prompts = cachedPrompts || [];
      var filter = promptSearchFilter;
      var filteredPrompts = !filter ? prompts : prompts.filter(function (prompt) {
        return [
          promptIdentifier(prompt),
          prompt.name,
          prompt.version
        ].some(function (value) {
          return String(value || "").toLowerCase().includes(filter);
        });
      });
      promptFilteredEmpty = !!prompts.length && filteredPrompts.length === 0;
      selectedPromptIds.forEach(function (promptId) {
        if (!prompts.some(function (prompt) { return promptIdentifier(prompt) === promptId; })) {
          selectedPromptIds.delete(promptId);
        }
      });
      syncBulkActionButton(bulkDeleteBtn, selectedPromptIds.size, "personas");
      promptPaginator.setData(filteredPrompts);
    }

    promptSearchInput.addEventListener("input", function (e) {
      promptSearchFilter = (e.target.value || "").trim().toLowerCase();
      applyPromptFilter();
    });

    async function refreshPrompts(selectedPromptId, preferredPrompt) {
      try {
        var prompts = await api("GET", ENDPOINTS.prompts);
        if (preferredPrompt && promptIdentifier(preferredPrompt)) {
          prompts = (prompts || []).map(function (prompt) {
            return promptIdentifier(prompt) === promptIdentifier(preferredPrompt)
              ? Object.assign({}, prompt, preferredPrompt)
              : prompt;
          });
        }
        cachedPrompts = prompts;
        applyPromptFilter();
        var activePromptId = selectedPromptId || (selectedPrompt && promptIdentifier(selectedPrompt));
        if (activePromptId) {
          var refreshedSelection = prompts.find(function (prompt) {
            return promptIdentifier(prompt) === activePromptId;
          });
          if (refreshedSelection) {
            if (preferredPrompt && promptIdentifier(preferredPrompt) === activePromptId) {
              refreshedSelection = Object.assign({}, refreshedSelection, preferredPrompt);
            }
            selectedPrompt = refreshedSelection;
            promptPaginator.ensureItemVisible(function (p) { return promptIdentifier(p) === activePromptId; });
            renderPromptDetail(detailPanel, refreshedSelection, function (nextSelectedPromptId, nextPreferredPrompt) {
              refreshPrompts(nextSelectedPromptId || activePromptId, nextPreferredPrompt || null);
            });
            return;
          }
        }
        selectedPrompt = null;
        clear(detailPanel);
        detailPanel.style.display = "none";
      } catch (err) {
        clear(tableWrap);
        tableWrap.appendChild(el("p", { className: "muted" }, "Failed to load personas"));
      }
    }

    refreshPrompts();
  }

  function renderPromptTable(wrap, prompts, rightPanel, filteredEmpty, refreshPrompts, selection) {
    clear(wrap);
    if (!prompts || prompts.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F4DD}"),
        el("p", null, filteredEmpty ? "No personas match this search" : "No personas found")
      ));
      return;
    }
    var table = el("table");
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible personas"
    });
    selectAllBox.checked = prompts.length > 0 && prompts.every(function (prompt) {
      return selection.selectedIds.has(promptIdentifier(prompt));
    });
    selectAllBox.indeterminate = !selectAllBox.checked && prompts.some(function (prompt) {
      return selection.selectedIds.has(promptIdentifier(prompt));
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      prompts.forEach(function (prompt) {
        var promptId = promptIdentifier(prompt);
        if (!promptId) return;
        if (selectAllBox.checked) selection.selectedIds.add(promptId);
        else selection.selectedIds.delete(promptId);
      });
      selection.onSelectionChange();
      renderPromptTable(wrap, prompts, rightPanel, filteredEmpty, refreshPrompts, selection);
    });
    var thead = el("thead", null,
      el("tr", null,
        el("th", { className: "selection-col" }, selectAllBox),
        el("th", null, "ID"),
        el("th", null, "Name"),
        el("th", null, "Version")
      )
    );
    var tbody = el("tbody");
    prompts.forEach(function (p) {
      var promptId = promptIdentifier(p);
      var isSelected = selectedPrompt && promptIdentifier(selectedPrompt) === promptId;
      var checkbox = el("input", {
        type: "checkbox",
        "aria-label": "Select persona " + (p.name || promptId || "")
      });
      checkbox.checked = selection.selectedIds.has(promptId);
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(promptId);
        else selection.selectedIds.delete(promptId);
        selection.onSelectionChange();
        renderPromptTable(wrap, prompts, rightPanel, filteredEmpty, refreshPrompts, selection);
      });
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
        el("td", null, el("code", { className: "plain-code" }, promptId)),
        el("td", null, p.name),
        el("td", null, p.version || "")
      );
      tr.addEventListener("click", function () {
        selectedPrompt = p;
        markSelectedRow(tbody, tr);
        renderPromptDetail(rightPanel, p, function (nextSelectedPromptId, nextPreferredPrompt) {
          refreshPrompts(nextSelectedPromptId || promptIdentifier(p), nextPreferredPrompt || null);
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
    panel.style.display = "";
    var promptId = promptIdentifier(prompt);
    panel.appendChild(el("h2", null, prompt.name));

    var summary = el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Name:"), " " + prompt.name),
      el("p", null, el("strong", null, "ID:"), " ", el("code", { className: "plain-code" }, promptId)),
      el("p", null, el("strong", null, "Version:"), " " + (prompt.version || "1.0"))
    );
    panel.appendChild(summary);

    // Edit
    var originalName = prompt.name || "";
    var originalVersion = prompt.version || "1.0";
    var originalPromptText = prompt.prompt || "";
    var isEditingPrompt = false;
    var nameInput = el("input", { type: "text", value: prompt.name || "", maxlength: "100", readonly: "true", "aria-readonly": "true" });
    var vInput = el("input", { type: "text", value: prompt.version || "1.0", maxlength: "25", readonly: "true", "aria-readonly": "true" });
    var tArea = el("textarea", { rows: "8", maxlength: "10000", readonly: "true", "aria-readonly": "true" }, prompt.prompt || "");
    var tCounter = characterCount(tArea, 10000);
    var saveBtn = el("button", { type: "button" }, "Save Changes");
    saveBtn.style.display = "none";
    saveBtn.addEventListener("click", function () {
      if (saveBtn.disabled) return;
      withButton(saveBtn, async function () {
        var savedPrompt = await api("PUT", ENDPOINTS.prompts + "/" + encodeURIComponent(promptId), {
          name: nameInput.value.trim(),
          prompt: tArea.value,
          version: vInput.value.trim(),
        });
        await loadAvailableKeys();
        var updatedPrompt = Object.assign({}, prompt, savedPrompt || {}, {
          name: nameInput.value.trim(),
          prompt: tArea.value,
          version: vInput.value.trim(),
        });
        onRefresh(promptId, updatedPrompt);
      }, "Persona updated");
    });
    
    var editPreview = createMarkdownPreview(tArea);
    var editorWrap = el("div", { className: "prompt-editor-pane", style: "display:none" },
      el("div", { className: "admin-create-form-grid persona-create-grid" },
        field("Name", nameInput),
        field("Version", vInput)
      ),
      el("div", { className: "stack" }, field("Persona Text", tArea), tCounter)
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Persona");
    var cancelBtn = el("button", { className: "secondary", type: "button", style: "display:none" }, "Cancel");
    function promptHasChanges() {
      return nameInput.value.trim() !== originalName || vInput.value.trim() !== originalVersion || tArea.value !== originalPromptText;
    }
    function syncPromptSaveState() {
      saveBtn.disabled = !isEditingPrompt || !promptHasChanges();
    }
    function setPromptEditMode(editing) {
      isEditingPrompt = editing;
      nameInput.readOnly = !editing;
      nameInput.setAttribute("aria-readonly", editing ? "false" : "true");
      if (editing) nameInput.removeAttribute("readonly");
      else nameInput.setAttribute("readonly", "true");
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
      saveBtn.style.display = editing ? "inline-flex" : "none";
      syncPromptSaveState();
    }
    editToggle.addEventListener("click", function () {
      setPromptEditMode(true);
    });
    cancelBtn.addEventListener("click", function () {
      nameInput.value = originalName;
      vInput.value = originalVersion;
      tArea.value = originalPromptText;
      tArea.dispatchEvent(new Event("input"));
      setPromptEditMode(false);
    });
    nameInput.addEventListener("input", syncPromptSaveState);
    vInput.addEventListener("input", syncPromptSaveState);
    tArea.addEventListener("input", syncPromptSaveState);
    bindValidationClear(nameInput, vInput, tArea);
    syncPromptSaveState();
    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      el("div", { className: "inline-form" }, editToggle, cancelBtn, saveBtn),
      previewWrap,
      editorWrap
    ));
    setPromptEditMode(false);

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
          onRefresh(null);
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
    clear(container);

    // --- Action bar: Server control ---
    var actionBar = el("div", { className: "ops-action-bar" });

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

    actionBar.appendChild(restartBtn);
    actionBar.appendChild(shutdownBtn);
    container.appendChild(actionBar);

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

  // ==================================================================
  // TAB: Adapters
  // ==================================================================

  async function loadAdapterFiles() {
    try {
      var data = await api("GET", ENDPOINTS.adapterConfigs);
      cachedAdapterFiles = data.files || [];
    } catch (_) {
      cachedAdapterFiles = [];
    }
    return cachedAdapterFiles;
  }

  function renderAdapters(container) {
    clear(container);

    // Destroy previous editor
    if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }

    // Lazy-load adapter file listing
    if (!cachedAdapterFiles) {
      container.appendChild(skeleton());
      loadAdapterFiles().then(function () {
        if (activeTab === "adapters") renderAdapters(container);
      });
      return;
    }

    var layout = el("div", { className: "tab-stacked-layout" });
    container.appendChild(layout);

    // ----- List panel: adapter list -----
    var leftPanel = el("div", { className: "panel" });
    layout.appendChild(leftPanel);

    var leftHeader = el("div", { style: "display:flex;align-items:center;gap:var(--sp-3);margin-bottom:var(--sp-3)" });
    leftHeader.appendChild(el("h2", { style: "margin:0" }, "Adapters"));
    var searchInput = el("input", { type: "text", placeholder: "Search adapters\u2026", style: "flex:1;min-width:0" });
    leftHeader.appendChild(searchInput);
    leftPanel.appendChild(leftHeader);

    var table = el("table");
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Name"),
        el("th", null, "Type"),
        el("th", { style: "width:70px;text-align:center" }, "Enabled")
      )
    );
    table.appendChild(thead);
    var tbody = el("tbody");
    table.appendChild(tbody);
    leftPanel.appendChild(table);

    // Flatten adapters from imported files only
    var allAdapters = [];
    (cachedAdapterFiles || []).forEach(function (f) {
      if (!f.imported) return; // Only show imported adapter files
      (f.adapters || []).forEach(function (a) {
        allAdapters.push({
          name: a.name,
          enabled: a.enabled !== false,
          type: a.type || "",
          adapter: a.adapter || "",
          datasource: a.datasource || "",
          inference_provider: a.inference_provider || "",
          model: a.model || "",
          embedding_provider: a.embedding_provider || "",
          filename: f.filename,
        });
      });
    });

    function makeToggle(a) {
      var track = el("button", {
        type: "button",
        className: "adapter-toggle" + (a.enabled ? " on" : ""),
        "aria-label": (a.enabled ? "Disable" : "Enable") + " adapter " + a.name,
        "aria-pressed": String(a.enabled),
      });
      var knob = el("span", { className: "adapter-toggle-knob" });
      track.appendChild(knob);

      track.addEventListener("click", function (e) {
        e.stopPropagation();
        var newState = !a.enabled;
        track.disabled = true;
        api("PATCH", ENDPOINTS.adapterConfigs + "/entry/" + encodeURIComponent(a.name) + "/toggle", { enabled: newState })
          .then(function () {
            a.enabled = newState;
            track.classList.toggle("on", newState);
            track.setAttribute("aria-pressed", String(newState));
            track.setAttribute("aria-label", (newState ? "Disable" : "Enable") + " adapter " + a.name);
            // Update cached data
            (cachedAdapterFiles || []).forEach(function (f) {
              (f.adapters || []).forEach(function (ca) {
                if (ca.name === a.name) ca.enabled = newState;
              });
            });
            showStatus("Adapter '" + a.name + "' " + (newState ? "enabled" : "disabled") + ". Reload to apply.");
          })
          .catch(function (err) { showError("Toggle failed: " + err.message); })
          .finally(function () { track.disabled = false; });
      });
      return track;
    }

    function buildAdapterRows(pageItems) {
      clear(tbody);
      if (!pageItems || pageItems.length === 0) {
        tbody.appendChild(el("tr", null, el("td", { colSpan: "3", className: "empty-state" }, "No adapters found")));
        return;
      }
      pageItems.forEach(function (a) {
        var row = el("tr", { className: "selectable-row", tabindex: "0" },
          el("td", null, a.name),
          el("td", null, a.adapter || a.type),
          el("td", { className: "adapter-toggle-cell" }, makeToggle(a))
        );

        if (selectedAdapterEntry && selectedAdapterEntry.name === a.name) {
          row.classList.add("selected-row");
          row.setAttribute("aria-selected", "true");
        }

        row.addEventListener("click", function () { selectAdapter(a); markSelectedRow(tbody, row); });
        row.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectAdapter(a); markSelectedRow(tbody, row); }
        });
        tbody.appendChild(row);
      });
    }

    var adapterPaginator = createPaginator({
      pageSize: ITEMS_PER_PAGE,
      onPageChange: function (pageItems) {
        buildAdapterRows(pageItems);
      }
    });
    leftPanel.appendChild(adapterPaginator.getControlsEl());

    function renderAdapterRows(filter) {
      var lc = (filter || "").toLowerCase();
      var filtered = !lc ? allAdapters : allAdapters.filter(function (a) {
        return a.name.toLowerCase().indexOf(lc) !== -1 || a.adapter.toLowerCase().indexOf(lc) !== -1;
      });
      adapterPaginator.setData(filtered);
    }

    searchInput.addEventListener("input", function () { renderAdapterRows(searchInput.value); });
    renderAdapterRows("");

    // ----- Detail panel: editor + actions -----
    var detailPanel = el("div", { className: "panel" });
    layout.appendChild(detailPanel);

    function renderEmptyDetail() {
      clear(detailPanel);
      detailPanel.appendChild(el("div", { className: "empty-state" },
        el("p", null, "Select an adapter to view and edit its configuration.")
      ));
    }

    function selectAdapter(a) {
      // If dirty and switching to a different adapter, confirm discard
      if (adapterEditor && selectedAdapterEntry && selectedAdapterEntry.name !== a.name) {
        var currentContent = adapterEditor.getValue();
        if (currentContent !== adapterOriginal) {
          confirmAction({
            title: "Unsaved Changes",
            message: "You have unsaved changes to '" + selectedAdapterEntry.name + "'. Discard them?",
            confirmLabel: "Discard",
            isDanger: true,
            onConfirm: function () {
              selectedAdapterEntry = a;
              renderDetail(a);
            }
          });
          return;
        }
      }
      selectedAdapterEntry = a;
      renderDetail(a);
    }

    function renderDetail(a) {
      clear(detailPanel);
      if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }

      // Header
      var headerRow = el("div", { style: "display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-2)" });
      headerRow.appendChild(el("h3", { style: "margin:0" }, a.name));
      headerRow.appendChild(el("span", { className: "monitoring-badge " + (a.enabled ? "green" : "muted") },
        a.enabled ? "enabled" : "disabled"
      ));
      headerRow.appendChild(el("span", { className: "adapter-file-badge" }, a.filename));
      detailPanel.appendChild(headerRow);

      // Info chips
      var chips = el("div", { className: "adapter-info-chips" });
      if (a.adapter) chips.appendChild(makeChip("adapter", a.adapter));
      if (a.type) chips.appendChild(makeChip("type", a.type));
      if (a.datasource) chips.appendChild(makeChip("datasource", a.datasource));
      if (a.inference_provider) chips.appendChild(makeChip("inference", a.inference_provider));
      if (a.model) chips.appendChild(makeChip("model", a.model));
      if (a.embedding_provider) chips.appendChild(makeChip("embedding", a.embedding_provider));
      if (chips.children.length) detailPanel.appendChild(chips);

      // Banner for save feedback
      var banner = el("div", { className: "settings-banner", style: "display:none", role: "status" });
      detailPanel.appendChild(banner);

      // Ace editor
      var editorWrap = el("div", { className: "adapter-ace-wrap" });
      detailPanel.appendChild(editorWrap);

      // Buttons
      var saveBtn = el("button", { className: "btn btn--primary", disabled: "true" }, "Save");
      var reloadDiskBtn = el("button", { className: "btn btn--neutral" }, "Reload from Disk");
      var reloadAdapterBtn = el("button", { className: "btn btn--neutral" }, "Reload Adapter");
      var reloadTemplatesBtn = el("button", { className: "btn btn--neutral" }, "Reload Templates");

      var btnRow = el("div", { style: "display:flex;flex-wrap:wrap;gap:var(--sp-2);margin-top:var(--sp-3)" });
      btnRow.appendChild(saveBtn);
      btnRow.appendChild(reloadDiskBtn);
      btnRow.appendChild(el("span", { className: "ops-action-divider" }));
      btnRow.appendChild(reloadAdapterBtn);
      btnRow.appendChild(reloadTemplatesBtn);
      detailPanel.appendChild(btnRow);

      // Initialise Ace
      ace.config.set("basePath", "/static");
      ace.config.set("modePath", "/static");
      ace.config.set("themePath", "/static");
      ace.config.set("workerPath", "/static");

      adapterEditor = ace.edit(editorWrap, {
        mode: "ace/mode/yaml",
        theme: "ace/theme/tomorrow",
        fontSize: 15,
        fontFamily: "var(--font-mono)",
        showPrintMargin: false,
        tabSize: 2,
        useSoftTabs: true,
        wrap: false,
        showGutter: true,
        highlightActiveLine: true,
        highlightSelectedWord: true,
        showFoldWidgets: true,
        displayIndentGuides: true,
        scrollPastEnd: 0.2,
      });
      ace.config.loadModule("ace/ext/searchbox", function () {});

      // Dirty tracking
      adapterEditor.session.on("change", function () {
        saveBtn.disabled = adapterEditor.getValue() === adapterOriginal;
      });

      // Load single adapter entry content
      async function loadEntry() {
        try {
          var data = await api("GET", ENDPOINTS.adapterConfigs + "/entry/" + encodeURIComponent(a.name));
          adapterOriginal = data.content;
          adapterEditor.setValue(data.content, -1);
          adapterEditor.getSession().getUndoManager().reset();
          saveBtn.disabled = true;
          banner.style.display = "none";
        } catch (err) {
          showError("Failed to load adapter '" + a.name + "': " + err.message);
        }
      }

      // Save handler — saves just this adapter's block back into its file
      saveBtn.addEventListener("click", async function () {
        saveBtn.disabled = true;
        try {
          await api("PUT", ENDPOINTS.adapterConfigs + "/entry/" + encodeURIComponent(a.name), { content: adapterEditor.getValue() });
          adapterOriginal = adapterEditor.getValue();
          // Refresh adapter list
          await loadAdapterFiles();
          renderAdapterRows(searchInput.value);
          // Show banner
          clear(banner);
          var reloadNowBtn = el("button", { className: "btn btn--neutral", style: "margin-left:var(--sp-3);padding:var(--sp-1) var(--sp-2);font-size:var(--text-xs)" }, "Reload Now");
          reloadNowBtn.addEventListener("click", function () {
            doReloadAdapter();
          });
          banner.appendChild(el("span", null, "Saved. Reload adapter to apply changes. "));
          banner.appendChild(reloadNowBtn);
          banner.style.display = "";
          showStatus("Adapter '" + a.name + "' saved");
        } catch (err) {
          showError("Save failed: " + err.message);
          saveBtn.disabled = adapterEditor.getValue() === adapterOriginal;
        }
      });

      // Reload from disk
      reloadDiskBtn.addEventListener("click", function () {
        var dirty = adapterEditor.getValue() !== adapterOriginal;
        if (dirty) {
          confirmAction({
            title: "Reload from Disk",
            message: "Discard unsaved changes and reload '" + a.name + "' from disk?",
            confirmLabel: "Discard & Reload",
            isDanger: true,
            onConfirm: async function () {
              await loadEntry();
              showStatus("Reloaded from disk");
            }
          });
        } else {
          loadEntry().then(function () { showStatus("Reloaded from disk"); });
        }
      });

      // Reload adapter (hot-swap via existing endpoint)
      async function doReloadAdapter() {
        withButton(reloadAdapterBtn, async function () {
          var path = ENDPOINTS.reloadAdapters + "/async?adapter_name=" + encodeURIComponent(a.name);
          var started = await api("POST", path);
          var job = await waitForAdminJob(started.job_id, "Reloading adapter\u2026");
          await loadAdapterCapabilities();
          banner.style.display = "none";
          showStatus("Adapter '" + a.name + "' reloaded");
        });
      }
      reloadAdapterBtn.addEventListener("click", function () {
        confirmAction({
          title: "Reload Adapter",
          message: "Reload adapter '" + a.name + "' from the current config on disk?",
          confirmLabel: "Reload",
          loadingLabel: "Reloading\u2026",
          onConfirm: doReloadAdapter,
        });
      });

      // Reload templates
      reloadTemplatesBtn.addEventListener("click", function () {
        var cap = (cachedAdapterCapabilities || []).find(function (c) { return c.name === a.name; });
        if (cap && !cap.supports_template_reload) {
          showError("This adapter does not support template reloading.");
          return;
        }
        if (cap && !cap.cached) {
          showError("Adapter must be cached (loaded) before templates can be reloaded. Send a query to it first.");
          return;
        }
        confirmAction({
          title: "Reload Templates",
          message: "Reload templates for adapter '" + a.name + "'?",
          confirmLabel: "Reload",
          loadingLabel: "Reloading\u2026",
          onConfirm: async function () {
            var path = ENDPOINTS.reloadTemplates + "/async?adapter_name=" + encodeURIComponent(a.name);
            var started = await api("POST", path);
            await waitForAdminJob(started.job_id, "Reloading templates\u2026");
            showStatus("Templates reloaded for '" + a.name + "'");
          }
        });
      });

      loadEntry();
    }

    function makeChip(label, value) {
      return el("span", { className: "adapter-chip" },
        el("span", { className: "chip-label" }, label + ":"),
        " " + value
      );
    }

    // Restore selection if we had one
    if (selectedAdapterEntry) {
      var match = allAdapters.find(function (a) { return a.name === selectedAdapterEntry.name; });
      if (match) {
        adapterPaginator.ensureItemVisible(function (a) { return a.name === selectedAdapterEntry.name; });
        renderDetail(match);
      } else {
        renderEmptyDetail();
      }
    } else {
      renderEmptyDetail();
    }
  }

  // ==================================================================
  // TAB: Settings (Ace Editor — YAML)
  // ==================================================================
  var settingsOriginal = "";
  var settingsEditor = null; // Ace editor instance

  function renderSettings(container) {
    clear(container);

    // Destroy previous editor instance
    if (settingsEditor) { settingsEditor.destroy(); settingsEditor = null; }

    var panel = el("div", { className: "panel", style: "max-width:100%" });
    panel.appendChild(el("h2", null, "Settings"));
    panel.appendChild(el("p", { className: "muted" },
      "Edit the main config.yaml file. Imported files (adapters, inference, etc.) are not shown here. " +
      "A server restart is required for most changes to take effect."
    ));

    var banner = el("div", { className: "settings-banner", style: "display:none" },
      "Config saved. Go to the Ops tab to restart the server for changes to take effect."
    );
    panel.appendChild(banner);

    var editorWrap = el("div", { id: "settings-ace-editor", className: "settings-ace-wrap" });
    panel.appendChild(editorWrap);

    var btnRow = el("div", { style: "display:flex;gap:var(--sp-3);margin-top:var(--sp-3)" });
    var saveBtn = el("button", { className: "btn btn--primary", disabled: "true" }, "Save");
    var reloadBtn = el("button", { className: "btn btn--neutral" }, "Reload from Disk");
    btnRow.appendChild(saveBtn);
    btnRow.appendChild(reloadBtn);
    panel.appendChild(btnRow);
    container.appendChild(panel);

    // Configure Ace to find mode/theme/worker files from static dir
    ace.config.set("basePath", "/static");
    ace.config.set("modePath", "/static");
    ace.config.set("themePath", "/static");
    ace.config.set("workerPath", "/static");

    // Initialize Ace editor
    settingsEditor = ace.edit(editorWrap, {
      mode: "ace/mode/yaml",
      theme: "ace/theme/tomorrow",
      fontSize: 15,
      fontFamily: "var(--font-mono)",
      showPrintMargin: false,
      tabSize: 2,
      useSoftTabs: true,
      wrap: false,
      showGutter: true,
      highlightActiveLine: true,
      highlightSelectedWord: true,
      showFoldWidgets: true,
      displayIndentGuides: true,
      scrollPastEnd: 0.2,
    });

    // Enable Cmd-F / Ctrl-F search
    ace.config.loadModule("ace/ext/searchbox", function () {});

    // Dirty tracking
    settingsEditor.session.on("change", function () {
      saveBtn.disabled = settingsEditor.getValue() === settingsOriginal;
    });

    // Load config from server
    async function loadConfig() {
      try {
        var data = await api("GET", ENDPOINTS.config);
        settingsOriginal = data.content;
        settingsEditor.setValue(data.content, -1); // -1 = move cursor to start
        settingsEditor.getSession().getUndoManager().reset();
        saveBtn.disabled = true;
        banner.style.display = "none";
      } catch (err) {
        showError("Failed to load config: " + err.message);
      }
    }

    // Save handler
    saveBtn.addEventListener("click", async function () {
      saveBtn.disabled = true;
      try {
        await api("PUT", ENDPOINTS.config, { content: settingsEditor.getValue() });
        settingsOriginal = settingsEditor.getValue();
        banner.style.display = "";
        setTimeout(function () { banner.style.display = "none"; }, 5000);
      } catch (err) {
        showError("Save failed: " + err.message);
        saveBtn.disabled = settingsEditor.getValue() === settingsOriginal;
      }
    });

    // Reload handler
    reloadBtn.addEventListener("click", function () {
      var dirty = settingsEditor.getValue() !== settingsOriginal;
      if (dirty) {
        confirmAction({
          title: "Reload Configuration",
          message: "You have unsaved changes. Reload from disk and discard them?",
          confirmLabel: "Discard & Reload",
          isDanger: true,
          loadingLabel: "Reloading…",
          onConfirm: async function () {
            await loadConfig();
            showStatus("Config reloaded from disk");
          },
        });
      } else {
        loadConfig().then(function () { showStatus("Config reloaded from disk"); });
      }
    });

    loadConfig();
  }

  // ==================================================================
  // TAB: Audit — admin/auth event ledger
  // ==================================================================

  var AUDIT_PAGE_SIZE = 25;

  var AUDIT_DOMAINS = [
    { value: "all",             label: "All" },
    { value: "auth.",           label: "Auth" },
    { value: "admin.api_key.",  label: "API Keys" },
    { value: "admin.config",    label: "Config" },
    { value: "admin.adapter.",  label: "Adapters" },
    { value: "admin.server.",   label: "Server" },
    { value: "admin.prompt.",   label: "Prompts" },
    { value: "admin.quota.",    label: "Quotas" },
  ];

  function formatAuditTimestamp(iso) {
    if (!iso) return "\u2014";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
      + "\u00A0" + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }

  function formatActor(ev) {
    if (ev.actor_type === "user") {
      return ev.actor_username || ev.actor_id || "\u2014";
    }
    if (ev.actor_type === "api_key") {
      return ev.actor_id || "API key";
    }
    return "anonymous";
  }

  function auditChip(label, pressed, onClick, variant) {
    var cls = "audit-chip";
    if (pressed) cls += " audit-chip--active";
    if (variant) cls += " audit-chip--" + variant;
    var btn = el("button", { type: "button", className: cls, "aria-pressed": String(!!pressed) }, label);
    btn.addEventListener("click", onClick);
    return btn;
  }

  async function renderAudit(container) {
    // ----- Layout: list panel (left) + dossier panel (right) -----
    var layout = el("div", { className: "tab-stacked-layout audit-view" });
    var listPanel = el("div", { className: "panel audit-view__list" });
    var detailPanel = el("div", { className: "panel audit-view__detail" });
    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    container.appendChild(layout);

    listPanel.appendChild(el("h2", null, "Audit Ledger"));
    listPanel.appendChild(el("p", { className: "muted" },
      "A register of privileged operations on /admin/* and /auth/* endpoints. ",
      "Read-only mutations — click a row to inspect the dossier."));

    // ----- State (per-render closure) -----
    var state = {
      outcome: "all",        // "all" | "success" | "failure"
      domain: "all",         // event_prefix value, or "all"
      q: "",                 // free-text search
      offset: 0,
      selectedIndex: null,
      lastPage: [],
      loading: false,
    };
    var searchDebounce = null;

    // ----- Filter strip -----
    var outcomeGroup = el("div", { className: "audit-view__chips" });
    var domainGroup = el("div", { className: "audit-view__chips" });
    var searchInput = el("input", {
      type: "search",
      placeholder: "Search actor, path, resource, IP\u2026",
      "aria-label": "Search audit events",
      className: "audit-view__search-input",
    });

    function renderChips() {
      clear(outcomeGroup);
      outcomeGroup.appendChild(el("span", { className: "audit-view__chip-label" }, "Outcome"));
      [
        ["all", "All", null],
        ["success", "Succeeded", null],
        ["failure", "Failed", "danger"],
      ].forEach(function (tuple) {
        var value = tuple[0], label = tuple[1], variant = tuple[2];
        outcomeGroup.appendChild(auditChip(label, state.outcome === value, function () {
          state.outcome = value;
          state.offset = 0;
          state.selectedIndex = null;
          renderChips();
          load();
        }, variant));
      });

      clear(domainGroup);
      domainGroup.appendChild(el("span", { className: "audit-view__chip-label" }, "Domain"));
      AUDIT_DOMAINS.forEach(function (d) {
        domainGroup.appendChild(auditChip(d.label, state.domain === d.value, function () {
          state.domain = d.value;
          state.offset = 0;
          state.selectedIndex = null;
          renderChips();
          load();
        }));
      });
    }

    searchInput.addEventListener("input", function (e) {
      var v = (e.target.value || "").trim();
      if (searchDebounce) clearTimeout(searchDebounce);
      searchDebounce = setTimeout(function () {
        state.q = v;
        state.offset = 0;
        state.selectedIndex = null;
        load();
      }, 250);
    });

    var refreshBtn = el("button", { type: "button", className: "secondary" }, "Refresh");
    refreshBtn.addEventListener("click", function () { load(); });

    listPanel.appendChild(el("div", { className: "audit-view__filters" },
      outcomeGroup,
      domainGroup,
      el("div", { className: "audit-view__search" }, searchInput),
      el("div", { className: "audit-view__actions" }, refreshBtn)
    ));
    renderChips();

    // ----- Table wrap + pagination -----
    var tableWrap = el("div", { className: "audit-view__table-wrap" }, skeleton());
    var pagerBar = el("div", { className: "audit-view__pager" });
    listPanel.appendChild(tableWrap);
    listPanel.appendChild(pagerBar);

    // ----- Dossier: empty initial state -----
    renderAuditDossierEmpty(detailPanel);

    // ----- Data loading -----
    async function load() {
      if (state.loading) return;
      state.loading = true;
      clear(tableWrap);
      tableWrap.appendChild(skeleton());
      clear(pagerBar);

      var params = new URLSearchParams();
      params.set("limit", String(AUDIT_PAGE_SIZE));
      params.set("offset", String(state.offset));
      if (state.outcome === "success") params.set("success", "true");
      else if (state.outcome === "failure") params.set("success", "false");
      if (state.domain && state.domain !== "all") params.set("event_prefix", state.domain);
      if (state.q) params.set("q", state.q);

      try {
        var resp = await api("GET", ENDPOINTS.auditEvents + "?" + params.toString());
        state.lastPage = resp.events || [];
        renderAuditTable(tableWrap, state, function (idx) {
          state.selectedIndex = idx;
          renderAuditDossier(detailPanel, state.lastPage[idx], function () {
            state.selectedIndex = null;
            renderAuditDossierEmpty(detailPanel);
            Array.prototype.forEach.call(
              tableWrap.querySelectorAll("tr.audit-row"),
              function (tr) { tr.classList.remove("audit-row--active"); }
            );
          });
          Array.prototype.forEach.call(
            tableWrap.querySelectorAll("tr.audit-row"),
            function (tr, i) { tr.classList.toggle("audit-row--active", i === idx); }
          );
        });
        renderAuditPager(pagerBar, state, resp, load);
      } catch (err) {
        clear(tableWrap);
        var msg = (err && err.message) || "";
        if (/admin audit is not enabled/i.test(msg)) {
          tableWrap.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Admin audit is not enabled."),
            el("p", { className: "muted" },
              "Set ",
              el("code", null, "internal_services.audit.enabled: true"),
              " and ",
              el("code", null, "internal_services.audit.admin_events.enabled: true"),
              " in config.yaml, then restart the server.")
          ));
        } else {
          tableWrap.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Failed to load audit events."),
            el("p", { className: "muted" }, (err && err.message) || "Unknown error")
          ));
        }
      } finally {
        state.loading = false;
      }
    }

    load();
  }

  function renderAuditTable(wrap, state, onSelect) {
    clear(wrap);
    var events = state.lastPage || [];
    if (events.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("p", null, "No events match the current filters."),
        el("p", { className: "muted" },
          state.offset > 0
            ? "Try jumping to page 1 or loosening the filters."
            : "As admin and auth actions occur they will appear here.")
      ));
      return;
    }

    var table = el("table", { className: "audit-table" });
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Time"),
        el("th", null, "Event"),
        el("th", null, "Actor"),
        el("th", null, "Resource"),
        el("th", { className: "audit-col-status" }, "Status")
      )
    );
    var tbody = el("tbody");

    events.forEach(function (ev, idx) {
      var statusCls = ev.success ? "badge-ok" : "badge-fail";
      var statusLabel = ev.success ? "ok" : "fail";

      var actorCell;
      if (ev.actor_type === "anonymous") {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-anon" }, "anonymous"),
          el("div", { className: "audit-actor-role" }, ev.actor_type)
        );
      } else {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-name" }, formatActor(ev)),
          el("div", { className: "audit-actor-role" }, ev.actor_type || "")
        );
      }

      var resourceText = ev.resource_id || ev.resource_type || "\u2014";

      var tr = el("tr", { className: "audit-row" + (state.selectedIndex === idx ? " audit-row--active" : "") },
        el("td", { className: "audit-col-time" }, formatAuditTimestamp(ev.timestamp)),
        el("td", { className: "audit-col-event" },
          el("div", { className: "audit-event-type" }, ev.event_type || "\u2014"),
          el("div", { className: "audit-event-action muted" }, ev.action || "")
        ),
        el("td", null, actorCell),
        el("td", { className: "audit-col-resource" }, resourceText),
        el("td", { className: "audit-col-status" },
          el("span", { className: "audit-status-code" }, String(ev.status_code != null ? ev.status_code : "")),
          el("span", { className: "badge " + statusCls }, statusLabel)
        )
      );
      tr.addEventListener("click", function () { onSelect(idx); });
      tbody.appendChild(tr);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(el("div", { className: "table-wrap" }, table));
  }

  function renderAuditPager(bar, state, resp, reload) {
    clear(bar);
    var returned = (resp && resp.returned) || 0;
    if (state.offset === 0 && returned === 0) return;

    var pageNum = Math.floor(state.offset / AUDIT_PAGE_SIZE) + 1;
    var start = state.offset + 1;
    var end = state.offset + returned;

    var hasPrev = state.offset > 0;
    var hasNext = returned >= AUDIT_PAGE_SIZE;

    bar.appendChild(el("span", { className: "pagination-info" },
      returned > 0
        ? "Showing " + start + "\u2013" + end + " \u00B7 Page " + pageNum
        : "Page " + pageNum));

    var btns = el("div", { className: "pagination-buttons" });
    var prevAttrs = { type: "button", className: "pagination-btn", "aria-label": "Previous page" };
    if (!hasPrev) prevAttrs.disabled = "true";
    var prevBtn = el("button", prevAttrs, "\u2039");
    prevBtn.addEventListener("click", function () {
      state.offset = Math.max(0, state.offset - AUDIT_PAGE_SIZE);
      state.selectedIndex = null;
      reload();
    });
    btns.appendChild(prevBtn);

    btns.appendChild(el("span", { className: "pagination-btn active", "aria-current": "page" }, String(pageNum)));

    var nextAttrs = { type: "button", className: "pagination-btn", "aria-label": "Next page" };
    if (!hasNext) nextAttrs.disabled = "true";
    var nextBtn = el("button", nextAttrs, "\u203A");
    nextBtn.addEventListener("click", function () {
      state.offset = state.offset + AUDIT_PAGE_SIZE;
      state.selectedIndex = null;
      reload();
    });
    btns.appendChild(nextBtn);

    bar.appendChild(btns);
  }

  function renderAuditDossierEmpty(panel) {
    clear(panel);
    panel.appendChild(el("h2", null, "Dossier"));
    panel.appendChild(el("div", { className: "empty-state" },
      el("p", null, "Select an entry from the register."),
      el("p", { className: "muted" }, "A dossier shows the actor, the request, its origin, and any fields captured in the request summary.")
    ));
  }

  function renderAuditDossier(panel, ev, onClose) {
    clear(panel);
    if (!ev) { renderAuditDossierEmpty(panel); return; }

    var closeBtn = el("button", { type: "button", className: "secondary audit-dossier__close" }, "Close");
    closeBtn.addEventListener("click", onClose);
    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Dossier"),
      closeBtn
    ));

    panel.appendChild(el("div", { className: "audit-dossier__headline" },
      el("div", { className: "audit-dossier__event-type" }, ev.event_type || "\u2014"),
      ev.action ? el("div", { className: "audit-dossier__action muted" }, ev.action) : null
    ));

    var verdictCls = "audit-verdict audit-verdict--" + (ev.success ? "success" : "failure");
    panel.appendChild(el("div", null,
      el("span", { className: verdictCls },
        ev.success ? "Succeeded" : "Failed",
        " \u00B7 HTTP " + (ev.status_code != null ? ev.status_code : "?")
      )
    ));

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Principals"));
    panel.appendChild(renderAuditFieldGrid([
      ["Actor", formatActor(ev)],
      ["Capacity", ev.actor_type || ""],
      ["Actor ID", ev.actor_id || "\u2014"],
      ["Resource", ev.resource_id || "\u2014"],
      ["Resource kind", ev.resource_type || ""],
    ]));

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Request"));
    panel.appendChild(renderAuditFieldGrid([
      ["Method", ev.method || ""],
      ["Path", ev.path || ""],
      ["Status", String(ev.status_code != null ? ev.status_code : "") + (ev.error_message ? " \u00B7 " + ev.error_message : "")],
      ["Timestamp", formatAuditTimestamp(ev.timestamp)],
      ["Event type", ev.event_type || ""],
      ["Action", ev.action || ""],
    ]));

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Origin"));
    var originRows = [
      ["IP", ev.ip || "\u2014"],
    ];
    if (ev.ip_metadata) {
      if (ev.ip_metadata.source) originRows.push(["Source", ev.ip_metadata.source]);
      if (ev.ip_metadata.type) originRows.push(["Type", ev.ip_metadata.type]);
    }
    if (ev.user_agent) originRows.push(["User-Agent", ev.user_agent]);
    panel.appendChild(renderAuditFieldGrid(originRows));

    var summary = ev.request_summary;
    if (summary && typeof summary === "object" && Object.keys(summary).length > 0) {
      panel.appendChild(el("h3", { className: "audit-section-heading" }, "Request summary"));
      panel.appendChild(el("p", { className: "muted audit-dossier__summary-note" },
        "Fields recorded by the middleware \u2014 secrets (passwords, raw API keys) are never stored."));
      var lines = Object.keys(summary).map(function (k) {
        var v = summary[k];
        var vStr;
        if (Array.isArray(v)) {
          vStr = "[" + v.map(function (x) { return JSON.stringify(x); }).join(", ") + "]";
        } else {
          vStr = JSON.stringify(v);
        }
        return k + ": " + vStr;
      });
      panel.appendChild(el("pre", { className: "audit-dossier__summary" }, lines.join("\n")));
    }
  }

  function renderAuditFieldGrid(rows) {
    var dl = el("dl", { className: "audit-field-grid" });
    rows.forEach(function (row) {
      dl.appendChild(el("dt", null, row[0]));
      dl.appendChild(el("dd", null, row[1] == null || row[1] === "" ? "\u2014" : row[1]));
    });
    return dl;
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
