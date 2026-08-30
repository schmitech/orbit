// Tool Skills admin tab (docs/roadmap/mcp-tool-skills.md Phase 3).
//
// Master-detail like prompts.js: a list on the left, frontmatter fields +
// markdown body on the right. Distinct from ORBIT-skill routing
// (capabilities.expose_as_skill, e.g. "mcp-agent") — these are SKILL.md
// procedural playbooks bound to MCP tools via an `mcp_tools` glob list; see
// docs/roadmap/mcp-tool-skills.md §1 for the terminology split.
export function createSkillsTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton, field,
  svgIcon, iconPlus, iconSave, iconX,
  withButton, requireTypedConfirmation, showStatus, showTableLoadError,
  bindValidationClear, setFieldReadOnly, characterCount, createMarkdownPreview,
  onSkillsChanged,
}) {
  var BODY_MAX = 24 * 1024;
  var cachedSkills = null;

  function reportFirstInvalid(inputs) {
    for (var i = 0; i < inputs.length; i += 1) {
      if (!inputs[i].checkValidity()) {
        inputs[i].reportValidity();
        return true;
      }
    }
    return false;
  }

  function priorityField(input, hintId) {
    return el("label", { className: "stack skill-priority-field" },
      el("span", null, "Priority"),
      el("span", { className: "skill-priority-control" },
        input,
        el("span", { id: hintId, className: "field-hint" }, "−1 is the lowest priority; higher values appear first.")
      )
    );
  }

  function enabledField(input) {
    return el("label", { className: "skill-enabled-field" },
      el("span", null, "Enabled"),
      input
    );
  }

  function notifySkillsChanged() {
    // The MCP tab's per-server "Playbooks" cross-reference fetches the skill
    // list once and caches it (mcp.js) — invalidate it on every create/
    // update/delete so it doesn't keep showing a stale skill set after a
    // CRUD operation here.
    if (typeof onSkillsChanged === "function") onSkillsChanged();
  }
  var selectedSkill = null;

  async function render(container) {
    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(createPanel);
    container.appendChild(layout);

    var skillsRefreshBtn = refreshButton("Refresh the tool skill list", function () { refreshSkills(); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Tool Skills"),
      skillsRefreshBtn
    ));
    listPanel.appendChild(el("p", { className: "field-hint" },
      "Procedural SKILL.md playbooks bound to MCP tools via an mcp_tools glob list. ",
      "A database skill with the same name as one under config/skills/ overrides the file at runtime; disabling or deleting it restores the file. ",
      "Up to 10,000 skills may be enabled; disabled drafts can be staged beyond that limit. "
    ));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "64", placeholder: "my-tool-playbook" });
    var descInput = el("textarea", {
      rows: "3", required: "true", maxlength: "500",
      placeholder: "Explain when this playbook should be used and what it helps accomplish."
    });
    var descCounter = characterCount(descInput, 500);
    var toolsInput = el("input", { type: "text", required: "true", maxlength: "16510", placeholder: "business-sample__list_customers, business-sample__get_customer_health" });
    var versionInput = el("input", {
      type: "text", value: "1.0", maxlength: "25", placeholder: "1.0", inputmode: "decimal",
      pattern: "\\d+(?:\\.\\d+)*", title: "Use numbers separated by dots, for example 1.0 or 1.2.3.", spellcheck: "false"
    });
    var priorityInput = el("input", {
      type: "number", value: "0", min: "-1", max: "99", step: "1", inputmode: "numeric",
      style: "max-width:5.5rem", "aria-describedby": "skill-priority-help"
    });
    var bodyArea = el("textarea", { rows: "8", required: "true", maxlength: String(BODY_MAX) });
    var bodyCounter = characterCount(bodyArea, BODY_MAX);
    var createBtn = el("button", { type: "button" }, "Create Tool Skill");

    function openCreatePanel() {
      createPanel.style.display = "";
      if (!selectedSkill) detailPanel.style.display = "none";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function closeCreatePanel() { createPanel.style.display = "none"; }
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");
    createPanelToggle.addEventListener("click", closeCreatePanel);
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New Tool Skill"),
      createPanelToggle
    ));
    createPanel.appendChild(el("div", { className: "admin-create-form" },
      el("div", { className: "skill-name-field" }, field("Name (lowercase-slug)", nameInput)),
      el("div", { className: "stack" },
        field("Description", descInput),
        descCounter
      ),
      el("div", { className: "skill-metadata-row" },
        field("Version (up to 25 characters)", versionInput),
        priorityField(priorityInput, "skill-priority-help")
      ),
      field("mcp_tools (comma-separated; max 64 patterns, 256 chars each)", toolsInput),
      el("div", { className: "stack" }, field("Playbook body (markdown; 24 KB UTF-8 max)", bodyArea), bodyCounter),
      el("div", { className: "admin-create-form-actions" }, createBtn)
    ));
    bindValidationClear(nameInput, descInput, versionInput, priorityInput, toolsInput, bodyArea);

    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create tool skill",
    }, svgIcon(iconPlus), el("span", null, "Create Tool Skill"));
    createLaunchBtn.addEventListener("click", openCreatePanel);
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn));

    var tableWrap = el("div", null, skeleton());
    listPanel.appendChild(tableWrap);

    createBtn.addEventListener("click", function () {
      var name = nameInput.value.trim();
      var description = descInput.value.trim();
      var mcpTools = parseToolsList(toolsInput.value);
      var body = bodyArea.value.trim();
      if (reportFirstInvalid([nameInput, descInput, versionInput, priorityInput, toolsInput, bodyArea])) return;
      if (!name || !description || !mcpTools.length || !body) return;
      withButton(createBtn, async function () {
        var created = await api("POST", endpoints.skills, {
          name: name,
          description: description,
          mcp_tools: mcpTools,
          body: body,
          version: versionInput.value.trim() || null,
          priority: parseInt(priorityInput.value, 10) || 0,
        });
        nameInput.value = "";
        descInput.value = "";
        toolsInput.value = "";
        versionInput.value = "1.0";
        priorityInput.value = "0";
        bodyArea.value = "";
        bodyArea.dispatchEvent(new Event("input"));
        closeCreatePanel();
        notifySkillsChanged();
        await refreshSkills(created ? created.id : null);
      }, "Tool skill created");
    });

    async function refreshSkills(selectedId) {
      try {
        var skills = await api("GET", endpoints.skills);
        cachedSkills = skills || [];
        renderSkillTable(tableWrap, cachedSkills, detailPanel, refreshSkills);
        var activeId = selectedId || (selectedSkill && selectedSkill.id);
        if (activeId) {
          var match = cachedSkills.find(function (s) { return s.id === activeId; });
          if (match) {
            selectedSkill = match;
            renderSkillDetail(detailPanel, match, function (nextId) { refreshSkills(nextId || activeId); });
            return;
          }
        }
        selectedSkill = null;
        clear(detailPanel);
        detailPanel.style.display = "none";
      } catch (err) {
        showTableLoadError(tableWrap, "Failed to load tool skills");
      }
    }

    refreshSkills();
  }

  function parseToolsList(raw) {
    return (raw || "")
      .split(",")
      .map(function (t) { return t.trim(); })
      .filter(Boolean);
  }

  function renderSkillTable(wrap, skills, detailPanel, refreshSkills) {
    clear(wrap);
    if (!skills || skills.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F4D8}"),
        el("p", null, "No tool skills found")
      ));
      return;
    }
    var table = el("table");
    var thead = el("thead", null, el("tr", null,
      el("th", null, "Name"),
      el("th", null, "Description"),
      el("th", null, "Priority"),
      el("th", null, "Enabled"),
    ));
    var tbody = el("tbody");
    skills.forEach(function (s) {
      var isSelected = selectedSkill && selectedSkill.id === s.id;
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
      },
        el("td", null, el("code", { className: "plain-code" }, s.name)),
        el("td", null, s.description),
        el("td", null, String(s.priority)),
        el("td", null, s.enabled ? "Yes" : "No"),
      );
      tr.addEventListener("click", function () {
        selectedSkill = s;
        renderSkillTable(wrap, skills, detailPanel, refreshSkills);
        renderSkillDetail(detailPanel, s, function (nextId) { refreshSkills(nextId || s.id); });
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(wrapTable(table));
  }

  function renderSkillDetail(panel, skill, onRefresh) {
    clear(panel);
    panel.style.display = "";
    panel.appendChild(el("h2", null, skill.name));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Name:"), " ", el("code", { className: "plain-code" }, skill.name)),
      el("p", null, el("strong", null, "ID:"), " ", el("code", { className: "plain-code" }, skill.id)),
      el("p", null, el("strong", null, "mcp_tools:"), " " + skill.mcp_tools.join(", ")),
    ));

    var originalDesc = skill.description || "";
    var originalName = skill.name || "";
    var originalTools = (skill.mcp_tools || []).join(", ");
    var originalPriority = String(skill.priority);
    var originalEnabled = !!skill.enabled;
    var originalBody = skill.body || "";
    var isEditing = false;

    var nameInput = el("input", {
      type: "text", value: originalName, required: "true", maxlength: "64", readonly: "true", "aria-readonly": "true",
      pattern: "[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", title: "Use a lowercase slug with letters, numbers, and hyphens."
    });
    // Unlike <input>, a textarea's initial content is text/value property,
    // not a `value` HTML attribute. Set it directly so saved descriptions
    // reappear when this detail panel is opened again.
    var descInput = el("textarea", { rows: "3", maxlength: "500", readonly: "true", "aria-readonly": "true" });
    descInput.value = originalDesc;
    var descCounter = characterCount(descInput, 500);
    var toolsInput = el("input", { type: "text", maxlength: "16510", value: originalTools, readonly: "true", "aria-readonly": "true" });
    var originalVersion = skill.version || "";
    var versionInput = el("input", {
      type: "text", value: originalVersion, maxlength: "25", readonly: "true", "aria-readonly": "true",
      inputmode: "decimal", pattern: "\\d+(?:\\.\\d+)*", title: "Use numbers separated by dots, for example 1.0 or 1.2.3.", spellcheck: "false"
    });
    var priorityInput = el("input", { type: "number", value: originalPriority, min: "-1", max: "99", step: "1", inputmode: "numeric", style: "max-width:5.5rem", readonly: "true", "aria-readonly": "true" });
    var enabledInput = el("input", { type: "checkbox" });
    enabledInput.checked = originalEnabled;
    enabledInput.disabled = true;
    var bodyArea = el("textarea", { rows: "10", maxlength: String(BODY_MAX), readonly: "true", "aria-readonly": "true" }, originalBody);
    var bodyCounter = characterCount(bodyArea, BODY_MAX);

    var saveBtn = el("button", {
      type: "button", "aria-label": "Save changes", title: "Save changes",
    }, svgIcon(iconSave), "Save changes");
    saveBtn.style.display = "none";
    saveBtn.addEventListener("click", function () {
      if (saveBtn.disabled) return;
      if (reportFirstInvalid([nameInput, descInput, versionInput, priorityInput, toolsInput, bodyArea])) return;
      withButton(saveBtn, async function () {
        var updated = await api("PUT", endpoints.skills + "/" + encodeURIComponent(skill.id), {
          name: nameInput.value.trim(),
          description: descInput.value.trim(),
          mcp_tools: parseToolsList(toolsInput.value),
          body: bodyArea.value.trim(),
          version: versionInput.value.trim() || null,
          priority: parseInt(priorityInput.value, 10) || 0,
          enabled: enabledInput.checked,
        });
        notifySkillsChanged();
        onRefresh(updated ? updated.id : skill.id);
      }, "Tool skill updated");
    });

    var editPreview = createMarkdownPreview(bodyArea);
    var editorWrap = el("div", { className: "prompt-editor-pane", style: "display:none" },
      el("div", { className: "skill-name-field" }, field("Name (lowercase-slug)", nameInput)),
      el("div", { className: "stack" },
        field("Description", descInput),
        descCounter
      ),
      el("div", { className: "skill-metadata-row" },
        field("Version (up to 25 characters)", versionInput),
        priorityField(priorityInput, null),
        enabledField(enabledInput)
      ),
      field("mcp_tools (comma-separated; max 64 patterns, 256 chars each)", toolsInput),
      el("div", { className: "stack" }, field("Playbook body (markdown; 24 KB UTF-8 max)", bodyArea), bodyCounter)
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Tool Skill");
    var cancelBtn = el("button", {
      className: "secondary", type: "button", style: "display:none",
      "aria-label": "Cancel editing tool skill", title: "Cancel editing tool skill",
    }, svgIcon(iconX), "Cancel");
    var editActions = el("div", { className: "admin-create-form-actions skill-edit-actions", style: "display:none" }, cancelBtn, saveBtn);

    function hasChanges() {
      return nameInput.value.trim() !== originalName
        || descInput.value.trim() !== originalDesc
        || toolsInput.value.trim() !== originalTools
        || versionInput.value.trim() !== originalVersion
        || priorityInput.value.trim() !== originalPriority
        || enabledInput.checked !== originalEnabled
        || bodyArea.value !== originalBody;
    }
    function syncSaveState() { saveBtn.disabled = !isEditing || !hasChanges(); }
    function setEditMode(editing) {
      isEditing = editing;
      setFieldReadOnly(nameInput, editing);
      setFieldReadOnly(descInput, editing);
      setFieldReadOnly(toolsInput, editing);
      setFieldReadOnly(versionInput, editing);
      setFieldReadOnly(priorityInput, editing);
      enabledInput.disabled = !editing;
      setFieldReadOnly(bodyArea, editing);
      editorWrap.style.display = editing ? "block" : "none";
      previewWrap.style.display = editing ? "none" : "block";
      editToggle.style.display = editing ? "none" : "inline-flex";
      cancelBtn.style.display = editing ? "inline-flex" : "none";
      saveBtn.style.display = editing ? "inline-flex" : "none";
      editActions.style.display = editing ? "flex" : "none";
      syncSaveState();
    }
    editToggle.addEventListener("click", function () { setEditMode(true); });
    cancelBtn.addEventListener("click", function () {
      nameInput.value = originalName;
      descInput.value = originalDesc;
      toolsInput.value = originalTools;
      versionInput.value = originalVersion;
      priorityInput.value = originalPriority;
      enabledInput.checked = originalEnabled;
      bodyArea.value = originalBody;
      bodyArea.dispatchEvent(new Event("input"));
      setEditMode(false);
    });
    [nameInput, descInput, toolsInput, versionInput, priorityInput, bodyArea].forEach(function (input) {
      input.addEventListener("input", syncSaveState);
    });
    enabledInput.addEventListener("change", syncSaveState);
    bindValidationClear(nameInput, descInput, toolsInput, versionInput, priorityInput, bodyArea);
    syncSaveState();

    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      el("div", { className: "inline-form" }, editToggle),
      previewWrap,
      editorWrap,
      editActions
    ));
    setEditMode(false);

    panel.appendChild(el("h3", null, "Danger Zone"));
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Tool Skill");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete Tool Skill",
        message: 'Delete tool skill "' + skill.name + '"? This cannot be undone.',
        expectedText: skill.name,
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", endpoints.skills + "/" + encodeURIComponent(skill.id));
          notifySkillsChanged();
          showStatus("Tool skill deleted");
          onRefresh(null);
        }
      });
    });
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Deleting a database tool skill falls back to the on-disk SKILL.md of the same name, if one exists."),
      deleteBtn
    ));
  }

  return { render };
}
