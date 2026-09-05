/** Small DOM primitives shared by admin-panel feature modules. */
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

export function clear(node) {
  node.querySelectorAll?.(".styled-select").forEach((select) => select.destroy?.());
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

export function wrapTable(table) {
  return el("div", { className: "table-wrap" }, table);
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
export function createSelect({ options = [], value, ariaLabel, className = "" } = {}) {
  let opts = options;
  // Mirrors a native <select>: with no explicit value, the first option is
  // the implicit selection rather than a blank trigger.
  let selected = value !== undefined ? value : (opts.length ? opts[0].value : null);
  let activeIndex = -1;

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
  const listbox = el("ul", { className: "styled-select-listbox", role: "listbox", tabindex: "-1" });
  const root = el("div", { className: "styled-select" }, trigger, listbox);

  function close() {
    root.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    listbox.hidden = true;
  }

  function open() {
    if (trigger.disabled) return;
    activeIndex = Math.max(0, opts.findIndex((o) => o.value === selected));
    root.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    listbox.hidden = false;
    highlight();
    listbox.focus();
  }

  function highlight() {
    Array.from(listbox.children).forEach((node, idx) => {
      node.classList.toggle("is-active", idx === activeIndex);
      node.setAttribute("aria-selected", node.dataset.value === selected ? "true" : "false");
    });
  }

  function commit(newValue) {
    const changed = newValue !== selected;
    selected = newValue;
    renderOptions();
    close();
    trigger.focus();
    if (changed) root.dispatchEvent(new Event("change"));
  }

  function renderOptions() {
    clear(listbox);
    const current = opts.find((o) => o.value === selected);
    valueLabel.textContent = current ? current.label : "";
    opts.forEach((opt) => {
      const item = el("li", {
        className: "styled-select-option",
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
      listbox.appendChild(item);
    });
  }

  trigger.addEventListener("click", () => (root.classList.contains("is-open") ? close() : open()));

  listbox.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); trigger.focus(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); activeIndex = Math.min(opts.length - 1, activeIndex + 1); highlight(); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); activeIndex = Math.max(0, activeIndex - 1); highlight(); return; }
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (opts[activeIndex]) commit(opts[activeIndex].value); return; }
    if (e.key === "Tab") close();
  });

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

  renderOptions();
  close();
  return root;
}
