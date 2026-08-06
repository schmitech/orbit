import { ENDPOINTS, createApi } from "./admin_panel/core/api.js";
import { standardChartOptions as feedbackChartOptions } from "./admin_panel/core/charts.js";
import { clear, el, wrapTable } from "./admin_panel/core/dom.js";
import { renderMetricCard } from "./admin_panel/core/metrics.js";
import { createFeedbackTab } from "./admin_panel/tabs/feedback.js";
import { createCostsTab } from "./admin_panel/tabs/costs.js";
import { createAuditTab } from "./admin_panel/tabs/audit.js";
import { createOverviewTab } from "./admin_panel/tabs/overview.js";

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
  let selectedUser = null;
  let selectedKey = null;
  let selectedPrompt = null;
  let selectedAdapterEntry = null; // { name, filename, ... }
  let adapterEditor = null;        // Ace editor instance for Adapters tab
  let adapterOriginal = "";        // Dirty tracking baseline
  let cachedAdapterFiles = null;   // Cached adapter file listing
  let cachedAdapterSpecs = null;   // Adapter SDK families available for creation
  let adapterPreviewEditor = null; // Read-only Ace editor for the create preview
  let messageCounter = 0;
  let opsLogPollTimer = null;


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

    if (activeTab === "mcp" && id !== "mcp" && mcpHasPendingEdits()) {
      confirmAction({
        title: "Unsaved Changes",
        message: "You have unsaved MCP changes. Discard them?",
        confirmLabel: "Discard",
        isDanger: true,
        onConfirm: function () {
          mcpPending = {};
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
      if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
      if (adapterPreviewEditor) { adapterPreviewEditor.destroy(); adapterPreviewEditor = null; }
    }
    // Destroy settings section editors when leaving settings tab
    if (activeTab === "settings" && id !== "settings") {
      destroyAllSettingsEditors();
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
    clearOpsLogPolling();
    var c = document.getElementById("tab-content");
    if (!c) return;
    clear(c);
    switch (activeTab) {
      case "overview": overviewTab.render(c); break;
      case "feedback": feedbackTab.render(c); break;
      case "users": renderUsers(c); break;
      case "keys": renderKeys(c); break;
      case "prompts": renderPrompts(c); break;
      case "adapters": renderAdapters(c); break;
      case "ops": renderOps(c); break;
      case "audit": auditTab.render(c); break;
      case "costs": costsTab.render(c); break;
      case "settings": renderSettings(c); break;
      case "mcp": renderMcp(c); break;
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

  // ==================================================================
  // TAB: Users
  // ==================================================================
  async function renderUsers(container) {
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var accountPanel = el("div", { className: "panel account-panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var userSearchFilter = "";
    var userSearchInteracted = false;
    var allUsers = [];
    var userFilteredEmpty = false;
    var selectedUserIds = new Set();
    var tableWrap = el("div", null, skeleton());
    var searchInput = el("input", {
      type: "search",
      name: "user-search",
      value: "",
      maxlength: "64",
      placeholder: "Search users",
      "aria-label": "Search users",
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
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
          currentUserId: currentUser && currentUser.id,
          sorter: userSorter
        });
      }
    });
    var userSorter = createColumnSorter(userPaginator);

    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(accountPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    var usersRefreshBtn = refreshButton("Refresh the user list", function () { loadUsers({}); });
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
    var thead = el("thead", null, selection.sorter.headerRow([
      { attrs: { className: "selection-col" }, content: selectAllBox },
      { label: "Username", key: "username", sortValue: function (u) { return u.email || u.username; } },
      {
        label: "Role",
        key: "role",
        sortValue: function (u) {
          return (u.roles && u.roles.length ? u.roles : [u.role]).filter(Boolean).join(", ");
        },
      },
      { label: "Status", key: "status", sortValue: function (u) { return u.active !== false ? "Active" : "Inactive"; } },
    ]));
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
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var keySearchFilter = "";
    var selectedKeyIds = new Set();
    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    var keysRefreshBtn = refreshButton("Refresh the API key list", function () { loadKeys(); });
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
    var createAllowedUsersSelect = allowedUsersSelect();
    var createAllowedEmailsInput = el("input", { type: "text", placeholder: "alice@company.com, bob@company.com" });
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
      el("div", { className: "stack" }, field(
        "Restrict to users (optional)",
        createAllowedUsersSelect,
        "Leave empty to allow any client holding this key. Hold Ctrl/Cmd to select multiple."
      )),
      el("div", { className: "stack" }, field(
        "Pre-authorize email addresses (optional)", createAllowedEmailsInput,
        "Comma-separated emails for people who have not logged in yet."
      )),
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
          },
          sorter: keySorter
        }, loadKeys);
      }
    });
    var keySorter = createColumnSorter(keyPaginator);
    listPanel.appendChild(keyPaginator.getControlsEl());

    function hideKeyDetail() {
      clear(detailPanel);
      detailPanel.style.display = "none";
    }

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
        var selectedUserIds = Array.from(createAllowedUsersSelect.selectedOptions).map(function (o) { return o.value; });
        if (selectedUserIds.length) body.allowed_user_ids = selectedUserIds;
        var allowedEmails = parseAllowedEmails(createAllowedEmailsInput.value);
        if (allowedEmails === null) { showError("Enter valid comma-separated email addresses."); return; }
        if (allowedEmails.length) body.allowed_emails = allowedEmails;
        await api("POST", ENDPOINTS.apiKeys, body);
        clientInput.value = "";
        promptSelect.value = "";
        notesInput.value = "";
        Array.from(createAllowedUsersSelect.options).forEach(function (o) { o.selected = false; });
        createAllowedEmailsInput.value = "";
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
            detailPanel.style.display = "";
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
            hideKeyDetail();
          }
        } else {
          hideKeyDetail();
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
    try {
      cachedApiKeyUsers = await api("GET", ENDPOINTS.users);
    } catch (_) {
      cachedApiKeyUsers = [];
    }
  }

  function allowedUsersSelect(selectedIds) {
    var select = el("select", { multiple: "true", size: "5" });
    (cachedApiKeyUsers || []).forEach(function (u) {
      var label = u.email || u.username || u.id;
      if (u.provider) label += " (" + u.provider + ")";
      var opt = el("option", { value: u.id }, label);
      if (selectedIds && selectedIds.indexOf(u.id) !== -1) opt.selected = true;
      select.appendChild(opt);
    });
    return select;
  }

  function parseAllowedEmails(value) {
    var emails = (value || "").split(",").map(function (email) { return email.trim().toLowerCase(); }).filter(Boolean);
    var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emails.some(function (email) { return !emailPattern.test(email); })) return null;
    return emails.filter(function (email, index) { return emails.indexOf(email) === index; }).sort();
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
    var thead = el("thead", null, selection.sorter.headerRow([
      { attrs: { className: "selection-col" }, content: selectAllBox },
      { label: "Client", key: "client", sortValue: function (k) { return k.client_name || ""; } },
      { label: "Adapter", key: "adapter", sortValue: function (k) { return k.adapter_name || "default"; } },
      { label: "Persona", key: "persona", sortValue: function (k) { return k.system_prompt_name || "None"; } },
      { label: "Active", key: "active", sortValue: function (k) { return k.active !== false ? "Active" : "Inactive"; } },
    ]));
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
        rightPanel.style.display = "";
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
    panel.style.display = "";
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
    var editAllowedUsersSelect = allowedUsersSelect(key.allowed_user_ids || []);
    var editAllowedEmailsInput = el("input", { type: "text", value: (key.allowed_emails || []).join(", ") });
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
    var originalAllowedUserIds = (key.allowed_user_ids || []).slice().sort();
    var originalAllowedEmails = (key.allowed_emails || []).slice().sort();
    var editForm = el("div", { style: "display:none" },
      el("div", { className: "admin-create-form" },
        el("div", { className: "admin-create-form-grid api-key-create-grid" },
          field("Client", clientInput),
          field("Adapter", adapterSelect),
          field("Persona", promptSelect)
        ),
        el("div", { className: "stack" }, field("Notes", notesInput), notesCounter),
        el("div", { className: "stack" }, field(
          "Restrict to users (optional)",
          editAllowedUsersSelect,
          "Leave empty to allow any client holding this key. Hold Ctrl/Cmd to select multiple."
        )),
        el("div", { className: "stack" }, field(
          "Pre-authorize email addresses (optional)", editAllowedEmailsInput,
          "Comma-separated emails for people who have not logged in yet."
        ))
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
    function selectedAllowedUserIds() {
      return Array.from(editAllowedUsersSelect.selectedOptions).map(function (o) { return o.value; }).sort();
    }
    function keyDetailsChanged() {
      var selectedEmails = parseAllowedEmails(editAllowedEmailsInput.value);
      if (selectedEmails === null) return false;
      return clientInput.value.trim() !== originalClientName ||
        adapterSelect.value !== originalAdapterName ||
        (promptSelect.value || "") !== originalPromptId ||
        notesInput.value !== originalNotes ||
        JSON.stringify(selectedAllowedUserIds()) !== JSON.stringify(originalAllowedUserIds) ||
        JSON.stringify(selectedEmails) !== JSON.stringify(originalAllowedEmails);
    }
    function syncKeySaveState() {
      saveBtn.disabled = !keyDetailsChanged();
    }
    function setKeyEditMode(editing) {
      setFieldReadOnly(clientInput, editing);
      adapterSelect.disabled = !editing;
      promptSelect.disabled = !editing;
      setFieldReadOnly(notesInput, editing);
      editAllowedUsersSelect.disabled = !editing;
      editAllowedEmailsInput.disabled = !editing;
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
      Array.from(editAllowedUsersSelect.options).forEach(function (o) {
        o.selected = originalAllowedUserIds.indexOf(o.value) !== -1;
      });
      editAllowedEmailsInput.value = originalAllowedEmails.join(", ");
      setKeyEditMode(false);
    });
    clientInput.addEventListener("input", syncKeySaveState);
    adapterSelect.addEventListener("change", syncKeySaveState);
    promptSelect.addEventListener("change", syncKeySaveState);
    notesInput.addEventListener("input", syncKeySaveState);
    editAllowedUsersSelect.addEventListener("change", syncKeySaveState);
    editAllowedEmailsInput.addEventListener("input", syncKeySaveState);
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
        var allowedEmails = parseAllowedEmails(editAllowedEmailsInput.value);
        if (allowedEmails === null) { showError("Enter valid comma-separated email addresses."); return; }
        await api("PUT", keyPath(keyId), {
          client_name: clientName,
          adapter_name: adapterSelect.value,
          system_prompt_id: promptSelect.value || null,
          notes: notesInput.value.trim() || null,
          allowed_user_ids: selectedAllowedUserIds(),
          allowed_emails: allowedEmails
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

    var personasRefreshBtn = refreshButton("Refresh the persona list", function () { refreshPrompts(); });
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
          },
          sorter: promptSorter
        });
      }
    });
    var promptSorter = createColumnSorter(promptPaginator);
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
    var thead = el("thead", null, selection.sorter.headerRow([
      { attrs: { className: "selection-col" }, content: selectAllBox },
      { label: "ID", key: "id", attrs: { className: "persona-id-col" }, sortValue: promptIdentifier },
      { label: "Name", key: "name", sortValue: function (p) { return p.name || ""; } },
      { label: "Version", key: "version", sortValue: function (p) { return p.version || ""; } },
    ]));
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
    var pauseResumeBtn = el("button", { className: "secondary", type: "button" }, "Pause Server");
    var isPaused = false;

    function setPauseResumeUI(paused) {
      isPaused = paused;
      pauseResumeBtn.textContent = paused ? "Resume Server" : "Pause Server";
    }

    pauseResumeBtn.addEventListener("click", function () {
      var action = isPaused ? "resume" : "pause";
      confirmDialog(
        isPaused ? "Resume Server" : "Pause Server",
        isPaused
          ? "The server will resume accepting new chat requests."
          : "The server will reject new chat requests until resumed. The process stays running and existing connections are unaffected.",
        async function () {
          pauseResumeBtn.disabled = true;
          try {
            await api("POST", ENDPOINTS[action]);
            setPauseResumeUI(!isPaused);
          } catch (err) {
            showError("Failed to " + action + " server: " + err.message);
          } finally {
            pauseResumeBtn.disabled = false;
          }
        },
        isPaused ? "Resume" : "Pause",
        false
      );
    });

    api("GET", ENDPOINTS.serverInfo)
      .then(function (info) { setPauseResumeUI(info && info.status === "paused"); })
      .catch(function () {});

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

    actionBar.appendChild(pauseResumeBtn);
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

  async function loadAdapterSpecs() {
    try {
      var data = await api("GET", ENDPOINTS.adapterSpecs);
      cachedAdapterSpecs = data.specs || [];
    } catch (_) {
      cachedAdapterSpecs = [];
    }
    return cachedAdapterSpecs;
  }

  function renderAdapters(container) {
    clear(container);

    // Destroy previous editors
    if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
    if (adapterPreviewEditor) { adapterPreviewEditor.destroy(); adapterPreviewEditor = null; }

    // Lazy-load adapter file listing, capability metadata (needed to know which
    // adapters support template reload) and the SDK spec registry (create form)
    if (!cachedAdapterFiles || !cachedAdapterCapabilities || !cachedAdapterSpecs) {
      container.appendChild(skeleton());
      Promise.all([
        cachedAdapterFiles ? Promise.resolve(cachedAdapterFiles) : loadAdapterFiles(),
        cachedAdapterCapabilities ? Promise.resolve(cachedAdapterCapabilities) : loadAdapterCapabilities(),
        cachedAdapterSpecs ? Promise.resolve(cachedAdapterSpecs) : loadAdapterSpecs(),
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

    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create adapter",
    }, svgIcon(ICON_PLUS), el("span", null, "Create Adapter"));
    createLaunchBtn.addEventListener("click", function () { openAdapterCreatePanel(); });
    leftPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn));

    var table = el("table");
    // Filled in below, once the paginator the sorter drives exists.
    var thead = el("thead");
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

    // Reordering rebuilds the body, which discards the toggle that was just
    // activated. Put focus back on its replacement so keyboard use survives.
    function refocusAdapterToggle(name) {
      var toggles = tbody.querySelectorAll(".adapter-toggle");
      for (var i = 0; i < toggles.length; i++) {
        if (toggles[i].dataset.adapter === name) {
          toggles[i].focus();
          return;
        }
      }
      // The row crossed a page boundary and has no replacement here, so
      // fall back to the header that ordered it rather than dropping focus
      // to the document.
      var sortedHeader = thead.querySelector(".th-sort.is-sorted");
      if (sortedHeader) sortedHeader.focus();
    }

    function makeToggle(a) {
      var track = el("button", {
        type: "button",
        className: "adapter-toggle" + (a.enabled ? " on" : ""),
        "aria-label": (a.enabled ? "Disable" : "Enable") + " adapter " + a.name,
        "aria-pressed": String(a.enabled),
        dataset: { adapter: a.name },
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
            // Toggling changed the value the table is ordered by, so the
            // row has to move or the list is visibly out of order.
            if (adapterSorter.isSortedBy("enabled")) {
              adapterSorter.reapply();
              refocusAdapterToggle(a.name);
            }
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
    var adapterSorter = createColumnSorter(adapterPaginator);
    thead.appendChild(adapterSorter.headerRow([
      { label: "Name", key: "name", sortValue: function (a) { return a.name || ""; } },
      { label: "Type", key: "type", sortValue: function (a) { return a.adapter || a.type || ""; } },
      {
        label: "Enabled",
        key: "enabled",
        attrs: { style: "width:70px;text-align:center" },
        sortValue: function (a) { return a.enabled ? "Enabled" : "Disabled"; },
      },
    ]));
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

    // ----- Create panel: spec-driven adapter generator -----
    // The whole form is built from GET /admin/adapters/specs, so adapter
    // knowledge stays in the SDK spec registry and never leaks into this file.
    var createPanel = el("div", { className: "panel", style: "display:none" });
    container.insertBefore(createPanel, layout);

    var closeCreateBtn = el("button", { className: "secondary", type: "button" }, "Close");
    closeCreateBtn.addEventListener("click", function () { closeAdapterCreatePanel(); });
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New Adapter"),
      closeCreateBtn
    ));

    var specSelect = el("select", null);
    (cachedAdapterSpecs || []).forEach(function (s) {
      specSelect.appendChild(el("option", { value: s.key }, s.title));
    });
    var specHint = el("p", { className: "muted", style: "margin:0" }, "");
    var formGrid = el("div", { className: "admin-create-form-grid" });
    var createBanner = el("div", { className: "settings-banner", style: "display:none", role: "status" });
    var previewWrap = el("div", {
      className: "adapter-ace-wrap",
      id: "adapter-yaml-preview",
      style: "display:none"
    });

    var previewBtn = el("button", {
      className: "secondary",
      type: "button",
      "aria-controls": "adapter-yaml-preview",
      "aria-expanded": "false"
    }, "Preview YAML");
    var createBtn = el("button", { type: "button" }, "Create Adapter");

    createPanel.appendChild(el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid" }, field("Adapter family", specSelect)),
      specHint,
      formGrid,
      createBanner,
      previewWrap,
      el("div", { className: "admin-create-form-actions" }, previewBtn, createBtn)
    ));

    // field name -> { q, input }, rebuilt whenever the family changes
    var createInputs = {};

    function currentSpec() {
      return (cachedAdapterSpecs || []).find(function (s) { return s.key === specSelect.value; });
    }

    function defaultAsString(q, value) {
      if (value === null || value === undefined) return "";
      if (q.type === "list") return Array.isArray(value) ? value.join(", ") : String(value);
      return String(value);
    }

    function applyDefault(q, input, value) {
      if (q.type === "bool") {
        input.checked = !!value;
        input._appliedDefault = String(!!value);
      } else {
        input.value = defaultAsString(q, value);
        input._appliedDefault = input.value;
      }
    }

    function readAnswer(q, input) {
      if (q.type === "bool") return input.checked;
      var raw = (input.value || "").trim();
      if (q.type === "list") {
        return raw.split(",").map(function (s) { return s.trim(); }).filter(Boolean);
      }
      if (!raw) return null;
      if (q.type === "int") {
        var n = parseInt(raw, 10);
        return isNaN(n) ? null : n;
      }
      return raw;
    }

    function collectAdapterAnswers() {
      var answers = {};
      Object.keys(createInputs).forEach(function (name) {
        var entry = createInputs[name];
        answers[name] = readAnswer(entry.q, entry.input);
      });
      return answers;
    }

    function makeQuestionInput(q) {
      if (q.type === "bool") return el("input", { type: "checkbox" });
      if (q.choices) {
        var sel = el("select", null);
        q.choices.forEach(function (c) { sel.appendChild(el("option", { value: c }, c)); });
        return sel;
      }
      if (q.type === "int") {
        var num = el("input", { type: "number" });
        if (q.min_value !== null && q.min_value !== undefined) num.min = String(q.min_value);
        if (q.max_value !== null && q.max_value !== undefined) num.max = String(q.max_value);
        return num;
      }
      var input = el("input", { type: "text" });
      if (q.type === "list") {
        // One comma-separated box holds the whole list, so maxlength can only be a
        // coarse overall cap; the per-entry limit is enforced server-side.
        input.maxLength = q.max_items * (q.max_length + 2);
      } else if (q.max_length) {
        input.maxLength = q.max_length;
      }
      return input;
    }

    // Say what the bound is up front — a maxlength that silently stops accepting
    // keystrokes with no stated limit reads as a broken input.
    function questionHint(q) {
      var parts = [];
      if (q.help) parts.push(q.help);
      if (q.type === "list") {
        parts.push("Comma-separated, up to " + q.max_items + " entries of "
          + q.max_length + " characters.");
      } else if (q.type === "int" && q.min_value !== null && q.min_value !== undefined) {
        parts.push("Between " + q.min_value + " and " + q.max_value + ".");
      } else if (q.type === "str" && q.max_length) {
        parts.push("Max " + q.max_length + " characters.");
      }
      return parts.join(" ");
    }

    function adapterQuestionField(q, input, hint) {
      if (q.type !== "bool") {
        var control = field(q.prompt, input, hint);
        // A counter only earns its space on the fields long enough that you can
        // lose track; short identifiers just get the hint.
        if (q.type === "str" && q.max_length >= 200) {
          control.appendChild(characterCount(input, q.max_length));
        }
        return control;
      }

      // Boolean questions are a single control, so keep the label and checkbox
      // together instead of placing the control on its own line.
      var checkboxLabel = el("label", { className: "adapter-checkbox-field" },
        input,
        el("span", null, q.prompt)
      );
      if (!hint) return checkboxLabel;
      return el("div", { className: "adapter-checkbox-question" },
        checkboxLabel,
        el("span", { className: "muted" }, hint)
      );
    }

    // A variant switch re-defaults only the fields the user has not touched, so
    // picking "docx" after "pdf" renames the adapter but keeps your own edits.
    function applyVariantDefaults(variant) {
      var spec = currentSpec();
      if (!spec || !spec.variant_field) return;
      spec.questions.forEach(function (q) {
        if (q.field === spec.variant_field) return;
        var entry = createInputs[q.field];
        if (!entry) return;
        var current = q.type === "bool" ? String(entry.input.checked) : entry.input.value;
        if (current !== entry.input._appliedDefault) return; // user-edited, leave alone
        var defaults = q.variant_defaults || {};
        applyDefault(q, entry.input, Object.prototype.hasOwnProperty.call(defaults, variant)
          ? defaults[variant] : q.default);
      });
    }

    function buildAdapterCreateForm() {
      var spec = currentSpec();
      clear(formGrid);
      createInputs = {};
      hideCreatePreview();
      if (!spec) return;

      specHint.textContent = spec.description;

      // Ask the variant selector first so the remaining defaults reflect it.
      var ordered = spec.questions.slice();
      if (spec.variant_field) {
        ordered.sort(function (a, b) {
          return (a.field === spec.variant_field ? 0 : 1) - (b.field === spec.variant_field ? 0 : 1);
        });
      }

      var variant = spec.variant_field
        ? (spec.variants && spec.variants.length ? spec.variants[0] : null)
        : null;

      ordered.forEach(function (q) {
        var input = makeQuestionInput(q);
        createInputs[q.field] = { q: q, input: input };
        var initial = q.variant_defaults && variant !== null
          && Object.prototype.hasOwnProperty.call(q.variant_defaults, variant)
          ? q.variant_defaults[variant] : q.default;
        applyDefault(q, input, initial);
        if (spec.variant_field && q.field === spec.variant_field) {
          input.value = variant;
          input._appliedDefault = variant;
          input.addEventListener("change", function () { applyVariantDefaults(input.value); });
        }
        formGrid.appendChild(adapterQuestionField(q, input, questionHint(q)));
      });

    }

    function hideCreatePreview() {
      if (adapterPreviewEditor) { adapterPreviewEditor.destroy(); adapterPreviewEditor = null; }
      previewWrap.style.display = "none";
      previewBtn.textContent = "Preview YAML";
      previewBtn.setAttribute("aria-expanded", "false");
      createBanner.style.display = "none";
      clear(createBanner);
    }

    function showCreatePreview(yamlText, errors) {
      previewWrap.style.display = "";
      previewBtn.textContent = "Hide Preview";
      previewBtn.setAttribute("aria-expanded", "true");
      if (!adapterPreviewEditor) {
        ace.config.set("basePath", "/static");
        ace.config.set("modePath", "/static");
        ace.config.set("themePath", "/static");
        ace.config.set("workerPath", "/static");
        adapterPreviewEditor = ace.edit(previewWrap, {
          mode: "ace/mode/yaml",
          theme: "ace/theme/tomorrow",
          fontSize: 15,
          fontFamily: "var(--font-mono)",
          readOnly: true,
          showPrintMargin: false,
          tabSize: 2,
          useSoftTabs: true,
          showGutter: true,
        });
      }
      adapterPreviewEditor.setValue(yamlText, -1);

      clear(createBanner);
      if (errors && errors.length) {
        createBanner.style.display = "";
        createBanner.appendChild(el("strong", null, "Validation errors"));
        errors.forEach(function (e) { createBanner.appendChild(el("div", null, e)); });
      } else {
        createBanner.style.display = "none";
      }
    }

    previewBtn.addEventListener("click", function () {
      if (previewWrap.style.display !== "none") {
        hideCreatePreview();
        return;
      }
      var spec = currentSpec();
      if (!spec) return;
      withButton(previewBtn, async function () {
        var data;
        try {
          data = await api("POST", ENDPOINTS.adapterPreview, {
            spec: spec.key,
            answers: collectAdapterAnswers(),
          });
        } catch (err) {
          throw new Error("Preview failed: " + err.message);
        }
        showCreatePreview(data.yaml, data.errors);
      });
    });

    createBtn.addEventListener("click", function () {
      var spec = currentSpec();
      if (!spec) return;
      var answers = collectAdapterAnswers();
      if (!answers.name) { showError("An adapter name is required."); return; }
      withButton(createBtn, async function () {
        var data;
        try {
          data = await api("POST", ENDPOINTS.adapterCreate, { spec: spec.key, answers: answers });
        } catch (err) {
          throw new Error("Create failed: " + err.message);
        }
        await loadAdapterFiles();
        await loadAdapterCapabilities();
        closeAdapterCreatePanel();
        // Re-render so the new adapter appears in the (re-flattened) list, then
        // open it in the detail editor.
        selectedAdapterEntry = { name: data.name, filename: data.filename };
        renderAdapters(container);
        if (data.reload_error) showError(data.message);
        else showStatus(data.message);
      });
    });

    function openAdapterCreatePanel() {
      createPanel.style.display = "";
      buildAdapterCreateForm();
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function closeAdapterCreatePanel() {
      hideCreatePreview();
      createPanel.style.display = "none";
    }

    specSelect.addEventListener("change", buildAdapterCreateForm);

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
  // TAB: MCP (external Model Context Protocol servers and their tools)
  //
  // Master-detail. "Defaults" is pinned to the head of the server list
  // because it is what every server inherits from — selecting it edits the
  // mcp_clients-level block. Each server's settings row states its
  // provenance (inherited vs override) and lights its leading edge when it
  // departs from the default, reusing the panel accent already used across
  // this design system to mean "this is the thing you changed".
  // ==================================================================
  var mcpData = null;      // { enabled, defaults, servers, settings }
  var mcpTools = null;     // { available, servers: { name: {reachable, tools} } }
  var mcpSelected = null;  // server name, or MCP_DEFAULTS_KEY
  var mcpPending = {};     // unsaved edits for the current selection only

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
  // and drop the caret. Reset on every full render.
  var mcpDirtyListeners = [];

  function mcpSyncDirty() {
    mcpDirtyListeners.forEach(function (fn) { fn(); });
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

  async function renderMcp(container) {
    clear(container);

    if (!mcpData) {
      container.appendChild(skeleton());
      try {
        mcpData = await api("GET", ENDPOINTS.mcpServers);
      } catch (err) {
        clear(container);
        container.appendChild(el("div", { className: "panel empty-state" },
          el("strong", null, "Could not read the MCP configuration"),
          el("p", null, err.message)
        ));
        return;
      }
      if (activeTab === "mcp") renderMcp(container);
      return;
    }

    if (mcpSelected === null) {
      mcpSelected = MCP_DEFAULTS_KEY;
    }

    mcpDirtyListeners = [];

    var layout = el("div", { className: "mcp-layout" });
    container.appendChild(layout);

    var listSlot = mcpRenderList();
    layout.appendChild(listSlot);
    // `enabled` is the only pending edit the list reflects, so rebuild only
    // when it changes rather than on every keystroke. Focus lives in the
    // detail pane, so replacing the list is safe.
    var lastEnabled = mcpPending.enabled;
    mcpDirtyListeners.push(function () {
      if (mcpPending.enabled === lastEnabled) return;
      lastEnabled = mcpPending.enabled;
      var fresh = mcpRenderList();
      layout.replaceChild(fresh, listSlot);
      listSlot = fresh;
    });

    var detail = el("div", { className: "panel mcp-detail" });
    layout.appendChild(detail);
    mcpRenderDetail(detail);
  }

  function mcpRerender() {
    var c = document.getElementById("tab-content");
    if (c && activeTab === "mcp") renderMcp(c);
  }

  // ----- Server list (master) -----

  function mcpRenderList() {
    var panel = el("div", { className: "panel mcp-list-panel" });

    var header = el("div", { className: "panel-header-row" },
      el("h2", null, "MCP servers"),
      el("div", { className: "mcp-list-actions" },
        el("button", {
          type: "button", className: "btn btn--primary", onclick: function () {
            if (mcpHasPendingEdits()) {
              confirmAction({ title: "Unsaved Changes", message: "Discard changes and add a server?", confirmLabel: "Discard", isDanger: true,
                onConfirm: function () { mcpPending = {}; mcpSelected = MCP_CREATE_KEY; mcpRerender(); } });
              return;
            }
            mcpSelected = MCP_CREATE_KEY;
            mcpRerender();
          }
        }, "Add server"),
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

    // Reflect an unsaved enable/disable for whichever entry is selected.
    function pendingEnabled(key, saved) {
      return (mcpSelected === key && mcpPending.enabled != null)
        ? mcpPending.enabled : saved;
    }

    var globalEnabled = pendingEnabled(MCP_DEFAULTS_KEY, mcpData.enabled);
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
      var discovery = (mcpTools && mcpTools.servers && mcpTools.servers[server.name]) || null;
      var state = "off";
      var meta = "Disabled";
      if (pendingEnabled(server.name, server.enabled)) {
        if (!discovery) {
          state = "unknown";
          meta = "Not checked";
        } else if (discovery.reachable) {
          state = "up";
          meta = discovery.tools.length + (discovery.tools.length === 1 ? " tool" : " tools");
        } else {
          state = "down";
          meta = "Unreachable";
        }
      }
      list.appendChild(mcpListItem({
        key: server.name,
        name: server.name,
        transport: server.transport,
        meta: meta,
        state: state,
        overrides: Object.keys(server.overrides || {}).length,
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
    var metaParts = [];
    if (opts.transport) {
      metaParts.push(el("span", { className: "mcp-transport" }, opts.transport));
    }
    metaParts.push(el("span", null, opts.meta));
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
      if (mcpSelected === opts.key) return;
      if (mcpHasPendingEdits()) {
        confirmAction({
          title: "Unsaved Changes",
          message: "You have unsaved changes here. Discard them?",
          confirmLabel: "Discard",
          isDanger: true,
          onConfirm: function () {
            mcpPending = {};
            mcpSelected = opts.key;
            mcpRerender();
          }
        });
        return;
      }
      mcpSelected = opts.key;
      mcpRerender();
    });
    return item;
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
      var transport = el("select", { className: "mcp-text", "aria-label": "Transport" },
        el("option", { value: "http" }, "Streamable HTTP"),
        el("option", { value: "stdio" }, "Subprocess (stdio)")
      );
      transport.value = draft.transport;
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
          var res = await api("POST", ENDPOINTS.mcpServers, { name: draft.name, transport: draft.transport, connection: connection });
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
    mcpDirtyListeners.push(function () {
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
      mcpDirtyListeners.push(row.sync);
      ledger.appendChild(row);
    });
    detail.appendChild(ledger);

    detail.appendChild(mcpSaveRow(async function () {
      var body = { settings: {} };
      Object.keys(mcpPending).forEach(function (key) {
        if (key === "enabled") body.enabled = mcpPending[key];
        else body.settings[key] = mcpPending[key];
      });
      var res = await api("PATCH", ENDPOINTS.mcpDefaults, body);
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
                var res = await api("DELETE", ENDPOINTS.mcpServers + "/" + encodeURIComponent(server.name));
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
        mcpDirtyListeners.push(function () {
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
        mcpDirtyListeners.push(function () {
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
    var toolsHeader = el("div", { className: "panel-header-row mcp-tools-header" },
      el("h3", null, "Tools"),
      el("button", {
        type: "button",
        className: "btn btn--neutral mcp-test-btn",
        onclick: function (e) {
          var btn = e.currentTarget;
          withButton(btn, async function () {
            mcpTools = await api("GET", ENDPOINTS.mcpTools);
            mcpRerender();
          });
        }
      }, "Test connection")
    );
    detail.appendChild(toolsHeader);
    detail.appendChild(mcpRenderTools(server, enabled));

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
    mcpDirtyListeners.push(syncSummary);

    detail.appendChild(el("div", { className: "panel-header-row mcp-settings-header" },
      el("h3", null, "Settings"),
      summary
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
      mcpDirtyListeners.push(row.sync);
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
        ENDPOINTS.mcpServers + "/" + encodeURIComponent(server.name),
        body
      );
      mcpPending = {};
      mcpData = null;
      mcpTools = null;
      showStatus(res.message || "Saved.");
      mcpRerender();
    }));
  }

  function mcpRenderTools(server, enabled) {
    if (!enabled) {
      return el("p", { className: "muted mcp-tools-empty" },
        "This server is disabled, so none of its tools reach the model."
      );
    }
    if (!mcpTools) {
      return el("p", { className: "muted mcp-tools-empty" },
        "Select Test connection to dial this server and list what it exposes."
      );
    }
    if (!mcpTools.available) {
      return el("p", { className: "muted mcp-tools-empty" }, mcpTools.reason);
    }
    var discovery = (mcpTools.servers || {})[server.name];
    if (!discovery) {
      return el("p", { className: "muted mcp-tools-empty" },
        "This server was added since tools were last discovered. Select Test connection."
      );
    }
    if (!discovery.reachable) {
      return el("div", { className: "mcp-unreachable" },
        el("strong", null, "Could not reach this server"),
        el("p", null,
          server.transport === "stdio"
            ? "Check the command runs and is on PATH. Startup logs record the underlying error."
            : "Check the URL is reachable and required headers are set. Startup logs record the underlying error."
        )
      );
    }
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
        provenance.appendChild(el("span", null, "override"));
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

  // ==================================================================
  // TAB: Settings (Ace Editor — YAML, split into config.yaml sections)
  // ==================================================================
  var settingsEditors = {}; // key -> { editor, original } for the selected section
  var selectedSettingsSection = null; // currently selected config.yaml top-level key
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

    var layout = el("div", { className: "settings-layout" });
    var navPanel = el("aside", { className: "settings-nav-panel" });
    var nav = el("nav", { className: "settings-nav", "aria-label": "Settings sections" });
    var body = el("div", { className: "settings-detail" });
    navPanel.appendChild(nav);
    layout.appendChild(navPanel);
    layout.appendChild(body);
    wrap.appendChild(layout);

    function syncSelectedSection() {
      nav.querySelectorAll(".settings-nav-item").forEach(function (item) {
        var isSelected = item.dataset.section === selectedSettingsSection;
        item.classList.toggle("is-selected", isSelected);
        item.setAttribute("aria-current", isSelected ? "page" : "false");
      });
    }

    function renderBody(key) {
      clear(body);
      destroyAllSettingsEditors();
      body.appendChild(renderSectionBlock(key));
      syncSelectedSection();
    }

    function selectSection(key) {
      if (key === selectedSettingsSection) return;
      if (settingsEditorsAreDirty()) {
        confirmAction({
          title: "Unsaved Changes",
          message: "You have unsaved changes in this section. Discard them?",
          confirmLabel: "Discard",
          isDanger: true,
          onConfirm: function () {
            selectedSettingsSection = key;
            renderBody(key);
          }
        });
        return;
      }
      selectedSettingsSection = key;
      renderBody(key);
    }

    groups.forEach(function (group) {
      var groupEl = el("div", { className: "settings-nav-group" });
      groupEl.appendChild(el("h3", { className: "settings-nav-group-title" }, group.label));
      var list = el("div", { className: "settings-nav-list" });
      group.keys.forEach(function (key) {
        var item = el("button", {
          type: "button",
          className: "settings-nav-item",
          "data-section": key,
          "aria-current": "false",
          onclick: function () { selectSection(key); }
        }, el("span", { className: "settings-nav-item__title" }, settingsSectionTitle(key)));
        list.appendChild(item);
      });
      groupEl.appendChild(list);
      nav.appendChild(groupEl);
    });

    function renderSectionBlock(key) {
      var titleText = settingsSectionTitle(key);

      var block = el("div", { className: "panel settings-section-block" });

      var headerRow = el("div", { style: "display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-2)" });
      headerRow.appendChild(el("h3", { style: "margin:0" }, titleText));
      block.appendChild(headerRow);

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

    if (!selectedSettingsSection || knownKeys.indexOf(selectedSettingsSection) === -1) {
      // `knownKeys` contains every eligible section, unlike an individual
      // group which may be empty after future grouping changes.
      selectedSettingsSection = knownKeys[0];
    }
    renderBody(selectedSettingsSection);
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
