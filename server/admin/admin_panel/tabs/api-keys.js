// Fallback used only when a server response omits `expiration_warning_days`
// (e.g. an older server). The real threshold always comes from the server.
var DEFAULT_EXPIRATION_WARNING_DAYS = 14;

// Matches the server's expiration_justification max_length (server/models/schema.py).
var MAX_JUSTIFICATION_LENGTH = 1000;

// Sanity bound for the custom-expiration input only (keeps the picker from
// accepting nonsense like a 5-digit year); the server remains the sole
// authority on the actual configured maximum lifetime.
var MAX_EXPIRATION_INPUT_YEARS = 100;

// Replaces the browser's native datetime-local widget (whose calendar has
// no visible way to close after picking a time) with Flatpickr: a small,
// self-hosted (server/admin/flatpickr.min.{js,css}, no CDN) calendar with
// an explicit Done button. `input` is a plain readonly text input; the
// picker keeps its value in the same "Y-m-d\THH:mm" shape the native
// widget produced, so buildExpirationRequest()'s `new Date(dateValue)`
// parsing is unchanged. Requires the global `flatpickr` (loaded via
// <script> in admin_panel.html) — a no-op if it isn't present.
function initExpirationDatePicker(input) {
  if (typeof window === "undefined" || !window.flatpickr) return null;
  var fp = window.flatpickr(input, {
    enableTime: true,
    time_24hr: true,
    dateFormat: "Y-m-d\\TH:i",
    closeOnSelect: false,
    minDate: new Date(Date.now() + 60000),
    maxDate: new Date(Date.now() + MAX_EXPIRATION_INPUT_YEARS * 365 * 24 * 60 * 60 * 1000),
    onReady: function (selectedDates, dateStr, instance) {
      var doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "flatpickr-done-btn";
      doneBtn.textContent = "Done";
      doneBtn.addEventListener("click", function () { instance.close(); });
      var footer = document.createElement("div");
      footer.className = "flatpickr-done-row";
      footer.appendChild(doneBtn);
      instance.calendarContainer.appendChild(footer);
    }
  });
  return fp;
}

// Sort sentinels: finite `expires_at` timestamps sort chronologically: a
// non-expiring exception sorts after every finite timestamp, and a key
// missing expiration metadata (not yet migrated) sorts last of all.
var EXPIRATION_SORT_NON_EXPIRING = Number.MAX_SAFE_INTEGER - 1;
var EXPIRATION_SORT_MISSING = Number.MAX_SAFE_INTEGER;

// Canonical display category for a key's expiration, derived only from
// server-supplied fields. `expired` is a server determination and always
// wins over policy so an active-looking policy can't mask an expired key;
// never compare `expires_at` against browser time here.
export function expirationState(key) {
  if (key && key.expired) return "expired";
  var policy = key && key.expiration_policy;
  if (policy === "non_expiring_exception") return "non_expiring";
  if (policy === "legacy_migration") return "legacy_migration";
  if (policy === "managed") return "managed";
  return "missing";
}

// Stable numeric sort value: finite timestamps sort chronologically, explicit
// non-expiring exceptions sort after all finite timestamps, and missing
// metadata sorts last of all.
export function expirationSortValue(key) {
  var state = expirationState(key);
  if (state === "non_expiring") return EXPIRATION_SORT_NON_EXPIRING;
  if (state === "missing") return EXPIRATION_SORT_MISSING;
  var ts = key && key.expires_at;
  return typeof ts === "number" && isFinite(ts) ? ts : EXPIRATION_SORT_MISSING;
}

// Display label (and optional secondary text/badge tone) for a key's
// expiration, in the list and detail views alike. `warningDays` is the
// server-supplied `expiration_warning_days`, threaded through rather than
// hardcoded so a deployment change is reflected without a UI change.
export function formatExpiration(key, warningDays) {
  var state = expirationState(key);
  var days = typeof warningDays === "number" ? warningDays : DEFAULT_EXPIRATION_WARNING_DAYS;
  var dateLabel = typeof key.expires_at === "number" ? new Date(key.expires_at * 1000).toLocaleString() : "";
  if (state === "expired") {
    return { label: "Expired " + dateLabel, badge: "error", state: state };
  }
  if (state === "non_expiring") {
    // The "Exception" badge already communicates this; no need to repeat it
    // as secondary text next to "Never" too.
    return { label: "Never", badge: "success", state: state };
  }
  if (state === "missing") {
    // No badge here: the label "Migration pending" already says it, and
    // this state previously shared the "neutral" tone with non-expiring
    // exceptions, which mislabeled it as "Exception" in the pill.
    return { label: "Migration pending", badge: null, state: state };
  }
  // managed or legacy_migration, not expired
  var remaining = key.days_remaining;
  if (typeof remaining === "number" && remaining <= days) {
    var roundedDays = Math.max(0, Math.round(remaining));
    return {
      label: dateLabel,
      secondary: roundedDays + (roundedDays === 1 ? " day" : " days"),
      badge: "warning",
      state: state
    };
  }
  return { label: dateLabel, badge: null, state: state };
}

// Access precedence (independent of expiration): Inactive, Expired, Active.
export function accessState(key) {
  if (key && key.active === false) return "inactive";
  if (key && key.expired) return "expired";
  return "active";
}

// Centralized, mutually-exclusive expiration request payload so create and
// renew cannot accidentally diverge. `choice` is one of "default" (create
// only — send no expiration fields), "custom", or "non_expiring".
export function buildExpirationRequest(choice, dateValue, justification) {
  if (choice === "default") return { ok: true, body: {} };
  if (choice === "custom") {
    if (!dateValue) return { ok: false, error: "Select an expiration date and time." };
    var date = new Date(dateValue);
    if (isNaN(date.getTime())) return { ok: false, error: "Enter a valid expiration date and time." };
    if (date.getTime() <= Date.now()) return { ok: false, error: "Expiration must be in the future." };
    var maxDate = new Date(Date.now() + MAX_EXPIRATION_INPUT_YEARS * 365 * 24 * 60 * 60 * 1000);
    if (date.getTime() > maxDate.getTime()) return { ok: false, error: "Enter a valid expiration date and time." };
    return { ok: true, body: { expires_at: date.toISOString() } };
  }
  if (choice === "non_expiring") {
    var trimmed = (justification || "").trim();
    if (!trimmed) return { ok: false, error: "A justification is required for a non-expiring key." };
    if (trimmed.length > MAX_JUSTIFICATION_LENGTH) {
      return { ok: false, error: "Justification must be " + MAX_JUSTIFICATION_LENGTH + " characters or fewer." };
    }
    return { ok: true, body: { non_expiring: true, expiration_justification: trimmed } };
  }
  return { ok: false, error: "Select an expiration option." };
}

// Pure paging algorithm behind loadAllKeys(): pages through server results
// with limit=1000 and increasing offset until a short page is returned,
// concatenating `keys` and capturing `expiration_warning_days` from the
// first page that has it. `fetchPage(limit, offset)` is injected so this is
// testable without a DOM or a real api() client.
export async function collectAllKeyPages(fetchPage) {
  var allKeys = [];
  var warningDays = DEFAULT_EXPIRATION_WARNING_DAYS;
  var sawWarningDays = false;
  var limit = 1000;
  var offset = 0;
  while (true) {
    var page = await fetchPage(limit, offset);
    if (Array.isArray(page)) page = { keys: page };
    var pageKeys = (page && page.keys) || [];
    if (!sawWarningDays && page && typeof page.expiration_warning_days === "number") {
      warningDays = page.expiration_warning_days;
      sawWarningDays = true;
    }
    allKeys = allKeys.concat(pageKeys);
    if (pageKeys.length < limit) break;
    offset += limit;
  }
  return { keys: allKeys, expirationWarningDays: warningDays, usedFallbackWarningDays: !sawWarningDays };
}

export function createApiKeysTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton, field, helpTooltip,
  svgIcon, iconPlus, iconEye, iconEyeOff, iconCopy, iconCheck, iconSave, iconX,
  createPaginator, createColumnSorter, itemsPerPage, markSelectedRow, syncVisibleSelection,
  syncBulkActionButton, withButton, confirmAction, requireTypedConfirmation, showStatus,
  showError, showTableLoadError, bindValidationClear, setFieldReadOnly,
  characterCount, createMarkdownPreview, copyTextToClipboard, maskSecret, promptIdentifier,
  keyPath, fillPromptSelect, createSelect,
  getCachedAdapters, getCachedPrompts, getCachedApiKeyUsers,
  getCachedKeys, setCachedKeys,
  loadAdaptersAndPrompts
}) {
  // Shared, DOM-backed expiration controls for both the create form and the
  // detail-view renewal form. `includeDefault` is false for renewal, since
  // the renew endpoint requires exactly one explicit choice. Returns
  // { el, reset(), validate() } — validate() delegates to the pure
  // buildExpirationRequest() helper so create and renew cannot diverge.
  function createExpirationControls(options) {
    var includeDefault = !options || options.includeDefault !== false;
    var groupName = "exp-choice-" + Math.random().toString(36).slice(2, 9);
    var defaultChoice = includeDefault ? "default" : "custom";
    var choices = [];
    if (includeDefault) choices.push({ value: "default", label: "Server default" });
    choices.push({ value: "custom", label: "Custom expiration" });
    choices.push({ value: "non_expiring", label: "Non-expiring exception" });

    var radios = [];
    var radioRows = choices.map(function (choice) {
      var radio = el("input", { type: "radio", name: groupName, value: choice.value });
      radio.checked = choice.value === defaultChoice;
      radios.push(radio);
      return el("label", { className: "check-row expiration-choice-row-item" }, radio, choice.label);
    });

    var dateInput = el("input", {
      type: "text",
      readonly: "readonly",
      className: "expiration-date-input",
      placeholder: "Select a date and time",
      "aria-label": "Custom expiration date and time"
    });
    var dateField = field(
      "Expiration date and time",
      dateInput,
      "The key stops working at this local date and time."
    );
    dateField.hidden = true;
    initExpirationDatePicker(dateInput);

    var justificationInput = el("textarea", {
      rows: "3",
      maxlength: String(MAX_JUSTIFICATION_LENGTH),
      "aria-label": "Non-expiring justification"
    });
    var justificationCounter = characterCount(justificationInput, MAX_JUSTIFICATION_LENGTH);
    var justificationField = field(
      "Justification",
      justificationInput,
      "Explain why this key should never expire. Required for a non-expiring exception."
    );
    var justificationWrap = el("div", { className: "stack" }, justificationField, justificationCounter);
    justificationWrap.hidden = true;

    bindValidationClear(dateInput, justificationInput);

    function currentChoice() {
      var checked = radios.filter(function (r) { return r.checked; })[0];
      return checked ? checked.value : defaultChoice;
    }

    function sync() {
      var choice = currentChoice();
      dateField.hidden = choice !== "custom";
      justificationWrap.hidden = choice !== "non_expiring";
    }
    radios.forEach(function (r) { r.addEventListener("change", sync); });
    sync();

    function reset() {
      radios.forEach(function (r) { r.checked = r.value === defaultChoice; });
      dateInput._flatpickr ? dateInput._flatpickr.clear() : (dateInput.value = "");
      justificationInput.value = "";
      // The counter renders from input events, so clearing .value alone
      // would leave a stale character count visible after reset.
      justificationInput.dispatchEvent(new Event("input"));
      sync();
    }

    function validate() {
      return buildExpirationRequest(currentChoice(), dateInput.value, justificationInput.value);
    }

    var fieldsetEl = el("fieldset", { className: "expiration-fieldset" },
      el("legend", null, "Expiration policy"),
      el("div", { className: "expiration-choice-row" }, radioRows),
      dateField,
      justificationWrap
    );

    return { el: fieldsetEl, reset: reset, validate: validate };
  }

  let selectedKey = null;
  // Server-supplied `expiration_warning_days`, cached alongside the key list
  // by loadAllKeys() so the list badge/filter and detail view stay in sync
  // with the deployment's configured threshold rather than a hardcoded one.
  let cachedExpirationWarningDays = DEFAULT_EXPIRATION_WARNING_DAYS;

  async function render(container) {
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var keySearchFilter = "";
    var keyExpirationFilter = "all";
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
    var adapterSelect = createSelect({ ariaLabel: "Adapter" });
    var availableAdapterNames = [];
    var cachedAdapters = getCachedAdapters();
    if (cachedAdapters) {
      cachedAdapters.forEach(function (a) {
        var name = typeof a === "string" ? a : (a.name || a.adapter_name || "");
        if (name) availableAdapterNames.push(name);
      });
    }
    if (availableAdapterNames.length) {
      adapterSelect.setOptions(availableAdapterNames.map(function (name) { return { value: name, label: name }; }), availableAdapterNames[0]);
    } else {
      adapterSelect.setOptions([{ value: "", label: "No adapters available" }], "");
      adapterSelect.disabled = true;
    }
    var promptSelect = createSelect({ ariaLabel: "Persona", options: [{ value: "", label: "No persona" }], value: "" });
    var cachedPrompts = getCachedPrompts();
    if (cachedPrompts) {
      var promptOptions = [{ value: "", label: "No persona" }].concat(cachedPrompts.map(function (p) {
        return { value: promptIdentifier(p), label: p.name + " (v" + (p.version || "1.0") + ")" };
      }));
      promptSelect.setOptions(promptOptions, "");
    }
    var notesInput = el("textarea", { rows: "4", maxlength: "2000" });
    var notesCounter = characterCount(notesInput, 2000);
    var createAllowedUsersSelect = allowedUsersSelect();
    var createClearAllowedUsersBtn = clearAllowedUsersButton(createAllowedUsersSelect);
    var createAllowedEmailsInput = el("input", { type: "text", maxlength: "2000", placeholder: "alice@company.com, bob@company.com" });
    var createAllowedEmailsCounter = characterCount(createAllowedEmailsInput, 2000);
    var createExpiration = createExpirationControls({ includeDefault: true });
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
      createExpiration.el,
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
    var keyExpirationFilterSelect = createSelect({
      ariaLabel: "Filter by expiration",
      options: [{ value: "all", label: "All keys" }, { value: "expired", label: "Expired" }, { value: "soon", label: "Expiring soon" }, { value: "non_expiring", label: "Non-expiring exceptions" }],
      value: "all"
    });
    listPanel.appendChild(el("div", { className: "admin-create-form-grid api-key-filter-grid" },
      field("Search", keySearchInput),
      field("Expiration", keyExpirationFilterSelect)
    ));
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
      var expirationResult = createExpiration.validate();
      if (!expirationResult.ok) {
        showError(expirationResult.error);
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
        Object.assign(body, expirationResult.body);
        await api("POST", endpoints.apiKeys, body);
        clientInput.value = "";
        promptSelect.value = "";
        notesInput.value = "";
        Array.from(createAllowedUsersSelect.options).forEach(function (o) { o.selected = false; });
        createClearAllowedUsersBtn.sync();
        createAllowedEmailsInput.value = "";
        createExpiration.reset();
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
      if (keyExpirationFilter !== "all") {
        filteredKeys = filteredKeys.filter(function (key) {
          if (keyExpirationFilter === "expired") return expirationState(key) === "expired";
          if (keyExpirationFilter === "non_expiring") return expirationState(key) === "non_expiring";
          if (keyExpirationFilter === "soon") return formatExpiration(key, cachedExpirationWarningDays).badge === "warning";
          return true;
        });
      }
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

    keyExpirationFilterSelect.addEventListener("change", function () {
      keyExpirationFilter = keyExpirationFilterSelect.value;
      applyKeyFilter();
    });

    // The list filters/sorts/paginates client-side, so a filtered view would
    // otherwise be incomplete past the server's default page. This pages
    // through the full result with limit=1000 before caching it, and caches
    // the response's expiration_warning_days alongside it.
    async function loadAllKeys() {
      var result = await collectAllKeyPages(function (limit, offset) {
        return api("GET", endpoints.apiKeys + "?limit=" + limit + "&offset=" + offset);
      });
      if (result.usedFallbackWarningDays) {
        console.warn("GET /admin/api-keys response is missing expiration_warning_days; falling back to " + DEFAULT_EXPIRATION_WARNING_DAYS + " days.");
      }
      return result;
    }

    async function loadKeys() {
      try {
        var result = await loadAllKeys();
        var keys = result.keys;
        cachedExpirationWarningDays = result.expirationWarningDays;
        keyExpirationFilterSelect.setOptions([
          { value: "all", label: "All keys" },
          { value: "expired", label: "Expired" },
          { value: "soon", label: "Expiring within " + cachedExpirationWarningDays + " days" },
          { value: "non_expiring", label: "Non-expiring exceptions" }
        ], keyExpirationFilterSelect.value);
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

  // Maps formatExpiration()'s badge tone to the shared `.monitoring-badge`
  // color modifier already used elsewhere in the admin panel, and to its
  // display text.
  var EXPIRATION_BADGE_CLASS = { error: "red", warning: "amber", success: "green" };
  var EXPIRATION_BADGE_TEXT = { error: "Expired", warning: "Expiring soon", success: "Exception" };

  function expirationCell(key) {
    var info = formatExpiration(key, cachedExpirationWarningDays);
    var children = [el("span", null, info.label)];
    if (info.secondary) children.push(el("span", { className: "expiration-secondary" }, " · " + info.secondary));
    if (info.badge) {
      children.push(el("span", { className: "monitoring-badge " + EXPIRATION_BADGE_CLASS[info.badge] }, EXPIRATION_BADGE_TEXT[info.badge]));
    }
    return el("td", { className: "expiration-cell" }, children);
  }

  function accessCell(key) {
    var state = accessState(key);
    var label = state === "inactive" ? "Inactive" : state === "expired" ? "Expired" : "Active";
    var className = state === "active" ? "status-active" : "status-inactive";
    return el("td", null, el("span", { className: className }, label));
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
      { label: "Expiration", key: "expiration", sortValue: expirationSortValue },
      { label: "Access", key: "access", sortValue: function (k) { return accessState(k); } },
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
        expirationCell(k),
        accessCell(k)
      );
      tr.addEventListener("click", async function () {
        selectedKey = { _id: k._id };
        markSelectedRow(tbody, tr);
        clear(rightPanel);
        rightPanel.style.display = "";
        rightPanel.appendChild(el("p", { className: "muted" }, "Loading key details..."));
        // On narrow layouts the detail panel stacks below the table, so
        // selecting a row leaves it out of view; scroll it in once the real
        // content is in place, but skip the jump on wide screens where the
        // split layout already shows it.
        function scrollDetailIntoView() {
          rightPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        try {
          var detail = await loadKeyDetail(k._id);
          selectedKey = detail;
          renderKeyDetail(rightPanel, detail, function () {
            selectedKey = null;
            reloadKeys();
          });
          scrollDetailIntoView();
        } catch (err) {
          selectedKey = null;
          clear(rightPanel);
          rightPanel.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Unable to load key details."),
            el("p", { className: "muted" }, err.message || "Unknown error")
          ));
          showError(err.message);
          scrollDetailIntoView();
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

  var EXPIRATION_POLICY_LABELS = {
    managed: "Managed",
    legacy_migration: "Legacy migration",
    non_expiring_exception: "Non-expiring exception"
  };

  var EXPIRATION_POLICY_HELP = {
    managed: "This key's expiration was set normally, either the server default or a date chosen at creation or renewal.",
    legacy_migration: "This key existed before expiration was enforced. It was automatically given a one-time grace-period expiration so it doesn't stop working without warning; renew it to set a deliberate expiration.",
    non_expiring_exception: "An admin explicitly granted this key an exception to never expire, with a recorded justification."
  };

  var STATE_HELP_TEXT = "Independent of the expiration policy: Inactive means the key was deactivated and won't work regardless of expiration; Expired means it has passed its expiration date; Non-expiring exception means it was granted an explicit exception to never expire; otherwise the key is Active.";

  // Same shape as infoRow(), but the label carries a help-icon tooltip.
  function infoRowWithHelp(label, value, helpText, helpId) {
    var labelEl = el("span", { className: "info-label field-label-row" },
      el("span", null, label),
      helpTooltip(label, helpText, helpId)
    );
    return el("div", { className: "info-row" }, labelEl, el("span", { className: "info-value" }, String(value)));
  }

  // Combined state shown in the detail view: expiration and deactivation are
  // independent, so an inactive key is called out even if it also has a
  // valid expires_at, and a non-expiring exception is distinguished from a
  // merely long-lived managed key.
  function expirationSummaryState(key) {
    if (key.active === false) return "Inactive";
    if (key.expired) return "Expired";
    if (expirationState(key) === "non_expiring") return "Non-expiring exception";
    return "Active";
  }

  function formatDaysRemainingLabel(days) {
    if (typeof days !== "number" || days < 0) return null;
    if (days < 1) return "less than a day";
    var rounded = Math.round(days);
    return rounded + (rounded === 1 ? " day" : " days");
  }

  // Expiration summary plus the renew/change-expiration inline form. Always
  // builds the renewal request from `keyId` (the record's non-secret _id),
  // never from the displayed/revealed key value.
  function renderExpirationSection(key, keyId, onRefresh) {
    var section = el("div", { className: "api-key-expiration-section" }, el("h3", null, "Expiration"));
    var state = expirationSummaryState(key);
    var isNonExpiring = expirationState(key) === "non_expiring";
    var dateLabel = isNonExpiring
      ? "Never"
      : (typeof key.expires_at === "number" ? new Date(key.expires_at * 1000).toLocaleString() : "Unknown (migration pending)");
    var daysLabel = formatDaysRemainingLabel(key.days_remaining);

    var summaryRows = [
      infoRowWithHelp("State", state, STATE_HELP_TEXT, "expiration-state-help-" + keyId),
      infoRow("Expires", dateLabel)
    ];
    if (daysLabel) summaryRows.push(infoRow("Days remaining", daysLabel));
    if (key.expiration_policy) {
      var policyHelp = EXPIRATION_POLICY_HELP[key.expiration_policy] || "How this key's expiration was set.";
      summaryRows.push(infoRowWithHelp(
        "Policy",
        EXPIRATION_POLICY_LABELS[key.expiration_policy] || key.expiration_policy,
        policyHelp,
        "expiration-policy-help-" + keyId
      ));
    }
    section.appendChild(el("div", { className: "info-grid" }, summaryRows));
    section.appendChild(el("p", { className: "muted" }, "Renewing a key's expiration does not reactivate an inactive key."));

    var renewToggle = el("button", { className: "secondary", type: "button" }, "Renew / Change Expiration");
    var renewControls = createExpirationControls({ includeDefault: false });
    var renewSubmitBtn = el("button", { type: "button", className: "btn btn--primary" }, "Save Expiration");
    var renewCancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var renewForm = el("div", { className: "stack api-key-renew-form", hidden: "true" },
      renewControls.el,
      el("div", { className: "inline-form" }, renewSubmitBtn, renewCancelBtn)
    );

    function closeRenewForm() {
      renewForm.hidden = true;
      renewToggle.hidden = false;
      renewControls.reset();
    }
    renewToggle.addEventListener("click", function () {
      renewForm.hidden = false;
      renewToggle.hidden = true;
    });
    renewCancelBtn.addEventListener("click", closeRenewForm);

    renewSubmitBtn.addEventListener("click", function () {
      var result = renewControls.validate();
      if (!result.ok) {
        showError(result.error);
        return;
      }
      var body = result.body;
      if (body.non_expiring) {
        confirmAction({
          title: "Grant Non-Expiring Exception",
          message: "This key will no longer expire automatically. Continue?",
          confirmLabel: "Grant Exception",
          onConfirm: async function () {
            await api("POST", keyPath(keyId, "/renew"), body);
            showStatus("API key renewed");
            closeRenewForm();
            onRefresh();
          }
        });
        return;
      }
      withButton(renewSubmitBtn, async function () {
        await api("POST", keyPath(keyId, "/renew"), body);
        closeRenewForm();
        onRefresh();
      }, "API key renewed");
    });

    section.appendChild(el("div", { className: "detail-action-row" }, renewToggle));
    section.appendChild(renewForm);
    return section;
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
        await api("PATCH", keyPath(keyId, "/rename"), { new_api_key: nk });
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
    var adapterSelect = createSelect({ ariaLabel: "Adapter" });
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
      adapterSelect.setOptions(availableAdapterNames.map(function (name) { return { value: name, label: name }; }), key.adapter_name);
    } else {
      adapterSelect.setOptions([{ value: key.adapter_name || "", label: key.adapter_name || "No adapters available" }], key.adapter_name || "");
      adapterSelect.disabled = true;
    }
    var promptSelect = createSelect({ ariaLabel: "Persona", options: [{ value: "", label: "No persona" }], value: "" });
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

    panel.appendChild(renderExpirationSection(key, keyId, onRefresh));

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
    } else {
      var activateBtn = el("button", { className: "secondary", type: "button" }, "Activate Key");
      activateBtn.addEventListener("click", function () {
        confirmAction({
          title: "Activate Key",
          message: "Activate this API key? It will start authenticating again.",
          confirmLabel: "Activate",
          onConfirm: async function () {
            activateBtn.disabled = true;
            try {
              await api("POST", keyPath(keyId, "/activate"));
              showStatus("Key activated");
              onRefresh();
            } finally {
              activateBtn.disabled = false;
            }
          }
        });
      });
      dangerActions.appendChild(activateBtn);
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
