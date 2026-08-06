// TAB: Settings (Ace Editor — YAML, split into config.yaml sections)
// ==================================================================
export function createSettingsTab({
  api, endpoints, el, clear, skeleton, svgIcon, iconSave, iconRefresh,
  confirmAction, showError, showStatus, getActiveTab
}) {
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

  function isDirty() {
    return settingsEditorsAreDirty();
  }

  function dispose() {
    destroyAllSettingsEditors();
  }

  return { render: renderSettings, dispose: dispose, isDirty: isDirty };
}
