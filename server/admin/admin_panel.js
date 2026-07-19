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
  let serverVersion = null;

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
  let feedbackCharts = {};
  let selectedFeedbackWindowDays = 30;
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
    roles: "/auth/roles",
    changePassword: "/auth/change-password",
    resetPassword: "/auth/reset-password",
    apiKeys: "/admin/api-keys",
    prompts: "/admin/prompts",
    adapterCapabilities: "/admin/adapters/capabilities",
    jobs: "/admin/jobs",
    logsTail: "/admin/logs/tail",
    logsFiles: "/admin/logs/files",
    renderMarkdown: "/admin/render-markdown",
    reloadAdapters: "/admin/reload-adapters",
    reloadTemplates: "/admin/reload-templates",
    restart: "/admin/restart",
    shutdown: "/admin/shutdown",
    adminExport: "/admin/export",
    login: "/admin/login",
    configSections: "/admin/config/sections",
    adapterConfigs: "/admin/adapters/config",
    auditEvents: "/admin/audit/events",
    feedbackAnalytics: "/admin/api/feedback-analytics",
    serverInfo: "/admin/info",
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

  function syncVisibleSelection(selectAllBox, rowCheckboxes, selectedIds, visibleIds) {
    selectAllBox.checked = visibleIds.length > 0 && visibleIds.every(function (id) {
      return selectedIds.has(id);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && visibleIds.some(function (id) {
      return selectedIds.has(id);
    });
    rowCheckboxes.forEach(function (checkbox) {
      checkbox.checked = selectedIds.has(checkbox._selectionId);
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
  var ICON_REFRESH = ["M21 12a9 9 0 1 1-2.64-6.36", "M21 3v6h-6"];
  var ICON_SAVE = ["M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z", "M17 21v-8H7v8", "M7 3v5h8"];
  var ICON_X = ["M18 6L6 18", "M6 6l12 12"];
  var USERNAME_MIN_LENGTH = 3;
  var USERNAME_MAX_LENGTH = 50;
  var PASSWORD_MIN_LENGTH = 8;
  var PASSWORD_MAX_LENGTH = 128;
  var USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;
  var ROLE_DETAILS = {
    admin: "Full access to every administrative capability.",
    analyst: "Reads conversations and feedback; cannot change configuration.",
    auditor: "Read-only logs, audit events, and system metrics.",
    operator: "Runs system configuration, adapters, and server control; no chat, log, or audit access.",
    "user-manager": "Creates and manages user accounts and role assignments.",
    user: "Standard account access with no administrative permissions."
  };

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
    button.style.visibility = count === 0 ? "hidden" : "visible";
    button.disabled = count === 0;
    button.textContent = "Delete " + count + " " + label;
  }

  function wrapTable(table) {
    return el("div", { className: "table-wrap" }, table);
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function setFieldReadOnly(input, editing) {
    input.readOnly = !editing;
    input.setAttribute("aria-readonly", editing ? "false" : "true");
    if (editing) input.removeAttribute("readonly");
    else input.setAttribute("readonly", "true");
  }

  function keyPath(keyId, suffix) {
    return ENDPOINTS.apiKeys + "/" + encodeURIComponent(keyId) + (suffix || "");
  }

  function showTableLoadError(tableWrap, message) {
    clear(tableWrap);
    tableWrap.appendChild(el("p", { className: "muted" }, message));
  }

  function copyTextToClipboard(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "true");
      textarea.style.position = "fixed";
      textarea.style.top = "-9999px";
      textarea.style.left = "-9999px";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        var ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        if (ok) resolve();
        else reject(new Error("Clipboard copy failed"));
      } catch (err) {
        document.body.removeChild(textarea);
        reject(err);
      }
    });
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

  function isVisible(node) {
    if (!node || !node.getClientRects().length) return false;
    return window.getComputedStyle(node).visibility !== "hidden";
  }

  function enabledSaveButtons(root) {
    return Array.prototype.slice.call(root.querySelectorAll('button[aria-label^="Save"]')).filter(function (btn) {
      return !btn.disabled && isVisible(btn);
    });
  }

  function findShortcutSaveButton() {
    if (document.querySelector(".confirm-dialog")) return null;

    var active = document.activeElement;
    var node = active && active.nodeType === 1 ? active : null;
    var scopeSelector = ".settings-section-block, .panel, .admin-create-form, #tab-content";

    while (node && node !== document.body) {
      if (node.matches && node.matches(scopeSelector)) {
        var scopedButtons = enabledSaveButtons(node);
        if (scopedButtons.length) return scopedButtons[0];
      }
      node = node.parentElement;
    }

    var tabContent = document.getElementById("tab-content");
    if (!tabContent) return null;
    var tabButtons = enabledSaveButtons(tabContent);
    return tabButtons.length === 1 ? tabButtons[0] : null;
  }

  function handleGlobalSaveShortcut(e) {
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || String(e.key).toLowerCase() !== "s") return;
    e.preventDefault();
    var saveBtn = findShortcutSaveButton();
    if (saveBtn) saveBtn.click();
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
      document.addEventListener("keydown", handleGlobalSaveShortcut, true);
      var resp = await fetch(ENDPOINTS.token);
      if (!resp.ok) {
        window.location.href = ENDPOINTS.login + "?next=/admin";
        return;
      }
      var data = await resp.json();
      authToken = data.token;
      currentUser = data.user;
      try {
        var infoResp = await fetch(ENDPOINTS.serverInfo, { headers: { "Authorization": "Bearer " + authToken }, credentials: "same-origin" });
        if (infoResp.ok) { var infoData = await infoResp.json(); serverVersion = infoData.version || null; }
      } catch (_) {}
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
    { id: "feedback", label: "Feedback", permission: "feedback.read" },
    { id: "users", label: "Users", permission: "users.manage" },
    { id: "keys", label: "API Keys", permission: "apikeys.manage" },
    { id: "prompts", label: "Personas", permission: "prompts.manage" },
    { id: "adapters", label: "Adapters", permission: "adapters.manage" },
    { id: "ops", label: "Ops", permission: "system.manage" },
    { id: "audit", label: "Audit", permission: "audit.read" },
    { id: "settings", label: "Settings", permission: "config.manage" },
  ];

  // A tab with no `permission` is visible to anyone who can load the panel.
  function hasTabPermission(tab) {
    if (!tab.permission) return true;
    var permissions = (currentUser && currentUser.permissions) || [];
    return permissions.indexOf("*") !== -1 || permissions.indexOf(tab.permission) !== -1;
  }

  function getVisibleTabs() {
    return TABS.filter(hasTabPermission);
  }

  function renderShell() {
    var app = document.getElementById("app");
    clear(app);
    var visibleTabs = getVisibleTabs();
    if (visibleTabs.every(function (t) { return t.id !== activeTab; })) {
      activeTab = visibleTabs.length ? visibleTabs[0].id : "overview";
    }

    // Topbar with inline nav
    var logoutBtn = el("button", { type: "button", className: "topbar-logout" }, "Logout");
    logoutBtn.addEventListener("click", doLogout);

    var nav = el("nav", { className: "topbar-nav", role: "tablist", "aria-label": "Admin sections" });
    visibleTabs.forEach(function (t) {
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
        var currentIndex = visibleTabs.findIndex(function (tab) { return tab.id === t.id; });
        if (e.key === "ArrowRight") {
          e.preventDefault();
          switchTab(visibleTabs[(currentIndex + 1) % visibleTabs.length].id);
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          switchTab(visibleTabs[(currentIndex - 1 + visibleTabs.length) % visibleTabs.length].id);
        }
      });
      nav.appendChild(btn);
    });

    var topbar = el("header", { className: "topbar", role: "banner" },
      el("div", { className: "brand-block" },
        el("a", { href: "/admin" },
          el("img", {
            src: "/static/orbit-logo-dark.png",
            alt: "ORBIT home",
            className: "brand-logo",
          })
        ),
        serverVersion ? el("p", null, "v" + serverVersion) : null
      ),
      nav,
      el("div", { className: "topbar-actions" },
        el("span", null, currentUser ? (currentUser.email || currentUser.username) : ""),
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
    if (activeTab === "settings" && id !== "settings" && settingsEditorsAreDirty()) {
      confirmAction({
        title: "Unsaved Changes",
        message: "You have unsaved changes in this category. Discard them?",
        confirmLabel: "Discard",
        isDanger: true,
        onConfirm: function () {
          destroyAllSettingsEditors();
          switchTab(id);
        }
      });
      return;
    }

    // Disconnect monitoring when leaving overview
    if (activeTab === "overview" && id !== "overview") {
      disconnectMetricsWs();
      destroyOverviewCharts();
    }
    if (activeTab === "feedback" && id !== "feedback") {
      destroyFeedbackCharts();
    }
    // Destroy adapter editor when leaving adapters tab
    if (activeTab === "adapters" && id !== "adapters") {
      if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
    }
    // Destroy settings section editors when leaving settings tab
    if (activeTab === "settings" && id !== "settings") {
      destroyAllSettingsEditors();
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
      case "feedback": renderFeedback(c); break;
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

  // --- Dark Grafana-style chart options ---
  var monitoringChartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false, axis: "x" },
    elements: { point: { radius: 0, hoverRadius: 4, hitRadius: 20 }, line: { borderWidth: 1.5 } },
    scales: {
      y: {
        beginAtZero: true,
        grid: { color: "rgba(15,29,51,0.06)", drawBorder: false },
        ticks: { color: "#6b7a96", font: { size: 10, family: "'JetBrains Mono', monospace" }, padding: 6 }
      },
      x: {
        grid: { color: "rgba(15,29,51,0.05)", drawBorder: false },
        ticks: { color: "#6b7a96", maxRotation: 0, minRotation: 0, font: { size: 10, family: "'JetBrains Mono', monospace" }, padding: 4 }
      }
    },
    plugins: {
      legend: {
        labels: {
          color: "#3d4f6f",
          usePointStyle: true,
          pointStyle: "line",
          boxWidth: 28,
          boxHeight: 2,
          font: { size: 11 },
          padding: 14
        }
      },
      tooltip: {
        backgroundColor: "rgba(10,14,23,0.96)",
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        titleColor: "#f4f6fa",
        bodyColor: "#e4e8f0",
        padding: 16,
        cornerRadius: 6,
        boxPadding: 8,
        titleFont: { family: "'JetBrains Mono', monospace", size: 18, weight: "500" },
        bodyFont: { family: "'JetBrains Mono', monospace", size: 17, weight: "400" }
      }
    }
  };

  function initOverviewCharts() {
    destroyOverviewCharts();
    var chartDefs = [
      { id: "mon-system-chart", series: [
          { label: "CPU %",    color: "#5794f2", rgb: [87,148,242],  fill: true },
          { label: "Memory %", color: "#73bf69", rgb: [115,191,105], fill: true }
        ]
      },
      { id: "mon-request-chart", series: [
          { label: "Requests/sec", color: "#f2a35e", rgb: [242,163,94],  fill: true },
          { label: "Error Rate %", color: "#f26073", rgb: [242,96,115],  fill: true }
        ]
      },
      { id: "mon-response-chart", series: [
          { label: "Avg Response Time", color: "#b877d9", rgb: [184,119,217], fill: true }
        ]
      },
      { id: "mon-percentile-chart", series: [
          { label: "P50", color: "#73bf69", fill: false },
          { label: "P95", color: "#f2a35e", fill: false, borderDash: [4, 3] },
          { label: "P99", color: "#f26073", fill: false, borderDash: [2, 2] }
        ]
      }
    ];

    chartDefs.forEach(function (def, i) {
      var canvas = document.getElementById(def.id);
      if (!canvas) return;
      var ctx = canvas.getContext("2d");

      var datasets = def.series.map(function (s) {
        var bg = (s.fill && s.rgb) ? (function () {
          var g = ctx.createLinearGradient(0, 0, 0, 300);
          g.addColorStop(0, "rgba(" + s.rgb[0] + "," + s.rgb[1] + "," + s.rgb[2] + ",0.2)");
          g.addColorStop(1, "rgba(" + s.rgb[0] + "," + s.rgb[1] + "," + s.rgb[2] + ",0)");
          return g;
        })() : "transparent";
        return {
          label: s.label, borderColor: s.color, backgroundColor: bg,
          fill: s.fill || false, tension: 0.3, borderDash: s.borderDash || [],
          borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 4, pointHitRadius: 20, data: []
        };
      });

      var opts = i === 1
        ? Object.assign({}, monitoringChartOpts, { scales: Object.assign({}, monitoringChartOpts.scales, { y: Object.assign({}, monitoringChartOpts.scales.y, { ticks: Object.assign({}, monitoringChartOpts.scales.y.ticks, { stepSize: 1, precision: 0 }), min: 0 }) }) })
        : monitoringChartOpts;

      overviewCharts[def.id] = new Chart(canvas, {
        type: "line",
        data: { labels: [], datasets: datasets },
        options: opts
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

  function formatSeconds(value) {
    return typeof value === "number" ? formatNum(value, value >= 10 ? 0 : 1) + " s" : "\u2014";
  }

  async function resetAdapterCircuit(adapterName, btn) {
    await withButton(btn, async function () {
      await api("POST", ENDPOINTS.healthAdapters + "/" + encodeURIComponent(adapterName) + "/reset");
      if (lastAdapters && lastAdapters[adapterName]) {
        var status = lastAdapters[adapterName];
        status.state = "closed";
        status.consecutive_failures = 0;
        status.consecutive_successes = 0;
        if (status.exponential_backoff) {
          status.exponential_backoff.recovery_attempts = 0;
          status.exponential_backoff.current_timeout = status.exponential_backoff.base_timeout || 0;
        }
        renderMonitoringAdapterList(lastAdapters);
      }
    }, "Circuit breaker reset for " + adapterName);
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
      var failures = (status && status.consecutive_failures) || 0;
      var reqs = (status && (status.request_count || status.success_count)) || 0;
      var latency = status && status.average_latency_ms;
      var backoff = status && status.exponential_backoff || {};
      var recoveryAttempts = backoff.recovery_attempts || 0;
      var nextRetry = state === "open" ? formatSeconds(backoff.current_timeout) : "\u2014";
      var latencyStr = typeof latency === "number" ? formatNum(latency, latency >= 100 ? 0 : 1) + " ms" : "\u2014";
      var resetBtn = el("button", {
        type: "button",
        className: "secondary",
        title: "Reset circuit breaker for " + name,
        "aria-label": "Reset circuit breaker for " + name,
        onclick: function () { resetAdapterCircuit(name, resetBtn); }
      }, "Reset");
      return [
        el("td", null, el("div", { className: "monitoring-table-primary", title: name }, name)),
        el("td", null, monitoringStatusCell(state.replace("_", " "), monitoringStateTone(state))),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(reqs)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(failures)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(recoveryAttempts)),
        el("td", { style: "text-align:right;font-weight:600" }, nextRetry),
        el("td", { style: "text-align:right;font-weight:600" }, latencyStr),
        el("td", { style: "text-align:right" }, resetBtn)
      ];
    });
    renderMonitoringTable(container, [
      { label: "Adapter" },
      { label: "State" },
      { label: "Requests", attrs: { style: "text-align:right" } },
      { label: "Failures", attrs: { style: "text-align:right" } },
      { label: "Recovery Attempts", attrs: { style: "text-align:right" } },
      { label: "Next Retry", attrs: { style: "text-align:right" } },
      { label: "Avg Latency", attrs: { style: "text-align:right" } },
      { label: "Actions", attrs: { style: "text-align:right" } }
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

  // ==================================================================
  // TAB: Feedback analytics
  // ==================================================================

  function destroyFeedbackCharts() {
    Object.keys(feedbackCharts).forEach(function (key) {
      try { feedbackCharts[key].destroy(); } catch (_) {}
    });
    feedbackCharts = {};
  }

  function feedbackPercent(value) {
    return value == null ? "—" : formatNum(value, 1) + "%";
  }

  function feedbackMetricCard(value, label, detail, progress, tone) {
    return el("div", { className: "metric-card" },
      el("div", { className: "metric-value" }, value),
      el("div", { className: "metric-label" }, label),
      el("div", { className: "metric-sub" }, detail || ""),
      progress == null ? null : el("div", { className: "monitoring-progress-track" },
        el("div", {
          className: "monitoring-progress-bar " + (tone || "sky"),
          style: "width:" + clampPercentage(progress) + "%"
        })
      )
    );
  }

  function feedbackChartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: { point: { radius: 2, hoverRadius: 5 }, line: { borderWidth: 2 } },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "rgba(15,29,51,0.06)" },
          ticks: { color: "#6b7a96", precision: 0, font: { size: 10 } }
        },
        x: {
          grid: { display: false },
          ticks: { color: "#6b7a96", maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: { size: 10 } }
        }
      },
      plugins: {
        legend: { labels: { color: "#3d4f6f", usePointStyle: true, boxWidth: 10, font: { size: 11 } } },
        tooltip: {
          backgroundColor: "rgba(10,14,23,0.96)",
          titleColor: "#f4f6fa",
          bodyColor: "#e4e8f0",
          padding: 12,
          cornerRadius: 6
        }
      }
    };
  }

  function initFeedbackCharts(data) {
    destroyFeedbackCharts();
    if (typeof Chart === "undefined" || !data.summary.total) return;

    var trendCanvas = document.getElementById("feedback-trend-chart");
    if (trendCanvas) {
      var trendOptions = feedbackChartOptions();
      trendOptions.scales.y1 = {
        beginAtZero: true,
        min: 0,
        max: 100,
        position: "right",
        grid: { drawOnChartArea: false },
        ticks: { color: "#6b7a96", callback: function (value) { return value + "%"; }, font: { size: 10 } }
      };
      feedbackCharts.trend = new Chart(trendCanvas, {
        type: "line",
        data: {
          labels: data.trend.map(function (item) {
            return new Date(item.date + "T00:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric" });
          }),
          datasets: [
            { label: "Positive", data: data.trend.map(function (item) { return item.positive; }), borderColor: "#28a66a", backgroundColor: "rgba(40,166,106,0.10)", fill: true, tension: 0.25 },
            { label: "Negative", data: data.trend.map(function (item) { return item.negative; }), borderColor: "#e05260", backgroundColor: "rgba(224,82,96,0.08)", fill: true, tension: 0.25 },
            { label: "Satisfaction %", data: data.trend.map(function (item) { return item.satisfaction_rate; }), borderColor: "#5794f2", backgroundColor: "transparent", borderDash: [5, 4], yAxisID: "y1", spanGaps: true, tension: 0.2 }
          ]
        },
        options: trendOptions
      });
    }

    var distributionCanvas = document.getElementById("feedback-distribution-chart");
    if (distributionCanvas) {
      feedbackCharts.distribution = new Chart(distributionCanvas, {
        type: "doughnut",
        data: {
          labels: ["Positive", "Negative"],
          datasets: [{
            data: [data.summary.positive, data.summary.negative],
            backgroundColor: ["#28a66a", "#e05260"],
            borderWidth: 0,
            hoverOffset: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "68%",
          plugins: feedbackChartOptions().plugins
        }
      });
    }

    var adapterCanvas = document.getElementById("feedback-adapter-chart");
    var adapterRows = data.adapters.slice(0, 10);
    if (adapterCanvas && adapterRows.length) {
      var adapterOptions = feedbackChartOptions();
      adapterOptions.indexAxis = "y";
      adapterOptions.scales.x.max = 100;
      adapterOptions.scales.x.ticks.callback = function (value) { return value + "%"; };
      adapterOptions.plugins.legend.display = false;
      adapterOptions.plugins.tooltip.callbacks = {
        afterLabel: function (context) {
          var row = adapterRows[context.dataIndex];
          return row.total + " ratings (" + row.positive + " positive, " + row.negative + " negative)";
        }
      };
      feedbackCharts.adapters = new Chart(adapterCanvas, {
        type: "bar",
        data: {
          labels: adapterRows.map(function (item) { return item.adapter; }),
          datasets: [{
            label: "Satisfaction",
            data: adapterRows.map(function (item) { return item.satisfaction_rate || 0; }),
            backgroundColor: adapterRows.map(function (item) {
              return item.satisfaction_rate >= 80 ? "#28a66a" : item.satisfaction_rate >= 60 ? "#e0a22f" : "#e05260";
            }),
            borderRadius: 4
          }]
        },
        options: adapterOptions
      });
    }
  }

  function renderFeedbackAdapterTable(container, adapters) {
    var table = el("table");
    table.appendChild(el("thead", null, el("tr", null,
      el("th", null, "Adapter"),
      el("th", { style: "text-align:right" }, "Ratings"),
      el("th", { style: "text-align:right" }, "Positive"),
      el("th", { style: "text-align:right" }, "Negative"),
      el("th", { style: "text-align:right" }, "Satisfaction"),
      el("th", { style: "text-align:right" }, "Comments")
    )));
    var body = el("tbody");
    adapters.forEach(function (item) {
      body.appendChild(el("tr", null,
        el("td", null, el("strong", null, item.adapter)),
        el("td", { style: "text-align:right" }, formatNum(item.total)),
        el("td", { style: "text-align:right;color:#208755" }, formatNum(item.positive)),
        el("td", { style: "text-align:right;color:#bd3f4d" }, formatNum(item.negative)),
        el("td", { style: "text-align:right;font-weight:700" }, feedbackPercent(item.satisfaction_rate)),
        el("td", { style: "text-align:right" }, formatNum(item.comments))
      ));
    });
    table.appendChild(body);
    container.appendChild(wrapTable(table));
  }

  function renderRecentNegativeFeedback(container, rows) {
    if (!rows.length) {
      container.appendChild(el("div", { className: "empty-state" },
        el("p", null, "No negative feedback was recorded in this window.")));
      return;
    }
    var table = el("table");
    table.appendChild(el("thead", null, el("tr", null,
      el("th", null, "When"),
      el("th", null, "Adapter / user"),
      el("th", null, "User prompt"),
      el("th", null, "Assistant response"),
      el("th", null, "Feedback comment")
    )));
    var body = el("tbody");
    rows.forEach(function (item) {
      var timestamp = item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown";
      body.appendChild(el("tr", null,
        el("td", { style: "white-space:nowrap" }, timestamp),
        el("td", null,
          el("strong", null, item.adapter || "Unknown"),
          el("div", { className: "muted", style: "font-size:var(--text-xs);margin-top:2px" }, item.user || "Anonymous")
        ),
        el("td", { title: item.user_prompt || "" }, item.user_prompt || "Unavailable"),
        el("td", { title: item.assistant_response || "" }, item.assistant_response || "Unavailable"),
        el("td", { title: item.comment || "" }, item.comment || "No comment")
      ));
    });
    table.appendChild(body);
    container.appendChild(wrapTable(table));
  }

  async function renderFeedback(container) {
    var requestVersion = 0;
    var header = el("div", { className: "panel" },
      el("div", { className: "panel-header-row" },
        el("div", null,
          el("h2", null, "Feedback intelligence"),
          el("p", { className: "muted" }, "Track satisfaction, compare adapters, and inspect the conversations behind negative ratings.")
        ),
        el("div", { className: "monitoring-toolbar-right", id: "feedback-window-controls" },
          [7, 30, 90, 365].map(function (days) {
            var button = el("button", {
              type: "button",
              className: "time-window-btn",
              "aria-pressed": days === selectedFeedbackWindowDays ? "true" : "false"
            }, days === 365 ? "1y" : days + "d");
            button.addEventListener("click", function () {
              if (selectedFeedbackWindowDays === days) return;
              selectedFeedbackWindowDays = days;
              load();
            });
            return button;
          })
        )
      )
    );
    var content = el("div", { style: "display:grid;gap:var(--sp-4)" }, skeleton());
    container.appendChild(header);
    container.appendChild(content);

    async function load() {
      var version = ++requestVersion;
      header.querySelectorAll(".time-window-btn").forEach(function (button) {
        var label = selectedFeedbackWindowDays === 365 ? "1y" : selectedFeedbackWindowDays + "d";
        button.setAttribute("aria-pressed", button.textContent === label ? "true" : "false");
      });
      destroyFeedbackCharts();
      clear(content);
      content.appendChild(skeleton());
      try {
        var data = await api("GET", ENDPOINTS.feedbackAnalytics + "?days=" + selectedFeedbackWindowDays);
        if (version !== requestVersion || activeTab !== "feedback") return;
        clear(content);

        if (data.meta.truncated) {
          content.appendChild(el("div", {
            className: "panel",
            style: "border-color:#e0a22f;background:rgba(224,162,47,0.08);font-size:var(--text-sm)"
          },
            "This view uses the newest " + formatNum(data.meta.record_limit) + " ratings in the selected window."
          ));
        }

        var summary = data.summary;
        var coverageDetail = summary.eligible_messages == null
          ? "Chat history unavailable"
          : summary.response_rate == null
            ? "Chat retention prevents a reliable denominator"
            : formatNum(summary.total) + " of " + formatNum(summary.eligible_messages) + " retained responses";
        content.appendChild(el("div", { className: "metric-cards-grid" },
          feedbackMetricCard(feedbackPercent(summary.satisfaction_rate), "Satisfaction", formatNum(summary.positive) + " positive / " + formatNum(summary.negative) + " negative", summary.satisfaction_rate, summary.satisfaction_rate >= 80 ? "green" : summary.satisfaction_rate >= 60 ? "amber" : "red"),
          feedbackMetricCard(formatNum(summary.total), "Ratings", formatNum(summary.sessions) + " sessions · " + formatNum(summary.users) + " identified users"),
          feedbackMetricCard(feedbackPercent(summary.response_rate), "Feedback coverage", coverageDetail, summary.response_rate, "sky"),
          feedbackMetricCard(feedbackPercent(summary.negative_comment_rate), "Negative detail rate", formatNum(summary.comments) + " comments on negative ratings", summary.negative_comment_rate, "amber")
        ));

        if (summary.total) {
          var charts = el("div", { className: "charts-grid" },
            el("div", { className: "chart-card" }, el("h3", null, "Ratings and satisfaction over time"), el("canvas", { id: "feedback-trend-chart" })),
            el("div", { className: "chart-card" }, el("h3", null, "Overall distribution"), el("canvas", { id: "feedback-distribution-chart" })),
            el("div", { className: "chart-card" }, el("h3", null, "Satisfaction by adapter (top 10 by volume)"), el("canvas", { id: "feedback-adapter-chart" }))
          );
          content.appendChild(charts);
        } else {
          content.appendChild(el("div", { className: "panel empty-state" },
            el("p", null, "No feedback has been recorded in this time window.")));
        }

        var adapterPanel = el("div", { className: "panel" },
          el("h2", null, "Adapter performance"),
          el("p", { className: "muted" }, "Compare rating volume and satisfaction together; low-volume percentages should be treated cautiously.")
        );
        if (data.adapters.length) renderFeedbackAdapterTable(adapterPanel, data.adapters);
        else adapterPanel.appendChild(el("p", { className: "muted" }, "No adapter feedback in this window."));
        content.appendChild(adapterPanel);

        var negativePanel = el("div", { className: "panel" },
          el("h2", null, "Recent negative feedback"),
          el("p", { className: "muted" }, "The linked prompt and response provide context for triage. Unavailable content may have expired under chat-history retention.")
        );
        renderRecentNegativeFeedback(negativePanel, data.recent_negative);
        content.appendChild(negativePanel);

        content.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
          data.window.basis + ". Generated " + new Date(data.meta.generated_at).toLocaleString() + "."
        ));
        initFeedbackCharts(data);
      } catch (err) {
        if (version !== requestVersion || activeTab !== "feedback") return;
        clear(content);
        content.appendChild(el("div", { className: "panel empty-state" },
          el("p", null, "Failed to load feedback analytics: " + err.message)
        ));
      }
    }

    load();
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
    var userSearchInteracted = false;
    var allUsers = [];
    var userFilteredEmpty = false;
    var selectedUserIds = new Set();
    var tableWrap = el("div", null, skeleton());
    var searchInput = el("input", {
      type: "text",
      name: "user-search",
      placeholder: "Search users",
      "aria-label": "Search users",
      autocomplete: "off"
    });
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
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

    var usersRefreshBtn = el("button", { type: "button", className: "secondary" }, "Refresh");
    usersRefreshBtn.addEventListener("click", function () { loadUsers({}); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Users"),
      usersRefreshBtn
    ));
    listPanel.appendChild(field("Search", searchInput));
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create user"
    }, svgIcon(ICON_PLUS), el("span", null, "Create User"));
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));
    listPanel.appendChild(tableWrap);
    listPanel.appendChild(userPaginator.getControlsEl());

    var usernameInput = el("input", {
      type: "text",
      maxlength: String(USERNAME_MAX_LENGTH),
      placeholder: "3-50 chars. Alphanumeric and ., _, - allowed.",
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var passwordInput = el("input", {
      type: "password",
      maxlength: String(PASSWORD_MAX_LENGTH),
      placeholder: "8-128 chars. No spaces.",
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var roleOptions = el("div", {
      className: "role-picker-options",
      role: "group",
      "aria-labelledby": "new-user-roles-label"
    });
    function syncAdminRoleState() {
      var adminCheckbox = roleOptions.querySelector('input[value="admin"]');
      var adminSelected = adminCheckbox && adminCheckbox.checked;
      Array.from(roleOptions.querySelectorAll("input")).forEach(function (input) {
        if (input === adminCheckbox) return;
        if (adminSelected) input.checked = false;
        input.disabled = Boolean(adminSelected);
        input.closest(".role-picker-option").classList.toggle("is-disabled", Boolean(adminSelected));
      });
    }

    function createRoleOption(name, index) {
      var checkbox = el("input", {
        id: "new-user-role-" + index,
        type: "checkbox",
        value: name,
        "aria-describedby": "new-user-role-description-" + index
      });
      checkbox.checked = name === "user";
      checkbox.addEventListener("change", syncAdminRoleState);
      return el("label", { className: "role-picker-option", htmlFor: checkbox.id },
        checkbox,
        el("span", { className: "role-picker-copy" },
          el("span", { className: "role-picker-option-label" }, name),
          el("span", { id: "new-user-role-description-" + index, className: "role-picker-option-description" },
            ROLE_DETAILS[name] || "Grants the permissions assigned to this role."
          )
        )
      );
    }

    function renderRoleOptions(roles) {
      clear(roleOptions);
      var orderedRoles = roles.slice().sort(function (a, b) {
        if (a === "admin") return -1;
        if (b === "admin") return 1;
        return a.localeCompare(b);
      });
      var adminIndex = orderedRoles.indexOf("admin");
      if (adminIndex !== -1) {
        roleOptions.appendChild(el("div", { className: "role-picker-section role-picker-section-admin" },
          createRoleOption("admin", adminIndex)
        ));
      }
      var scopedRoles = orderedRoles.filter(function (name) { return name !== "admin"; });
      if (adminIndex !== -1 && scopedRoles.length) {
        roleOptions.appendChild(el("div", { className: "role-picker-divider", role: "separator" }, "Scoped access"));
      }
      if (scopedRoles.length) {
        var scopedSection = el("div", { className: "role-picker-section role-picker-section-scoped" });
        scopedRoles.forEach(function (name) {
          scopedSection.appendChild(createRoleOption(name, orderedRoles.indexOf(name)));
        });
        roleOptions.appendChild(scopedSection);
      }
      syncAdminRoleState();
    }

    renderRoleOptions(["user"]);
    (async function populateRoleOptions() {
      try {
        var data = await api("GET", ENDPOINTS.roles);
        renderRoleOptions(data.roles || ["user"]);
      } catch (_) { /* keep the "user" fallback option */ }
    })();
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
      el("div", { className: "stack role-picker" },
        el("span", { id: "new-user-roles-label" }, "Roles"),
        el("span", { className: "muted" }, "Select all that apply"),
        roleOptions
      ),
      el("div", { className: "admin-create-form-grid user-create-grid" },
        field("Username", usernameInput),
        passwordField("Password", passwordInput)
      ),
      el("div", { className: "admin-create-form-actions user-create-form-actions" }, createBtn)
    );
    createPanel.appendChild(form);
    bindValidationClear(usernameInput, passwordInput, roleOptions);

    renderSelectedUserPlaceholder(detailPanel);
    renderAccountSecurityPanel(accountPanel);

    createBtn.addEventListener("click", function () {
      var u = usernameInput.value.trim();
      var p = passwordInput.value;
      var usernameError = validateUsername(u);
      if (usernameError) { showError(usernameError); return; }
      var passwordError = validatePassword(p);
      if (passwordError) { showError(passwordError); return; }
      var selectedRoles = Array.from(roleOptions.querySelectorAll("input:checked")).map(function (input) { return input.value; });
      if (!selectedRoles.length) { showError("Select at least one role."); return; }
      withButton(createBtn, async function () {
        await api("POST", ENDPOINTS.register, { username: u, password: p, roles: selectedRoles });
        usernameInput.value = "";
        passwordInput.value = "";
        Array.from(roleOptions.querySelectorAll("input")).forEach(function (input) { input.checked = input.value === "user"; });
        syncAdminRoleState();
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
          (user.roles || []).join(" "),
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
    searchInput.addEventListener("keydown", function () { userSearchInteracted = true; });
    searchInput.addEventListener("paste", function () { userSearchInteracted = true; });

    function clearAutofilledUserSearch() {
      if (userSearchInteracted || document.activeElement === searchInput) return;
      searchInput.value = "";
      userSearchFilter = "";
      applyUserFilter();
    }

    // Some browsers ignore autocomplete="off" and populate the field after it mounts.
    window.requestAnimationFrame(function () {
      clearAutofilledUserSearch();
      window.setTimeout(clearAutofilledUserSearch, 200);
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
        showTableLoadError(tableWrap, "Failed to load users");
        renderSelectedUserPlaceholder(detailPanel);
      }
    }

    loadUsers();
  }

  function renderAccountSecurityPanel(panel) {
    clear(panel);
    var isSsoUser = !!(currentUser && currentUser.provider);
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
      isSsoUser ? null : toggleBtn
    ));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Username:"), " " + ((currentUser && currentUser.username) || "N/A")),
      el("p", null, el("strong", null, "Roles:"), " " + ((currentUser && currentUser.roles && currentUser.roles.join(", ")) || "N/A"))
    ));
    if (isSsoUser) {
      panel.appendChild(el("p", { className: "muted" },
        "Your password is managed by your identity provider (" + currentUser.provider + "). Sign in through that provider to change it."
      ));
      return;
    }
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
    var changeBtn = el("button", {
      type: "button",
      className: "btn--icon",
      "aria-label": "Save password",
      title: "Save password",
    }, svgIcon(ICON_SAVE));
    var cancelBtn = el("button", {
      className: "secondary btn--icon",
      type: "button",
      "aria-label": "Cancel password change",
      title: "Cancel password change",
    }, svgIcon(ICON_X));

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
    var selectableUserIds = selectableUsers.map(function (user) { return user.id; });
    var rowCheckboxes = [];
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible users"
    });
    selectAllBox.checked = selectableUserIds.length > 0 && selectableUserIds.every(function (userId) {
      return selection.selectedIds.has(userId);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && selectableUserIds.some(function (userId) {
      return selection.selectedIds.has(userId);
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      selectableUsers.forEach(function (user) {
        if (selectAllBox.checked) selection.selectedIds.add(user.id);
        else selection.selectedIds.delete(user.id);
      });
      selection.onSelectionChange();
      syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, selectableUserIds);
    });
    table.appendChild(el("colgroup", null, el("col", { className: "selection-col-width" })));
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
      checkbox._selectionId = u.id;
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
        syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, selectableUserIds);
      });
      rowCheckboxes.push(checkbox);
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
        el("td", null, u.email || u.username),
        el("td", null, (u.roles && u.roles.length ? u.roles : [u.role]).filter(Boolean).join(", ")),
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

    panel.appendChild(el("h2", { className: "detail-title" }, user.email || user.username || "User Details"));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "ID:"), " " + (user.id || "N/A")),
      el("p", null, el("strong", null, "Email:"), " " + (user.email || "N/A")),
      el("p", null, el("strong", null, "Username:"), " " + (user.username || "N/A")),
      el("p", null, el("strong", null, "Roles:"), " " + ((user.roles && user.roles.length ? user.roles : [user.role]).filter(Boolean).join(", ") || "N/A")),
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
      var roleEditor = el("div", { className: "role-editor", style: "display:none" });
      var roleEditorOptions = el("div", {
        className: "role-picker-options",
        role: "group",
        "aria-labelledby": "edit-user-roles-label"
      });
      var saveRolesBtn = el("button", { type: "button" }, "Save Roles");
      var cancelRolesBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
      var editRolesToggle = el("button", { className: "secondary", type: "button" }, "Edit Roles");

      function syncEditedAdminRoleState() {
        var adminCheckbox = roleEditorOptions.querySelector('input[value="admin"]');
        var adminSelected = adminCheckbox && adminCheckbox.checked;
        Array.from(roleEditorOptions.querySelectorAll("input")).forEach(function (input) {
          if (input === adminCheckbox) return;
          if (adminSelected) input.checked = false;
          input.disabled = Boolean(adminSelected);
          input.closest(".role-picker-option").classList.toggle("is-disabled", Boolean(adminSelected));
        });
      }

      function renderRoleEditorOptions(roles) {
        clear(roleEditorOptions);
        var assignedRoles = user.roles && user.roles.length ? user.roles : [user.role];
        var orderedRoles = roles.slice().sort(function (a, b) {
          if (a === "admin") return -1;
          if (b === "admin") return 1;
          return a.localeCompare(b);
        });

        function option(name, index) {
          var checkbox = el("input", {
            id: "edit-user-role-" + index,
            type: "checkbox",
            value: name,
            "aria-describedby": "edit-user-role-description-" + index
          });
          checkbox.checked = assignedRoles.indexOf(name) !== -1;
          checkbox.addEventListener("change", syncEditedAdminRoleState);
          return el("label", { className: "role-picker-option", htmlFor: checkbox.id },
            checkbox,
            el("span", { className: "role-picker-copy" },
              el("span", { className: "role-picker-option-label" }, name),
              el("span", { id: "edit-user-role-description-" + index, className: "role-picker-option-description" },
                ROLE_DETAILS[name] || "Grants the permissions assigned to this role."
              )
            )
          );
        }

        var adminIndex = orderedRoles.indexOf("admin");
        if (adminIndex !== -1) {
          roleEditorOptions.appendChild(el("div", { className: "role-picker-section role-picker-section-admin" }, option("admin", adminIndex)));
        }
        var scopedRoles = orderedRoles.filter(function (name) { return name !== "admin"; });
        if (adminIndex !== -1 && scopedRoles.length) {
          roleEditorOptions.appendChild(el("div", { className: "role-picker-divider", role: "separator" }, "Scoped access"));
        }
        if (scopedRoles.length) {
          var scopedSection = el("div", { className: "role-picker-section role-picker-section-scoped" });
          scopedRoles.forEach(function (name) { scopedSection.appendChild(option(name, orderedRoles.indexOf(name))); });
          roleEditorOptions.appendChild(scopedSection);
        }
        syncEditedAdminRoleState();
      }

      function closeRoleEditor() {
        roleEditor.style.display = "none";
        editRolesToggle.textContent = "Edit Roles";
      }

      editRolesToggle.addEventListener("click", async function () {
        if (roleEditor.style.display !== "none") {
          closeRoleEditor();
          return;
        }
        editRolesToggle.disabled = true;
        try {
          var data = await api("GET", ENDPOINTS.roles);
          renderRoleEditorOptions(data.roles || ["user"]);
          roleEditor.style.display = "";
          editRolesToggle.textContent = "Close Role Editor";
        } catch (err) {
          showError(err.message);
        } finally {
          editRolesToggle.disabled = false;
        }
      });

      cancelRolesBtn.addEventListener("click", closeRoleEditor);
      saveRolesBtn.addEventListener("click", function () {
        var selectedRoles = Array.from(roleEditorOptions.querySelectorAll("input:checked")).map(function (input) { return input.value; });
        if (!selectedRoles.length) { showError("Select at least one role."); return; }
        withButton(saveRolesBtn, async function () {
          await api("PUT", ENDPOINTS.users + "/" + encodeURIComponent(user.id) + "/roles", { roles: selectedRoles });
          closeRoleEditor();
          onRefresh({ preferredUserId: user.id });
        }, "Roles updated");
      });

      roleEditor.appendChild(el("div", { className: "stack" },
        el("span", { id: "edit-user-roles-label" }, "Roles"),
        el("span", { className: "muted" }, "Select all that apply"),
        roleEditorOptions,
        el("div", { className: "inline-form detail-action-row" }, cancelRolesBtn, saveRolesBtn)
      ));
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
      actionRow.appendChild(editRolesToggle);
      actionRow.appendChild(toggleBtn);
      if (!user.provider) actionRow.appendChild(resetToggle);
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
      panel.appendChild(roleEditor);
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

    var keysRefreshBtn = el("button", { type: "button", className: "secondary" }, "Refresh");
    keysRefreshBtn.addEventListener("click", function () { loadKeys(); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "API Keys"),
      keysRefreshBtn
    ));

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
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create API key"
    }, svgIcon(ICON_PLUS), el("span", null, "Create API Key"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));

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

    function showEmptyKeyDetail() {
      clear(detailPanel);
      detailPanel.appendChild(el("h2", null, "Key Details"));
      detailPanel.appendChild(el("p", { className: "muted" }, "Select an API key to manage"));
    }
    showEmptyKeyDetail();

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
            await api("DELETE", keyPath(ids[i]));
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
            showEmptyKeyDetail();
          }
        } else {
          showEmptyKeyDetail();
        }
      } catch (err) {
        showTableLoadError(tableWrap, "Failed to load API keys");
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
    return api("GET", keyPath(keyId, "/detail"));
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
    var keyIds = keys.map(function (key) { return key._id; });
    var rowCheckboxes = [];
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible API keys"
    });
    selectAllBox.checked = keyIds.length > 0 && keyIds.every(function (keyId) {
      return selection.selectedIds.has(keyId);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && keyIds.some(function (keyId) {
      return selection.selectedIds.has(keyId);
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      keys.forEach(function (key) {
        if (selectAllBox.checked) selection.selectedIds.add(key._id);
        else selection.selectedIds.delete(key._id);
      });
      selection.onSelectionChange();
      syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, keyIds);
    });
    table.appendChild(el("colgroup", null, el("col", { className: "selection-col-width" })));
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
      checkbox._selectionId = k._id;
      checkbox.checked = selection.selectedIds.has(k._id);
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(k._id);
        else selection.selectedIds.delete(k._id);
        selection.onSelectionChange();
        syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, keyIds);
      });
      rowCheckboxes.push(checkbox);
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
      copyTextToClipboard(keyVal).then(function () {
        copyBtn.innerHTML = "";
        copyBtn.appendChild(svgIcon(ICON_CHECK));
        setTimeout(function () {
          copyBtn.innerHTML = "";
          copyBtn.appendChild(svgIcon(ICON_COPY));
        }, 1500);
      }).catch(function (err) {
        showError(err && err.message ? err.message : "Unable to copy API key");
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
    var saveBtn = el("button", {
      type: "button",
      className: "btn--icon",
      "aria-label": "Save details",
      title: "Save details",
    }, svgIcon(ICON_SAVE));
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
    var cancelBtn = el("button", {
      className: "secondary btn--icon",
      type: "button",
      style: "display:none",
      "aria-label": "Cancel editing details",
      title: "Cancel editing details",
    }, svgIcon(ICON_X));
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
      setFieldReadOnly(clientInput, editing);
      adapterSelect.disabled = !editing;
      promptSelect.disabled = !editing;
      setFieldReadOnly(notesInput, editing);
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
        await api("PUT", keyPath(keyId), {
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
        await api("GET", keyPath(keyId, "/status"));
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
        await api("PATCH", keyPath(keyId, "/rename?new_api_key=" + encodeURIComponent(nk)));
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
        var quota = await api("GET", keyPath(keyId, "/quota"));
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
              await api("POST", keyPath(keyId, "/deactivate"));
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
          await api("DELETE", keyPath(keyId));
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
              await api("POST", keyPath(keyId, "/quota/reset?period=" + period));
              showStatus("Quota " + period + " reset");
              var updated = await api("GET", keyPath(keyId, "/quota"));
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
    var editForm = el("div", { className: "admin-create-form", style: "display:none" });

    var dailyInput = el("input", { type: "number", placeholder: "Daily limit (blank=unlimited)", value: config.daily_limit != null ? config.daily_limit : "" });
    var monthlyInput = el("input", { type: "number", placeholder: "Monthly limit (blank=unlimited)", value: config.monthly_limit != null ? config.monthly_limit : "" });
    var throttleCheck = el("input", { type: "checkbox" });
    if (config.throttle_enabled) throttleCheck.checked = true;
    var priorityInput = el("input", { type: "range", min: "1", max: "10", value: config.throttle_priority || 5 });
    var priorityLabel = el("span", null, "Priority: " + (config.throttle_priority || 5));
    priorityInput.addEventListener("input", function () { priorityLabel.textContent = "Priority: " + priorityInput.value; });

    var saveBtn = el("button", {
      type: "button",
      className: "btn--icon",
      "aria-label": "Save quota",
      title: "Save quota",
    }, svgIcon(ICON_SAVE));
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
        await api("PUT", keyPath(keyId, "/quota"), body);
        showStatus("Quota updated");
        var updated = await api("GET", keyPath(keyId, "/quota"));
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
      editToggle.classList.toggle("btn--icon", hidden);
      editToggle.setAttribute("aria-label", hidden ? "Cancel editing quota" : "Edit quota");
      editToggle.setAttribute("title", hidden ? "Cancel editing quota" : "Edit quota");
      clear(editToggle);
      if (hidden) {
        editToggle.appendChild(svgIcon(ICON_X));
      } else {
        editToggle.appendChild(document.createTextNode("Edit Quota"));
      }
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

    var personasRefreshBtn = el("button", { type: "button", className: "secondary" }, "Refresh");
    personasRefreshBtn.addEventListener("click", function () { refreshPrompts(); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Personas"),
      personasRefreshBtn
    ));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "100" });
    var versionInput = el("input", { type: "text", value: "1.0", maxlength: "25" });
    var textArea = el("textarea", { rows: "5", required: "true", maxlength: "25000" });
    var textCounter = characterCount(textArea, 25000);
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
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create persona"
    }, svgIcon(ICON_PLUS), el("span", null, "Create Persona"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));

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

    createBtn.addEventListener("click", function () {
      var n = nameInput.value.trim();
      var t = textArea.value.trim();
      if (!n || !t) return;
      withButton(createBtn, async function () {
        var createdPrompt = await api("POST", ENDPOINTS.prompts, { name: n, prompt: t, version: versionInput.value.trim() || "1.0" });
        if (createKeySelect.value && createdPrompt && promptIdentifier(createdPrompt)) {
          await api("POST", keyPath(createKeySelect.value, "/prompt"), {
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
        showTableLoadError(tableWrap, "Failed to load personas");
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
    var promptIds = prompts.map(function (prompt) { return promptIdentifier(prompt); }).filter(Boolean);
    var rowCheckboxes = [];
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible personas"
    });
    selectAllBox.checked = promptIds.length > 0 && promptIds.every(function (promptId) {
      return selection.selectedIds.has(promptId);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && promptIds.some(function (promptId) {
      return selection.selectedIds.has(promptId);
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
      syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, promptIds);
    });
    table.appendChild(el("colgroup", null, el("col", { className: "selection-col-width" })));
    var thead = el("thead", null,
      el("tr", null,
        el("th", { className: "selection-col" }, selectAllBox),
        el("th", { className: "persona-id-col" }, "ID"),
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
      checkbox._selectionId = promptId;
      checkbox.checked = selection.selectedIds.has(promptId);
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(promptId);
        else selection.selectedIds.delete(promptId);
        selection.onSelectionChange();
        syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, promptIds);
      });
      rowCheckboxes.push(checkbox);
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
        el("td", { className: "persona-id-col" }, el("code", { className: "plain-code", title: promptId }, promptId ? promptId.slice(0, 8) : "")),
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
    var tArea = el("textarea", { rows: "8", maxlength: "25000", readonly: "true", "aria-readonly": "true" }, prompt.prompt || "");
    var tCounter = characterCount(tArea, 25000);
    var saveBtn = el("button", {
      type: "button",
      className: "btn--icon",
      "aria-label": "Save changes",
      title: "Save changes",
    }, svgIcon(ICON_SAVE));
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
    var cancelBtn = el("button", {
      className: "secondary btn--icon",
      type: "button",
      style: "display:none",
      "aria-label": "Cancel editing persona",
      title: "Cancel editing persona",
    }, svgIcon(ICON_X));
    function promptHasChanges() {
      return nameInput.value.trim() !== originalName || vInput.value.trim() !== originalVersion || tArea.value !== originalPromptText;
    }
    function syncPromptSaveState() {
      saveBtn.disabled = !isEditingPrompt || !promptHasChanges();
    }
    function setPromptEditMode(editing) {
      isEditingPrompt = editing;
      setFieldReadOnly(nameInput, editing);
      setFieldReadOnly(vInput, editing);
      setFieldReadOnly(tArea, editing);
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
        await api("POST", keyPath(k, "/prompt"), { prompt_id: promptId });
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

    // Log viewing is a separate permission (logs.read) from running the
    // server (system.manage) - operator, for example, has the latter but not
    // the former. Skip building the viewer (and its network calls) entirely
    // rather than rendering a panel that will just 401.
    var opsPermissions = (currentUser && currentUser.permissions) || [];
    var canReadLogs = opsPermissions.indexOf("*") !== -1 || opsPermissions.indexOf("logs.read") !== -1;
    if (!canReadLogs) {
      container.appendChild(el("p", { className: "muted" },
        "Server log viewing requires the logs.read permission (the auditor role, for example)."
      ));
      return;
    }

    // --- Log viewer: full-width terminal-style panel ---
    var logLevelFilter = "all";
    var logSearchTerm = "";
    var rawLogLines = [];
    var userNearBottom = true;
    var pendingNewLines = 0;
    var selectedLogFile = null; // null = always load latest

    var logFileSelect = el("select", { className: "log-file-select", "aria-label": "Select log file" },
      el("option", { value: "" }, "Loading files…")
    );
    logFileSelect.addEventListener("change", function () {
      selectedLogFile = logFileSelect.value || null;
      rawLogLines = [];
      loadLogs(false);
    });

    async function loadLogFiles() {
      try {
        var result = await api("GET", ENDPOINTS.logsFiles);
        var files = result.files || [];
        logFileSelect.innerHTML = "";
        files.forEach(function (f) {
          var label = f.filename + (f.is_current ? " (current)" : "") +
            " — " + formatLogFileSize(f.size);
          var opt = el("option", { value: f.is_current ? "" : f.filename }, label);
          logFileSelect.appendChild(opt);
        });
        if (!files.length) {
          logFileSelect.appendChild(el("option", { value: "" }, "No log files found"));
        }
      } catch (_) {
        logFileSelect.innerHTML = "";
        logFileSelect.appendChild(el("option", { value: "" }, "orbit.log"));
      }
    }

    function formatLogDate(iso) {
      var d = new Date(iso);
      if (isNaN(d)) return iso;
      return d.toLocaleString(undefined, {
        month: "short", day: "numeric", year: "numeric",
        hour: "2-digit", minute: "2-digit"
      });
    }

    function formatLogFileSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / 1048576).toFixed(1) + " MB";
    }

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
      logCount.textContent = visible < rawLogLines.length ? visible + " / " + rawLogLines.length + " lines" : "";
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
        var url = ENDPOINTS.logsTail + "?lines=500" + (selectedLogFile ? "&file=" + encodeURIComponent(selectedLogFile) : "");
        var result = await api("GET", url);
        logUpdated.textContent = result.updated_at ? "Updated " + formatLogDate(result.updated_at) : "";
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
        if (!selectedLogFile) scheduleLogRefresh();
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
        logFileSelect,
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

    loadLogFiles();
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

    // Lazy-load adapter file listing and capability metadata (needed to know
    // which adapters support template reload)
    if (!cachedAdapterFiles || !cachedAdapterCapabilities) {
      container.appendChild(skeleton());
      Promise.all([
        cachedAdapterFiles ? Promise.resolve(cachedAdapterFiles) : loadAdapterFiles(),
        cachedAdapterCapabilities ? Promise.resolve(cachedAdapterCapabilities) : loadAdapterCapabilities(),
      ]).then(function () {
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
      var saveBtn = el("button", {
        type: "button",
        className: "btn btn--primary btn--icon",
        disabled: "true",
        "aria-label": "Save adapter config",
        title: "Save adapter config",
      }, svgIcon(ICON_SAVE));
      var reloadDiskBtn = el("button", {
        className: "btn btn--neutral btn--icon",
        "aria-label": "Reload from disk",
        title: "Reload from disk",
      }, svgIcon(ICON_REFRESH));
      // Template reload only applies to adapters whose implementation exposes
      // reload_templates() (intent/composite retrievers) — driven by the backend
      // capability flag so this stays correct as new adapter types are added.
      var adapterCap = (cachedAdapterCapabilities || []).find(function (c) { return c.name === a.name; });
      var supportsTemplateReload = !!(adapterCap && adapterCap.supports_template_reload);
      var reloadTemplatesBtn = supportsTemplateReload
        ? el("button", { className: "btn btn--neutral" }, "Reload Templates")
        : null;

      var btnRow = el("div", { style: "display:flex;flex-wrap:wrap;gap:var(--sp-2);margin-top:var(--sp-3)" });
      btnRow.appendChild(saveBtn);
      btnRow.appendChild(reloadDiskBtn);
      if (reloadTemplatesBtn) {
        btnRow.appendChild(el("span", { className: "ops-action-divider" }));
        btnRow.appendChild(reloadTemplatesBtn);
      }
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

      // Save handler — saves just this adapter's block back into its file, then hot-reloads it
      saveBtn.addEventListener("click", async function () {
        saveBtn.disabled = true;
        try {
          await api("PUT", ENDPOINTS.adapterConfigs + "/entry/" + encodeURIComponent(a.name), { content: adapterEditor.getValue() });
          adapterOriginal = adapterEditor.getValue();
          // Refresh adapter list
          await loadAdapterFiles();
          renderAdapterRows(searchInput.value);
          clear(banner);
          banner.style.display = "none";
          await doReloadAdapter();
        } catch (err) {
          showError("Save failed: " + err.message);
        } finally {
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

      // Reload adapter (hot-swap via existing endpoint) \u2014 triggered automatically after save
      async function doReloadAdapter() {
        await withButton(saveBtn, async function () {
          var path = ENDPOINTS.reloadAdapters + "/async?adapter_name=" + encodeURIComponent(a.name);
          var started = await api("POST", path);
          await waitForAdminJob(started.job_id, "Reloading adapter\u2026");
          await loadAdapterCapabilities();
          showStatus("Adapter '" + a.name + "' saved and reloaded");
        });
      }

      // Reload templates
      if (reloadTemplatesBtn) {
        reloadTemplatesBtn.addEventListener("click", function () {
          if (!adapterCap.cached) {
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
      }

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
  // TAB: Settings (Ace Editor — YAML, split into config.yaml sections)
  // ==================================================================
  var settingsEditors = {}; // key -> { editor, original } for every section rendered in the active category
  var selectedSettingsCategory = null; // currently selected category group label
  var cachedSettingsSections = null; // [{key, line_count}, ...]

  function destroyAllSettingsEditors() {
    Object.keys(settingsEditors).forEach(function (key) {
      settingsEditors[key].editor.destroy();
    });
    settingsEditors = {};
  }

  function settingsEditorsAreDirty() {
    return Object.keys(settingsEditors).some(function (key) {
      var st = settingsEditors[key];
      return !!st && st.editor.getValue() !== st.original;
    });
  }

  // Grouping + display copy for known top-level config.yaml keys. A key that
  // isn't listed here still shows up, under "Uncategorized" — so a new key
  // added to config.yaml is never hidden, just uncategorized until this list
  // catches up. "import" is deliberately excluded: it's a list of included
  // files, not an editable settings section.
  var SETTINGS_HIDDEN_KEYS = ["import"];
  var SETTINGS_GROUPS = [
    { label: "General & Performance", keys: ["general", "performance", "language_detection", "clock_service"] },
    { label: "Authentication & Security", keys: ["auth", "api_keys", "security", "secrets_management"] },
    { label: "Internal Services & Storage", keys: ["internal_services", "chat_history", "conversation_threading", "prompt_service"] },
    { label: "Retrieval & Files", keys: ["composite_retrieval", "autocomplete", "skill_routing", "files"] },
    { label: "Reliability & Messaging", keys: ["fault_tolerance", "messaging", "messages"] },
    { label: "Logging & Monitoring", keys: ["logging", "monitoring"] },
  ];
  var SETTINGS_TITLES = {
    general: "General", performance: "Performance", language_detection: "Language Detection",
    clock_service: "Clock Service", auth: "Authentication", api_keys: "API Keys", security: "Security",
    secrets_management: "Secrets Management",
    internal_services: "Internal Services", chat_history: "Chat History",
    conversation_threading: "Conversation Threading", prompt_service: "Prompt Service",
    composite_retrieval: "Composite Retrieval", autocomplete: "Autocomplete",
    skill_routing: "Skill Routing", files: "Files",
    fault_tolerance: "Fault Tolerance", messaging: "Message Queue", messages: "Messages",
    logging: "Logging", monitoring: "Monitoring",
  };

  function settingsSectionTitle(key) {
    if (SETTINGS_TITLES[key]) return SETTINGS_TITLES[key];
    return key.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function settingsLineLabel(n) {
    return n + (n === 1 ? " line" : " lines");
  }

  async function renderSettings(container) {
    clear(container);
    destroyAllSettingsEditors();

    if (!cachedSettingsSections) {
      container.appendChild(skeleton());
      try {
        var data = await api("GET", ENDPOINTS.configSections);
        cachedSettingsSections = data.sections || [];
      } catch (err) {
        showError("Failed to load config sections: " + err.message);
        cachedSettingsSections = [];
      }
      if (activeTab === "settings") renderSettings(container);
      return;
    }

    var wrap = el("div", { className: "settings-view" });
    container.appendChild(wrap);

    var sectionByKey = {};
    cachedSettingsSections.forEach(function (s) { sectionByKey[s.key] = s; });
    var knownKeys = cachedSettingsSections
      .map(function (s) { return s.key; })
      .filter(function (k) { return SETTINGS_HIDDEN_KEYS.indexOf(k) === -1; });
    var groupedKeys = {};
    var groups = SETTINGS_GROUPS
      .map(function (g) { return { label: g.label, keys: g.keys.filter(function (k) { return knownKeys.indexOf(k) !== -1; }) }; })
      .filter(function (g) { return g.keys.length > 0; });
    groups.forEach(function (g) { g.keys.forEach(function (k) { groupedKeys[k] = true; }); });
    var otherKeys = knownKeys.filter(function (k) { return !groupedKeys[k]; });
    if (otherKeys.length) {
      groups.push({ label: "Uncategorized", keys: otherKeys });
    }

    if (!groups.length) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("strong", null, "No settings sections found"),
        el("p", null, "config.yaml does not currently define any recognized top-level sections.")
      ));
      return;
    }

    // ----- Category dropdown -----
    var picker = el("div", { className: "settings-category-picker" });
    var pickerLabel = el("label", { htmlFor: "settings-category-select" }, "Category");
    var select = el("select", { id: "settings-category-select", "aria-label": "Settings category" });
    groups.forEach(function (g) {
      select.appendChild(el("option", { value: g.label },
        g.label + " (" + g.keys.length + (g.keys.length === 1 ? " section" : " sections") + ")"
      ));
    });
    picker.appendChild(pickerLabel);
    picker.appendChild(select);
    wrap.appendChild(picker);

    var body = el("div", { className: "settings-category-body" });
    wrap.appendChild(body);

    function findGroup(label) {
      return groups.filter(function (g) { return g.label === label; })[0] || null;
    }

    function categoryIsDirty(label) {
      var g = findGroup(label);
      if (!g) return false;
      return g.keys.some(function (key) {
        var st = settingsEditors[key];
        return !!st && st.editor.getValue() !== st.original;
      });
    }

    select.addEventListener("change", function () {
      var nextLabel = select.value;
      if (nextLabel === selectedSettingsCategory) return;
      if (categoryIsDirty(selectedSettingsCategory)) {
        select.value = selectedSettingsCategory; // revert until the user confirms
        confirmAction({
          title: "Unsaved Changes",
          message: "You have unsaved changes in this category. Discard them?",
          confirmLabel: "Discard",
          isDanger: true,
          onConfirm: function () {
            selectedSettingsCategory = nextLabel;
            select.value = nextLabel;
            renderBody(nextLabel);
          }
        });
        return;
      }
      selectedSettingsCategory = nextLabel;
      renderBody(nextLabel);
    });

    function renderBody(label) {
      clear(body);
      destroyAllSettingsEditors();
      var g = findGroup(label);
      if (!g) return;
      g.keys.forEach(function (key) { body.appendChild(renderSectionBlock(key)); });
    }

    function renderSectionBlock(key) {
      var titleText = settingsSectionTitle(key);

      var block = el("div", { className: "panel settings-section-block" });

      var headerRow = el("div", { style: "display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-2)" });
      headerRow.appendChild(el("h3", { style: "margin:0" }, titleText));
      block.appendChild(headerRow);

      var metaEl = el("p", { className: "muted settings-section-block__meta" },
        settingsLineLabel(sectionByKey[key] ? sectionByKey[key].line_count : 0)
      );
      block.appendChild(metaEl);

      var banner = el("div", { className: "settings-banner", style: "display:none", role: "status" });
      block.appendChild(banner);

      var editorWrap = el("div", { className: "settings-ace-wrap" });
      block.appendChild(editorWrap);

      var btnRow = el("div", { style: "display:flex;gap:var(--sp-3);margin-top:var(--sp-3)" });
      var saveBtn = el("button", {
        type: "button",
        className: "btn btn--primary btn--icon",
        disabled: "true",
        "aria-label": "Save config section",
        title: "Save config section",
      }, svgIcon(ICON_SAVE));
      var reloadBtn = el("button", {
        className: "btn btn--neutral btn--icon",
        "aria-label": "Reload from disk",
        title: "Reload from disk",
      }, svgIcon(ICON_REFRESH));
      btnRow.appendChild(saveBtn);
      btnRow.appendChild(reloadBtn);
      block.appendChild(btnRow);

      ace.config.set("basePath", "/static");
      ace.config.set("modePath", "/static");
      ace.config.set("themePath", "/static");
      ace.config.set("workerPath", "/static");

      var editor = ace.edit(editorWrap, {
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
        minLines: 4,
        maxLines: 40,
        scrollPastEnd: 0.2,
      });
      ace.config.loadModule("ace/ext/searchbox", function () {});
      var editorState = { editor: editor, original: "" };
      settingsEditors[key] = editorState;

      function isCurrentEditor() {
        return settingsEditors[key] === editorState;
      }

      editor.session.on("change", function () {
        if (!isCurrentEditor()) return;
        saveBtn.disabled = editor.getValue() === editorState.original;
      });

      var endpoint = ENDPOINTS.configSections + "/" + encodeURIComponent(key);

      async function loadContent() {
        try {
          var data = await api("GET", endpoint);
          if (!isCurrentEditor()) return;
          editorState.original = data.content;
          editor.setValue(data.content, -1);
          metaEl.textContent = settingsLineLabel(editor.getValue().split("\n").length);
          editor.getSession().getUndoManager().reset();
          saveBtn.disabled = true;
          banner.style.display = "none";
        } catch (err) {
          if (isCurrentEditor()) showError("Failed to load: " + err.message);
        }
      }

      saveBtn.addEventListener("click", async function () {
        saveBtn.disabled = true;
        try {
          await api("PUT", endpoint, { content: editor.getValue() });
          if (!isCurrentEditor()) return;
          editorState.original = editor.getValue();
          banner.textContent = "'" + titleText + "' saved. Go to the Ops tab to restart the server for changes to take effect.";
          banner.style.display = "";
          setTimeout(function () { banner.style.display = "none"; }, 5000);
          var sec = sectionByKey[key];
          if (sec) sec.line_count = editor.getValue().split("\n").length;
          metaEl.textContent = settingsLineLabel(editor.getValue().split("\n").length);
        } catch (err) {
          if (isCurrentEditor()) {
            showError("Save failed: " + err.message);
            saveBtn.disabled = editor.getValue() === editorState.original;
          }
        }
      });

      reloadBtn.addEventListener("click", function () {
        var dirty = editor.getValue() !== editorState.original;
        if (dirty) {
          confirmAction({
            title: "Reload",
            message: "You have unsaved changes. Reload from disk and discard them?",
            confirmLabel: "Discard & Reload",
            isDanger: true,
            loadingLabel: "Reloading…",
            onConfirm: async function () {
              await loadContent();
              showStatus("Reloaded from disk");
            },
          });
        } else {
          loadContent().then(function () { showStatus("Reloaded from disk"); });
        }
      });

      loadContent();
      return block;
    }

    var validCategories = groups.map(function (g) { return g.label; });
    if (!selectedSettingsCategory || validCategories.indexOf(selectedSettingsCategory) === -1) {
      selectedSettingsCategory = groups[0].label;
    }
    select.value = selectedSettingsCategory;
    renderBody(selectedSettingsCategory);
  }

  // ==================================================================
  // TAB: Audit — admin/auth + inference request ledger
  // ==================================================================

  var AUDIT_PAGE_SIZE = 25;
  var AUDIT_STREAMS = [
    { value: "all", label: "All" },
    { value: "admin", label: "Admin" },
    { value: "inference", label: "Inference" },
  ];

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

  function isInferenceAudit(ev) {
    return !!ev && ev.audit_source === "inference";
  }

  function displayActorId(ev) {
    if (!ev) return "\u2014";
    if (ev.actor_type === "anonymous") return "anonymous";
    return ev.actor_id || ev.actor_username || "\u2014";
  }

  function auditSourceLabel(ev) {
    return isInferenceAudit(ev) ? "Inference" : "Admin";
  }

  function auditSourceBadgeClass(ev) {
    return "audit-source-badge audit-source-badge--" + (isInferenceAudit(ev) ? "inference" : "admin");
  }

  function auditEventTitle(ev) {
    if (isInferenceAudit(ev)) return ev.title || ev.provider || "inference";
    return ev.event_type || "\u2014";
  }

  function auditEventSubtitle(ev) {
    if (isInferenceAudit(ev)) return ev.subtitle || ev.adapter_name || "inference request";
    return ev.action || "";
  }

  function auditResourceText(ev) {
    if (isInferenceAudit(ev)) {
      return ev.adapter_name || ev.provider || ev.resource_id || "\u2014";
    }
    return ev.resource_id || ev.resource_type || "\u2014";
  }

  function auditOutcomeLabel(ev) {
    if (isInferenceAudit(ev)) {
      return ev.success ? "served" : "blocked";
    }
    return ev.success ? "ok" : "fail";
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
      "A unified register of admin/auth activity and inference requests captured by the audit service. ",
      "Use the stream filter to isolate operational events from live inference traffic."));

    // ----- State (per-render closure) -----
    var state = {
      source: "all",          // "all" | "admin" | "inference"
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
    var sourceSelect = el("select", { className: "audit-view__select", "aria-label": "Filter audit stream" });
    var outcomeSelect = el("select", { className: "audit-view__select", "aria-label": "Filter audit outcome" });
    var domainSelect = el("select", { className: "audit-view__select", "aria-label": "Filter audit domain" });
    var searchInput = el("input", {
      type: "search",
      placeholder: "Search actor id, provider, query, path, resource, IP\u2026",
      "aria-label": "Search audit events",
      className: "audit-view__search-input",
    });

    function renderFilters() {
      clear(sourceSelect);
      AUDIT_STREAMS.forEach(function (stream) {
        var option = el("option", { value: stream.value }, stream.label);
        if (state.source === stream.value) option.selected = true;
        sourceSelect.appendChild(option);
      });

      clear(outcomeSelect);
      [
        ["all", "All"],
        ["success", "Succeeded"],
        ["failure", "Failed"],
      ].forEach(function (tuple) {
        var value = tuple[0], label = tuple[1];
        var option = el("option", { value: value }, label);
        if (state.outcome === value) option.selected = true;
        outcomeSelect.appendChild(option);
      });

      clear(domainSelect);
      AUDIT_DOMAINS.forEach(function (d) {
        var option = el("option", { value: d.value }, d.label);
        if (state.domain === d.value) option.selected = true;
        domainSelect.appendChild(option);
      });
      domainSelect.disabled = state.source === "inference";
    }

    sourceSelect.addEventListener("change", function () {
      state.source = sourceSelect.value;
      if (state.source === "inference") state.domain = "all";
      state.offset = 0;
      state.selectedIndex = null;
      renderFilters();
      load();
    });

    outcomeSelect.addEventListener("change", function () {
      state.outcome = outcomeSelect.value;
      state.offset = 0;
      state.selectedIndex = null;
      load();
    });

    domainSelect.addEventListener("change", function () {
      state.domain = domainSelect.value;
      state.offset = 0;
      state.selectedIndex = null;
      load();
    });

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
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Stream"),
        sourceSelect
      ),
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Outcome"),
        outcomeSelect
      ),
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Domain"),
        domainSelect
      ),
      el("div", { className: "audit-view__search" }, searchInput),
      el("div", { className: "audit-view__actions" }, refreshBtn)
    ));
    renderFilters();

    // ----- Table wrap + pagination -----
    var tableWrap = el("div", { className: "audit-view__table-wrap" }, skeleton());
    var pagerBar = el("div", { className: "audit-view__pager pagination-bar" });
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
      params.set("source", state.source);
      if (state.outcome === "success") params.set("success", "true");
      else if (state.outcome === "failure") params.set("success", "false");
      if (state.domain && state.domain !== "all" && state.source !== "inference") params.set("event_prefix", state.domain);
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
        if (/audit ledger is not enabled/i.test(msg) || /admin audit is not enabled/i.test(msg) || /inference request audit is not enabled/i.test(msg)) {
          tableWrap.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Audit ledger is not enabled."),
            el("p", { className: "muted" },
              "Set ",
              el("code", null, "internal_services.audit.enabled: true"),
              " for inference request auditing, and ",
              el("code", null, "internal_services.audit.admin_events.enabled: true"),
              " if you also want admin/auth events, then restart the server.")
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
            : "As admin actions and inference requests occur they will appear here.")
      ));
      return;
    }

    var table = el("table", { className: "audit-table" });
    var thead = el("thead", null,
      el("tr", null,
        el("th", null, "Time"),
        el("th", null, "Event"),
        el("th", null, "Principal"),
        el("th", null, "Resource"),
        el("th", { className: "audit-col-status" }, "Status")
      )
    );
    var tbody = el("tbody");

    events.forEach(function (ev, idx) {
      var statusCls = ev.success ? "badge-ok" : "badge-fail";
      var statusLabel = auditOutcomeLabel(ev);
      var isSelected = state.selectedIndex === idx;

      var actorCell;
      if (ev.actor_type === "anonymous") {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-anon" }, "anonymous"),
          el("div", { className: "audit-actor-role" }, ev.actor_type)
        );
      } else {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-name" }, displayActorId(ev)),
          el("div", { className: "audit-actor-role" }, ev.actor_type || "")
        );
      }

      var resourceText = auditResourceText(ev);

      var rowClass = "selectable-row audit-row audit-row--source-" + (isInferenceAudit(ev) ? "inference" : "admin");
      if (isSelected) rowClass += " selected-row audit-row--active";

      var tr = el("tr", { className: rowClass },
        el("td", { className: "audit-col-time" }, formatAuditTimestamp(ev.timestamp)),
        el("td", { className: "audit-col-event" },
          el("div", { className: "audit-event-meta" },
            el("span", { className: auditSourceBadgeClass(ev) }, auditSourceLabel(ev))
          ),
          el("div", { className: "audit-event-type" }, auditEventTitle(ev)),
          el("div", { className: "audit-event-action muted" }, auditEventSubtitle(ev))
        ),
        el("td", null, actorCell),
        el("td", { className: "audit-col-resource" }, resourceText),
        el("td", { className: "audit-col-status" },
          el("span", { className: "audit-status-code" }, isInferenceAudit(ev) ? (ev.provider || "") : String(ev.status_code != null ? ev.status_code : "")),
          el("span", { className: "badge " + statusCls }, statusLabel)
        )
      );
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", isSelected ? "true" : "false");
      tr.addEventListener("click", function () {
        markSelectedRow(tbody, tr);
        onSelect(idx);
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
    panel.appendChild(el("h2", null, "Details"));
    panel.appendChild(el("div", { className: "empty-state" },
      el("p", null, "Select an entry from the register."),
      el("p", { className: "muted" }, "A dossier shows the actor, request metadata, origin details, and the captured payload or summary for the selected audit record.")
    ));
  }

  function renderAuditDossier(panel, ev, onClose) {
    clear(panel);
    if (!ev) { renderAuditDossierEmpty(panel); return; }

    var closeBtn = el("button", { type: "button", className: "secondary audit-dossier__close" }, "Close");
    closeBtn.addEventListener("click", onClose);
    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Details"),
      closeBtn
    ));

    panel.appendChild(el("div", { className: "audit-dossier__headline" },
      el("div", { className: "audit-dossier__meta" },
        el("span", { className: auditSourceBadgeClass(ev) }, auditSourceLabel(ev))
      ),
      el("div", { className: "audit-dossier__event-type" }, auditEventTitle(ev)),
      auditEventSubtitle(ev) ? el("div", { className: "audit-dossier__action muted" }, auditEventSubtitle(ev)) : null
    ));

    var verdictCls = "audit-verdict audit-verdict--" + (ev.success ? "success" : "failure");
    panel.appendChild(el("div", null,
      el("span", { className: verdictCls },
        isInferenceAudit(ev) ? (ev.success ? "Served" : "Blocked") : (ev.success ? "Succeeded" : "Failed"),
        isInferenceAudit(ev)
          ? " \u00B7 " + (ev.provider || "inference")
          : " \u00B7 HTTP " + (ev.status_code != null ? ev.status_code : "?")
      )
    ));

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Principals"));
    if (isInferenceAudit(ev)) {
      panel.appendChild(renderAuditFieldGrid([
        ["Actor type", ev.actor_type || ""],
        ["Actor ID", ev.actor_id || "\u2014"],
        ["User ID", ev.user_id || "\u2014"],
        ["API key", ev.api_key && ev.api_key.key ? ev.api_key.key : "\u2014"],
        ["Session", ev.session_id || "\u2014"],
      ]));
    } else {
      panel.appendChild(renderAuditFieldGrid([
        ["Actor type", ev.actor_type || ""],
        ["Actor ID", ev.actor_id || "\u2014"],
        ["Resource", ev.resource_id || "\u2014"],
        ["Resource kind", ev.resource_type || ""],
      ]));
    }

    panel.appendChild(el("h3", { className: "audit-section-heading" }, isInferenceAudit(ev) ? "Inference" : "Request"));
    if (isInferenceAudit(ev)) {
      panel.appendChild(renderAuditFieldGrid([
        ["Provider", ev.provider || "\u2014"],
        ["Model", ev.model || "\u2014"],
        ["Adapter", ev.adapter_name || "\u2014"],
        ["Blocked", ev.blocked ? "yes" : "no"],
        ["Timestamp", formatAuditTimestamp(ev.timestamp)],
        ["Event type", ev.event_type || ""],
        ["Action", ev.action || ""],
      ]));
    } else {
      panel.appendChild(renderAuditFieldGrid([
        ["Method", ev.method || ""],
        ["Path", ev.path || ""],
        ["Status", String(ev.status_code != null ? ev.status_code : "") + (ev.error_message ? " \u00B7 " + ev.error_message : "")],
        ["Timestamp", formatAuditTimestamp(ev.timestamp)],
        ["Event type", ev.event_type || ""],
        ["Action", ev.action || ""],
      ]));
    }

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

    if (isInferenceAudit(ev)) {
      panel.appendChild(el("h3", { className: "audit-section-heading" }, "Payload"));
      panel.appendChild(el("div", { className: "audit-dossier__payload" },
        el("div", { className: "audit-dossier__payload-block" },
          el("div", { className: "audit-dossier__payload-label" }, "Query"),
          el("pre", { className: "audit-dossier__summary" }, ev.query || "\u2014")
        ),
        el("div", { className: "audit-dossier__payload-block" },
          el("div", { className: "audit-dossier__payload-label" }, "Response"),
          el("pre", { className: "audit-dossier__summary" }, ev.response || "\u2014")
        )
      ));
    } else {
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
