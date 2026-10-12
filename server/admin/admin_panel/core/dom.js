/** Small DOM primitives shared by admin-panel feature modules. */

/** The Ace theme matching the app's current light/dark setting. */
export function aceThemeName() {
  return document.documentElement.getAttribute("data-theme") === "light"
    ? "ace/theme/tomorrow"
    : "ace/theme/tomorrow_night";
}

export function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "className") node.className = value;
      else if (key === "htmlFor") node.setAttribute("for", value);
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
      else if (key === "dataset") {
        for (const [dataKey, dataValue] of Object.entries(value)) node.dataset[dataKey] = dataValue;
      } else if (value != null) node.setAttribute(key, value);
    }
  }
  for (const child of children) {
    if (child == null || child === false) continue;
    if (typeof child === "string" || typeof child === "number") node.appendChild(document.createTextNode(String(child)));
    else if (Array.isArray(child)) child.forEach((item) => { if (item) node.appendChild(item); });
    else node.appendChild(child);
  }
  return node;
}

/** Bring explicitly selected record details into view, below the sticky workbar. */
export function revealDetails(panel) {
  if (!panel || !panel.isConnected) return;
  panel.setAttribute("tabindex", "-1");
  panel.focus({ preventScroll: true });
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  panel.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
}

export function clear(node) {
  node.querySelectorAll?.(".styled-select").forEach((select) => select.destroy?.());
  node.querySelectorAll?.(".flatpickr-input").forEach((input) => input._flatpickr?.destroy());
  while (node.firstChild) node.removeChild(node.firstChild);
}

// Tracks every live createSelect() so a single observer can sweep out ones
// discarded through a removal path other than clear() (.remove(), innerHTML,
// replaceChildren) — those never get an explicit destroy() call, so without
// this a stale select's document click listener (and its closure over the
// detached root) would linger forever, only realizing it's detached the next
// time a user happens to click anywhere on the page.
const liveSelects = new Set();
let selectGcObserver = null;

function reapDetachedSelects() {
  liveSelects.forEach((entry) => {
    if (!document.contains(entry.root)) entry.destroy();
  });
  if (liveSelects.size === 0 && selectGcObserver) {
    selectGcObserver.disconnect();
    selectGcObserver = null;
  }
}

function trackSelect(entry) {
  liveSelects.add(entry);
  if (!selectGcObserver) {
    selectGcObserver = new MutationObserver(reapDetachedSelects);
    selectGcObserver.observe(document.body, { childList: true, subtree: true });
  }
}

/** Explicit column roles keep widths stable across filtering and pagination.
 * Use "fluid" for prose columns that share the space left by fixed columns.
 * Each fluid column retains a readable minimum via the table's scroll width.
 */
export function sizeTable(table, columns) {
  table.querySelectorAll("colgroup").forEach((group) => group.remove());
  table.classList.add("sized-table");
  table.style.setProperty("--table-min-width", "calc(" + columns.map((role) =>
    "var(--table-col-" + role + ")"
  ).join(" + ") + ")");
  table.prepend(el("colgroup", null, columns.map((role) =>
    el("col", role === "fluid" ? null : { style: "width:var(--table-col-" + role + ")" })
  )));
  return table;
}

export function wrapTable(table, columns) {
  if (columns) sizeTable(table, columns);
  // Let keyboard users reach and horizontally scroll wide tables too.
  return el("div", {
    className: "table-wrap",
    tabindex: "0",
    role: "region",
    "aria-label": table.getAttribute("aria-label") || "Data table"
  }, table);
}

/**
 * A "?" icon that reveals `helpText` in a tooltip on hover/focus. `helpId` is
 * the id of the tooltip element; pair it with `aria-describedby` on the
 * field it documents.
 */
export function helpTooltip(labelText, helpText, helpId) {
  const helpButton = el("button", {
    type: "button",
    className: "help-button",
    "aria-label": "Help for " + labelText,
    "aria-describedby": helpId,
    // Keep the explanation available if a surrounding panel clips or
    // obscures the styled tooltip. The custom tooltip still serves keyboard
    // users and appears immediately on hover/focus; this is a browser-native
    // fallback for pointer users.
    title: helpText,
  }, "?");
  helpButton.addEventListener("keydown", (event) => {
    if (event.key === "Escape") helpButton.blur();
  });
  return el("span", { className: "help-tooltip-wrap" },
    helpButton,
    el("span", { id: helpId, className: "help-tooltip", role: "tooltip" }, helpText)
  );
}

/**
 * Wraps a label + input with a help-icon tooltip instead of a description
 * beside/below the field. `helpId` becomes both the tooltip's id and the
 * input's id fallback.
 */
export function tooltipField(labelText, input, helpText, helpId, className) {
  input.id = input.id || helpId + "-input";
  input.setAttribute("aria-describedby", helpId);
  return el("div", { className: "stack tooltip-field" + (className ? " " + className : "") },
    el("div", { className: "field-label-row" },
      el("label", { htmlFor: input.id }, labelText),
      helpTooltip(labelText, helpText, helpId)
    ),
    input
  );
}

/** A titled group of fields, used to break a long form into scannable sections. */
export function formSection(title, description, content) {
  return el("section", { className: "form-section" },
    el("div", { className: "form-section-heading" },
      el("h3", null, title),
      el("p", null, description)
    ),
    content
  );
}

/**
 * Themed replacement for a native <select> — the browser renders a native
 * select's open popup with OS chrome that ignores page CSS entirely, so on
 * platforms with a dark system theme it shows up as an unstyled dark menu
 * regardless of how the closed control is styled. This renders both the
 * closed control and the open listbox from page markup, and exposes the
 * same `.value`/`.disabled` + "change" event surface as a native select so
 * it can be swapped in without touching caller wiring.
 *
 * options: [{ value, label }]
 */
/**
 * `searchable: true` adds a type-to-filter box at the top of the open
 * listbox — for option lists that can run into the hundreds (e.g. adapters,
 * personas), scrolling to find one entry isn't practical.
 */
export function createSelect({ options = [], value, ariaLabel, className = "", searchable = false, searchPlaceholder = "Search" } = {}) {
  let opts = options;
  // Mirrors a native <select>: with no explicit value, the first option is
  // the implicit selection rather than a blank trigger.
  let selected = value !== undefined ? value : (opts.length ? opts[0].value : null);
  let activeIndex = -1;
  let query = "";

  const valueLabel = el("span", { className: "styled-select-value" });
  const trigger = el("button", {
    type: "button",
    className: `styled-select-trigger ${className}`.trim(),
    "aria-haspopup": "listbox",
    "aria-expanded": "false",
    "aria-label": ariaLabel || null,
  },
    valueLabel,
    el("svg", { className: "styled-select-chevron", viewBox: "0 0 14 9", fill: "none", "aria-hidden": "true" },
      el("path", { d: "M1.5 1.5 7 7l5.5-5.5", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round" }))
  );
  const listbox = el("ul", { className: "styled-select-listbox", role: "listbox", tabindex: searchable ? "-1" : "-1" });
  const searchInput = searchable ? el("input", {
    type: "text",
    className: "styled-select-search",
    placeholder: searchPlaceholder,
    "aria-label": searchPlaceholder,
    autocomplete: "off",
  }) : null;
  const root = el("div", { className: `styled-select${searchable ? " has-search" : ""}` }, trigger, listbox);
  const searchRow = searchInput ? el("li", { className: "styled-select-search-row", role: "presentation" }, searchInput) : null;

  function filteredOptions() {
    if (!query) return opts;
    const lc = query.toLowerCase();
    return opts.filter((o) => o.label.toLowerCase().indexOf(lc) !== -1);
  }

  function close() {
    root.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    listbox.hidden = true;
    if (searchInput) { query = ""; searchInput.value = ""; }
  }

  function open() {
    if (trigger.disabled) return;
    query = "";
    root.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    listbox.hidden = false;
    activeIndex = Math.max(0, filteredOptions().findIndex((o) => o.value === selected));
    renderListOptions();
    if (searchInput) searchInput.focus();
    else listbox.focus();
  }

  function highlight() {
    listbox.querySelectorAll(".styled-select-option").forEach((node, idx) => {
      node.classList.toggle("is-active", idx === activeIndex);
      node.setAttribute("aria-selected", node.dataset.value === selected ? "true" : "false");
    });
  }

  function scrollActiveIntoView() {
    const activeEl = listbox.querySelector(".styled-select-option.is-active");
    if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
  }

  function commit(newValue) {
    const changed = newValue !== selected;
    selected = newValue;
    updateValueLabel();
    close();
    trigger.focus();
    if (changed) root.dispatchEvent(new Event("change"));
  }

  function updateValueLabel() {
    const current = opts.find((o) => o.value === selected);
    valueLabel.textContent = current ? current.label : "";
  }

  function optionItem(opt, idx) {
    return el("li", {
      className: "styled-select-option" + (idx === activeIndex ? " is-active" : ""),
      role: "option",
      "data-value": opt.value,
      "aria-selected": opt.value === selected ? "true" : "false",
      onMousedown: (e) => e.preventDefault(),
      // A wrapping <label> (as used for form fields) forwards any click
      // outside the labeled control's own subtree as a synthetic click on
      // that control — and an option <li> is a sibling of the trigger
      // button, not its descendant, so it qualifies. Without preventDefault
      // here, that synthetic click lands right after commit()'s close()
      // and immediately reopens the dropdown.
      onClick: (e) => { e.preventDefault(); commit(opt.value); },
    }, opt.label);
  }

  function renderListOptions() {
    // The search row holds the live, focused <input> — rebuilding it on every
    // keystroke (as clear(listbox) would) detaches that input from the DOM
    // and the browser drops its focus, so only the first keystroke ever
    // lands. Keep that row in place and only replace the option rows below it.
    if (searchRow) {
      Array.from(listbox.children).forEach((child) => { if (child !== searchRow) child.remove(); });
      if (!searchRow.isConnected) listbox.appendChild(searchRow);
    } else {
      clear(listbox);
    }
    const list = filteredOptions();
    if (searchable && !list.length) {
      listbox.appendChild(el("li", { className: "styled-select-empty", role: "presentation" }, "No matches"));
    }
    list.forEach((opt, idx) => listbox.appendChild(optionItem(opt, idx)));
  }

  function renderOptions() {
    updateValueLabel();
    if (!listbox.hidden) renderListOptions();
  }

  trigger.addEventListener("click", () => (root.classList.contains("is-open") ? close() : open()));

  function handleNavKey(e) {
    const list = filteredOptions();
    if (e.key === "Escape") { e.preventDefault(); close(); trigger.focus(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); activeIndex = Math.min(list.length - 1, activeIndex + 1); highlight(); scrollActiveIntoView(); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); activeIndex = Math.max(0, activeIndex - 1); highlight(); scrollActiveIntoView(); return; }
    if (e.key === "Enter" || (e.key === " " && !searchInput)) { e.preventDefault(); if (list[activeIndex]) commit(list[activeIndex].value); return; }
    if (e.key === "Tab") close();
  }

  listbox.addEventListener("keydown", (e) => { if (!searchInput) handleNavKey(e); });

  if (searchInput) {
    searchInput.addEventListener("keydown", handleNavKey);
    searchInput.addEventListener("input", () => {
      query = searchInput.value.trim();
      activeIndex = query ? 0 : Math.max(0, filteredOptions().findIndex((o) => o.value === selected));
      renderListOptions();
    });
  }

  function onDocumentClick(e) {
    if (!root.contains(e.target)) close();
  }
  document.addEventListener("click", onDocumentClick);

  let destroyed = false;
  root.destroy = () => {
    if (destroyed) return;
    destroyed = true;
    document.removeEventListener("click", onDocumentClick);
    liveSelects.delete(entry);
    if (liveSelects.size === 0 && selectGcObserver) {
      selectGcObserver.disconnect();
      selectGcObserver = null;
    }
  };
  const entry = { root, destroy: root.destroy };
  trackSelect(entry);

  Object.defineProperty(root, "value", {
    get() { return selected; },
    set(v) { selected = v; renderOptions(); },
  });

  Object.defineProperty(root, "disabled", {
    get() { return trigger.disabled; },
    set(v) { trigger.disabled = !!v; root.classList.toggle("is-disabled", !!v); if (v) close(); },
  });

  root.setOptions = (newOptions, newValue) => {
    opts = newOptions;
    if (newValue !== undefined) selected = newValue;
    renderOptions();
  };

  updateValueLabel();
  close();
  return root;
}
