export function createUsersTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton, field, passwordField,
  svgIcon, iconPlus, iconPencil, iconSave, iconX, roleDetails, usernameMaxLength, passwordMaxLength,
  createPaginator, createColumnSorter, itemsPerPage, markSelectedRow, syncVisibleSelection,
  syncBulkActionButton, withButton, confirmAction, requireTypedConfirmation, showStatus,
  showError, showTableLoadError, validateUsername, bindValidationClear,
  createSelect, getCurrentUser
}) {
  let selectedUser = null;
  let passwordPolicy = null;
  let passwordPolicyInputs = [];
  let passwordPolicyHints = [];

  function describePasswordPolicy() {
    if (!passwordPolicy) return "Password requirements are loading.";
    var requirements = [
      "at least " + passwordPolicy.min_length + " characters",
      "at most " + passwordPolicy.max_length + " characters",
    ];
    if (passwordPolicy.require_uppercase) requirements.push("an uppercase letter");
    if (passwordPolicy.require_lowercase) requirements.push("a lowercase letter");
    if (passwordPolicy.require_digit) requirements.push("a digit");
    if (passwordPolicy.require_symbol) requirements.push("a symbol");
    requirements.push("no whitespace");
    if (passwordPolicy.reject_common_passwords) requirements.push("not a common password");
    return "Password must include " + requirements.join(", ") + ".";
  }

  function applyPasswordPolicyGuidance() {
    var description = describePasswordPolicy();
    passwordPolicyHints.forEach(function (hint) { hint.textContent = description; });
    passwordPolicyInputs.forEach(function (input) {
      input.placeholder = passwordPolicy
        ? "Meet the password requirements below"
        : "Password requirements unavailable";
    });
  }

  function validateConfiguredPassword(password) {
    if (!password) return "Password is required";
    // JavaScript character classes and string lengths cannot exactly mirror
    // Python's Unicode-aware predicates. Keep the panel advisory; the API
    // returns the authoritative aggregated policy error after submission.
    return "";
  }

  async function render(container) {
    passwordPolicyInputs = [];
    passwordPolicyHints = [];

    (async function loadPasswordPolicy() {
      try {
        passwordPolicy = await api("GET", endpoints.passwordPolicy);
      } catch (_) {
        // The server still enforces its policy and returns the complete error.
      }
      applyPasswordPolicyGuidance();
    })();

    var layout = el("div", { className: "tab-stacked-layout" });
    var listPanel = el("div", { className: "panel" });
    var detailPanel = el("div", { className: "panel", style: "display:none" });
    var accountPanel = el("div", { className: "panel account-panel" });
    var createPanel = el("div", { className: "panel", style: "display:none" });
    var allowlistPanel = el("div", { className: "panel" });
    var blacklistPanel = el("div", { className: "panel" });
    var userSearchFilter = "";
    var userSearchInteracted = false;
    var allUsers = [];
    var userFilteredEmpty = false;
    var selectedUserIds = new Set();
    var tableWrap = el("div", null, skeleton());
    var searchInput = el("input", {
      type: "search",
      name: "user-search",
      value: "",
      maxlength: "64",
      placeholder: "Search users",
      "aria-label": "Search users",
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var bulkDeleteBtn = el("button", { className: "danger", type: "button" }, "Delete Selected");
    bulkDeleteBtn.style.visibility = "hidden";
    bulkDeleteBtn.disabled = true;
    var userPaginator = createPaginator({
      pageSize: itemsPerPage,
      onPageChange: function (pageItems) {
        renderUserTable(tableWrap, pageItems, userFilteredEmpty, handleSelectUser, {
          selectedIds: selectedUserIds,
          onSelectionChange: function () {
            syncBulkActionButton(bulkDeleteBtn, selectedUserIds.size, "users");
          },
          currentUserId: getCurrentUser() && getCurrentUser().id,
          sorter: userSorter
        });
      }
    });
    var userSorter = createColumnSorter(userPaginator);

    layout.appendChild(listPanel);
    layout.appendChild(detailPanel);
    layout.appendChild(createPanel);
    // Operator-facing user management sits above "My Account", which is
    // personal and reads as the tab's footer. Allowed comes before Blocked:
    // clearance is what decides whether an account exists at all, so it reads
    // as the broader control, with the deny-list as the exception to it.
    layout.appendChild(allowlistPanel);
    layout.appendChild(blacklistPanel);
    layout.appendChild(accountPanel);
    container.appendChild(layout);

    var usersRefreshBtn = refreshButton("Refresh the user list", function () { loadUsers({}); });
    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Users"),
      usersRefreshBtn
    ));
    listPanel.appendChild(field("Search", searchInput));
    var createLaunchBtn = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": "Create user"
    }, svgIcon(iconPlus), el("span", null, "Create User"));
    listPanel.appendChild(el("div", { className: "bulk-action-row" }, createLaunchBtn, bulkDeleteBtn));
    listPanel.appendChild(tableWrap);
    listPanel.appendChild(userPaginator.getControlsEl());

    var usernameInput = el("input", {
      type: "text",
      maxlength: String(usernameMaxLength),
      placeholder: "3-50 chars. Alphanumeric and ., _, - allowed.",
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var passwordInput = el("input", {
      type: "password",
      maxlength: String(passwordMaxLength),
      placeholder: "Meet the password requirements below",
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    passwordPolicyInputs.push(passwordInput);
    var createPasswordHint = el("p", { className: "muted" }, describePasswordPolicy());
    passwordPolicyHints.push(createPasswordHint);
    var roleOptions = el("div", {
      className: "role-picker-options",
      role: "group",
      "aria-labelledby": "new-user-roles-label"
    });
    function syncAdminRoleState() {
      var adminCheckbox = roleOptions.querySelector('input[value="admin"]');
      var adminSelected = adminCheckbox && adminCheckbox.checked;
      Array.from(roleOptions.querySelectorAll("input")).forEach(function (input) {
        if (input === adminCheckbox) return;
        if (adminSelected) input.checked = false;
        input.disabled = Boolean(adminSelected);
        input.closest(".role-picker-option").classList.toggle("is-disabled", Boolean(adminSelected));
      });
    }

    function createRoleOption(name, index) {
      var checkbox = el("input", {
        id: "new-user-role-" + index,
        type: "checkbox",
        value: name,
        "aria-describedby": "new-user-role-description-" + index
      });
      checkbox.checked = name === "user";
      checkbox.addEventListener("change", syncAdminRoleState);
      return el("label", { className: "role-picker-option", htmlFor: checkbox.id },
        checkbox,
        el("span", { className: "role-picker-copy" },
          el("span", { className: "role-picker-option-label" }, name),
          el("span", { id: "new-user-role-description-" + index, className: "role-picker-option-description" },
            roleDetails[name] || "Grants the permissions assigned to this role."
          )
        )
      );
    }

    function renderRoleOptions(roles) {
      clear(roleOptions);
      var orderedRoles = roles.slice().sort(function (a, b) {
        if (a === "admin") return -1;
        if (b === "admin") return 1;
        return a.localeCompare(b);
      });
      var adminIndex = orderedRoles.indexOf("admin");
      if (adminIndex !== -1) {
        roleOptions.appendChild(el("div", { className: "role-picker-section role-picker-section-admin" },
          createRoleOption("admin", adminIndex)
        ));
      }
      var scopedRoles = orderedRoles.filter(function (name) { return name !== "admin"; });
      if (adminIndex !== -1 && scopedRoles.length) {
        roleOptions.appendChild(el("div", { className: "role-picker-divider", role: "separator" }, "Scoped access"));
      }
      if (scopedRoles.length) {
        var scopedSection = el("div", { className: "role-picker-section role-picker-section-scoped" });
        scopedRoles.forEach(function (name) {
          scopedSection.appendChild(createRoleOption(name, orderedRoles.indexOf(name)));
        });
        roleOptions.appendChild(scopedSection);
      }
      syncAdminRoleState();
    }

    renderRoleOptions(["user"]);
    (async function populateRoleOptions() {
      try {
        var data = await api("GET", endpoints.roles);
        renderRoleOptions(data.roles || ["user"]);
      } catch (_) { /* keep the "user" fallback option */ }
    })();
    var createBtn = el("button", { type: "button" }, "Create User");
    var createPanelToggle = el("button", { className: "secondary", type: "button" }, "Close");

    function openCreatePanel() {
      createPanel.style.display = "";
      createPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function closeCreatePanel() {
      createPanel.style.display = "none";
    }

    createLaunchBtn.addEventListener("click", openCreatePanel);
    createPanelToggle.addEventListener("click", closeCreatePanel);

    createPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "New User"),
      createPanelToggle
    ));

    var form = el("div", { className: "admin-create-form" },
      el("div", { className: "stack role-picker" },
        el("span", { id: "new-user-roles-label" }, "Roles"),
        el("span", { className: "muted" }, "Select all that apply"),
        roleOptions
      ),
      el("div", { className: "admin-create-form-grid user-create-grid" },
        field("Username", usernameInput),
        passwordField("Password", passwordInput)
      ),
      createPasswordHint,
      el("div", { className: "admin-create-form-actions user-create-form-actions" }, createBtn)
    );
    createPanel.appendChild(form);
    bindValidationClear(usernameInput, passwordInput, roleOptions);

    renderSelectedUserPlaceholder(detailPanel);
    renderAccountSecurityPanel(accountPanel);
    renderIdentityRulesPanel(allowlistPanel, RULE_PANELS.allowlist);
    renderIdentityRulesPanel(blacklistPanel, RULE_PANELS.blacklist);

    createBtn.addEventListener("click", function () {
      var u = usernameInput.value.trim();
      var p = passwordInput.value;
      var usernameError = validateUsername(u);
      if (usernameError) { showError(usernameError); return; }
      var passwordError = validateConfiguredPassword(p);
      if (passwordError) { showError(passwordError); return; }
      var selectedRoles = Array.from(roleOptions.querySelectorAll("input:checked")).map(function (input) { return input.value; });
      if (!selectedRoles.length) { showError("Select at least one role."); return; }
      withButton(createBtn, async function () {
        await api("POST", endpoints.register, { username: u, password: p, roles: selectedRoles });
        usernameInput.value = "";
        passwordInput.value = "";
        Array.from(roleOptions.querySelectorAll("input")).forEach(function (input) { input.checked = input.value === "user"; });
        syncAdminRoleState();
        closeCreatePanel();
        loadUsers({ preferredUsername: u });
      }, "User created");
    });

    bulkDeleteBtn.addEventListener("click", function () {
      var ids = Array.from(selectedUserIds);
      if (!ids.length) return;
      confirmAction({
        title: "Delete Users",
        message: "Delete " + ids.length + " selected users? This cannot be undone.",
        confirmLabel: "Delete",
        isDanger: true,
        loadingLabel: "Deleting...",
        onConfirm: async function () {
          for (var i = 0; i < ids.length; i++) {
            await api("DELETE", endpoints.users + "/" + encodeURIComponent(ids[i]));
          }
          ids.forEach(function (id) { selectedUserIds.delete(id); });
          if (selectedUser && ids.indexOf(selectedUser.id) !== -1) selectedUser = null;
          showStatus(ids.length + " user" + (ids.length === 1 ? "" : "s") + " deleted");
          await loadUsers({ clearSelection: !selectedUser });
        }
      });
    });

    function applyUserFilter() {
      var filter = userSearchFilter;
      var filteredUsers = !filter ? allUsers : allUsers.filter(function (user) {
        return [
          user.username,
          user.role,
          (user.roles || []).join(" "),
          user.id,
          user.active !== false ? "active" : "inactive"
        ].some(function (value) {
          return String(value || "").toLowerCase().includes(filter);
        });
      });
      userFilteredEmpty = !!allUsers.length && filteredUsers.length === 0;
      selectedUserIds.forEach(function (userId) {
        if (!allUsers.some(function (user) { return user.id === userId; })) {
          selectedUserIds.delete(userId);
        }
      });
      syncBulkActionButton(bulkDeleteBtn, selectedUserIds.size, "users");
      userPaginator.setData(filteredUsers);
    }

    function handleSelectUser(user) {
      selectedUser = user;
      renderUserDetail(detailPanel, user, function (options) {
        loadUsers(options || {});
      });
    }

    searchInput.addEventListener("input", function (e) {
      userSearchFilter = (e.target.value || "").trim().toLowerCase();
      applyUserFilter();
    });
    searchInput.addEventListener("keydown", function () { userSearchInteracted = true; });
    searchInput.addEventListener("paste", function () { userSearchInteracted = true; });

    function clearAutofilledUserSearch() {
      if (userSearchInteracted || document.activeElement === searchInput) return;
      searchInput.value = "";
      userSearchFilter = "";
      applyUserFilter();
    }

    // Some browsers ignore autocomplete="off" and populate the field after it mounts.
    window.requestAnimationFrame(function () {
      clearAutofilledUserSearch();
      window.setTimeout(clearAutofilledUserSearch, 200);
    });

    async function loadUsers(options) {
      options = options || {};
      try {
        var users = await api("GET", endpoints.users);
        allUsers = users;
        applyUserFilter();

        if (options.clearSelection) {
          selectedUser = null;
          renderSelectedUserPlaceholder(detailPanel);
          return;
        }

        var refreshedSelection = null;
        var preferredId = options.preferredUserId || (selectedUser && selectedUser.id);
        if (preferredId) {
          refreshedSelection = users.find(function (user) {
            return user.id === preferredId;
          });
        }
        if (!refreshedSelection && options.preferredUsername) {
          refreshedSelection = users.find(function (user) {
            return user.username === options.preferredUsername;
          });
        }

        if (refreshedSelection) {
          selectedUser = refreshedSelection;
          userPaginator.ensureItemVisible(function (user) {
            return user.id === refreshedSelection.id;
          });
          renderUserDetail(detailPanel, refreshedSelection, function (refreshOptions) {
            loadUsers(refreshOptions || {});
          });
        } else {
          selectedUser = null;
          renderSelectedUserPlaceholder(detailPanel);
        }
      } catch (err) {
        showTableLoadError(tableWrap, "Failed to load users");
        renderSelectedUserPlaceholder(detailPanel);
      }
    }

    loadUsers();
  }

  // The blocked- and allowed-identity panels are the same machinery pointed at
  // opposite rule sets, so one builder drives both. Everything that differs is
  // wording plus which direction revokes access: adding a *deny* rule cuts
  // people off, while it is *removing* an allow rule that does.
  var RULE_PANELS = {
    blacklist: {
      endpointKey: "blacklist",
      heading: "Blocked Identities",
      refreshLabel: "Refresh the blacklist",
      description:
        "Deny authentication by pattern, across every surface \u2014 chat, admin panel, file upload, and A2A. " +
        "Use * and ? as wildcards (for example, *@spam-domain.com). Unlike deactivating a user, " +
        "a rule also blocks external users who have never signed in, so it prevents their account from being created at all.",
      entryTypes: [
        { value: "email", label: "Email", placeholder: "abuser@example.com or *@spam-domain.com" },
        { value: "username", label: "Username", placeholder: "baduser or entra:abc*" },
        { value: "user_id", label: "User ID", placeholder: "The ORBIT user id, wildcards allowed" }
      ],
      selectLabel: "Blacklist entry type",
      addToggleLabel: "Add blacklist rule",
      addSubmitLabel: "Block Identity",
      reasonPlaceholder: "Optional. Why this identity is blocked.",
      emptyPatternError: "Enter a pattern to block.",
      addConfirm: function (pattern) {
        return {
          title: "Block Identity",
          message: 'Block "' + pattern + '"? Matching users are signed out immediately and cannot authenticate again until the rule is removed.',
          confirmLabel: "Block",
          isDanger: true,
          loadingLabel: "Blocking..."
        };
      },
      addStatus: function (rule) {
        return "Identity blocked" + revocationSuffix(rule);
      },
      removeConfirm: function (pattern) {
        return {
          title: "Remove Blacklist Rule",
          message: 'Stop blocking "' + pattern + '"? Previously revoked sessions are not restored.',
          confirmLabel: "Remove"
        };
      },
      removeStatus: function () { return "Blacklist rule removed"; },
      updateConfirm: function (pattern) {
        return {
          title: "Update Blacklist Rule",
          message: 'Change this rule to block "' + pattern + '"? Matching users are signed out immediately.',
          confirmLabel: "Update",
          isDanger: true,
          loadingLabel: "Updating..."
        };
      },
      emptyIcon: "\u{1F6AB}",
      emptyText: "No blocked identities",
      loadError: "Failed to load blocked identities"
    },
    allowlist: {
      endpointKey: "allowlist",
      heading: "Allowed Identities",
      refreshLabel: "Refresh the allowlist",
      description:
        "Pre-clear external (Microsoft / Auth0) identities. When auth.providers.access_control is 'allowlist', " +
        "an identity that matches no rule here is never given an ORBIT account at all \u2014 so an empty list admits nobody. " +
        "Local password accounts are never affected, and admin_users entries are always cleared. " +
        "Removing a rule withdraws access and signs those users out.",
      entryTypes: [
        { value: "email", label: "Email", placeholder: "alice@corp.example.com or *@corp.example.com" },
        { value: "username", label: "Username", placeholder: "entra:00000000-... or auth0:abc*" },
        { value: "user_id", label: "User ID", placeholder: "The ORBIT user id, wildcards allowed" }
      ],
      selectLabel: "Allowlist entry type",
      addToggleLabel: "Add allowlist rule",
      addSubmitLabel: "Allow Identity",
      reasonPlaceholder: "Optional. Why this identity is approved.",
      emptyPatternError: "Enter a pattern to allow.",
      addConfirm: function (pattern) {
        return {
          title: "Allow Identity",
          message: 'Pre-clear "' + pattern + '"? Matching identities will be able to sign in and have an ORBIT account created on first login.',
          confirmLabel: "Allow",
          loadingLabel: "Allowing..."
        };
      },
      // Adding an allow rule grants and revokes nothing, so there is no count.
      addStatus: function () { return "Identity allowed"; },
      removeConfirm: function (pattern) {
        return {
          title: "Remove Allowlist Rule",
          message: 'Stop allowing "' + pattern + '"? Users cleared only by this rule are signed out immediately and cannot sign in again.',
          confirmLabel: "Remove",
          isDanger: true,
          loadingLabel: "Removing..."
        };
      },
      removeStatus: function (result) {
        return "Allowlist rule removed" + revocationSuffix(result);
      },
      updateConfirm: function (pattern) {
        return {
          title: "Update Allowlist Rule",
          message: 'Change this rule to allow "' + pattern + '"? Anyone it stops covering is signed out immediately.',
          confirmLabel: "Update",
          isDanger: true,
          loadingLabel: "Updating..."
        };
      },
      emptyIcon: "\u{1F511}",
      emptyText: "No allowed identities",
      loadError: "Failed to load allowed identities"
    }
  };

  // "3 users matched, 5 sessions revoked", or "" when nothing was cut off.
  function revocationSuffix(result) {
    if (!result || !result.matched_users) return "";
    var users = result.matched_users;
    var sessions = result.revoked_sessions || 0;
    return " \u2014 " + users + " user" + (users === 1 ? "" : "s") + " matched, " +
      sessions + " session" + (sessions === 1 ? "" : "s") + " revoked";
  }

  function renderIdentityRulesPanel(panel, spec) {
    clear(panel);
    var endpoint = endpoints[spec.endpointKey];
    var ENTRY_TYPES = spec.entryTypes;
    var tableWrap = el("div", { className: "blacklist-rules-wrap" }, skeleton());
    var formWrap = el("div", { className: "collapsible-panel-body", style: "display:none" });
    var addToggle = el("button", {
      className: "secondary create-launch-btn",
      type: "button",
      "aria-label": spec.addToggleLabel
    }, svgIcon(iconPlus), el("span", null, "Add Rule"));

    var typeSelect = createSelect({
      ariaLabel: spec.selectLabel,
      options: ENTRY_TYPES.map(function (entry) { return { value: entry.value, label: entry.label }; }),
      value: ENTRY_TYPES[0].value
    });
    var patternInput = el("input", {
      type: "text",
      maxlength: "320",
      placeholder: ENTRY_TYPES[0].placeholder,
      autocomplete: "off",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var reasonInput = el("input", {
      type: "text",
      maxlength: "500",
      placeholder: spec.reasonPlaceholder,
      autocomplete: "off"
    });
    var addBtn = el("button", { type: "button" }, spec.addSubmitLabel);
    var cancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");

    typeSelect.addEventListener("change", function () {
      var entry = ENTRY_TYPES.find(function (item) { return item.value === typeSelect.value; });
      patternInput.placeholder = entry ? entry.placeholder : "";
    });

    function closeForm() {
      formWrap.style.display = "none";
      patternInput.value = "";
      reasonInput.value = "";
    }

    addToggle.addEventListener("click", function () {
      if (formWrap.style.display === "none") formWrap.style.display = "";
      else closeForm();
    });
    cancelBtn.addEventListener("click", closeForm);

    addBtn.addEventListener("click", function () {
      var pattern = patternInput.value.trim();
      if (!pattern) { showError(spec.emptyPatternError); return; }
      if (pattern.replace(/[*?]/g, "") === "") {
        showError("Pattern must contain at least one literal character.");
        return;
      }
      confirmAction(Object.assign(spec.addConfirm(pattern), {
        onConfirm: async function () {
          var rule = await api("POST", endpoint, {
            pattern: pattern,
            entry_type: typeSelect.value,
            reason: reasonInput.value.trim() || null
          });
          closeForm();
          showStatus(spec.addStatus(rule));
          await loadRules();
        }
      }));
    });

    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, spec.heading),
      refreshButton(spec.refreshLabel, function () { loadRules(); })
    ));
    panel.appendChild(el("p", { className: "muted" }, spec.description));
    panel.appendChild(el("div", { className: "bulk-action-row" }, addToggle));
    formWrap.appendChild(el("div", { className: "admin-create-form" },
      el("div", { className: "admin-create-form-grid" },
        field("Match On", typeSelect),
        field("Pattern", patternInput)
      ),
      field("Reason", reasonInput),
      el("div", { className: "admin-create-form-actions" }, cancelBtn, addBtn)
    ));
    panel.appendChild(formWrap);
    panel.appendChild(tableWrap);
    bindValidationClear(patternInput, reasonInput);

    function entryLabel(entryType) {
      var entry = ENTRY_TYPES.find(function (item) { return item.value === entryType; });
      return entry ? entry.label : entryType;
    }

    // Each row toggles between a read view and an inline edit view. Only one
    // row edits at a time: opening an editor re-renders the others as read-only.
    function buildRuleRow(rule) {
      var editing = false;

      function replaceRow(nextRow) {
        var current = row;
        row = nextRow;
        current.replaceWith(nextRow);
      }

      function readRow() {
        var editBtn = el("button", {
          className: "secondary btn--icon",
          type: "button",
          "aria-label": "Edit rule for " + rule.pattern,
          title: "Edit rule"
        }, svgIcon(iconPencil));
        var removeBtn = el("button", {
          className: "secondary btn--icon btn--icon-danger",
          type: "button",
          "aria-label": "Remove rule for " + rule.pattern,
          title: "Remove rule"
        }, svgIcon(iconX));

        editBtn.addEventListener("click", function () {
          if (editing) return;
          editing = true;
          replaceRow(editRow());
        });
        removeBtn.addEventListener("click", function () {
          confirmAction(Object.assign(spec.removeConfirm(rule.pattern), {
            onConfirm: async function () {
              var result = await api("DELETE", endpoint + "/" + encodeURIComponent(rule.id));
              showStatus(spec.removeStatus(result));
              await loadRules();
            }
          }));
        });

        return el("tr", null,
          el("td", null, entryLabel(rule.entry_type)),
          el("td", null, el("code", null, rule.pattern)),
          el("td", null, rule.reason || "—"),
          el("td", null, rule.created_by || "—"),
          el("td", null, el("div", { className: "inline-form" }, editBtn, removeBtn))
        );
      }

      function editRow() {
        var typeSel = createSelect({
          ariaLabel: spec.selectLabel,
          options: ENTRY_TYPES.map(function (entry) { return { value: entry.value, label: entry.label }; }),
          value: rule.entry_type
        });
        var patternIn = el("input", {
          type: "text",
          value: rule.pattern,
          maxlength: "320",
          "aria-label": "Pattern",
          autocomplete: "off",
          autocapitalize: "none",
          autocorrect: "off",
          spellcheck: "false"
        });
        var reasonIn = el("input", {
          type: "text",
          value: rule.reason || "",
          maxlength: "500",
          "aria-label": "Reason",
          placeholder: "Optional",
          autocomplete: "off"
        });
        var saveBtn = el("button", {
          className: "btn--icon",
          type: "button",
          "aria-label": "Save rule",
          title: "Save rule"
        }, svgIcon(iconSave));
        var cancelBtn = el("button", {
          className: "secondary btn--icon",
          type: "button",
          "aria-label": "Cancel editing rule",
          title: "Cancel editing"
        }, svgIcon(iconX));

        cancelBtn.addEventListener("click", function () {
          editing = false;
          replaceRow(readRow());
        });

        saveBtn.addEventListener("click", function () {
          var pattern = patternIn.value.trim();
          if (!pattern) { showError(spec.emptyPatternError); return; }
          if (pattern.replace(/[*?]/g, "") === "") {
            showError("Pattern must contain at least one literal character.");
            return;
          }
          async function submit() {
            var updated = await api("PUT", endpoint + "/" + encodeURIComponent(rule.id), {
              pattern: pattern,
              entry_type: typeSel.value,
              reason: reasonIn.value.trim() || null
            });
            editing = false;
            showStatus("Rule updated" + revocationSuffix(updated));
            await loadRules();
          }

          // Only confirm when the edit alters who the rule covers; a
          // reason-only change has no effect on access, so it saves straight away.
          var changesWhoIsCovered = pattern.toLowerCase() !== rule.pattern
            || typeSel.value !== rule.entry_type;
          if (!changesWhoIsCovered) {
            withButton(saveBtn, submit);
            return;
          }
          confirmAction(Object.assign(spec.updateConfirm(pattern), { onConfirm: submit }));
        });

        bindValidationClear(patternIn, reasonIn);
        return el("tr", null,
          el("td", null, typeSel),
          el("td", null, patternIn),
          el("td", null, reasonIn),
          el("td", null, rule.created_by || "—"),
          el("td", null, el("div", { className: "inline-form" }, cancelBtn, saveBtn))
        );
      }

      var row = readRow();
      return row;
    }

    function renderRules(rules) {
      clear(tableWrap);
      if (!rules || rules.length === 0) {
        tableWrap.appendChild(el("div", { className: "empty-state" },
          el("div", { className: "empty-state-icon" }, spec.emptyIcon),
          el("p", null, spec.emptyText)
        ));
        return;
      }
      var table = el("table");
      table.appendChild(el("thead", null, el("tr", null,
        el("th", null, "Match On"),
        el("th", null, "Pattern"),
        el("th", null, "Reason"),
        el("th", null, "Added By"),
        el("th", null, "")
      )));
      var tbody = el("tbody");
      rules.forEach(function (rule) {
        tbody.appendChild(buildRuleRow(rule));
      });
      table.appendChild(tbody);
      tableWrap.appendChild(wrapTable(table));
    }

    async function loadRules() {
      try {
        renderRules(await api("GET", endpoint));
      } catch (err) {
        showTableLoadError(tableWrap, spec.loadError);
      }
    }

    loadRules();
  }

  function renderAccountSecurityPanel(panel) {
    clear(panel);
    var currentUser = getCurrentUser();
    var isSsoUser = !!(currentUser && currentUser.provider);
    var formWrap = el("div", { className: "collapsible-panel-body", style: "display:none" });
    var toggleBtn = el("button", { className: "secondary", type: "button" }, "Change Password");

    function openForm() {
      formWrap.style.display = "";
      toggleBtn.textContent = "Close";
    }

    function closeForm() {
      formWrap.style.display = "none";
      toggleBtn.textContent = "Change Password";
    }

    toggleBtn.addEventListener("click", function () {
      if (formWrap.style.display === "none") openForm();
      else closeForm();
    });

    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "My Account"),
      isSsoUser ? null : toggleBtn
    ));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "Username:"), " " + ((currentUser && currentUser.username) || "N/A")),
      el("p", null, el("strong", null, "Roles:"), " " + ((currentUser && currentUser.roles && currentUser.roles.join(", ")) || "N/A"))
    ));
    if (isSsoUser) {
      panel.appendChild(el("p", { className: "muted" },
        "Your password is managed by your identity provider (" + currentUser.provider + "). Sign in through that provider to change it."
      ));
      return;
    }
    renderChangeMyPassword(formWrap, closeForm);
    panel.appendChild(formWrap);
  }

  function renderChangeMyPassword(panel, onDone) {
    clear(panel);
    var curPwInput = el("input", {
      type: "password",
      placeholder: "Current password",
      maxlength: String(passwordMaxLength),
      autocomplete: "current-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var newPwInput = el("input", {
      type: "password",
      placeholder: "New password",
      maxlength: String(passwordMaxLength),
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    passwordPolicyInputs.push(newPwInput);
    var changePasswordHint = el("p", { className: "muted" }, describePasswordPolicy());
    passwordPolicyHints.push(changePasswordHint);
    var confirmPwInput = el("input", {
      type: "password",
      placeholder: "Confirm new password",
      maxlength: String(passwordMaxLength),
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    var changeBtn = el("button", {
      type: "button",
      className: "btn--icon",
      "aria-label": "Save password",
      title: "Save password",
    }, svgIcon(iconSave));
    var cancelBtn = el("button", {
      className: "secondary btn--icon",
      type: "button",
      "aria-label": "Cancel password change",
      title: "Cancel password change",
    }, svgIcon(iconX));

    cancelBtn.addEventListener("click", function () {
      curPwInput.value = "";
      newPwInput.value = "";
      confirmPwInput.value = "";
      if (onDone) onDone();
    });

    changeBtn.addEventListener("click", function () {
      var cur = curPwInput.value;
      var nw = newPwInput.value;
      var conf = confirmPwInput.value;
      if (!cur) { showError("Enter your current password"); return; }
      if (!nw) { showError("Enter a new password"); return; }
      if (!conf) { showError("Confirm your new password"); return; }
      var passwordError = validateConfiguredPassword(nw);
      if (passwordError) { showError(passwordError); return; }
      if (nw !== conf) { showError("Passwords do not match"); return; }
      withButton(changeBtn, async function () {
        await api("POST", endpoints.changePassword, { current_password: cur, new_password: nw });
        curPwInput.value = "";
        newPwInput.value = "";
        confirmPwInput.value = "";
        if (onDone) onDone();
      }, "Password changed successfully");
    });

    panel.appendChild(el("div", { className: "admin-create-form" },
      el("p", { className: "muted" }, "Update the password for the account currently signed into the admin panel."),
      passwordField("Current Password", curPwInput),
      passwordField("New Password", newPwInput),
      changePasswordHint,
      passwordField("Confirm Password", confirmPwInput),
      el("div", { className: "inline-form detail-action-row" }, cancelBtn, changeBtn)
    ));
    bindValidationClear(curPwInput, newPwInput, confirmPwInput);
  }

  function renderSelectedUserPlaceholder(panel) {
    clear(panel);
    panel.style.display = "none";
  }

  function renderUserTable(wrap, users, filteredEmpty, onSelect, selection) {
    clear(wrap);
    if (!users || users.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("div", { className: "empty-state-icon" }, "\u{1F464}"),
        el("p", null, filteredEmpty ? "No users match the current search" : "No users found")
      ));
      return;
    }
    var table = el("table");
    var selectableUsers = users.filter(function (user) {
      return !selection.currentUserId || user.id !== selection.currentUserId;
    });
    var selectableUserIds = selectableUsers.map(function (user) { return user.id; });
    var rowCheckboxes = [];
    var selectAllBox = el("input", {
      type: "checkbox",
      "aria-label": "Select all visible users"
    });
    selectAllBox.checked = selectableUserIds.length > 0 && selectableUserIds.every(function (userId) {
      return selection.selectedIds.has(userId);
    });
    selectAllBox.indeterminate = !selectAllBox.checked && selectableUserIds.some(function (userId) {
      return selection.selectedIds.has(userId);
    });
    selectAllBox.addEventListener("click", function (e) { e.stopPropagation(); });
    selectAllBox.addEventListener("change", function () {
      selectableUsers.forEach(function (user) {
        if (selectAllBox.checked) selection.selectedIds.add(user.id);
        else selection.selectedIds.delete(user.id);
      });
      selection.onSelectionChange();
      syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, selectableUserIds);
    });
    table.appendChild(el("colgroup", null, el("col", { className: "selection-col-width" })));
    var thead = el("thead", null, selection.sorter.headerRow([
      { attrs: { className: "selection-col" }, content: selectAllBox },
      { label: "Username", key: "username", sortValue: function (u) { return u.email || u.username; } },
      {
        label: "Role",
        key: "role",
        sortValue: function (u) {
          return (u.roles && u.roles.length ? u.roles : [u.role]).filter(Boolean).join(", ");
        },
      },
      { label: "Status", key: "status", sortValue: function (u) { return u.active !== false ? "Active" : "Inactive"; } },
    ]));
    var tbody = el("tbody");
    users.forEach(function (u) {
      var isSelected = selectedUser && selectedUser.id === u.id;
      var checkbox = el("input", {
        type: "checkbox",
        "aria-label": "Select user " + u.username
      });
      checkbox._selectionId = u.id;
      checkbox.checked = selection.selectedIds.has(u.id);
      if (selection.currentUserId && selection.currentUserId === u.id) {
        checkbox.disabled = true;
        checkbox.title = "You cannot bulk-delete the current admin account";
      }
      checkbox.addEventListener("click", function (e) { e.stopPropagation(); });
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selection.selectedIds.add(u.id);
        else selection.selectedIds.delete(u.id);
        selection.onSelectionChange();
        syncVisibleSelection(selectAllBox, rowCheckboxes, selection.selectedIds, selectableUserIds);
      });
      rowCheckboxes.push(checkbox);
      var tr = el("tr", {
        className: "selectable-row" + (isSelected ? " selected-row" : ""),
        tabindex: "0",
        "aria-selected": isSelected ? "true" : "false",
      },
        el("td", { className: "selection-col" }, checkbox),
        el("td", null, u.email || u.username),
        el("td", null, (u.roles && u.roles.length ? u.roles : [u.role]).filter(Boolean).join(", ")),
        el("td", null,
          el("span", { className: u.active !== false ? "status-active" : "status-inactive" },
            u.active !== false ? "Active" : "Inactive"
          )
        )
      );
      tr.addEventListener("click", function () {
        markSelectedRow(tbody, tr);
        onSelect(u);
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

  function renderUserDetail(panel, user, onRefresh) {
    clear(panel);
    panel.style.display = "";
    var currentUser = getCurrentUser();
    var isCurrentUser = !!(currentUser && currentUser.id && user && user.id && currentUser.id === user.id);
    var resetPanel = el("div", { className: "collapsible-panel-body", style: "display:none" });
    var newPwInput = el("input", {
      type: "password",
      maxlength: String(passwordMaxLength),
      placeholder: "Meet the password requirements below",
      autocomplete: "new-password",
      autocapitalize: "none",
      autocorrect: "off",
      spellcheck: "false"
    });
    passwordPolicyInputs.push(newPwInput);
    var resetPasswordHint = el("p", { className: "muted" }, describePasswordPolicy());
    passwordPolicyHints.push(resetPasswordHint);
    var resetBtn = el("button", { type: "button" }, "Apply Reset");
    var resetCancelBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
    var resetToggle = el("button", { className: "secondary", type: "button" }, "Reset Password");

    function closeResetPanel() {
      newPwInput.value = "";
      resetPanel.style.display = "none";
      resetToggle.textContent = "Reset Password";
    }

    resetToggle.addEventListener("click", function () {
      if (resetPanel.style.display === "none") {
        resetPanel.style.display = "";
        resetToggle.textContent = "Close Reset";
      } else {
        closeResetPanel();
      }
    });

    resetCancelBtn.addEventListener("click", closeResetPanel);

    panel.appendChild(el("h2", { className: "detail-title" }, user.email || user.username || "User Details"));
    panel.appendChild(el("div", { className: "key-summary" },
      el("p", null, el("strong", null, "ID:"), " " + (user.id || "N/A")),
      el("p", null, el("strong", null, "Email:"), " " + (user.email || "N/A")),
      el("p", null, el("strong", null, "Username:"), " " + (user.username || "N/A")),
      el("p", null, el("strong", null, "Roles:"), " " + ((user.roles && user.roles.length ? user.roles : [user.role]).filter(Boolean).join(", ") || "N/A")),
      el("p", null, el("strong", null, "Status:"), " ",
        el("span", { className: user.active !== false ? "status-active" : "status-inactive" },
          user.active !== false ? "Active" : "Inactive"
        )
      )
    ));

    if (isCurrentUser) {
      panel.appendChild(el("div", { className: "danger-zone" },
        el("p", null, "The account currently used for this admin session cannot be deactivated or deleted here."),
        el("p", { className: "muted" }, "Use My Account to update your own password.")
      ));
    } else {
      var roleEditor = el("div", { className: "role-editor", style: "display:none" });
      var roleEditorOptions = el("div", {
        className: "role-picker-options",
        role: "group",
        "aria-labelledby": "edit-user-roles-label"
      });
      var saveRolesBtn = el("button", { type: "button" }, "Save Roles");
      var cancelRolesBtn = el("button", { className: "secondary", type: "button" }, "Cancel");
      var editRolesToggle = el("button", { className: "secondary", type: "button" }, "Edit Roles");

      function syncEditedAdminRoleState() {
        var adminCheckbox = roleEditorOptions.querySelector('input[value="admin"]');
        var adminSelected = adminCheckbox && adminCheckbox.checked;
        Array.from(roleEditorOptions.querySelectorAll("input")).forEach(function (input) {
          if (input === adminCheckbox) return;
          if (adminSelected) input.checked = false;
          input.disabled = Boolean(adminSelected);
          input.closest(".role-picker-option").classList.toggle("is-disabled", Boolean(adminSelected));
        });
      }

      function renderRoleEditorOptions(roles) {
        clear(roleEditorOptions);
        var assignedRoles = user.roles && user.roles.length ? user.roles : [user.role];
        var orderedRoles = roles.slice().sort(function (a, b) {
          if (a === "admin") return -1;
          if (b === "admin") return 1;
          return a.localeCompare(b);
        });

        function option(name, index) {
          var checkbox = el("input", {
            id: "edit-user-role-" + index,
            type: "checkbox",
            value: name,
            "aria-describedby": "edit-user-role-description-" + index
          });
          checkbox.checked = assignedRoles.indexOf(name) !== -1;
          checkbox.addEventListener("change", syncEditedAdminRoleState);
          return el("label", { className: "role-picker-option", htmlFor: checkbox.id },
            checkbox,
            el("span", { className: "role-picker-copy" },
              el("span", { className: "role-picker-option-label" }, name),
              el("span", { id: "edit-user-role-description-" + index, className: "role-picker-option-description" },
                roleDetails[name] || "Grants the permissions assigned to this role."
              )
            )
          );
        }

        var adminIndex = orderedRoles.indexOf("admin");
        if (adminIndex !== -1) {
          roleEditorOptions.appendChild(el("div", { className: "role-picker-section role-picker-section-admin" }, option("admin", adminIndex)));
        }
        var scopedRoles = orderedRoles.filter(function (name) { return name !== "admin"; });
        if (adminIndex !== -1 && scopedRoles.length) {
          roleEditorOptions.appendChild(el("div", { className: "role-picker-divider", role: "separator" }, "Scoped access"));
        }
        if (scopedRoles.length) {
          var scopedSection = el("div", { className: "role-picker-section role-picker-section-scoped" });
          scopedRoles.forEach(function (name) { scopedSection.appendChild(option(name, orderedRoles.indexOf(name))); });
          roleEditorOptions.appendChild(scopedSection);
        }
        syncEditedAdminRoleState();
      }

      function closeRoleEditor() {
        roleEditor.style.display = "none";
        editRolesToggle.textContent = "Edit Roles";
      }

      editRolesToggle.addEventListener("click", async function () {
        if (roleEditor.style.display !== "none") {
          closeRoleEditor();
          return;
        }
        editRolesToggle.disabled = true;
        try {
          var data = await api("GET", endpoints.roles);
          renderRoleEditorOptions(data.roles || ["user"]);
          roleEditor.style.display = "";
          editRolesToggle.textContent = "Close Role Editor";
        } catch (err) {
          showError(err.message);
        } finally {
          editRolesToggle.disabled = false;
        }
      });

      cancelRolesBtn.addEventListener("click", closeRoleEditor);
      saveRolesBtn.addEventListener("click", function () {
        var selectedRoles = Array.from(roleEditorOptions.querySelectorAll("input:checked")).map(function (input) { return input.value; });
        if (!selectedRoles.length) { showError("Select at least one role."); return; }
        withButton(saveRolesBtn, async function () {
          await api("PUT", endpoints.users + "/" + encodeURIComponent(user.id) + "/roles", { roles: selectedRoles });
          closeRoleEditor();
          onRefresh({ preferredUserId: user.id });
        }, "Roles updated");
      });

      roleEditor.appendChild(el("div", { className: "stack" },
        el("span", { id: "edit-user-roles-label" }, "Roles"),
        el("span", { className: "muted" }, "Select all that apply"),
        roleEditorOptions,
        el("div", { className: "inline-form detail-action-row" }, cancelRolesBtn, saveRolesBtn)
      ));
      var actionRow = el("div", { className: "inline-form detail-action-row" });
      var toggleBtn = el("button", { className: "secondary", type: "button" },
        user.active !== false ? "Deactivate User" : "Activate User"
      );
      toggleBtn.addEventListener("click", async function () {
        var action = user.active !== false ? "deactivate" : "activate";
        confirmAction({
          title: (action === "deactivate" ? "Deactivate" : "Activate") + " User",
          message: "Are you sure you want to " + action + " " + user.username + "?",
          confirmLabel: action === "deactivate" ? "Deactivate" : "Activate",
          onConfirm: async function () {
            toggleBtn.disabled = true;
            try {
              await api("POST", endpoints.users + "/" + encodeURIComponent(user.id) + "/" + action);
              showStatus("User " + action + "d");
              onRefresh({ preferredUserId: user.id });
            } finally {
              toggleBtn.disabled = false;
            }
          }
        });
      });
      resetBtn.addEventListener("click", function () {
        var pw = newPwInput.value;
        if (!pw) return;
        var passwordError = validateConfiguredPassword(pw);
        if (passwordError) { showError(passwordError); return; }
        confirmAction({
          title: "Reset Password",
          message: "Reset the password for " + user.username + "?",
          confirmLabel: "Reset",
          onConfirm: async function () {
            resetBtn.disabled = true;
            try {
              await api("POST", endpoints.resetPassword, { user_id: user.id, new_password: pw });
              closeResetPanel();
              showStatus("Password reset");
            } finally {
              resetBtn.disabled = false;
            }
          }
        });
      });
      actionRow.appendChild(editRolesToggle);
      actionRow.appendChild(toggleBtn);
      if (!user.provider) actionRow.appendChild(resetToggle);
      var deleteBtn = el("button", { className: "danger", type: "button" }, "Delete User");
      deleteBtn.addEventListener("click", function () {
        requireTypedConfirmation({
          title: "Delete User",
          message: 'Delete user "' + user.username + '"? This cannot be undone.',
          expectedText: user.username,
          confirmLabel: "Delete",
          onConfirm: async function () {
            await api("DELETE", endpoints.users + "/" + encodeURIComponent(user.id));
            showStatus("User deleted");
            onRefresh({ clearSelection: true });
          }
        });
      });
      actionRow.appendChild(deleteBtn);
      panel.appendChild(actionRow);
      panel.appendChild(roleEditor);
      resetPanel.appendChild(el("div", { className: "admin-create-form user-reset-form" },
        passwordField("New Password", newPwInput),
        resetPasswordHint,
        el("div", { className: "inline-form detail-action-row" }, resetCancelBtn, resetBtn)
      ));
      bindValidationClear(newPwInput);
      panel.appendChild(resetPanel);
    }

    panel.appendChild(renderSessionsSection(user, isCurrentUser));
  }

  // Self-service (isCurrentUser) uses /auth/sessions, which needs no special
  // permission - every user may always see and revoke their own sessions.
  // Viewing another user's sessions uses /auth/users/{id}/sessions, which the
  // server gates on sessions.manage; a viewer without it simply sees a load
  // error here; there is no permission check duplicated in this file.
  function renderSessionsSection(user, isCurrentUser) {
    var section = el("div", { className: "detail-subsection" });
    var listEndpoint = isCurrentUser
      ? endpoints.sessions
      : endpoints.users + "/" + encodeURIComponent(user.id) + "/sessions";
    var tableWrap = el("div", null, skeleton());

    section.appendChild(el("div", { className: "panel-header-row" },
      el("h3", null, "Active Sessions"),
      refreshButton("Refresh Sessions", function () { loadSessions(); })
    ));
    section.appendChild(tableWrap);

    function formatTimestamp(value) {
      if (!value) return "—";
      var date = new Date(value);
      return isNaN(date.getTime()) ? String(value) : date.toLocaleString();
    }

    function buildSessionRow(session) {
      var revokeBtn = el("button", { className: "secondary btn--icon btn--icon-danger", type: "button" },
        svgIcon(iconX)
      );
      revokeBtn.setAttribute("aria-label", "Revoke session " + session.id);
      revokeBtn.title = "Revoke session";
      revokeBtn.addEventListener("click", function () {
        confirmAction({
          title: "Revoke Session",
          message: "Sign out this session (" + (session.ip_address || "unknown IP") + ")?",
          confirmLabel: "Revoke",
          onConfirm: async function () {
            await api("DELETE", listEndpoint + "/" + encodeURIComponent(session.id));
            showStatus("Session revoked");
            await loadSessions();
          }
        });
      });

      return el("tr", null,
        el("td", null, session.ip_address || "—"),
        el("td", null, session.user_agent || "—"),
        el("td", null, formatTimestamp(session.created_at)),
        el("td", null, formatTimestamp(session.last_seen_at)),
        el("td", null, revokeBtn)
      );
    }

    function renderSessions(sessions) {
      clear(tableWrap);
      if (!sessions.length) {
        tableWrap.appendChild(el("p", { className: "muted" }, "No active sessions."));
        return;
      }
      var table = el("table");
      table.appendChild(el("thead", null, el("tr", null,
        el("th", null, "IP Address"),
        el("th", null, "User Agent"),
        el("th", null, "Created"),
        el("th", null, "Last Seen"),
        el("th", null, "")
      )));
      var tbody = el("tbody");
      sessions.forEach(function (session) {
        tbody.appendChild(buildSessionRow(session));
      });
      table.appendChild(tbody);
      tableWrap.appendChild(wrapTable(table));
    }

    async function loadSessions() {
      try {
        renderSessions(await api("GET", listEndpoint));
      } catch (err) {
        showTableLoadError(tableWrap, "Failed to load sessions");
      }
    }

    loadSessions();
    return section;
  }

  return { render };
}
