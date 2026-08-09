export function createApiKeysTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton, field,
  svgIcon, iconPlus, iconEye, iconEyeOff, iconCopy, iconCheck, iconSave, iconX,
  createPaginator, createColumnSorter, itemsPerPage, markSelectedRow, syncVisibleSelection,
  syncBulkActionButton, withButton, confirmAction, requireTypedConfirmation, showStatus,
  showError, showTableLoadError, bindValidationClear, setFieldReadOnly,
  characterCount, createMarkdownPreview, copyTextToClipboard, maskSecret, promptIdentifier,
  keyPath, fillPromptSelect,
  getCachedAdapters, getCachedPrompts, getCachedApiKeyUsers,
  getCachedKeys, setCachedKeys,
  loadAdaptersAndPrompts
}) {
  let selectedKey = null;

  async function render(container) {
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
    var cachedAdapters = getCachedAdapters();
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
    var cachedPrompts = getCachedPrompts();
    if (cachedPrompts) {
      cachedPrompts.forEach(function (p) {
        promptSelect.appendChild(el("option", { value: promptIdentifier(p) }, p.name + " (v" + (p.version || "1.0") + ")"));
      });
    }
    var notesInput = el("textarea", { rows: "4", maxlength: "2000" });
    var notesCounter = characterCount(notesInput, 2000);
    var createAllowedUsersSelect = allowedUsersSelect();
    var createClearAllowedUsersBtn = clearAllowedUsersButton(createAllowedUsersSelect);
    var createAllowedEmailsInput = el("input", { type: "text", maxlength: "2000", placeholder: "alice@company.com, bob@company.com" });
    var createAllowedEmailsCounter = characterCount(createAllowedEmailsInput, 2000);
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
      el("div", { className: "stack" },
        field(
          "Restrict to users (optional)",
          createAllowedUsersSelect,
          "No users selected: any client holding this key can use it. Select one or more users to restrict access. Hold Ctrl/Cmd to select multiple."
        ),
        createClearAllowedUsersBtn
      ),
      el("div", { className: "stack" }, field(
        "Pre-authorize email addresses (optional)", createAllowedEmailsInput,
        "Comma-separated emails for people who have not logged in yet."
      ), createAllowedEmailsCounter),
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
    }, svgIcon(iconPlus), el("span", null, "Create API Key"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));

    var tableWrap = el("div", null, skeleton());
    listPanel.appendChild(tableWrap);

    var keyFilteredEmpty = false;
    var keyPaginator = createPaginator({
      pageSize: itemsPerPage,
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
        await api("POST", endpoints.apiKeys, body);
        clientInput.value = "";
        promptSelect.value = "";
        notesInput.value = "";
        Array.from(createAllowedUsersSelect.options).forEach(function (o) { o.selected = false; });
        createClearAllowedUsersBtn.sync();
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
      var keys = getCachedKeys() || [];
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
        var keys = await api("GET", endpoints.apiKeys);
        setCachedKeys(keys);
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
                loadKeys();
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

  function allowedUsersSelect(selectedIds) {
    var select = el("select", { className: "api-key-allowed-users-select", multiple: "true", size: "5" });
    (getCachedApiKeyUsers() || []).forEach(function (u) {
      var label = u.email || u.username || u.id;
      if (u.provider) label += " (" + u.provider + ")";
      var opt = el("option", { value: u.id }, label);
      if (selectedIds && selectedIds.indexOf(u.id) !== -1) opt.selected = true;
      select.appendChild(opt);
    });
    return select;
  }

  function clearAllowedUsersButton(select) {
    var button = el("button", { className: "secondary api-key-clear-users-btn", type: "button" }, "Clear selection");
    function sync() {
      button.disabled = select.disabled || !Array.from(select.options).some(function (option) {
        return option.selected;
      });
    }
    button.addEventListener("click", function () {
      Array.from(select.options).forEach(function (option) { option.selected = false; });
      select.dispatchEvent(new Event("change", { bubbles: true }));
      select.focus();
      sync();
    });
    select.addEventListener("change", sync);
    button.sync = sync;
    sync();
    return button;
  }

  function parseAllowedEmails(value) {
    var emails = (value || "").split(",").map(function (email) { return email.trim().toLowerCase(); }).filter(Boolean);
    var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (emails.some(function (email) { return !emailPattern.test(email); })) return null;
    return emails.filter(function (email, index) { return emails.indexOf(email) === index; }).sort();
  }

  async function loadKeyDetail(keyId) {
    return api("GET", keyPath(keyId, "/detail"));
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
    revealBtn.appendChild(svgIcon(iconEye));
    revealBtn.addEventListener("click", function () {
      revealSecret = !revealSecret;
      keyCode.textContent = revealSecret ? keyVal : maskSecret(keyVal);
      revealBtn.setAttribute("aria-label", revealSecret ? "Hide API key" : "Show API key");
      revealBtn.setAttribute("title", revealSecret ? "Hide API key" : "Show API key");
      revealBtn.innerHTML = "";
      revealBtn.appendChild(svgIcon(revealSecret ? iconEyeOff : iconEye));
    });
    var copyBtn = el("button", {
      type: "button",
      className: "copy-btn",
      "aria-label": "Copy API key",
      title: "Copy API key",
    });
    copyBtn.appendChild(svgIcon(iconCopy));
    copyBtn.addEventListener("click", function () {
      copyTextToClipboard(keyVal).then(function () {
        copyBtn.innerHTML = "";
        copyBtn.appendChild(svgIcon(iconCheck));
        setTimeout(function () {
          copyBtn.innerHTML = "";
          copyBtn.appendChild(svgIcon(iconCopy));
        }, 1500);
      }).catch(function (err) {
        showError(err && err.message ? err.message : "Unable to copy API key");
      });
    });
    var keyField = el("div", { className: "secret-field" }, keyCode, revealBtn, copyBtn);
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
    var renameInput = el("input", {
      type: "text", maxlength: "100", placeholder: "New key value", "aria-label": "New key value"
    });
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
    var keyControls = el("div", { className: "api-key-secret-controls" },
      keyField,
      el("div", { className: "api-key-secret-actions" },
        testBtn,
        el("div", { className: "api-key-rename-control" }, renameInput, renameBtn)
      ),
      testResult
    );
    var notesInput = el("textarea", { rows: "4", maxlength: "2000" }, key.notes || "");
    var notesCounter = characterCount(notesInput, 2000);
    var notesPreview = createMarkdownPreview(notesInput);

    var summary = el("div", { className: "key-summary" },
      el("div", { className: "key-summary-key-row" }, el("strong", null, "Key:"), keyControls),
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
    var cachedAdapters = getCachedAdapters();
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
    fillPromptSelect(promptSelect, getCachedPrompts(), key.system_prompt_id);
    var editAllowedUsersSelect = allowedUsersSelect(key.allowed_user_ids || []);
    var editClearAllowedUsersBtn = clearAllowedUsersButton(editAllowedUsersSelect);
    var editAllowedEmailsInput = el("input", { type: "text", maxlength: "2000", value: (key.allowed_emails || []).join(", ") });
    var editAllowedEmailsCounter = characterCount(editAllowedEmailsInput, 2000);
    var saveBtn = el("button", {
      type: "button",
      className: "btn btn--primary",
      "aria-label": "Save details",
      title: "Save details",
    }, svgIcon(iconSave), "Save");
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
        el("div", { className: "stack" },
          field(
            "Restrict to users (optional)",
            editAllowedUsersSelect,
            "No users selected: any client holding this key can use it. Select one or more users to restrict access. Hold Ctrl/Cmd to select multiple."
          ),
          editClearAllowedUsersBtn
        ),
        el("div", { className: "stack" }, field(
          "Pre-authorize email addresses (optional)", editAllowedEmailsInput,
          "Comma-separated emails for people who have not logged in yet."
        ), editAllowedEmailsCounter)
      )
    );
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Details");
    var cancelBtn = el("button", {
      className: "secondary",
      type: "button",
      style: "display:none",
      "aria-label": "Cancel editing details",
      title: "Cancel editing details",
    }, svgIcon(iconX), "Cancel");
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
      editClearAllowedUsersBtn.sync();
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
      // The preview renders from input events. Resetting textarea.value alone
      // leaves the last unsaved preview visible after cancel.
      notesInput.dispatchEvent(new Event("input"));
      Array.from(editAllowedUsersSelect.options).forEach(function (o) {
        o.selected = originalAllowedUserIds.indexOf(o.value) !== -1;
      });
      editClearAllowedUsersBtn.sync();
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
      editForm,
      el("div", { className: "inline-form detail-action-row api-key-edit-actions" }, editToggle, cancelBtn, saveBtn)
    ));
    setKeyEditMode(false);

    // Quota controls are relevant only while server-side throttling is active.
    // Load them automatically so managing a key does not require a second step.
    if (key.quota_available) {
      var quotaSection = el("div", { className: "api-key-quota-section" }, el("h3", null, "Quota Management"));
      var quotaWrap = el("div", { className: "quota-section" },
        el("p", { className: "muted" }, "Loading quota settings…")
      );
      quotaSection.appendChild(quotaWrap);
      panel.appendChild(quotaSection);
      api("GET", keyPath(keyId, "/quota")).then(function (quota) {
        renderQuotaDetail(quotaWrap, keyId, quota);
      }).catch(function (err) {
        quotaSection.remove();
        showError(err.message);
      });
    }

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
    var info = el("div", { className: "info-grid quota-info-grid" },
      infoRow("Daily Used", usage.daily_used != null ? usage.daily_used : "N/A"),
      infoRow("Daily Limit", config.daily_limit != null ? config.daily_limit : "Unlimited"),
      infoRow("Daily Remaining", quota.daily_remaining != null ? quota.daily_remaining : "N/A"),
      infoRow("Monthly Used", usage.monthly_used != null ? usage.monthly_used : "N/A"),
      infoRow("Monthly Limit", config.monthly_limit != null ? config.monthly_limit : "Unlimited"),
      infoRow("Monthly Remaining", quota.monthly_remaining != null ? quota.monthly_remaining : "N/A"),
      infoRow("Throttle", config.throttle_enabled ? "Enabled (priority " + (config.throttle_priority || 5) + ")" : "Disabled")
    );
    wrap.appendChild(info);
    var dailyLimitValue = info.children[1].querySelector(".info-value");
    var monthlyLimitValue = info.children[4].querySelector(".info-value");
    var throttleValue = info.children[6].querySelector(".info-value");

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
    var cancelBtn = el("button", { className: "secondary", type: "button", style: "display:none" },
      svgIcon(iconX), "Cancel");

    var originalDailyLimit = config.daily_limit != null ? String(config.daily_limit) : "";
    var originalMonthlyLimit = config.monthly_limit != null ? String(config.monthly_limit) : "";
    var originalThrottleEnabled = !!config.throttle_enabled;
    var originalThrottlePriority = String(config.throttle_priority || 5);
    var dailyInput = el("input", { className: "quota-inline-number", type: "number", min: "0", step: "1", placeholder: "Unlimited", value: originalDailyLimit });
    var monthlyInput = el("input", { className: "quota-inline-number", type: "number", min: "0", step: "1", placeholder: "Unlimited", value: originalMonthlyLimit });
    var throttleCheck = el("input", { type: "checkbox" });
    throttleCheck.checked = originalThrottleEnabled;
    var priorityInput = el("input", { type: "range", min: "1", max: "10", value: originalThrottlePriority });
    var priorityLabel = el("span", { className: "quota-priority-label" }, "Priority " + originalThrottlePriority);
    priorityInput.addEventListener("input", function () { priorityLabel.textContent = "Priority " + priorityInput.value; });

    var saveBtn = el("button", {
      type: "button",
      className: "btn btn--primary",
      "aria-label": "Save quota",
      title: "Save quota",
    }, svgIcon(iconSave), "Save");
    saveBtn.style.display = "none";
    function quotaChanged() {
      return dailyInput.value !== originalDailyLimit ||
        monthlyInput.value !== originalMonthlyLimit ||
        throttleCheck.checked !== originalThrottleEnabled ||
        priorityInput.value !== originalThrottlePriority;
    }
    function syncQuotaSaveState() {
      saveBtn.disabled = !quotaChanged();
    }
    [dailyInput, monthlyInput, priorityInput].forEach(function (input) {
      input.addEventListener("input", syncQuotaSaveState);
    });
    throttleCheck.addEventListener("change", syncQuotaSaveState);
    saveBtn.addEventListener("click", function () {
      withButton(saveBtn, async function () {
        var body = {
          throttle_enabled: throttleCheck.checked,
          throttle_priority: parseInt(priorityInput.value),
        };
        if (dailyInput.value !== "") body.daily_limit = parseInt(dailyInput.value);
        else body.daily_limit = null;
        if (monthlyInput.value !== "") body.monthly_limit = parseInt(monthlyInput.value);
        else body.monthly_limit = null;
        await api("PUT", keyPath(keyId, "/quota"), body);
        var updated = await api("GET", keyPath(keyId, "/quota"));
        renderQuotaDetail(wrap, keyId, updated);
      }, "Quota updated");
    });

    function showQuotaSummary(editing) {
      [dailyLimitValue, monthlyLimitValue, throttleValue].forEach(function (value) {
        value.classList.toggle("quota-inline-value", editing);
        clear(value);
      });
      if (editing) {
        dailyLimitValue.appendChild(dailyInput);
        monthlyLimitValue.appendChild(monthlyInput);
        throttleValue.appendChild(el("label", { className: "check-row quota-inline-toggle" }, throttleCheck, "Enabled"));
        throttleValue.appendChild(el("div", { className: "quota-priority-control quota-priority-inline" }, priorityLabel, priorityInput));
        return;
      }
      dailyLimitValue.textContent = originalDailyLimit || "Unlimited";
      monthlyLimitValue.textContent = originalMonthlyLimit || "Unlimited";
      throttleValue.textContent = originalThrottleEnabled
        ? "Enabled (priority " + originalThrottlePriority + ")"
        : "Disabled";
    }

    editToggle.addEventListener("click", function () {
      showQuotaSummary(true);
      editToggle.style.display = "none";
      cancelBtn.style.display = "inline-flex";
      saveBtn.style.display = "inline-flex";
      quotaEditActions.style.display = "flex";
      syncQuotaSaveState();
    });
    cancelBtn.addEventListener("click", function () {
      dailyInput.value = originalDailyLimit;
      monthlyInput.value = originalMonthlyLimit;
      throttleCheck.checked = originalThrottleEnabled;
      priorityInput.value = originalThrottlePriority;
      priorityLabel.textContent = "Priority " + originalThrottlePriority;
      showQuotaSummary(false);
      editToggle.style.display = "inline-flex";
      cancelBtn.style.display = "none";
      saveBtn.style.display = "none";
      quotaEditActions.style.display = "none";
      syncQuotaSaveState();
    });

    resetRow.insertBefore(editToggle, resetRow.firstChild);
    var quotaEditActions = el("div", { className: "inline-form quota-edit-actions", style: "display:none" }, cancelBtn, saveBtn);
    wrap.appendChild(quotaEditActions);
  }

  function infoRow(label, value) {
    return el("div", { className: "info-row" },
      el("span", { className: "info-label" }, label),
      el("span", { className: "info-value" }, String(value))
    );
  }

  return { render };
}
