// Tool Skills admin tab (docs/roadmap/mcp-tool-skills.md Phase 3).
//
// Master-detail like prompts.js: a list on the left, frontmatter fields +
// markdown body on the right. Distinct from ORBIT-skill routing
// (capabilities.expose_as_skill, e.g. "mcp-agent") — these are SKILL.md
// procedural playbooks bound to MCP tools via an `mcp_tools` glob list; see
// docs/roadmap/mcp-tool-skills.md §1 for the terminology split.
export function createSkillsTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton,
  svgIcon, iconPlus, iconSave, iconX,
  withButton, requireTypedConfirmation, showStatus, showTableLoadError,
  bindValidationClear, setFieldReadOnly, characterCount, createMarkdownPreview,
  onSkillsChanged, helpTooltip, tooltipField, formSection,
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
    return tooltipField("Loading priority", input, "Higher values load first. Use -1 to 99.", hintId, "skill-priority-field");
  }

  function enforcePriorityRange(input) {
    input.addEventListener("input", function () {
      // Keep "-" as a temporary value while the user types -1, but normalize
      // every other negative value immediately. The pattern remains the final
      // validation guard for programmatic changes and form submission.
      if (input.value.charAt(0) === "-" && input.value !== "-" && input.value !== "-1") {
        input.value = "-1";
      }
    });
  }

  function versionField(input, hintId) {
    return tooltipField("Version", input, "Use dotted numbers, such as 1.0 or 1.2.3.", hintId, "skill-version-field");
  }

  function enabledField(input, hintId) {
    input.id = input.id || hintId + "-input";
    input.setAttribute("aria-describedby", hintId);
    return el("div", { className: "skill-enabled-field" },
      input,
      el("label", { className: "skill-enabled-title", htmlFor: input.id }, "Enabled"),
      helpTooltip("Enabled", "Makes this skill available to load.", hintId)
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

    var skillsRefreshBtn = refreshButton("Refresh the skill list", function () { refreshSkills(); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Skills"),
      skillsRefreshBtn
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
      // A text input is intentional: number inputs ignore maxlength, allowing
      // arbitrarily long values to be typed despite their min/max attributes.
      type: "text", value: "0", maxlength: "2", inputmode: "numeric",
      pattern: "(?:-1|[0-9]|[1-9][0-9])", title: "Enter a whole number from −1 to 99.",
      style: "max-width:5.5rem", "aria-describedby": "skill-priority-help", autocomplete: "off"
    });
    enforcePriorityRange(priorityInput);
    var bodyArea = el("textarea", { rows: "8", required: "true", maxlength: String(BODY_MAX) });
    var bodyCounter = characterCount(bodyArea, BODY_MAX);
    var createBtn = el("button", { type: "button" }, "Create Skill");

    function openCreatePanel() {
      createPanel.style.display = "";
      if (!selectedSkill) detailPanel.style.display = "none";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function closeCreatePanel() { createPanel.style.display = "none"; }
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");
    createPanelToggle.addEventListener("click", closeCreatePanel);
    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New Skill"),
      createPanelToggle
    ));
    bodyArea.className = "skill-body-input";
    createPanel.appendChild(el("div", { className: "admin-create-form skill-form" },
      formSection("Basics", "Identify this playbook and control when it loads.",
        el("div", { className: "skill-basics-grid" },
          tooltipField("Name", nameInput, "Use lowercase letters, numbers, and hyphens.", "skill-name-help", "skill-name-field"),
          versionField(versionInput, "skill-version-help"),
          priorityField(priorityInput, "skill-priority-help"),
          el("div", { className: "stack skill-description-field" },
            tooltipField("Description", descInput, "Explain when this playbook should be used.", "skill-description-help"),
            descCounter
          )
        )
      ),
      formSection("Tool matching", "Choose the MCP tools that make this playbook relevant.",
        tooltipField("MCP tools", toolsInput, "Enter comma-separated glob patterns; up to 64 patterns and 256 characters per pattern.", "skill-tools-help")
      ),
      formSection("Instructions", "Write the procedural guidance the model should follow.",
        el("div", { className: "stack" }, tooltipField("Playbook body", bodyArea, "Supports Markdown; 24 KB UTF-8 maximum.", "skill-body-help"), bodyCounter)
      ),
      el("div", { className: "admin-create-form-actions" }, createBtn)
    ));
    bindValidationClear(nameInput, descInput, versionInput, priorityInput, toolsInput, bodyArea);

    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create skill",
    }, svgIcon(iconPlus), el("span", null, "Create Skill"));
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
      }, "Skill created");
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
        showTableLoadError(tableWrap, "Failed to load skills");
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
        el("p", null, "No skills found")
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
    var priorityInput = el("input", {
      type: "text", value: originalPriority, maxlength: "2", inputmode: "numeric",
      pattern: "(?:-1|[0-9]|[1-9][0-9])", title: "Enter a whole number from −1 to 99.",
      style: "max-width:5.5rem", readonly: "true", "aria-readonly": "true",
      "aria-describedby": "skill-priority-help-edit", autocomplete: "off"
    });
    enforcePriorityRange(priorityInput);
    var enabledInput = el("input", { type: "checkbox" });
    enabledInput.checked = originalEnabled;
    enabledInput.disabled = true;
    var bodyArea = el("textarea", { rows: "10", maxlength: String(BODY_MAX), readonly: "true", "aria-readonly": "true" }, originalBody);
    bodyArea.className = "skill-body-input";
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
      }, "Skill updated");
    });

    var editPreview = createMarkdownPreview(bodyArea);
    var editorWrap = el("div", { className: "prompt-editor-pane skill-form", style: "display:none" },
      formSection("Basics", "Identify this playbook and control when it loads.",
        el("div", { className: "skill-basics-grid skill-basics-grid-edit" },
          tooltipField("Name", nameInput, "Use lowercase letters, numbers, and hyphens.", "skill-name-help-edit", "skill-name-field"),
          versionField(versionInput, "skill-version-help-edit"),
          priorityField(priorityInput, "skill-priority-help-edit"),
          enabledField(enabledInput, "skill-enabled-help-edit"),
          el("div", { className: "stack skill-description-field" },
            tooltipField("Description", descInput, "Explain when this playbook should be used.", "skill-description-help-edit"),
            descCounter
          )
        )
      ),
      formSection("Tool matching", "Choose the MCP tools that make this playbook relevant.",
        tooltipField("MCP tools", toolsInput, "Enter comma-separated glob patterns; up to 64 patterns and 256 characters per pattern.", "skill-tools-help-edit")
      ),
      formSection("Instructions", "Write the procedural guidance the model should follow.",
        el("div", { className: "stack" }, tooltipField("Playbook body", bodyArea, "Supports Markdown; 24 KB UTF-8 maximum.", "skill-body-help-edit"), bodyCounter)
      )
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Skill");
    var cancelBtn = el("button", {
      className: "secondary", type: "button", style: "display:none",
      "aria-label": "Cancel editing skill", title: "Cancel editing skill",
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
    var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete Skill");
    deleteBtn.addEventListener("click", function () {
      requireTypedConfirmation({
        title: "Delete Skill",
        message: 'Delete skill "' + skill.name + '"? This cannot be undone.',
        expectedText: skill.name,
        confirmLabel: "Delete",
        onConfirm: async function () {
          await api("DELETE", endpoints.skills + "/" + encodeURIComponent(skill.id));
          notifySkillsChanged();
          showStatus("Skill deleted");
          onRefresh(null);
        }
      });
    });
    panel.appendChild(el("div", { className: "danger-zone" },
      el("p", null, "Deleting a database skill restores the on-disk SKILL.md of the same name, if one exists."),
      deleteBtn
    ));
  }

  return { render };
}
