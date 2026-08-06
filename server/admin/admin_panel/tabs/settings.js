// TAB: Settings (Ace Editor — YAML, split into config.yaml sections)
// ==================================================================
export function createSettingsTab({
  api, endpoints, el, clear, skeleton, svgIcon, iconSave, iconRefresh, iconChevronDown, iconSearch, iconX,
  confirmAction, showError, showStatus, getActiveTab
}) {
  var settingsEditors = {}; // key -> { editor, original } for the selected section
  var selectedSettingsSection = null; // currently selected config.yaml top-level key
  var cachedSettingsSections = null; // [{key, line_count}, ...]
  var settingsContentCache = {}; // key -> raw section text, filled lazily to power search
  var collapsedGroups = {}; // group label -> true, persists across re-renders while the tab stays mounted
  var settingsSearchQuery = ""; // persists across re-renders so re-selecting a section keeps the filter

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
        var data = await api("GET", endpoints.configSections);
        cachedSettingsSections = data.sections || [];
      } catch (err) {
        showError("Failed to load config sections: " + err.message);
        cachedSettingsSections = [];
      }
      if (getActiveTab() === "settings") renderSettings(container);
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
    var searchWrap = el("div", { className: "settings-search" });
    var searchInput = el("input", {
      type: "search",
      className: "settings-search-input",
      placeholder: "Search settings…",
      "aria-label": "Search settings",
      value: settingsSearchQuery,
    });
    var searchStatus = el("p", { className: "settings-search-status", "aria-live": "polite" });
    searchWrap.appendChild(el("span", { className: "settings-search-icon", "aria-hidden": "true" }, svgIcon(iconSearch)));
    searchWrap.appendChild(searchInput);
    var searchClearBtn = el("button", {
      type: "button",
      className: "settings-search-clear",
      "aria-label": "Clear search",
      title: "Clear search",
      style: "display:none",
      onclick: function () { searchInput.value = ""; onSearchInput(); searchInput.focus(); }
    }, svgIcon(iconX));
    searchWrap.appendChild(searchClearBtn);
    navPanel.appendChild(searchWrap);
    navPanel.appendChild(searchStatus);
    var toggleAllBtn = el("button", {
      type: "button",
      className: "settings-nav-toggle-all",
      onclick: function () { toggleAllGroups(); }
    });
    navPanel.appendChild(toggleAllBtn);
    var nav = el("nav", { className: "settings-nav", "aria-label": "Settings sections" });
    var body = el("div", { className: "settings-detail" });
    navPanel.appendChild(nav);
    layout.appendChild(navPanel);
    layout.appendChild(body);
    wrap.appendChild(layout);

    // Every section's raw text, fetched once and reused so search can jump
    // straight to a match without waiting on a request per keystroke.
    function ensureContentCache() {
      var missing = knownKeys.filter(function (k) { return settingsContentCache[k] === undefined; });
      if (!missing.length) return Promise.resolve();
      return Promise.all(missing.map(function (k) {
        return api("GET", endpoints.configSections + "/" + encodeURIComponent(k))
          .then(function (data) { settingsContentCache[k] = data.content; })
          .catch(function () { settingsContentCache[k] = ""; });
      }));
    }

    function firstMatchingLine(content, query) {
      var lines = content.split("\n");
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].toLowerCase().indexOf(query) !== -1) {
          return { line: i + 1, text: lines[i].trim() };
        }
      }
      return null;
    }

    // While a search is active, every group renders fully expanded and only
    // keys with a title or content match are shown — collapsedGroups is left
    // untouched so clearing the search restores whatever the user had set.
    function computeSearchMatches(query) {
      var matches = {}; // key -> { line, text } | true (title-only match)
      knownKeys.forEach(function (key) {
        if (settingsSectionTitle(key).toLowerCase().indexOf(query) !== -1 || key.indexOf(query) !== -1) {
          matches[key] = true;
        }
      });
      knownKeys.forEach(function (key) {
        if (matches[key] === true) return;
        var hit = firstMatchingLine(settingsContentCache[key] || "", query);
        if (hit) matches[key] = hit;
      });
      return matches;
    }

    function syncSelectedSection() {
      nav.querySelectorAll(".settings-nav-item").forEach(function (item) {
        var isSelected = item.dataset.section === selectedSettingsSection;
        item.classList.toggle("is-selected", isSelected);
        item.setAttribute("aria-current", isSelected ? "page" : "false");
      });
    }

    function renderBody(key, jumpQuery) {
      clear(body);
      destroyAllSettingsEditors();
      body.appendChild(renderSectionBlock(key, jumpQuery));
      syncSelectedSection();
    }

    function selectSection(key, jumpQuery) {
      if (key === selectedSettingsSection) {
        if (jumpQuery) jumpToQueryInCurrentEditor(jumpQuery);
        return;
      }
      if (settingsEditorsAreDirty()) {
        confirmAction({
          title: "Unsaved Changes",
          message: "You have unsaved changes in this section. Discard them?",
          confirmLabel: "Discard",
          isDanger: true,
          onConfirm: function () {
            selectedSettingsSection = key;
            renderBody(key, jumpQuery);
          }
        });
        return;
      }
      selectedSettingsSection = key;
      renderBody(key, jumpQuery);
    }

    function jumpToQueryInCurrentEditor(query) {
      var state = settingsEditors[selectedSettingsSection];
      if (!state) return;
      state.editor.find(query, { wrap: true, caseSensitive: false, wholeWord: false });
      state.editor.focus();
    }

    function isGroupCollapsed(label) {
      // Groups start collapsed to keep the tree short; collapsedGroups only
      // ever records an explicit override once the user toggles one open.
      return collapsedGroups[label] !== false;
    }

    function toggleGroup(label) {
      collapsedGroups[label] = isGroupCollapsed(label) ? false : true;
      renderNav();
    }

    function toggleAllGroups() {
      // If any group is still collapsed, "expand all" wins first; only once
      // everything is already open does the button switch to collapsing.
      var anyCollapsed = groups.some(function (g) { return isGroupCollapsed(g.label); });
      groups.forEach(function (g) { collapsedGroups[g.label] = anyCollapsed ? false : true; });
      renderNav();
    }

    function renderNav() {
      clear(nav);
      var query = settingsSearchQuery.trim().toLowerCase();
      var isSearching = query.length > 0;
      var matches = isSearching ? computeSearchMatches(query) : null;

      toggleAllBtn.style.display = isSearching ? "none" : "";
      if (!isSearching) {
        var anyCollapsed = groups.some(function (g) { return isGroupCollapsed(g.label); });
        clear(toggleAllBtn);
        toggleAllBtn.classList.toggle("is-all-expanded", !anyCollapsed);
        toggleAllBtn.appendChild(el("span", { className: "settings-nav-toggle-all-chevron", "aria-hidden": "true" }, svgIcon(iconChevronDown)));
        toggleAllBtn.appendChild(el("span", null, anyCollapsed ? "Expand all" : "Collapse all"));
      }

      groups.forEach(function (group) {
        var visibleKeys = isSearching ? group.keys.filter(function (k) { return matches[k]; }) : group.keys;
        if (isSearching && !visibleKeys.length) return;

        var groupEl = el("div", { className: "settings-nav-group" });
        var isCollapsed = !isSearching && isGroupCollapsed(group.label);
        groupEl.classList.toggle("is-collapsed", isCollapsed);

        var header = el("button", {
          type: "button",
          className: "settings-nav-group-header",
          "aria-expanded": String(!isCollapsed),
          onclick: function () { toggleGroup(group.label); }
        },
          el("span", { className: "settings-nav-group-chevron", "aria-hidden": "true" }, svgIcon(iconChevronDown)),
          el("span", { className: "settings-nav-group-title" }, group.label)
        );
        groupEl.appendChild(header);

        var list = el("div", { className: "settings-nav-list" });
        visibleKeys.forEach(function (key) {
          var match = isSearching ? matches[key] : null;
          var item = el("button", {
            type: "button",
            className: "settings-nav-item",
            "data-section": key,
            "aria-current": "false",
            onclick: function () { selectSection(key, match && match.line ? query : null); }
          }, el("span", { className: "settings-nav-item__title" }, settingsSectionTitle(key)));
          if (match && match.line) {
            item.appendChild(el("span", { className: "settings-nav-item__match" },
              el("span", { className: "settings-nav-item__match-line" }, "L" + match.line), " " + match.text));
          }
          list.appendChild(item);
        });
        groupEl.appendChild(list);
        nav.appendChild(groupEl);
      });

      if (isSearching && !nav.children.length) {
        nav.appendChild(el("p", { className: "settings-search-empty" }, "No settings match “" + settingsSearchQuery.trim() + "”."));
      }
      syncSelectedSection();
    }

    var searchDebounceTimer = null;
    function onSearchInput() {
      settingsSearchQuery = searchInput.value;
      searchClearBtn.style.display = settingsSearchQuery ? "" : "none";
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      var query = settingsSearchQuery.trim();
      if (!query) {
        searchStatus.textContent = "";
        renderNav();
        return;
      }
      searchStatus.textContent = "Searching…";
      searchDebounceTimer = setTimeout(function () {
        ensureContentCache().then(function () {
          if (searchInput.value.trim() === query) {
            searchStatus.textContent = "";
            renderNav();
          }
        });
      }, 150);
    }
    searchInput.addEventListener("input", onSearchInput);
    searchInput.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape" && searchInput.value) {
        evt.stopPropagation();
        searchInput.value = "";
        onSearchInput();
      } else if (evt.key === "Enter") {
        var firstMatch = nav.querySelector(".settings-nav-item");
        if (firstMatch) firstMatch.click();
      }
    });

    searchClearBtn.style.display = settingsSearchQuery ? "" : "none";
    renderNav();

    function renderSectionBlock(key, jumpQuery) {
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
      }, svgIcon(iconSave));
      var reloadBtn = el("button", {
        className: "btn btn--neutral btn--icon",
        "aria-label": "Reload from disk",
        title: "Reload from disk",
      }, svgIcon(iconRefresh));
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

      var endpoint = endpoints.configSections + "/" + encodeURIComponent(key);

      async function loadContent() {
        try {
          var data = await api("GET", endpoint);
          if (!isCurrentEditor()) return;
          editorState.original = data.content;
          settingsContentCache[key] = data.content;
          editor.setValue(data.content, -1);
          editor.getSession().getUndoManager().reset();
          saveBtn.disabled = true;
          banner.style.display = "none";
          if (jumpQuery) {
            var queryToJumpTo = jumpQuery;
            jumpQuery = null;
            requestAnimationFrame(function () {
              if (isCurrentEditor()) editor.find(queryToJumpTo, { wrap: true, caseSensitive: false, wholeWord: false });
            });
          }
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
          settingsContentCache[key] = editorState.original;
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

  function isDirty() {
    return settingsEditorsAreDirty();
  }

  function dispose() {
    destroyAllSettingsEditors();
  }

  return { render: renderSettings, dispose: dispose, isDirty: isDirty };
}
