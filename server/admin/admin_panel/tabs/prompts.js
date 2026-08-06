export function createPromptsTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton, field,
  svgIcon, iconPlus, iconSave, iconX,
  createPaginator, createColumnSorter, itemsPerPage, markSelectedRow, syncVisibleSelection,
  syncBulkActionButton, withButton, confirmAction, requireTypedConfirmation, showStatus,
  showTableLoadError, bindValidationClear, setFieldReadOnly,
  characterCount, createMarkdownPreview, promptIdentifier,
  keyPath, fillKeySelect, loadAvailableKeys,
  getCachedKeys, getCachedPrompts, setCachedPrompts
}) {
  let selectedPrompt = null;

  async function render(container) {
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

    fillCreatePersonaKeySelect(getCachedKeys());
    if (!getCachedKeys()) {
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
    }, svgIcon(iconPlus), el("span", null, "Create Persona"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));

    var tableWrap = el("div", null, skeleton());
    listPanel.appendChild(tableWrap);

    var promptFilteredEmpty = false;
    var promptPaginator = createPaginator({
      pageSize: itemsPerPage,
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
        var createdPrompt = await api("POST", endpoints.prompts, { name: n, prompt: t, version: versionInput.value.trim() || "1.0" });
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
            await api("DELETE", endpoints.prompts + "/" + encodeURIComponent(ids[i]));
          }
          ids.forEach(function (id) { selectedPromptIds.delete(id); });
          if (selectedPrompt && ids.indexOf(promptIdentifier(selectedPrompt)) !== -1) selectedPrompt = null;
          showStatus(ids.length + " persona" + (ids.length === 1 ? "" : "s") + " deleted");
          await refreshPrompts();
        }
      });
    });

    function applyPromptFilter() {
      var prompts = getCachedPrompts() || [];
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
        var prompts = await api("GET", endpoints.prompts);
        if (preferredPrompt && promptIdentifier(preferredPrompt)) {
          prompts = (prompts || []).map(function (prompt) {
            return promptIdentifier(prompt) === promptIdentifier(preferredPrompt)
              ? Object.assign({}, prompt, preferredPrompt)
              : prompt;
          });
        }
        setCachedPrompts(prompts);
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
    }, svgIcon(iconSave));
    saveBtn.style.display = "none";
    saveBtn.addEventListener("click", function () {
      if (saveBtn.disabled) return;
      withButton(saveBtn, async function () {
        var savedPrompt = await api("PUT", endpoints.prompts + "/" + encodeURIComponent(promptId), {
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
    }, svgIcon(iconX));
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
    var cachedKeys = getCachedKeys();
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
          await api("DELETE", endpoints.prompts + "/" + encodeURIComponent(promptId));
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

  return { render };
}
