export function createOpsTab({
  api, endpoints, el, clear, confirmDialog, requireTypedConfirmation, showError, showServerOverlay,
  getCurrentUser, getActiveTab
}) {
  var opsLogPollTimer = null;

  function clearOpsLogPolling() {
    if (opsLogPollTimer) {
      clearTimeout(opsLogPollTimer);
      opsLogPollTimer = null;
    }
  }

  function render(container) {
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
            await api("POST", endpoints[action]);
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

    api("GET", endpoints.serverInfo)
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
            await api("POST", endpoints.restart);
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
            await api("POST", endpoints.shutdown);
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
    var currentUser = getCurrentUser();
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
        var result = await api("GET", endpoints.logsFiles);
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
          jumpBanner.textContent = pendingNewLines + " new line" + (pendingNewLines !== 1 ? "s" : "") + " below ↓";
          jumpBanner.classList.remove("hidden");
        }
      }
    }

    var logsInFlight = false;

    function scheduleLogRefresh() {
      clearOpsLogPolling();
      if (getActiveTab() !== "ops") return;
      if (document.hidden) return;
      opsLogPollTimer = setTimeout(function () {
        loadLogs(true);
      }, 3000);
    }

    async function loadLogs(silent) {
      if (logsInFlight) return;
      logsInFlight = true;
      try {
        var url = endpoints.logsTail + "?lines=500" + (selectedLogFile ? "&file=" + encodeURIComponent(selectedLogFile) : "");
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
      if (!document.hidden && getActiveTab() === "ops") {
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

  function dispose() {
    clearOpsLogPolling();
  }

  return { render, dispose };
}
