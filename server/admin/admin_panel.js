import { ENDPOINTS, createApi } from "./admin_panel/core/api.js";
import { standardChartOptions as feedbackChartOptions } from "./admin_panel/core/charts.js";
import { clear, el, wrapTable } from "./admin_panel/core/dom.js";
import { renderMetricCard } from "./admin_panel/core/metrics.js";
import { createFeedbackTab } from "./admin_panel/tabs/feedback.js";
import { createCostsTab } from "./admin_panel/tabs/costs.js";
import { createAuditTab } from "./admin_panel/tabs/audit.js";
import { createOverviewTab } from "./admin_panel/tabs/overview.js";
import { createUsersTab } from "./admin_panel/tabs/users.js";
import { createApiKeysTab } from "./admin_panel/tabs/api-keys.js";
import { createPromptsTab } from "./admin_panel/tabs/prompts.js";
import { createOpsTab } from "./admin_panel/tabs/ops.js";
import { createAdaptersTab } from "./admin_panel/tabs/adapters.js";
import { createMcpTab } from "./admin_panel/tabs/mcp.js";
import { createSettingsTab } from "./admin_panel/tabs/settings.js";

/* ============================================================
   ORBIT Admin Portal — Single-file vanilla JS client
   ============================================================ */
  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let authToken = null;
  let currentUser = null;
  let activeTab = "overview";
  let serverVersion = null;
  let railCollapsed = readStoredFlag("orbit.admin.railCollapsed");

  // Cached data
  let cachedAdapters = null;
  let cachedAdapterCapabilities = null;
  let cachedPrompts = null;
  let cachedKeys = null;
  let cachedApiKeyUsers = null; // Users available to pick for API key allowlists

  // Selection state per tab
  let messageCounter = 0;


  const api = createApi({
    getAuthToken: function () { return authToken; },
    onUnauthorized: function () {
      authToken = null;
      currentUser = null;
      window.location.href = ENDPOINTS.login + "?next=/admin";
    }
  });

  // ------------------------------------------------------------------
  // Stored UI preferences
  // Web storage can be blocked outright (embedded views, hardened
  // browsers), so persistence is best-effort: on failure the preference
  // just lives in memory for the session.
  // ------------------------------------------------------------------
  function readStoredFlag(key) {
    try {
      return localStorage.getItem(key) === "1";
    } catch (err) {
      return false;
    }
  }

  function writeStoredFlag(key, value) {
    try {
      localStorage.setItem(key, value ? "1" : "0");
    } catch (err) {
      /* Preference is not persisted; the in-memory value still applies. */
    }
  }

  // ------------------------------------------------------------------
  // DOM helpers
  // ------------------------------------------------------------------
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
  var ICON_PENCIL = ["M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"];
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
    operator: "Runs system configuration, adapters, server control, and server logs; no chat or audit access.",
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

  // ------------------------------------------------------------------
  // Sortable column headers
  //
  // Client-paged tables all render from an array held by their paginator,
  // so sorting means installing a comparator and letting the paginator
  // reorder and redraw. Columns declare how to read their own value; the
  // sorter keeps only the state, since each table rebuilds its header on
  // every render.
  // ------------------------------------------------------------------
  var SORT_LEADING_NUMBER = /^-?[\d,]*\.?\d+/;
  var ICON_SORT_NONE = ["M5 10.5l3-3 3 3", "M5 13.5l3 3 3-3"];
  var ICON_SORT_ASC = ["M5 14l3-3 3 3"];
  var ICON_SORT_DESC = ["M5 10l3 3 3-3"];

  // "5 / 30", "12 ms" and "42.5%" all sort on their leading number rather
  // than as text, which is what the formatted cells actually contain.
  function sortNumber(value) {
    if (typeof value === "number") return isFinite(value) ? value : null;
    if (value == null) return null;
    var match = SORT_LEADING_NUMBER.exec(String(value).trim());
    return match ? parseFloat(match[0].replace(/,/g, "")) : null;
  }

  function isBlankSortValue(value) {
    if (value == null) return true;
    var text = String(value).trim();
    return text === "" || text === "\u2014" || text === "N/A";
  }

  function compareSortValues(a, b) {
    var numA = sortNumber(a);
    var numB = sortNumber(b);
    if (numA !== null && numB !== null) return numA - numB;
    return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
  }

  function sortIndicator(dir) {
    var paths = dir === 0 ? ICON_SORT_NONE : dir > 0 ? ICON_SORT_ASC : ICON_SORT_DESC;
    var icon = svgIcon(paths);
    icon.setAttribute("class", "th-sort-icon");
    icon.setAttribute("aria-hidden", "true");
    return icon;
  }

  function createColumnSorter(paginator) {
    var state = { key: null, dir: 1 };
    var columns = [];
    var mountedRow = null;

    function comparator() {
      var column = columns.filter(function (c) { return c.key === state.key; })[0];
      if (!column || !column.sortValue) return null;
      return function (rowA, rowB) {
        var a = column.sortValue(rowA);
        var b = column.sortValue(rowB);
        // Blanks sort last in both directions, so an empty cell never
        // wins a descending sort.
        var blankA = isBlankSortValue(a);
        var blankB = isBlankSortValue(b);
        if (blankA || blankB) return blankA && blankB ? 0 : (blankA ? 1 : -1);
        return compareSortValues(a, b) * state.dir;
      };
    }

    function toggle(key) {
      if (state.key === key) state.dir = -state.dir;
      else { state.key = key; state.dir = 1; }
      // Some tables rebuild their header when the data is reordered and
      // some only rebuild the body, so refresh it here for the latter.
      if (mountedRow && mountedRow.parentNode) {
        var previousRow = mountedRow;
        var replacement = headerRow(columns);
        previousRow.parentNode.replaceChild(replacement, previousRow);
      }
      if (paginator) paginator.setComparator(comparator());
      // Only now is mountedRow the row that survived, so keyboard focus
      // stays on the header that was just activated.
      var active = mountedRow && mountedRow.querySelector(".th-sort.is-sorted");
      if (active) active.focus();
    }

    function headerRow(nextColumns) {
      columns = nextColumns || columns;
      var row = el("tr", null, columns.map(function (column) {
        var attrs = {};
        Object.keys(column.attrs || {}).forEach(function (k) { attrs[k] = column.attrs[k]; });
        if (!column.sortValue) return el("th", attrs, column.content || column.label || null);
        var isSorted = column.key === state.key;
        attrs["aria-sort"] = isSorted ? (state.dir === 1 ? "ascending" : "descending") : "none";
        var button = el("button", {
          type: "button",
          className: "th-sort" + (isSorted ? " is-sorted" : ""),
        }, el("span", null, column.label), sortIndicator(isSorted ? state.dir : 0));
        button.addEventListener("click", function () { toggle(column.key); });
        return el("th", attrs, button);
      }));
      mountedRow = row;
      return row;
    }

    return {
      headerRow: headerRow,
      isSortedBy: function (key) { return state.key === key; },
      // For when an in-place edit changes the value the table is ordered
      // by. Keeps the current page: the user didn't ask to navigate.
      reapply: function () {
        if (paginator) paginator.setComparator(comparator(), true);
      },
    };
  }

  function createPaginator(opts) {
    var pageSize = opts.pageSize || ITEMS_PER_PAGE;
    var onPageChange = opts.onPageChange || function () {};
    var allItems = [];
    var sourceItems = [];
    var comparator = null;
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
      sourceItems = items || [];
      allItems = comparator ? sourceItems.slice().sort(comparator) : sourceItems;
      if (!preservePage) currentPage = 1;
      computePages();
      renderControls();
      onPageChange(getSlice(), currentPage, totalPages);
    }

    // Held on the paginator so a live-refreshing table keeps its sort when
    // the next snapshot replaces the data.
    function setComparator(compare, preservePage) {
      comparator = compare || null;
      setData(sourceItems, preservePage);
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
      setComparator: setComparator,
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
    overviewTab.dispose();
    opsTab.dispose();

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
      // /admin/info requires system.manage; skip the call for roles without
      // it (auditor, analyst, user-manager) rather than firing a request that
      // can only 401. serverVersion just stays null and the version display
      // is omitted.
      if (userHasPermission("system.manage")) {
        try {
          var infoResp = await fetch(ENDPOINTS.serverInfo, { headers: { "Authorization": "Bearer " + authToken }, credentials: "same-origin" });
          if (infoResp.ok) { var infoData = await infoResp.json(); serverVersion = infoData.version || null; }
        } catch (_) {}
      }
      renderShell();
    } catch (err) {
      document.getElementById("app").textContent = "Failed to initialize: " + err.message;
    }
  }

  // ------------------------------------------------------------------
  // Shell: side rail + workbar + content area
  // ------------------------------------------------------------------
  var ICON_NAV_OVERVIEW = ["M22 12h-4l-3 9L9 3l-3 9H2"];
  var ICON_NAV_FEEDBACK = ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"];
  var ICON_NAV_USERS = [
    "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2",
    "M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
    "M23 21v-2a4 4 0 0 0-3-3.87",
    "M16 3.13A4 4 0 0 1 16 11",
  ];
  var ICON_NAV_KEYS = [
    "M10.5 13.5a4.5 4.5 0 1 1-3.2-1.3 4.5 4.5 0 0 1 3.2 1.3z",
    "M10.5 13.5L19 5",
    "M16 8l3 3 3-3-3-3",
  ];
  var ICON_NAV_PERSONAS = [
    "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
    "M9 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
    "M5.5 17c.6-1.8 1.9-2.6 3.5-2.6s2.9.8 3.5 2.6",
    "M16 9.5h3",
    "M16 13.5h3",
  ];
  var ICON_NAV_ADAPTERS = [
    "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "M8.6 10.5l6.8-3.9",
    "M8.6 13.5l6.8 3.9",
  ];
  var ICON_NAV_SETTINGS = [
    "M4 21v-7", "M4 10V3", "M12 21v-9", "M12 8V3", "M20 21v-5", "M20 12V3",
    "M1 14h6", "M9 8h6", "M17 16h6",
  ];
  var ICON_NAV_OPS = ["M4 17l6-6-6-6", "M12 19h8"];
  var ICON_NAV_AUDIT = ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"];
  // The Model Context Protocol mark, from the project's own favicon
  // (modelcontextprotocol.io), used nominatively to label the MCP integration.
  // Its three stroked paths are reproduced verbatim in shape but rescaled from
  // the source 180 grid onto the 24 grid every other icon here uses: the rail
  // sets `stroke-width: 1.6` in CSS, which overrides the SVG attribute, so a
  // 180-unit viewBox would render this as an invisible 0.14px hairline. At this
  // scale the mark spans 17x19 units, matching the optical size of its
  // neighbours, and the rail's 1.6 lands within a hair of the logo's own
  // 1.40 stroke ratio.
  var ICON_NAV_MCP = [
    "M3.52 11.51L11.43 3.59C12.53 2.5 14.3 2.5 15.39 3.59C16.48 4.69 16.48 6.46 15.39 7.55L9.41 13.53",
    "M9.5 13.45L15.39 7.55C16.48 6.46 18.26 6.46 19.35 7.55L19.39 7.59C20.48 8.69 20.48 10.46 19.39 11.55L12.23 18.71C11.87 19.07 11.87 19.67 12.23 20.03L13.7 21.5",
    "M13.41 5.57L7.56 11.43C6.46 12.52 6.46 14.29 7.56 15.39C8.65 16.48 10.42 16.48 11.52 15.39L17.37 9.53",
  ];
  var ICON_NAV_COSTS = ["M3 3v18h18", "M7 15l4-6 3 4 4-7"];
  var ICON_CHEVRONS_LEFT = ["M11 17l-5-5 5-5", "M18 17l-5-5 5-5"];
  var ICON_CHEVRON_DOWN = ["M6 9l6 6 6-6"];
  var ICON_SEARCH = ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.35-4.35"];

  var TABS = [
    { id: "overview", label: "Dashboard", group: "observe", icon: ICON_NAV_OVERVIEW },
    { id: "feedback", label: "Feedback", permission: "feedback.read", group: "observe", icon: ICON_NAV_FEEDBACK },
    { id: "costs", label: "Costs", permission: "audit.read", group: "observe", icon: ICON_NAV_COSTS },
    { id: "users", label: "Users", permission: "users.manage", group: "access", icon: ICON_NAV_USERS },
    { id: "keys", label: "API Keys", permission: "apikeys.manage", group: "access", icon: ICON_NAV_KEYS },
    { id: "prompts", label: "Personas", permission: "prompts.manage", group: "configure", icon: ICON_NAV_PERSONAS },
    { id: "adapters", label: "Adapters", permission: "adapters.manage", group: "configure", icon: ICON_NAV_ADAPTERS },
    { id: "settings", label: "Settings", permission: "config.manage", group: "configure", icon: ICON_NAV_SETTINGS },
    { id: "mcp", label: "MCP", permission: "config.manage", group: "system", icon: ICON_NAV_MCP },
    { id: "ops", label: "Ops", permission: "system.manage", group: "system", icon: ICON_NAV_OPS },
    { id: "audit", label: "Audit", permission: "audit.read", group: "system", icon: ICON_NAV_AUDIT },
  ];

  // Groups describe what each section lets you do, and label the current
  // location in the workbar eyebrow.
  var NAV_GROUPS = [
    { id: "observe", label: "Observe" },
    { id: "access", label: "Access" },
    { id: "configure", label: "Configure" },
    { id: "system", label: "System" },
  ];

  function tabById(id) {
    return TABS.filter(function (t) { return t.id === id; })[0] || null;
  }

  // The workbar repeats the rail icon of the selected tab, so the heading and
  // the nav item that lit it read as one object. Rebuilt on every tab switch
  // because the icon changes with the title.
  function fillWorkbarTitle(heading, tab) {
    clear(heading);
    if (tab && tab.icon) {
      heading.appendChild(el("span", { className: "workbar-title-icon", "aria-hidden": "true" }, svgIcon(tab.icon)));
    }
    heading.appendChild(el("span", null, tab ? tab.label : "Admin"));
  }

  // One refresh control across the panel: a circular arrow at the right of the
  // panel heading. The label has to name what gets refreshed, because unlike
  // the old text button the glyph cannot say it.
  function refreshButton(label, onClick) {
    var btn = el("button", {
      type: "button",
      className: "btn btn--neutral btn--icon",
      "aria-label": label,
      title: label,
    }, svgIcon(ICON_REFRESH));
    btn.addEventListener("click", onClick);
    return btn;
  }

  function userHasPermission(permission) {
    var permissions = (currentUser && currentUser.permissions) || [];
    return permissions.indexOf("*") !== -1 || permissions.indexOf(permission) !== -1;
  }

  // A tab with no `permission` is visible to anyone who can load the panel.
  function hasTabPermission(tab) {
    if (!tab.permission) return true;
    return userHasPermission(tab.permission);
  }

  function getVisibleTabs() {
    return TABS.filter(hasTabPermission);
  }

  function renderShell() {
    var app = document.getElementById("app");
    clear(app);
    var visibleTabs = getVisibleTabs();
    // Overview is visible to everyone but its content needs metrics.read;
    // don't land a user there when it would only show a permission notice.
    // This also covers the initial load, where activeTab defaults to
    // "overview" and is always in visibleTabs.
    var landable = visibleTabs.filter(function (t) {
      return t.id !== "overview" || userHasPermission("metrics.read");
    });
    var candidates = landable.length ? landable : visibleTabs;
    if (candidates.every(function (t) { return t.id !== activeTab; })) {
      activeTab = candidates.length ? candidates[0].id : "overview";
    }

    // Side rail: grouped vertical nav
    var nav = el("nav", { className: "rail-nav", role: "tablist", "aria-label": "Admin sections" });
    NAV_GROUPS.forEach(function (group) {
      var tabsInGroup = visibleTabs.filter(function (t) { return t.group === group.id; });
      if (!tabsInGroup.length) return;
      // role=presentation keeps the tabs as direct tablist children for AT
      // while still letting us group them visually.
      var section = el("div", { className: "rail-group", role: "presentation" },
        el("p", { className: "rail-group-label", "aria-hidden": "true" }, group.label)
      );
      tabsInGroup.forEach(function (t) {
        var isSelected = t.id === activeTab;
        var link = el("a", {
          id: "tab-" + t.id,
          role: "tab",
          href: "#",
          title: t.label,
          "aria-selected": String(isSelected),
          "aria-controls": "tab-content",
          tabindex: isSelected ? "0" : "-1",
          className: "rail-link" + (isSelected ? " active" : ""),
          dataset: { tab: t.id },
        },
          el("span", { className: "rail-link-icon" }, svgIcon(t.icon)),
          el("span", { className: "rail-link-label" }, t.label)
        );
        link.addEventListener("click", function (e) { e.preventDefault(); switchTab(t.id); });
        link.addEventListener("keydown", function (e) {
          var currentIndex = visibleTabs.findIndex(function (tab) { return tab.id === t.id; });
          if (e.key === "ArrowDown") {
            e.preventDefault();
            switchTab(visibleTabs[(currentIndex + 1) % visibleTabs.length].id);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            switchTab(visibleTabs[(currentIndex - 1 + visibleTabs.length) % visibleTabs.length].id);
          }
        });
        section.appendChild(link);
      });
      nav.appendChild(section);
    });

    var collapseBtn = el("button", {
      type: "button",
      className: "rail-collapse-btn",
      "aria-expanded": String(!railCollapsed),
    },
      el("span", { className: "rail-collapse-icon" }, svgIcon(ICON_CHEVRONS_LEFT)),
      el("span", { className: "rail-link-label" }, "Collapse")
    );
    collapseBtn.addEventListener("click", toggleRail);

    var rail = el("header", { className: "rail", role: "banner" },
      el("div", { className: "rail-brand" },
        el("a", { className: "rail-logo", href: "/admin", title: "ORBIT home" },
          el("img", {
            src: "/static/orbit-logo-dark.png",
            alt: "ORBIT home",
            className: "brand-logo",
          }),
          el("img", {
            src: "/static/favicon.svg",
            alt: "",
            className: "brand-mark",
          })
        ),
        serverVersion ? el("p", { className: "rail-version" }, "v" + serverVersion) : null
      ),
      nav,
      el("div", { className: "rail-footer" }, collapseBtn)
    );

    // Workbar: where you are, who you are
    var logoutBtn = el("button", { type: "button", className: "secondary workbar-logout" }, "Log out");
    logoutBtn.addEventListener("click", doLogout);

    var current = tabById(activeTab);
    var workbarTitle = el("h1", { className: "workbar-title", id: "workbar-title" });
    fillWorkbarTitle(workbarTitle, current);
    var workbar = el("div", { className: "workbar" },
      el("div", { className: "workbar-heading" },
        workbarTitle
      ),
      el("div", { className: "workbar-actions" },
        el("span", { className: "workbar-user" }, currentUser ? (currentUser.email || currentUser.username) : ""),
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

    var shell = el("div", {
      className: "app-shell" + (railCollapsed ? " rail-collapsed" : ""),
    }, rail, el("div", { className: "app-body" }, workbar, toastRegion, content));
    app.appendChild(shell);

    renderTab();
  }

  function toggleRail() {
    railCollapsed = !railCollapsed;
    writeStoredFlag("orbit.admin.railCollapsed", railCollapsed);
    var shell = document.querySelector(".app-shell");
    if (shell) shell.classList.toggle("rail-collapsed", railCollapsed);
    var btn = document.querySelector(".rail-collapse-btn");
    if (btn) btn.setAttribute("aria-expanded", String(!railCollapsed));
  }

  // Feature modules receive their dependencies explicitly so their state and
  // lifecycle remain isolated as the remaining tabs are extracted.
  var feedbackTab = createFeedbackTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    wrapTable: wrapTable,
    skeleton: skeleton,
    refreshButton: refreshButton,
    formatNum: formatNum,
    clampPercentage: clampPercentage,
    getActiveTab: function () { return activeTab; }
  });
  var costsTab = createCostsTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    skeleton: skeleton,
    refreshButton: refreshButton,
    formatNum: formatNum,
    chartOptions: feedbackChartOptions,
    renderMetricCard: renderMetricCard,
    getActiveTab: function () { return activeTab; }
  });
  var auditTab = createAuditTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    skeleton: skeleton,
    refreshButton: refreshButton,
    formatNum: formatNum,
    markSelectedRow: markSelectedRow
  });
  var overviewTab = createOverviewTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    formatNum: formatNum,
    clampPercentage: clampPercentage,
    userHasPermission: userHasPermission,
    createPaginator: createPaginator,
    createColumnSorter: createColumnSorter,
    withButton: withButton,
    itemsPerPage: ITEMS_PER_PAGE,
    getActiveTab: function () { return activeTab; }
  });
  var usersTab = createUsersTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    wrapTable: wrapTable,
    skeleton: skeleton,
    refreshButton: refreshButton,
    field: field,
    passwordField: passwordField,
    svgIcon: svgIcon,
    iconPlus: ICON_PLUS,
    iconPencil: ICON_PENCIL,
    iconSave: ICON_SAVE,
    iconX: ICON_X,
    roleDetails: ROLE_DETAILS,
    usernameMaxLength: USERNAME_MAX_LENGTH,
    passwordMaxLength: PASSWORD_MAX_LENGTH,
    createPaginator: createPaginator,
    createColumnSorter: createColumnSorter,
    itemsPerPage: ITEMS_PER_PAGE,
    markSelectedRow: markSelectedRow,
    syncVisibleSelection: syncVisibleSelection,
    syncBulkActionButton: syncBulkActionButton,
    withButton: withButton,
    confirmAction: confirmAction,
    requireTypedConfirmation: requireTypedConfirmation,
    showStatus: showStatus,
    showError: showError,
    showTableLoadError: showTableLoadError,
    validateUsername: validateUsername,
    validatePassword: validatePassword,
    bindValidationClear: bindValidationClear,
    getCurrentUser: function () { return currentUser; }
  });
  var apiKeysTab = createApiKeysTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    wrapTable: wrapTable,
    skeleton: skeleton,
    refreshButton: refreshButton,
    field: field,
    svgIcon: svgIcon,
    iconPlus: ICON_PLUS,
    iconEye: ICON_EYE,
    iconEyeOff: ICON_EYE_OFF,
    iconCopy: ICON_COPY,
    iconCheck: ICON_CHECK,
    iconSave: ICON_SAVE,
    iconX: ICON_X,
    createPaginator: createPaginator,
    createColumnSorter: createColumnSorter,
    itemsPerPage: ITEMS_PER_PAGE,
    markSelectedRow: markSelectedRow,
    syncVisibleSelection: syncVisibleSelection,
    syncBulkActionButton: syncBulkActionButton,
    withButton: withButton,
    confirmAction: confirmAction,
    requireTypedConfirmation: requireTypedConfirmation,
    showStatus: showStatus,
    showError: showError,
    showTableLoadError: showTableLoadError,
    bindValidationClear: bindValidationClear,
    setFieldReadOnly: setFieldReadOnly,
    characterCount: characterCount,
    createMarkdownPreview: createMarkdownPreview,
    copyTextToClipboard: copyTextToClipboard,
    maskSecret: maskSecret,
    promptIdentifier: promptIdentifier,
    keyPath: keyPath,
    fillPromptSelect: fillPromptSelect,
    getCachedAdapters: function () { return cachedAdapters; },
    getCachedPrompts: function () { return cachedPrompts; },
    getCachedApiKeyUsers: function () { return cachedApiKeyUsers; },
    getCachedKeys: function () { return cachedKeys; },
    setCachedKeys: function (keys) { cachedKeys = keys; },
    loadAdaptersAndPrompts: loadAdaptersAndPrompts
  });
  var promptsTab = createPromptsTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    wrapTable: wrapTable,
    skeleton: skeleton,
    refreshButton: refreshButton,
    field: field,
    svgIcon: svgIcon,
    iconPlus: ICON_PLUS,
    iconSave: ICON_SAVE,
    iconX: ICON_X,
    createPaginator: createPaginator,
    createColumnSorter: createColumnSorter,
    itemsPerPage: ITEMS_PER_PAGE,
    markSelectedRow: markSelectedRow,
    syncVisibleSelection: syncVisibleSelection,
    syncBulkActionButton: syncBulkActionButton,
    withButton: withButton,
    confirmAction: confirmAction,
    requireTypedConfirmation: requireTypedConfirmation,
    showStatus: showStatus,
    showTableLoadError: showTableLoadError,
    bindValidationClear: bindValidationClear,
    setFieldReadOnly: setFieldReadOnly,
    characterCount: characterCount,
    createMarkdownPreview: createMarkdownPreview,
    promptIdentifier: promptIdentifier,
    keyPath: keyPath,
    fillKeySelect: fillKeySelect,
    loadAvailableKeys: loadAvailableKeys,
    getCachedKeys: function () { return cachedKeys; },
    getCachedPrompts: function () { return cachedPrompts; },
    setCachedPrompts: function (prompts) { cachedPrompts = prompts; }
  });
  var opsTab = createOpsTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    confirmDialog: confirmDialog,
    requireTypedConfirmation: requireTypedConfirmation,
    showError: showError,
    showServerOverlay: showServerOverlay,
    getCurrentUser: function () { return currentUser; },
    getActiveTab: function () { return activeTab; }
  });
  var adaptersTab = createAdaptersTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    skeleton: skeleton,
    svgIcon: svgIcon,
    iconPlus: ICON_PLUS,
    iconSave: ICON_SAVE,
    iconRefresh: ICON_REFRESH,
    field: field,
    characterCount: characterCount,
    withButton: withButton,
    createPaginator: createPaginator,
    createColumnSorter: createColumnSorter,
    itemsPerPage: ITEMS_PER_PAGE,
    markSelectedRow: markSelectedRow,
    confirmAction: confirmAction,
    requireTypedConfirmation: requireTypedConfirmation,
    showError: showError,
    showStatus: showStatus,
    waitForAdminJob: waitForAdminJob,
    getActiveTab: function () { return activeTab; },
    getCachedAdapterCapabilities: function () { return cachedAdapterCapabilities; },
    loadAdapterCapabilities: loadAdapterCapabilities
  });
  var mcpTab = createMcpTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    skeleton: skeleton,
    refreshButton: refreshButton,
    withButton: withButton,
    confirmAction: confirmAction,
    showError: showError,
    showStatus: showStatus,
    getActiveTab: function () { return activeTab; }
  });

  var settingsTab = createSettingsTab({
    api: api,
    endpoints: ENDPOINTS,
    el: el,
    clear: clear,
    skeleton: skeleton,
    svgIcon: svgIcon,
    iconSave: ICON_SAVE,
    iconRefresh: ICON_REFRESH,
    iconChevronDown: ICON_CHEVRON_DOWN,
    iconSearch: ICON_SEARCH,
    iconX: ICON_X,
    confirmAction: confirmAction,
    showError: showError,
    showStatus: showStatus,
    getActiveTab: function () { return activeTab; }
  });

  function switchTab(id) {
    if (activeTab === "settings" && id !== "settings" && settingsTab.isDirty()) {
      confirmAction({
        title: "Unsaved Changes",
        message: "You have unsaved changes in this category. Discard them?",
        confirmLabel: "Discard",
        isDanger: true,
        onConfirm: function () {
          settingsTab.dispose();
          switchTab(id);
        }
      });
      return;
    }

    if (activeTab === "mcp" && id !== "mcp" && mcpTab.hasPendingEdits()) {
      confirmAction({
        title: "Unsaved Changes",
        message: "You have unsaved MCP changes. Discard them?",
        confirmLabel: "Discard",
        isDanger: true,
        onConfirm: function () {
          mcpTab.clearPendingEdits();
          switchTab(id);
        }
      });
      return;
    }

    // Disconnect monitoring when leaving overview
    if (activeTab === "overview" && id !== "overview") {
      overviewTab.dispose();
    }
    if (activeTab === "feedback" && id !== "feedback") {
      feedbackTab.dispose();
    }
    if (activeTab === "costs" && id !== "costs") {
      costsTab.dispose();
    }
    // Destroy adapter editor when leaving adapters tab
    if (activeTab === "adapters" && id !== "adapters") {
      adaptersTab.dispose();
    }
    // Destroy settings section editors when leaving settings tab
    if (activeTab === "settings" && id !== "settings") {
      settingsTab.dispose();
    }
    activeTab = id;
    document.querySelectorAll(".rail-link").forEach(function (b) {
      var isActive = b.dataset.tab === id;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-selected", String(isActive));
      b.setAttribute("tabindex", isActive ? "0" : "-1");
      if (isActive) b.focus();
    });
    var current = tabById(id);
    var title = document.getElementById("workbar-title");
    if (title) fillWorkbarTitle(title, current);
    var panel = document.getElementById("tab-content");
    if (panel) panel.setAttribute("aria-labelledby", "tab-" + id);
    renderTab();
  }

  function renderTab() {
    opsTab.dispose();
    var c = document.getElementById("tab-content");
    if (!c) return;
    clear(c);
    switch (activeTab) {
      case "overview": overviewTab.render(c); break;
      case "feedback": feedbackTab.render(c); break;
      case "users": usersTab.render(c); break;
      case "keys": apiKeysTab.render(c); break;
      case "prompts": promptsTab.render(c); break;
      case "adapters": adaptersTab.render(c); break;
      case "ops": opsTab.render(c); break;
      case "audit": auditTab.render(c); break;
      case "costs": costsTab.render(c); break;
      case "settings": settingsTab.render(c); break;
      case "mcp": mcpTab.render(c); break;
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
  // Shared numeric formatting helpers (used by several tabs)
  // ==================================================================

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
    try {
      cachedApiKeyUsers = await api("GET", ENDPOINTS.users);
    } catch (_) {
      cachedApiKeyUsers = [];
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

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  window.addEventListener("beforeunload", function () {
    overviewTab.dispose();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
