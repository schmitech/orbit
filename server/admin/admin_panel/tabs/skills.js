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
  var BODY_MAX = 32 * 1024;
  var cachedSkills = null;

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
      "A skill with the same name as one under config/skills/ overrides it here."
    ));

    var nameInput = el("input", { type: "text", required: "true", maxlength: "64", placeholder: "my-tool-playbook" });
    var descInput = el("input", { type: "text", required: "true", maxlength: "500" });
    var toolsInput = el("input", { type: "text", required: "true", placeholder: "business-sample__list_customers, business-sample__get_customer_health" });
    var priorityInput = el("input", { type: "number", value: "0" });
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
      el("div", { className: "admin-create-form-grid persona-create-grid" },
        field("Name (lowercase-slug)", nameInput),
        field("Description", descInput),
        field("Priority", priorityInput)
      ),
      field("mcp_tools (comma-separated glob patterns)", toolsInput),
      el("div", { className: "stack" }, field("Playbook body (markdown)", bodyArea), bodyCounter),
      el("div", { className: "admin-create-form-actions" }, createBtn)
    ));
    bindValidationClear(nameInput, descInput, toolsInput, bodyArea);

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
      if (!name || !description || !mcpTools.length || !body) return;
      withButton(createBtn, async function () {
        var created = await api("POST", endpoints.skills, {
          name: name,
          description: description,
          mcp_tools: mcpTools,
          body: body,
          priority: parseInt(priorityInput.value, 10) || 0,
        });
        nameInput.value = "";
        descInput.value = "";
        toolsInput.value = "";
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
    var originalTools = (skill.mcp_tools || []).join(", ");
    var originalPriority = String(skill.priority);
    var originalEnabled = !!skill.enabled;
    var originalBody = skill.body || "";
    var isEditing = false;

    var descInput = el("input", { type: "text", value: originalDesc, maxlength: "500", readonly: "true", "aria-readonly": "true" });
    var toolsInput = el("input", { type: "text", value: originalTools, readonly: "true", "aria-readonly": "true" });
    var priorityInput = el("input", { type: "number", value: originalPriority, readonly: "true", "aria-readonly": "true" });
    var enabledInput = el("input", { type: "checkbox" });
    enabledInput.checked = originalEnabled;
    enabledInput.disabled = true;
    var bodyArea = el("textarea", { rows: "10", maxlength: String(BODY_MAX), readonly: "true", "aria-readonly": "true" }, originalBody);
    var bodyCounter = characterCount(bodyArea, BODY_MAX);

    var saveBtn = el("button", {
      type: "button", className: "btn--icon", "aria-label": "Save changes", title: "Save changes",
    }, svgIcon(iconSave));
    saveBtn.style.display = "none";
    saveBtn.addEventListener("click", function () {
      if (saveBtn.disabled) return;
      withButton(saveBtn, async function () {
        var updated = await api("PUT", endpoints.skills + "/" + encodeURIComponent(skill.id), {
          description: descInput.value.trim(),
          mcp_tools: parseToolsList(toolsInput.value),
          body: bodyArea.value.trim(),
          priority: parseInt(priorityInput.value, 10) || 0,
          enabled: enabledInput.checked,
        });
        notifySkillsChanged();
        onRefresh(updated ? updated.id : skill.id);
      }, "Tool skill updated");
    });

    var editPreview = createMarkdownPreview(bodyArea);
    var editorWrap = el("div", { className: "prompt-editor-pane", style: "display:none" },
      el("div", { className: "admin-create-form-grid persona-create-grid" },
        field("Description", descInput),
        field("Priority", priorityInput),
        field("Enabled", enabledInput)
      ),
      field("mcp_tools (comma-separated)", toolsInput),
      el("div", { className: "stack" }, field("Playbook body (markdown)", bodyArea), bodyCounter)
    );
    var previewWrap = el("div", { className: "prompt-preview-pane" }, editPreview);
    var editToggle = el("button", { className: "secondary", type: "button" }, "Edit Tool Skill");
    var cancelBtn = el("button", {
      className: "secondary btn--icon", type: "button", style: "display:none",
      "aria-label": "Cancel editing tool skill", title: "Cancel editing tool skill",
    }, svgIcon(iconX));

    function hasChanges() {
      return descInput.value.trim() !== originalDesc
        || toolsInput.value.trim() !== originalTools
        || priorityInput.value.trim() !== originalPriority
        || enabledInput.checked !== originalEnabled
        || bodyArea.value !== originalBody;
    }
    function syncSaveState() { saveBtn.disabled = !isEditing || !hasChanges(); }
    function setEditMode(editing) {
      isEditing = editing;
      setFieldReadOnly(descInput, editing);
      setFieldReadOnly(toolsInput, editing);
      setFieldReadOnly(priorityInput, editing);
      enabledInput.disabled = !editing;
      setFieldReadOnly(bodyArea, editing);
      editorWrap.style.display = editing ? "block" : "none";
      previewWrap.style.display = editing ? "none" : "block";
      editToggle.style.display = editing ? "none" : "inline-flex";
      cancelBtn.style.display = editing ? "inline-flex" : "none";
      saveBtn.style.display = editing ? "inline-flex" : "none";
      syncSaveState();
    }
    editToggle.addEventListener("click", function () { setEditMode(true); });
    cancelBtn.addEventListener("click", function () {
      descInput.value = originalDesc;
      toolsInput.value = originalTools;
      priorityInput.value = originalPriority;
      enabledInput.checked = originalEnabled;
      bodyArea.value = originalBody;
      bodyArea.dispatchEvent(new Event("input"));
      setEditMode(false);
    });
    [descInput, toolsInput, priorityInput, bodyArea].forEach(function (input) {
      input.addEventListener("input", syncSaveState);
    });
    enabledInput.addEventListener("change", syncSaveState);
    bindValidationClear(descInput, toolsInput, priorityInput, bodyArea);
    syncSaveState();

    panel.appendChild(el("div", { className: "stack", style: "margin-top:var(--sp-3)" },
      el("div", { className: "inline-form" }, editToggle, cancelBtn, saveBtn),
      previewWrap,
      editorWrap
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
