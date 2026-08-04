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
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function wrapTable(table) {
  return el("div", { className: "table-wrap" }, table);
}
