export function createAdaptersTab({
  api, endpoints, el, clear, skeleton, svgIcon, iconPlus, iconSave, iconRefresh,
  field, helpTooltip, characterCount, withButton, createPaginator, createColumnSorter, itemsPerPage,
  markSelectedRow, confirmAction, requireTypedConfirmation, showError, showStatus, waitForAdminJob,
  createSelect, getActiveTab, getCachedAdapterCapabilities, loadAdapterCapabilities
}) {
  var adapterEditor = null;        // Ace editor instance for Adapters tab
  var adapterOriginal = "";        // Dirty tracking baseline
  var cachedAdapterFiles = null;   // Cached adapter file listing
  var cachedAdapterSpecs = null;   // Adapter SDK families available for creation
  var cachedAdapterAnswerOptions = null; // Enumerable values for options_source questions
  var adapterPreviewEditor = null; // Read-only Ace editor for the create preview
  var importEditor = null;         // Ace editor instance for the import panel
  var selectedAdapterEntry = null; // { name, filename, ... }

  async function loadAdapterFiles() {
    try {
      var data = await api("GET", endpoints.adapterConfigs);
      cachedAdapterFiles = data.files || [];
    } catch (_) {
      cachedAdapterFiles = [];
    }
    return cachedAdapterFiles;
  }

  async function loadAdapterSpecs() {
    try {
      var data = await api("GET", endpoints.adapterSpecs);
      cachedAdapterSpecs = data.specs || [];
    } catch (_) {
      cachedAdapterSpecs = [];
    }
    return cachedAdapterSpecs;
  }

  // Point-in-time snapshot of app.state.config, like cachedAdapterSpecs — reloaded
  // on every panel open rather than invalidated, so a config reload can't leave it stale.
  async function loadAdapterAnswerOptions() {
    try {
      cachedAdapterAnswerOptions = await api("GET", endpoints.adapterAnswerOptions);
    } catch (_) {
      cachedAdapterAnswerOptions = {};
    }
    return cachedAdapterAnswerOptions;
  }

  function render(container) {
    clear(container);

    // Destroy previous editors
    if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
    if (adapterPreviewEditor) { adapterPreviewEditor.destroy(); adapterPreviewEditor = null; }
    if (importEditor) { importEditor.destroy(); importEditor = null; }

    // Lazy-load adapter file listing, capability metadata (needed to know which
    // adapters support template reload) and the SDK spec registry (create form)
    var cachedAdapterCapabilities = getCachedAdapterCapabilities();
    if (!cachedAdapterFiles || !cachedAdapterCapabilities || !cachedAdapterSpecs || !cachedAdapterAnswerOptions) {
      container.appendChild(skeleton());
      Promise.all([
        cachedAdapterFiles ? Promise.resolve(cachedAdapterFiles) : loadAdapterFiles(),
        cachedAdapterCapabilities ? Promise.resolve(cachedAdapterCapabilities) : loadAdapterCapabilities(),
        cachedAdapterSpecs ? Promise.resolve(cachedAdapterSpecs) : loadAdapterSpecs(),
        cachedAdapterAnswerOptions ? Promise.resolve(cachedAdapterAnswerOptions) : loadAdapterAnswerOptions(),
      ]).then(function () {
        if (getActiveTab() === "adapters") render(container);
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
    var searchInput = el("input", { type: "text", placeholder: "Search adapters…", style: "flex:1;min-width:0" });
    leftHeader.appendChild(searchInput);
    leftPanel.appendChild(leftHeader);

    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create adapter",
    }, svgIcon(iconPlus), el("span", null, "Create Adapter"));
    createLaunchBtn.addEventListener("click", function () { openAdapterCreatePanel(); });
    var importLaunchBtn = el("button", {
      className: "secondary",
      type: "button",
      "aria-label": "Import adapter",
    }, "Import Adapter");
    importLaunchBtn.addEventListener("click", function () { openAdapterImportPanel(); });
    leftPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, importLaunchBtn));

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
        api("PATCH", endpoints.adapterConfigs + "/entry/" + encodeURIComponent(a.name) + "/toggle", { enabled: newState })
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
        tbody.appendChild(el("tr", null, el("td", { colSpan: "3", className: "empty-state" },
          el("div", { className: "empty-state-icon" }, "\u{1F50C}"),
          el("p", null, "No adapters found")
        )));
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
      pageSize: itemsPerPage,
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

    var createPanelTitle = el("h2", null, "New Adapter");
    var closeCreateBtn = el("button", { className: "secondary", type: "button" }, "Close");
    closeCreateBtn.addEventListener("click", function () { closeAdapterCreatePanel(); });
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      createPanelTitle,
      closeCreateBtn
    ));

    var specSelect = createSelect({
      ariaLabel: "Adapter family",
      options: (cachedAdapterSpecs || []).map(function (s) { return { value: s.key, label: s.title }; })
    });
    var specHint = el("p", { className: "muted", style: "margin:0" }, "");
    var formGrid = el("div", { className: "admin-create-form-grid" });
    // Boolean questions land here instead of the grid — a checkbox is a fraction
    // of the width of a text field, so mixed into the two-column grid it leaves a
    // half-empty cell next to it every time. Grouped and wrapped together, on/off
    // switches read as one cluster of settings instead of debris between fields.
    var optionsGroup = el("div", { className: "adapter-options-group is-empty" });
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
      optionsGroup,
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

    // A locked-down field (currently just inference_provider) can only ever save
    // successfully as one of the enabled, configured values — validate_providers
    // rejects anything else server-side — so it's a <select>, not free text.
    // Options are filled in by populateStrictSelect() once the initial value for
    // this question is known, not here.
    //
    function populateStrictSelect(q, select, currentValue) {
      var options = ((cachedAdapterAnswerOptions || {})[q.options_source] || []).slice();
      // Questions whose default is `null` (e.g. "override; blank for global
      // default") must stay clearable — the old free-text combobox let a user
      // just empty the box, and a <select> needs an explicit blank option to
      // offer the same way back out once something else has been picked.
      if (q.default === null && options.indexOf("") === -1) {
        options.unshift("");
      }
      if (!options.length) options = [""];
      select.setOptions(options.map(function (v) {
        return { value: v, label: v || (q.default === null ? "(use global default)" : "(none configured)") };
      }));
    }

    function makeQuestionInput(q) {
      if (q.type === "bool") return el("input", { type: "checkbox" });
      if (q.options_strict) return createSelect({ ariaLabel: q.prompt });
      if (q.choices) {
        return createSelect({
          ariaLabel: q.prompt,
          options: q.choices.map(function (c) { return { value: c, label: c }; })
        });
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

    // A <select> would force the value to a known one; this combobox keeps the
    // field free-text (so e.g. a store defined after the panel's cache loaded can
    // still be typed) while suggesting the enumerable, enabled values as the user
    // types — styled to the admin theme instead of the browser's native <datalist>.
    // `cachedAdapterAnswerOptions` is read live on every open/keystroke, not
    // snapshotted here, so a mid-session refresh (see openAdapterCreatePanel)
    // reaches an already-built combobox with no separate rebuild step.
    function wrapAnswerCombobox(q, input) {
      var wrap = el("div", { className: "adapter-combobox" }, input);
      var panel = el("div", { className: "adapter-combobox-panel", role: "listbox", style: "display:none" });
      wrap.appendChild(panel);

      input.setAttribute("autocomplete", "off");
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-autocomplete", "list");

      var currentOptions = [];
      var activeIndex = -1;

      function optionsForQuery(query) {
        var all = (cachedAdapterAnswerOptions || {})[q.options_source] || [];
        if (!query) return all;
        var lc = query.toLowerCase();
        return all.filter(function (v) { return v.toLowerCase().indexOf(lc) !== -1; });
      }

      function renderPanel() {
        clear(panel);
        if (!currentOptions.length) {
          panel.style.display = "none";
          input.setAttribute("aria-expanded", "false");
          return;
        }
        var query = input.value.trim();
        currentOptions.forEach(function (value, i) {
          var matchAt = query ? value.toLowerCase().indexOf(query.toLowerCase()) : -1;
          var label = matchAt === -1
            ? el("span", null, value)
            : el("span", null,
                value.slice(0, matchAt),
                el("strong", null, value.slice(matchAt, matchAt + query.length)),
                value.slice(matchAt + query.length)
              );
          var opt = el("div", {
            className: "adapter-combobox-option" + (i === activeIndex ? " is-active" : ""),
            role: "option",
            "aria-selected": String(i === activeIndex),
            dataset: { index: String(i) },
          }, el("span", { className: "adapter-combobox-dot" }), label);
          // Not renderPanel() here: rebuilding every option's DOM node on hover means a
          // real click's mousedown and mouseup can land on two different node objects
          // (a mousemove between them re-fires mouseenter and rebuilds mid-gesture) —
          // browsers only dispatch "click" when both share the same target, so the
          // click silently never fires. Toggling classes in place keeps the nodes stable.
          opt.addEventListener("mouseenter", function () {
            if (activeIndex === i) return;
            var prev = panel.querySelector(".adapter-combobox-option.is-active");
            if (prev) { prev.classList.remove("is-active"); prev.setAttribute("aria-selected", "false"); }
            activeIndex = i;
            opt.classList.add("is-active");
            opt.setAttribute("aria-selected", "true");
          });
          panel.appendChild(opt);
        });
        panel.style.display = "";
        input.setAttribute("aria-expanded", "true");
      }

      // Delegated on the panel, not per-option: a mousedown that lands on the
      // panel's own padding (between/around rows) still has to preventDefault or
      // the browser blurs the input right there, and the 100ms blur timeout below
      // closes the panel before the click that follows ever reaches an option —
      // the value never gets applied and the field looks like it lost its edit.
      panel.addEventListener("mousedown", function (e) { e.preventDefault(); });
      panel.addEventListener("click", function (e) {
        var optEl = e.target.closest(".adapter-combobox-option");
        if (!optEl) return;
        // The preceding mousedown keeps focus on the input; suppress any
        // remaining browser default action before applying the choice.
        e.preventDefault();
        var value = currentOptions[Number(optEl.dataset.index)];
        if (value !== undefined) selectValue(value);
      });

      function scrollActiveIntoView() {
        var activeEl = panel.querySelector(".is-active");
        if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
      }

      function openPanel() {
        currentOptions = optionsForQuery(input.value.trim());
        activeIndex = -1;
        renderPanel();
      }

      function closePanel() {
        panel.style.display = "none";
        input.setAttribute("aria-expanded", "false");
        activeIndex = -1;
      }

      function selectValue(value) {
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true })); // updates character/entry counts
        closePanel();
        input.focus();
      }

      input.addEventListener("focus", openPanel);
      input.addEventListener("input", openPanel);
      input.addEventListener("blur", function () { setTimeout(closePanel, 100); });
      input.addEventListener("keydown", function (e) {
        if (panel.style.display === "none" && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
          openPanel();
          return;
        }
        if (!currentOptions.length) return;
        if (e.key === "ArrowDown") {
          e.preventDefault();
          activeIndex = Math.min(activeIndex + 1, currentOptions.length - 1);
          renderPanel();
          scrollActiveIntoView();
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          activeIndex = Math.max(activeIndex - 1, 0);
          renderPanel();
          scrollActiveIntoView();
        } else if (e.key === "Enter") {
          if (activeIndex >= 0) { e.preventDefault(); selectValue(currentOptions[activeIndex]); }
        } else if (e.key === "Escape") {
          closePanel();
        }
      });

      return wrap;
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
      if (q.options_strict) parts.push("Only active, configured providers are listed.");
      else if (q.options_source) parts.push("Start typing to see configured values.");
      return parts.join(" ");
    }

    // List questions pack every entry into one comma-separated box, so a raw
    // character count against that box's inflated maxlength would be meaningless —
    // count entries against max_items instead, the bound that actually matters.
    function entryCount(input, maxItems) {
      var counter = el("div", { className: "character-count", "aria-live": "polite" });
      function sync() {
        var count = (input.value || "").split(",").map(function (s) { return s.trim(); }).filter(Boolean).length;
        counter.textContent = count + "/" + maxItems + " entries";
        counter.classList.toggle("near-limit", count >= maxItems);
      }
      input.addEventListener("input", sync);
      sync();
      return counter;
    }

    function adapterQuestionField(q, input, hint) {
      if (q.type !== "bool") {
        var control;
        if (q.options_source && !q.options_strict) {
          // A combobox's option panel must not be nested in the <label>. Apart
          // from being invalid label content, option clicks then also trigger
          // the label's native focus action, which can swallow the selection.
          var id = input.id || "field-" + Math.random().toString(36).slice(2, 9);
          input.id = id;
          var labelRow = [el("label", { htmlFor: id }, q.prompt)];
          if (hint) {
            var helpId = id + "-help";
            input.setAttribute("aria-describedby", helpId);
            labelRow.push(helpTooltip(q.prompt, hint, helpId));
          }
          var fieldParts = [el("div", { className: "field-label-row" }, labelRow), wrapAnswerCombobox(q, input)];
          control = el("div", { className: "stack" }, fieldParts);
        } else {
          control = field(q.prompt, input, hint);
        }
        if (q.type === "str" && q.max_length) {
          control.appendChild(characterCount(input, q.max_length));
        } else if (q.type === "list" && q.max_items) {
          control.appendChild(entryCount(input, q.max_items));
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
      var checkboxHelpId = (input.id || "field-" + Math.random().toString(36).slice(2, 9)) + "-help";
      input.id = input.id || checkboxHelpId.slice(0, -5);
      input.setAttribute("aria-describedby", checkboxHelpId);
      return el("div", { className: "adapter-checkbox-question" },
        checkboxLabel,
        helpTooltip(q.prompt, hint, checkboxHelpId)
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
      clear(optionsGroup);
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
        ? (spec.variants && spec.variants.length ? spec.variants[0] : null) : null;

      ordered.forEach(function (q) {
        var input = makeQuestionInput(q);
        createInputs[q.field] = { q: q, input: input };
        var initial = q.variant_defaults && variant !== null
          && Object.prototype.hasOwnProperty.call(q.variant_defaults, variant)
          ? q.variant_defaults[variant] : q.default;
        if (q.options_strict) populateStrictSelect(q, input, defaultAsString(q, initial));
        applyDefault(q, input, initial);
        if (spec.variant_field && q.field === spec.variant_field) {
          input.value = variant;
          input._appliedDefault = variant;
          input.addEventListener("change", function () { applyVariantDefaults(input.value); });
        }
        var target = q.type === "bool" ? optionsGroup : formGrid;
        target.appendChild(adapterQuestionField(q, input, questionHint(q)));
      });
      if (optionsGroup.children.length) {
        optionsGroup.insertBefore(el("span", { className: "adapter-options-group-label" }, "Options"), optionsGroup.firstChild);
      }
      optionsGroup.classList.toggle("is-empty", !optionsGroup.children.length);
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
          data = await api("POST", endpoints.adapterPreview, {
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
          data = await api("POST", endpoints.adapterCreate, { spec: spec.key, answers: answers });
        } catch (err) {
          throw new Error("Create failed: " + err.message);
        }
        await loadAdapterFiles();
        await loadAdapterCapabilities();
        closeAdapterCreatePanel();
        // Re-render so the adapter appears in the (re-flattened) list, then
        // open it in the detail editor.
        selectedAdapterEntry = { name: data.name, filename: data.filename };
        render(container);
        if (data.reload_error) showError(data.message);
        else showStatus(data.message);
      });
    });

    async function openAdapterCreatePanel() {
      createPanelTitle.textContent = "New Adapter";
      // Refresh the enumerable answer options (providers/stores/datasources) so a
      // config change since the panel last loaded is reflected, before the form is
      // built — a strict field (e.g. inference_provider) bakes this list into a
      // <select> at build time, unlike the free-text combobox which re-reads
      // `cachedAdapterAnswerOptions` live on every open/keystroke.
      await loadAdapterAnswerOptions();
      createPanel.style.display = "";
      buildAdapterCreateForm();
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function closeAdapterCreatePanel() {
      hideCreatePreview();
      createPanel.style.display = "none";
    }

    specSelect.addEventListener("change", buildAdapterCreateForm);

    // ----- Import panel: paste or upload a single-adapter YAML export -----
    var importPanel = el("div", { className: "panel", style: "display:none" });
    container.insertBefore(importPanel, layout);

    var closeImportBtn = el("button", { className: "secondary", type: "button" }, "Close");
    closeImportBtn.addEventListener("click", function () { closeAdapterImportPanel(); });
    importPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Import Adapter"),
      closeImportBtn
    ));

    var importFileInput = el("input", { type: "file", accept: ".yaml,.yml" });
    var importHint = el("p", { className: "muted", style: "margin:0" },
      "Paste one adapter — a full exported 'adapters:' document, a bare '- name: ...' entry, "
      + "or a mapping starting with 'name: ...' — or choose a file above. Use Format to "
      + "normalize indentation and check it before importing.");
    var importEditorWrap = el("div", { className: "adapter-ace-wrap", style: "height:320px" });
    var importOverwriteLabel = el("label", { className: "adapter-checkbox-field" },
      el("input", { type: "checkbox", id: "adapter-import-overwrite" }),
      el("span", null, "Overwrite if a file with this adapter's name already exists")
    );
    var importOverwrite = importOverwriteLabel.querySelector("input");
    var importBanner = el("div", { className: "settings-banner", style: "display:none", role: "status" });
    var formatBtn = el("button", { className: "secondary", type: "button" }, "Format");
    var importBtn = el("button", { type: "button" }, "Import Adapter");

    function ensureImportEditor() {
      if (importEditor) return importEditor;
      ace.config.set("basePath", "/static");
      ace.config.set("modePath", "/static");
      ace.config.set("themePath", "/static");
      ace.config.set("workerPath", "/static");
      importEditor = ace.edit(importEditorWrap, {
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
        showFoldWidgets: true,
        displayIndentGuides: true,
      });
      return importEditor;
    }

    importFileInput.addEventListener("change", function () {
      var file = importFileInput.files && importFileInput.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () { ensureImportEditor().setValue(String(reader.result || ""), -1); };
      reader.readAsText(file);
    });

    importPanel.appendChild(el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid" }, field("Adapter file", importFileInput)),
      importHint,
      importEditorWrap,
      el("div", { className: "admin-create-form-grid" }, importOverwriteLabel),
      importBanner,
      el("div", { className: "admin-create-form-actions" }, formatBtn, importBtn)
    ));

    var importBannerTimeout = null;

    function showImportBanner(message, autoHideMs) {
      if (importBannerTimeout) { clearTimeout(importBannerTimeout); importBannerTimeout = null; }
      clear(importBanner);
      importBanner.appendChild(el("div", null, message));
      importBanner.style.display = "";
      if (autoHideMs) {
        importBannerTimeout = setTimeout(function () {
          importBanner.style.display = "none";
          importBannerTimeout = null;
        }, autoHideMs);
      }
    }

    function hideImportBanner() {
      if (importBannerTimeout) { clearTimeout(importBannerTimeout); importBannerTimeout = null; }
      clear(importBanner);
      importBanner.style.display = "none";
    }

    // Normalizes indentation/shape through the same PyYAML-based logic the import
    // endpoint itself applies (server/routes/admin/adapters.py:_normalize_import_document),
    // rather than shipping a second YAML formatter into the browser bundle.
    formatBtn.addEventListener("click", function () {
      var content = ensureImportEditor().getValue().trim();
      if (!content) { showError("Paste or choose an adapter YAML file first."); return; }
      withButton(formatBtn, async function () {
        var data;
        try {
          data = await api("POST", endpoints.adapterImportFormat, { content: content });
        } catch (err) {
          throw new Error("Format failed: " + err.message);
        }
        ensureImportEditor().setValue(data.yaml, -1);
        if (data.errors && data.errors.length) {
          // Left up until the operator fixes it and re-formats — not on a timer,
          // since it's still actionable.
          showImportBanner("Formatted, but still invalid: " + data.errors.join("; "));
        } else {
          showImportBanner("Formatted and validated.", 3000);
        }
      });
    });

    importBtn.addEventListener("click", function () {
      var content = ensureImportEditor().getValue().trim();
      if (!content) { showError("Paste or choose an adapter YAML file first."); return; }
      withButton(importBtn, async function () {
        hideImportBanner();
        var data;
        try {
          data = await api("POST", endpoints.adapterImport, { content: content, overwrite: importOverwrite.checked });
        } catch (err) {
          throw new Error("Import failed: " + err.message);
        }
        await loadAdapterFiles();
        await loadAdapterCapabilities();
        closeAdapterImportPanel();
        selectedAdapterEntry = { name: data.name, filename: data.filename };
        render(container);
        if (data.reload_error) showError(data.message);
        else showStatus(data.message);
      });
    });

    function openAdapterImportPanel() {
      ensureImportEditor().setValue("", -1);
      importFileInput.value = "";
      importOverwrite.checked = false;
      hideImportBanner();
      importPanel.style.display = "";
      importPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      ensureImportEditor().resize();
    }

    function closeAdapterImportPanel() {
      if (importBannerTimeout) { clearTimeout(importBannerTimeout); importBannerTimeout = null; }
      importPanel.style.display = "none";
    }

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
      headerRow.appendChild(el("h3", { style: "margin:0;padding-top:0;border-top:0" }, a.name));
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
      }, svgIcon(iconSave));
      var reloadDiskBtn = el("button", {
        className: "btn btn--neutral btn--icon",
        "aria-label": "Reload from disk",
        title: "Reload from disk",
      }, svgIcon(iconRefresh));
      // Template reload only applies to adapters whose implementation exposes
      // reload_templates() (intent/composite retrievers) — driven by the backend
      // capability flag so this stays correct as new adapter types are added.
      var adapterCap = (getCachedAdapterCapabilities() || []).find(function (c) { return c.name === a.name; });
      var supportsTemplateReload = !!(adapterCap && adapterCap.supports_template_reload);
      var reloadTemplatesBtn = supportsTemplateReload
        ? el("button", { className: "btn btn--neutral" }, "Reload Templates")
        : null;
      // Test Query only applies to intent/composite retrievers (the ones with
      // templates to match against) — driven by the same capability flag pattern
      // as Reload Templates so it stays correct as new adapter types are added.
      var supportsTestQuery = !!(adapterCap && adapterCap.supports_test_query);
      var testQueryBtn = supportsTestQuery
        ? el("button", { className: "btn btn--neutral" }, "Test Query")
        : null;

      var exportBtn = el("button", { className: "secondary", type: "button" }, "Export");
      var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Adapter");

      var btnRow = el("div", { style: "display:flex;flex-wrap:wrap;gap:var(--sp-2);margin-top:var(--sp-3)" });
      btnRow.appendChild(saveBtn);
      btnRow.appendChild(reloadDiskBtn);
      if (reloadTemplatesBtn) {
        btnRow.appendChild(el("span", { className: "ops-action-divider" }));
        btnRow.appendChild(reloadTemplatesBtn);
      }
      if (testQueryBtn) {
        btnRow.appendChild(el("span", { className: "ops-action-divider" }));
        btnRow.appendChild(testQueryBtn);
      }
      btnRow.appendChild(el("span", { className: "ops-action-divider" }));
      btnRow.appendChild(exportBtn);
      btnRow.appendChild(deleteBtn);
      detailPanel.appendChild(btnRow);

      // Test Query panel — collapsed by default, built lazily on first expand.
      // Drives POST /admin/adapters/{name}/test-query, which runs template
      // matching/extraction/rendering (and optionally execution) without the
      // full LLM pipeline (server/utils/template_diagnostics.py).
      var testQueryRunFromMiss = null; // set once buildTestQueryBody runs; lets the Misses panel prefill+run it
      if (testQueryBtn) {
        var testQuerySection = el("details", { className: "panel", style: "margin-top:var(--sp-3)" });
        var testQuerySummary = el("summary", { style: "cursor:pointer;font-weight:600" }, "Test Query");
        testQuerySection.appendChild(testQuerySummary);
        var testQueryBuilt = false;
        testQueryBtn.addEventListener("click", function () {
          testQuerySection.open = !testQuerySection.open;
          if (testQuerySection.open && !testQueryBuilt) {
            testQueryBuilt = true;
            testQueryRunFromMiss = buildTestQueryBody(testQuerySection, a);
          }
          if (testQuerySection.open) testQuerySection.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
        detailPanel.appendChild(testQuerySection);

        // Misses panel — lists queries this adapter failed to match (or matched
        // below threshold), backed by the in-memory store in
        // server/services/template_misses.py. Each row can jump straight into
        // Test Query for that exact query string.
        var missesSection = el("details", { className: "panel", style: "margin-top:var(--sp-3)" });
        var missesSummary = el("summary", { style: "cursor:pointer;font-weight:600" }, "Misses");
        missesSection.appendChild(missesSummary);
        var missesReload = null; // set once buildMissesBody constructs the DOM; called on every reopen
        missesSection.addEventListener("toggle", function () {
          if (!missesSection.open) return;
          if (!missesReload) {
            missesReload = buildMissesBody(missesSection, a, function (query) {
              testQuerySection.open = true;
              if (!testQueryBuilt) {
                testQueryBuilt = true;
                testQueryRunFromMiss = buildTestQueryBody(testQuerySection, a);
              }
              if (testQueryRunFromMiss) testQueryRunFromMiss(query);
              testQuerySection.scrollIntoView({ behavior: "smooth", block: "nearest" });
            });
          } else {
            // DOM already built from a previous open — just refresh the data
            // so misses recorded while this panel was closed show up now.
            missesReload();
          }
        });
        detailPanel.appendChild(missesSection);
      }

      // Downloads the adapter as a standalone YAML file for moving it to another
      // environment. The exported document is whatever is on disk verbatim — secrets
      // stay as ${ENV_VAR} references, never resolved values, so this is safe to share.
      exportBtn.addEventListener("click", function () {
        withButton(exportBtn, async function () {
          var text;
          try {
            text = await api("GET", endpoints.adapterCreate + "/" + encodeURIComponent(a.name) + "/export");
          } catch (err) {
            throw new Error("Export failed: " + err.message);
          }
          var blob = new Blob([typeof text === "string" ? text : JSON.stringify(text)], { type: "application/x-yaml" });
          var url = URL.createObjectURL(blob);
          var link = el("a", { href: url, download: a.name + ".yaml" });
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        });
      });

      // Deleting removes the adapter's YAML block, its import line, and evicts it from
      // the running server. The server refuses with 409 while API keys or other
      // adapters' skill lists still name it; that needs a second, explicit confirmation
      // because forcing leaves those referrers pointing at nothing.
      async function doDeleteAdapter(force) {
        var url = endpoints.adapterCreate + "/" + encodeURIComponent(a.name);
        if (force) url += "?force=true";
        var data = await api("DELETE", url);
        await loadAdapterFiles();
        await loadAdapterCapabilities();
        selectedAdapterEntry = null;
        render(container);
        if (data.reload_error) showError(data.message);
        else showStatus(data.message);
      }

      deleteBtn.addEventListener("click", function () {
        requireTypedConfirmation({
          title: "Delete Adapter",
          message: "Delete adapter '" + a.name + "'? This removes it from "
            + a.filename + " and from the running server. This cannot be undone.",
          expectedText: a.name,
          confirmLabel: "Delete",
          onConfirm: async function () {
            try {
              await doDeleteAdapter(false);
            } catch (err) {
              if (!/still referenced by/i.test(err.message)) throw err;
              requireTypedConfirmation({
                title: "Adapter Still Referenced",
                message: err.message + " Deleting anyway will break them.",
                expectedText: a.name,
                confirmLabel: "Delete Anyway",
                onConfirm: function () { return doDeleteAdapter(true); }
              });
            }
          }
        });
      });

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
          var data = await api("GET", endpoints.adapterConfigs + "/entry/" + encodeURIComponent(a.name));
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
          await api("PUT", endpoints.adapterConfigs + "/entry/" + encodeURIComponent(a.name), { content: adapterEditor.getValue() });
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

      // Reload adapter (hot-swap via existing endpoint) — triggered automatically after save
      async function doReloadAdapter() {
        await withButton(saveBtn, async function () {
          var path = endpoints.reloadAdapters + "/async?adapter_name=" + encodeURIComponent(a.name);
          var started = await api("POST", path);
          await waitForAdminJob(started.job_id, "Reloading adapter…");
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
            loadingLabel: "Reloading…",
            onConfirm: async function () {
              var path = endpoints.reloadTemplates + "/async?adapter_name=" + encodeURIComponent(a.name);
              var started = await api("POST", path);
              await waitForAdminJob(started.job_id, "Reloading templates…");
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

    function scoreBadgeClass(score) {
      if (score >= 0.7) return "monitoring-badge green";
      if (score >= 0.4) return "monitoring-badge amber";
      return "monitoring-badge red";
    }

    function dataTable(headers, rows) {
      var table = el("table");
      table.appendChild(el("thead", null, el("tr", null, headers.map(function (h) { return el("th", null, h); }))));
      var tbody = el("tbody");
      rows.forEach(function (cells) { tbody.appendChild(el("tr", null, cells)); });
      table.appendChild(tbody);
      return el("div", { className: "table-wrap" }, table);
    }

    // Builds the Test Query form + results area inside an intent adapter's
    // detail panel. Lazily constructed on first expand of the <details> section.
    function buildTestQueryBody(section, a) {
      var queryInput = el("input", { type: "text", maxlength: "1000", style: "width:100%",
        placeholder: "Natural language query to test, e.g. \"salary stats for engineering\"" });
      var maxTemplatesInput = el("input", { type: "number", value: "5", min: "1", max: "20", style: "width:70px" });
      var executeLabel = el("label", { className: "adapter-checkbox-field" },
        el("input", { type: "checkbox", checked: "checked" }), el("span", null, "Execute"));
      var verboseLabel = el("label", { className: "adapter-checkbox-field" },
        el("input", { type: "checkbox" }), el("span", null, "Verbose"));
      var allCandidatesLabel = el("label", { className: "adapter-checkbox-field" },
        el("input", { type: "checkbox" }), el("span", null, "All candidates"));
      var executeInput = executeLabel.querySelector("input");
      var verboseInput = verboseLabel.querySelector("input");
      var allCandidatesInput = allCandidatesLabel.querySelector("input");
      var runBtn = el("button", { type: "button", className: "secondary" }, "Run");
      var resultsContainer = el("div", { style: "margin-top:var(--sp-3)" });

      section.appendChild(el("p", { className: "muted", style: "margin:var(--sp-2) 0" },
        "Runs matching, parameter extraction, and (optionally) execution against this adapter's "
        + "templates without the full LLM pipeline."));
      section.appendChild(el("div", { className: "admin-create-form-grid" },
        field("Query", queryInput),
        field("Max candidates", maxTemplatesInput)
      ));
      section.appendChild(el("div", {
        style: "display:flex;flex-wrap:wrap;gap:var(--sp-3);align-items:center;margin:var(--sp-2) 0"
      }, executeLabel, verboseLabel, allCandidatesLabel, runBtn));
      section.appendChild(resultsContainer);

      function runTest() {
        var query = queryInput.value.trim();
        if (!query) { showError("Enter a query to test."); return; }
        withButton(runBtn, async function () {
          clear(resultsContainer);
          resultsContainer.appendChild(skeleton());
          var data;
          try {
            data = await api("POST", endpoints.adapterCreate + "/" + encodeURIComponent(a.name) + "/test-query", {
              query: query,
              max_templates: parseInt(maxTemplatesInput.value, 10) || 5,
              execute: executeInput.checked,
              include_all_candidates: allCandidatesInput.checked,
              verbose: verboseInput.checked,
            });
          } catch (err) {
            clear(resultsContainer);
            resultsContainer.appendChild(el("div", { className: "empty-state" },
              el("p", null, "Test query failed: " + err.message)));
            return;
          }
          clear(resultsContainer);
          renderTestQueryResults(resultsContainer, data);
        });
      }

      runBtn.addEventListener("click", runTest);
      queryInput.addEventListener("keydown", function (e) { if (e.key === "Enter") runTest(); });

      // Returned so the Misses panel can jump a stored miss straight into a re-test.
      return function runWithQuery(query) {
        queryInput.value = query;
        runTest();
      };
    }

    // Builds the Misses list inside an intent adapter's detail panel: queries
    // that failed to match (or matched below threshold), most recent first.
    // onTestInDiagnostics(query) is called when the user clicks "Test in
    // diagnostics" on a row. Constructs the DOM once and loads data
    // immediately; returns the load function so the caller can re-invoke it
    // on every reopen without rebuilding the DOM, keeping the list fresh.
    function buildMissesBody(section, a, onTestInDiagnostics) {
      var resultsContainer = el("div", { style: "margin-top:var(--sp-2)" });
      section.appendChild(el("p", { className: "muted", style: "margin:var(--sp-2) 0" },
        "Queries that found no matching template, or couldn't extract required parameters, "
        + "for this adapter. In-memory only — cleared on server restart."));
      section.appendChild(resultsContainer);

      async function load() {
        clear(resultsContainer);
        resultsContainer.appendChild(skeleton());
        var data;
        try {
          data = await api("GET", endpoints.adapterCreate + "/" + encodeURIComponent(a.name) + "/misses");
        } catch (err) {
          clear(resultsContainer);
          resultsContainer.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Failed to load misses: " + err.message)));
          return;
        }
        clear(resultsContainer);
        var misses = data.misses || [];
        if (!misses.length) {
          resultsContainer.appendChild(el("p", { className: "muted" }, "No misses recorded yet."));
          return;
        }
        resultsContainer.appendChild(dataTable(
          ["Query", "Reason", "Candidates", "When", ""],
          misses.map(function (m) {
            var candidates = (m.candidates || []).map(function (c) {
              return c.template_id + (typeof c.similarity === "number" ? " (" + c.similarity.toFixed(3) + ")" : "");
            }).join(", ");
            var testBtn = el("button", { className: "secondary", type: "button" }, "Test in diagnostics");
            testBtn.addEventListener("click", function () { onTestInDiagnostics(m.query); });
            return [
              el("td", null, m.query),
              el("td", { className: "muted" }, m.reason),
              el("td", { className: "muted" }, candidates || "—"),
              el("td", { className: "muted" }, m.timestamp ? new Date(m.timestamp * 1000).toLocaleString() : ""),
              el("td", null, testBtn),
            ];
          })
        ));
      }

      load();
      return load; // caller re-invokes this on every reopen to refresh the list
    }

    function renderTestQueryResults(container, data) {
      var timing = data.timing || {};
      if (Object.keys(timing).length) {
        var timingParts = Object.keys(timing).map(function (k) {
          return k.replace(/_ms$/, "").replace(/_/g, " ") + ": " + timing[k] + "ms";
        });
        container.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" }, timingParts.join(" · ")));
      }

      var search = data.template_search;
      if (search) {
        container.appendChild(el("h4", null,
          "Template candidates (" + (search.candidates_found || 0) + " found, threshold "
          + search.confidence_threshold + ")"));
        if (search.error) {
          container.appendChild(el("p", null, search.error));
        } else if ((search.candidates || []).length) {
          container.appendChild(dataTable(
            ["Score", "Template", "Description"],
            search.candidates.map(function (c) {
              var sim = c.similarity || 0;
              var badge = el("span", { className: scoreBadgeClass(sim) }, sim.toFixed(4));
              var rescued = c.rescued_by_nl_example
                ? el("span", { className: "muted", style: "margin-left:6px" }, "(rescued)")
                : null;
              return [
                el("td", null, badge, rescued),
                el("td", null, c.template_id || "?"),
                el("td", { className: "muted" }, c.description || "")
              ];
            })
          ));
        } else {
          container.appendChild(el("p", { className: "muted" }, "No candidates found."));
        }
      }

      var reranking = data.reranking;
      if (reranking && reranking.applied && (reranking.reranked_scores || []).length) {
        container.appendChild(el("h4", null, "Reranking" + (reranking.order_changed ? " (order changed)" : "")));
        container.appendChild(dataTable(
          ["Template", "Original", "Boost", "Final"],
          reranking.reranked_scores.slice(0, 5).map(function (entry) {
            var boost = entry.boost || 0;
            return [
              el("td", null, entry.template_id || "?"),
              el("td", null, (entry.original_similarity || 0).toFixed(4)),
              el("td", null, boost > 0 ? "+" + boost.toFixed(3) : "0"),
              el("td", null, (entry.final_similarity || 0).toFixed(4))
            ];
          })
        ));
      }

      var selected = data.selected_template;
      if (selected) {
        container.appendChild(el("h4", null, "Selected template"));
        if (selected.error) {
          container.appendChild(el("p", null, selected.error
            + (selected.best_score != null ? " (best score: " + selected.best_score + ")" : "")));
        } else {
          container.appendChild(el("p", null,
            el("strong", null, selected.template_id || "?"),
            " — similarity " + (selected.similarity || 0).toFixed(4)
          ));
          if (selected.description) container.appendChild(el("p", { className: "muted" }, selected.description));
        }
      }

      var extraction = data.parameter_extraction;
      if (extraction) {
        container.appendChild(el("h4", null, "Parameter extraction (" + (extraction.method || "?") + ")"));
        if (extraction.error) container.appendChild(el("p", null, extraction.error));
        var extracted = extraction.extracted || {};
        if (Object.keys(extracted).length) {
          container.appendChild(dataTable(
            ["Parameter", "Value"],
            Object.keys(extracted).map(function (k) {
              return [el("td", null, k), el("td", null, String(extracted[k]))];
            })
          ));
        } else {
          container.appendChild(el("p", { className: "muted" }, "No parameters extracted."));
        }
        (extraction.validation_errors || []).forEach(function (err) {
          container.appendChild(el("p", { style: "color:#bd3f4d" }, "Validation: " + err));
        });
      }

      var rendered = data.rendered_query;
      if (rendered) {
        container.appendChild(el("h4", null, "Rendered query"));
        if (rendered.error) container.appendChild(el("p", null, rendered.error));
        var queryText = rendered.query || rendered.endpoint || rendered.raw_template;
        if (queryText) container.appendChild(el("pre", null, String(queryText)));
        var params = rendered.parameters || rendered.variables;
        if (params && Object.keys(params).length) {
          container.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
            "Parameters: " + JSON.stringify(params)));
        }
      }

      var tried = data.templates_tried;
      if (tried && tried.length > 1) {
        container.appendChild(el("h4", null, "Templates tried (" + tried.length + ")"));
        container.appendChild(dataTable(
          ["Outcome", "Template", "Score", "Detail"],
          tried.map(function (entry) {
            var detail = entry.detail || (entry.outcome === "success" ? (entry.row_count || 0) + " rows" : "");
            return [
              el("td", null, entry.outcome || "?"),
              el("td", null, entry.template_id || "?"),
              el("td", null, (entry.similarity || 0).toFixed(4)),
              el("td", { className: "muted" }, detail)
            ];
          })
        ));
      }

      var execution = data.execution;
      if (execution) {
        container.appendChild(el("h4", null, "Execution"));
        if (execution.error) container.appendChild(el("p", null, execution.error));
        container.appendChild(el("p", { className: "muted" },
          (execution.success ? "Success" : "Failed") + " — " + (execution.row_count || 0) + " rows"));
        var results = execution.results || [];
        if (results.length) {
          container.appendChild(el("pre", null, JSON.stringify(results.slice(0, 10), null, 2)));
          if (results.length > 10) {
            container.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
              "... and " + (results.length - 10) + " more rows"));
          }
        }
      } else if (selected && !selected.error) {
        container.appendChild(el("p", { className: "muted" }, "(execution skipped)"));
      }

      // Verbose diagnostics
      var vsInfo = data.vector_store_info;
      if (vsInfo && !vsInfo.error) {
        container.appendChild(el("h4", null, "Vector store"));
        container.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
          "type: " + (vsInfo.store_type || "?") + " · collection: " + (vsInfo.collection_name || "?")
          + " · vectors: " + (vsInfo.total_vectors != null ? vsInfo.total_vectors : "?")
          + " · dimensions: " + (vsInfo.embedding_dimension != null ? vsInfo.embedding_dimension : "?")));
      }
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

  function dispose() {
    if (adapterEditor) { adapterEditor.destroy(); adapterEditor = null; }
    if (adapterPreviewEditor) { adapterPreviewEditor.destroy(); adapterPreviewEditor = null; }
    if (importEditor) { importEditor.destroy(); importEditor = null; }
  }

  return { render, dispose };
}
