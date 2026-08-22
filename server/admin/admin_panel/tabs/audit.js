const AUDIT_PAGE_SIZE = 25;
const AUDIT_STREAMS = [
  { value: "all", label: "All" },
  { value: "admin", label: "Admin" },
  { value: "chat", label: "Inference" },
];

const AUDIT_DOMAINS = [
  { value: "all",             label: "All" },
  { value: "auth.",           label: "Auth" },
  { value: "admin.api_key.",  label: "API Keys" },
  { value: "admin.config",    label: "Config" },
  { value: "admin.adapter.",  label: "Adapters" },
  { value: "admin.server.",   label: "Server" },
  { value: "admin.prompt.",   label: "Prompts" },
  { value: "admin.quota.",    label: "Quotas" },
];

const CALL_TYPE_LABELS = {
  chat: "Chat",
  embedding: "Embedding",
  reranking: "Reranking",
  image: "Image",
  video: "Video",
  audio: "Audio",
  document: "Document",
};

const AUDIT_CALL_TYPES = [
  { value: "all",       label: "All" },
  { value: "chat", label: "Chat" },
  { value: "embedding", label: "Embedding" },
  { value: "reranking", label: "Reranking" },
  { value: "image",     label: "Image" },
  { value: "video",     label: "Video" },
  { value: "audio",     label: "Audio" },
  { value: "document",  label: "Document" },
];

export function createAuditTab({ api, endpoints, el, clear, skeleton, refreshButton, formatNum, markSelectedRow, createSelect }) {
  function obsCost(value) {
    if (value == null) return "—";
    if (value === 0) return "$0.00";
    // Scale precision to magnitude — a per-request average can be a few
    // hundredths of a cent, and 4 decimal places (the old fixed precision)
    // rounds anything below $0.00005 down to a misleading "$0.0000".
    const frac = value < 0.001 ? 8 : value < 1 ? 4 : 2;
    return "$" + formatNum(value, frac);
  }

  function formatAuditTimestamp(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate())
      + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }

  function isChatAudit(ev) {
    return !!ev && ev.audit_source === "chat";
  }

  function displayActorId(ev) {
    if (!ev) return "—";
    if (ev.actor_type === "anonymous") return "anonymous";
    return ev.actor_id || ev.actor_username || "—";
  }

  function auditCallType(ev) {
    return (ev && ev.call_type) || "chat";
  }

  function auditSourceLabel(ev) {
    if (isChatAudit(ev)) return CALL_TYPE_LABELS[auditCallType(ev)] || "Chat";
    return "Admin";
  }

  function auditSourceBadgeClass(ev) {
    if (isChatAudit(ev)) return "audit-source-badge audit-source-badge--" + auditCallType(ev);
    return "audit-source-badge audit-source-badge--admin";
  }

  function auditEventTitle(ev) {
    if (isChatAudit(ev)) return ev.title || ev.provider || "chat";
    return ev.event_type || "—";
  }

  function auditEventSubtitle(ev) {
    if (isChatAudit(ev)) return ev.subtitle || ev.adapter_name || "chat request";
    return ev.action || "";
  }

  function auditResourceText(ev) {
    if (isChatAudit(ev)) {
      return ev.adapter_name || ev.provider || ev.resource_id || "—";
    }
    return ev.resource_id || ev.resource_type || "—";
  }

  function auditOutcomeLabel(ev) {
    if (isChatAudit(ev)) {
      return ev.success ? "served" : "blocked";
    }
    return ev.success ? "ok" : "fail";
  }

  function renderAuditFieldGrid(rows) {
    const dl = el("dl", { className: "audit-field-grid" });
    rows.forEach((row) => {
      dl.appendChild(el("dt", null, row[0]));
      dl.appendChild(el("dd", null, row[1] == null || row[1] === "" ? "—" : row[1]));
    });
    return dl;
  }

  function renderAuditDossier(panel, ev, onClose) {
    clear(panel);

    const closeBtn = el("button", { type: "button", className: "secondary audit-dossier__close" }, "Close");
    closeBtn.addEventListener("click", onClose);
    panel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Details"),
      closeBtn
    ));

    panel.appendChild(el("div", { className: "audit-dossier__headline" },
      el("div", { className: "audit-dossier__meta" },
        el("span", { className: auditSourceBadgeClass(ev) }, auditSourceLabel(ev))
      ),
      el("div", { className: "audit-dossier__event-type" }, auditEventTitle(ev)),
      auditEventSubtitle(ev) ? el("div", { className: "audit-dossier__action muted" }, auditEventSubtitle(ev)) : null
    ));

    const verdictCls = "audit-verdict audit-verdict--" + (ev.success ? "success" : "failure");
    panel.appendChild(el("div", null,
      el("span", { className: verdictCls },
        isChatAudit(ev) ? (ev.success ? "Served" : "Blocked") : (ev.success ? "Succeeded" : "Failed"),
        isChatAudit(ev)
          ? " · " + (ev.provider || "chat")
          : " · HTTP " + (ev.status_code != null ? ev.status_code : "?")
      )
    ));

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Principals"));
    if (isChatAudit(ev)) {
      panel.appendChild(renderAuditFieldGrid([
        ["Actor type", ev.actor_type || ""],
        ["Actor ID", ev.actor_id || "—"],
        ["User ID", ev.user_id || "—"],
        ["API key", ev.api_key && ev.api_key.key ? ev.api_key.key : "—"],
        ["Session", ev.session_id || "—"],
      ]));
    } else {
      panel.appendChild(renderAuditFieldGrid([
        ["Actor type", ev.actor_type || ""],
        ["Actor ID", ev.actor_id || "—"],
        ["Resource", ev.resource_id || "—"],
        ["Resource kind", ev.resource_type || ""],
      ]));
    }

    panel.appendChild(el("h3", { className: "audit-section-heading" }, isChatAudit(ev) ? "Chat" : "Request"));
    if (isChatAudit(ev)) {
      panel.appendChild(renderAuditFieldGrid([
        ["Provider", ev.provider || "—"],
        ["Model", ev.model || "—"],
        ["Adapter", ev.adapter_name || "—"],
        ["Blocked", ev.blocked ? "yes" : "no"],
        ["Timestamp", formatAuditTimestamp(ev.timestamp)],
        ["Event type", ev.event_type || ""],
        ["Action", ev.action || ""],
      ]));
    } else {
      panel.appendChild(renderAuditFieldGrid([
        ["Method", ev.method || ""],
        ["Path", ev.path || ""],
        ["Status", String(ev.status_code != null ? ev.status_code : "") + (ev.error_message ? " · " + ev.error_message : "")],
        ["Timestamp", formatAuditTimestamp(ev.timestamp)],
        ["Event type", ev.event_type || ""],
        ["Action", ev.action || ""],
      ]));
    }

    if (isChatAudit(ev)) {
      panel.appendChild(el("h3", { className: "audit-section-heading" }, "Usage & cost"));
      const usageRows = [
        ["Prompt tokens", ev.prompt_tokens != null ? formatNum(ev.prompt_tokens) : "—"],
        ["Completion tokens", ev.completion_tokens != null ? formatNum(ev.completion_tokens) : "—"],
        ["Total tokens", ev.total_tokens != null ? formatNum(ev.total_tokens) : "—"],
        ["Estimated cost", obsCost(ev.cost_usd)],
        ["Input rate / 1M", ev.input_rate_per_1m != null ? "$" + formatNum(ev.input_rate_per_1m, 4) : "—"],
        ["Output rate / 1M", ev.output_rate_per_1m != null ? "$" + formatNum(ev.output_rate_per_1m, 4) : "—"],
        ["Pricing source", ev.pricing_source || "—"],
      ];
      // Only shown when the provider actually breaks reasoning/thinking
      // tokens out separately (OpenAI o-series/gpt-5, Gemini) — already
      // included in "Completion tokens" above, purely informational.
      if (ev.reasoning_tokens != null) {
        usageRows.splice(2, 0, ["Reasoning tokens", formatNum(ev.reasoning_tokens)]);
      }
      // Only shown when the provider reports a prompt-cache hit (Anthropic
      // cache_control, DeepSeek/xAI automatic caching) — already included in
      // "Prompt tokens" above; priced at a discount when the pricing table
      // has a cached_input_per_1m tier configured for this provider/model
      // (see PricingService.estimate), otherwise at the full input rate.
      if (ev.cached_prompt_tokens != null) {
        usageRows.splice(1, 0, ["Cached prompt tokens", formatNum(ev.cached_prompt_tokens)]);
      }
      // Only shown for discrete-unit media requests (images/video seconds/
      // TTS characters/STT seconds/OCR pages) — token-billed requests never
      // set these, so the row is omitted entirely rather than showing "—".
      if (ev.usage_unit != null && ev.usage_quantity != null) {
        usageRows.push(["Usage", formatNum(ev.usage_quantity) + " " + ev.usage_unit]);
      }
      panel.appendChild(renderAuditFieldGrid(usageRows));
    }

    panel.appendChild(el("h3", { className: "audit-section-heading" }, "Origin"));
    const originRows = [
      ["IP", ev.ip || "—"],
    ];
    if (ev.ip_metadata) {
      if (ev.ip_metadata.source) originRows.push(["Source", ev.ip_metadata.source]);
      if (ev.ip_metadata.type) originRows.push(["Type", ev.ip_metadata.type]);
    }
    if (ev.user_agent) originRows.push(["User-Agent", ev.user_agent]);
    panel.appendChild(renderAuditFieldGrid(originRows));

    if (isChatAudit(ev)) {
      panel.appendChild(el("h3", { className: "audit-section-heading" }, "Payload"));
      panel.appendChild(el("div", { className: "audit-dossier__payload" },
        el("div", { className: "audit-dossier__payload-block" },
          el("div", { className: "audit-dossier__payload-label" }, "Query"),
          el("pre", { className: "audit-dossier__summary" }, ev.query || "—")
        ),
        el("div", { className: "audit-dossier__payload-block" },
          el("div", { className: "audit-dossier__payload-label" }, "Response"),
          el("pre", { className: "audit-dossier__summary" }, ev.response || "—")
        )
      ));
    } else {
      const summary = ev.request_summary;
      if (summary && typeof summary === "object" && Object.keys(summary).length > 0) {
        panel.appendChild(el("h3", { className: "audit-section-heading" }, "Request summary"));
        panel.appendChild(el("p", { className: "muted audit-dossier__summary-note" },
          "Fields recorded by the middleware — secrets (passwords, raw API keys) are never stored."));
        const lines = Object.keys(summary).map((k) => {
          const v = summary[k];
          const vStr = Array.isArray(v) ? "[" + v.map((x) => JSON.stringify(x)).join(", ") + "]" : JSON.stringify(v);
          return k + ": " + vStr;
        });
        panel.appendChild(el("pre", { className: "audit-dossier__summary" }, lines.join("\n")));
      }
    }
  }

  function renderAuditTable(wrap, state, onSelect) {
    clear(wrap);
    const events = state.lastPage || [];
    if (events.length === 0) {
      wrap.appendChild(el("div", { className: "empty-state" },
        el("p", null, "No events match the current filters."),
        el("p", { className: "muted" },
          state.offset > 0
            ? "Try jumping to page 1 or loosening the filters."
            : "As admin actions and chat requests occur they will appear here.")
      ));
      return;
    }

    const table = el("table", { className: "audit-table" });
    const thead = el("thead", null,
      el("tr", null,
        el("th", null, "Time"),
        el("th", null, "Event"),
        el("th", null, "Principal"),
        el("th", null, "Resource"),
        el("th", { className: "audit-col-tokens" }, "Tokens"),
        el("th", { className: "audit-col-cost" }, "Cost"),
        el("th", { className: "audit-col-status" }, "Status")
      )
    );
    const tbody = el("tbody");

    events.forEach((ev, idx) => {
      const statusCls = ev.success ? "badge-ok" : "badge-fail";
      const statusLabel = auditOutcomeLabel(ev);
      const isSelected = state.selectedIndex === idx;

      let actorCell;
      if (ev.actor_type === "anonymous") {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-anon" }, "anonymous"),
          el("div", { className: "audit-actor-role" }, ev.actor_type)
        );
      } else {
        actorCell = el("div", null,
          el("span", { className: "audit-actor-name" }, displayActorId(ev)),
          el("div", { className: "audit-actor-role" }, ev.actor_type || "")
        );
      }

      const resourceText = auditResourceText(ev);

      let rowClass = "selectable-row audit-row audit-row--source-" + (isChatAudit(ev) ? "chat" : "admin");
      if (isSelected) rowClass += " selected-row audit-row--active";

      const tr = el("tr", { className: rowClass },
        el("td", { className: "audit-col-time" }, formatAuditTimestamp(ev.timestamp)),
        el("td", { className: "audit-col-event" },
          el("div", { className: "audit-event-meta" },
            el("span", { className: auditSourceBadgeClass(ev) }, auditSourceLabel(ev))
          ),
          el("div", { className: "audit-event-type" }, auditEventTitle(ev)),
          el("div", { className: "audit-event-action muted" }, auditEventSubtitle(ev))
        ),
        el("td", null, actorCell),
        el("td", { className: "audit-col-resource" }, resourceText),
        el("td", { className: "audit-col-tokens" },
          isChatAudit(ev) && ev.total_tokens != null ? formatNum(ev.total_tokens) : "—"),
        el("td", { className: "audit-col-cost", title: isChatAudit(ev) ? (ev.pricing_source || "") : "" },
          isChatAudit(ev) ? obsCost(ev.cost_usd) : "—"),
        el("td", { className: "audit-col-status" },
          el("span", { className: "audit-status-code" }, isChatAudit(ev) ? (ev.provider || "") : String(ev.status_code != null ? ev.status_code : "")),
          el("span", { className: "badge " + statusCls }, statusLabel)
        )
      );
      tr.tabIndex = 0;
      tr.setAttribute("aria-selected", isSelected ? "true" : "false");
      tr.addEventListener("click", () => {
        markSelectedRow(tbody, tr);
        onSelect(idx);
      });
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          tr.click();
        }
      });
      tbody.appendChild(tr);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.appendChild(el("div", { className: "table-wrap" }, table));
  }

  // Mirrors admin_panel.js's createPaginator numbering (ellipsis past 7 pages) —
  // that one paginates an already-loaded client-side array, while audit rows
  // are fetched a page at a time from the server, so the page list here is
  // driven by resp.total/offset instead of an in-memory item count.
  function buildAuditPageNumbers(cur, total) {
    if (total <= 7) {
      const arr = [];
      for (let i = 1; i <= total; i++) arr.push(i);
      return arr;
    }
    const pages = [1];
    if (cur > 3) pages.push("...");
    for (let j = Math.max(2, cur - 1); j <= Math.min(total - 1, cur + 1); j++) pages.push(j);
    if (cur < total - 2) pages.push("...");
    pages.push(total);
    return pages;
  }

  function renderAuditPager(bar, state, resp, reload) {
    clear(bar);
    const returned = (resp && resp.returned) || 0;
    const total = (resp && resp.total) || 0;
    if (state.offset === 0 && returned === 0) return;

    const pageNum = Math.floor(state.offset / AUDIT_PAGE_SIZE) + 1;
    const totalPages = Math.max(pageNum, Math.ceil(total / AUDIT_PAGE_SIZE));
    const start = state.offset + 1;
    const end = state.offset + returned;

    function goToPage(n) {
      n = Math.max(1, Math.min(n, totalPages));
      state.offset = (n - 1) * AUDIT_PAGE_SIZE;
      state.selectedIndex = null;
      reload();
    }

    bar.appendChild(el("span", { className: "pagination-info" },
      returned > 0
        ? "Showing " + start + "–" + end + " of " + total
        : "Page " + pageNum));

    const btns = el("div", { className: "pagination-buttons" });
    const prevAttrs = { type: "button", className: "pagination-btn", "aria-label": "Previous page" };
    if (pageNum <= 1) prevAttrs.disabled = "true";
    const prevBtn = el("button", prevAttrs, "‹");
    prevBtn.addEventListener("click", () => goToPage(pageNum - 1));
    btns.appendChild(prevBtn);

    buildAuditPageNumbers(pageNum, totalPages).forEach((p) => {
      if (p === "...") {
        btns.appendChild(el("span", { className: "pagination-ellipsis" }, "…"));
        return;
      }
      const pageAttrs = {
        type: "button",
        className: "pagination-btn" + (p === pageNum ? " active" : ""),
        "aria-label": "Page " + p,
      };
      if (p === pageNum) pageAttrs["aria-current"] = "page";
      const btn = el("button", pageAttrs, String(p));
      btn.addEventListener("click", () => goToPage(p));
      btns.appendChild(btn);
    });

    const nextAttrs = { type: "button", className: "pagination-btn", "aria-label": "Next page" };
    if (pageNum >= totalPages) nextAttrs.disabled = "true";
    const nextBtn = el("button", nextAttrs, "›");
    nextBtn.addEventListener("click", () => goToPage(pageNum + 1));
    btns.appendChild(nextBtn);

    bar.appendChild(btns);
  }

  async function render(container) {
    // ----- Layout: the dossier is added only after a row is selected -----
    const layout = el("div", { className: "tab-stacked-layout audit-view" });
    const listPanel = el("div", { className: "panel audit-view__list" });
    layout.appendChild(listPanel);
    container.appendChild(layout);
    let detailPanel = null;

    // Refresh sits beside the ledger title, not in the filter strip: it acts on
    // the whole register, while every control in the strip narrows it.
    const refreshBtn = refreshButton("Refresh the register", () => { state.selectedIndex = null; load(); });

    listPanel.appendChild(el("div", { className: "panel-header-row" },
      el("h2", null, "Audit Ledger"),
      refreshBtn
    ));
    listPanel.appendChild(el("p", { className: "muted" },
      "A unified register of admin/auth activity and chat requests captured by the audit service. ",
      "Use the stream filter to isolate operational events from live chat traffic."));

    // ----- State (per-render closure) -----
    const state = {
      source: "all",          // "all" | "admin" | "chat"
      outcome: "all",        // "all" | "success" | "failure"
      domain: "all",         // event_prefix value, or "all"
      callType: "all",       // call_type value, or "all"
      q: "",                 // free-text search
      offset: 0,
      selectedIndex: null,
      lastPage: [],
      loading: false,
    };
    let searchDebounce = null;

    // ----- Filter strip -----
    const sourceSelect = createSelect({ className: "audit-view__select", ariaLabel: "Filter audit stream" });
    const outcomeSelect = createSelect({ className: "audit-view__select", ariaLabel: "Filter audit outcome" });
    const domainSelect = createSelect({ className: "audit-view__select", ariaLabel: "Filter audit domain" });
    const callTypeSelect = createSelect({ className: "audit-view__select", ariaLabel: "Filter audit call type" });
    const searchInput = el("input", {
      type: "search",
      placeholder: "Search actor id, provider, query, path, resource, IP…",
      "aria-label": "Search audit events",
      className: "audit-view__search-input",
    });

    function renderFilters() {
      sourceSelect.setOptions(AUDIT_STREAMS.map((s) => ({ value: s.value, label: s.label })), state.source);

      outcomeSelect.setOptions([
        { value: "all", label: "All" },
        { value: "success", label: "Succeeded" },
        { value: "failure", label: "Failed" },
      ], state.outcome);

      domainSelect.setOptions(AUDIT_DOMAINS.map((d) => ({ value: d.value, label: d.label })), state.domain);
      domainSelect.disabled = state.source === "chat";

      callTypeSelect.setOptions(AUDIT_CALL_TYPES.map((t) => ({ value: t.value, label: t.label })), state.callType);
      callTypeSelect.disabled = state.source === "admin";
    }

    sourceSelect.addEventListener("change", () => {
      state.source = sourceSelect.value;
      if (state.source === "chat") state.domain = "all";
      if (state.source === "admin") state.callType = "all";
      state.offset = 0;
      state.selectedIndex = null;
      renderFilters();
      load();
    });

    outcomeSelect.addEventListener("change", () => {
      state.outcome = outcomeSelect.value;
      state.offset = 0;
      state.selectedIndex = null;
      load();
    });

    domainSelect.addEventListener("change", () => {
      state.domain = domainSelect.value;
      state.offset = 0;
      state.selectedIndex = null;
      load();
    });

    callTypeSelect.addEventListener("change", () => {
      state.callType = callTypeSelect.value;
      state.offset = 0;
      state.selectedIndex = null;
      load();
    });

    searchInput.addEventListener("input", (e) => {
      const v = (e.target.value || "").trim();
      if (searchDebounce) clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        state.q = v;
        state.offset = 0;
        state.selectedIndex = null;
        load();
      }, 250);
    });

    listPanel.appendChild(el("div", { className: "audit-view__filters" },
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Stream"),
        sourceSelect
      ),
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Outcome"),
        outcomeSelect
      ),
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Domain"),
        domainSelect
      ),
      el("label", { className: "audit-view__filter-field" },
        el("span", { className: "audit-view__filter-label" }, "Type"),
        callTypeSelect
      ),
      el("div", { className: "audit-view__search" }, searchInput)
    ));
    renderFilters();

    // ----- Table wrap + pagination -----
    const tableWrap = el("div", { className: "audit-view__table-wrap" }, skeleton());
    const pagerBar = el("div", { className: "audit-view__pager pagination-bar" });
    listPanel.appendChild(tableWrap);
    listPanel.appendChild(pagerBar);

    function hideDossier() {
      if (!detailPanel) return;
      detailPanel.remove();
      detailPanel = null;
      layout.classList.remove("audit-view--detail-open");
    }

    function showDossier(ev) {
      if (!detailPanel) {
        detailPanel = el("div", { className: "panel audit-view__detail" });
        layout.appendChild(detailPanel);
        layout.classList.add("audit-view--detail-open");
      }
      renderAuditDossier(detailPanel, ev, () => {
        state.selectedIndex = null;
        hideDossier();
        Array.prototype.forEach.call(
          tableWrap.querySelectorAll("tr.audit-row"),
          (tr) => {
            tr.classList.remove("selected-row", "audit-row--active");
            tr.setAttribute("aria-selected", "false");
          }
        );
      });
    }

    // At narrow widths the dossier stacks under the ledger, so bring it into
    // view on selection instead of leaving the reader to hunt for it. Above the
    // split breakpoint it is already beside the table and must not move.
    function revealDossier() {
      if (!detailPanel) return;
      if (window.matchMedia("(min-width: 1280px)").matches) return;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      detailPanel.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }

    // ----- Data loading -----
    async function load() {
      if (state.loading) return;
      state.loading = true;
      if (state.selectedIndex === null) hideDossier();
      clear(tableWrap);
      tableWrap.appendChild(skeleton());
      clear(pagerBar);

      const params = new URLSearchParams();
      params.set("limit", String(AUDIT_PAGE_SIZE));
      params.set("offset", String(state.offset));
      params.set("source", state.source);
      if (state.outcome === "success") params.set("success", "true");
      else if (state.outcome === "failure") params.set("success", "false");
      if (state.domain && state.domain !== "all" && state.source !== "chat") params.set("event_prefix", state.domain);
      if (state.callType && state.callType !== "all" && state.source !== "admin") params.set("call_type", state.callType);
      if (state.q) params.set("q", state.q);

      try {
        const resp = await api("GET", endpoints.auditEvents + "?" + params.toString());
        state.lastPage = resp.events || [];
        renderAuditTable(tableWrap, state, (idx) => {
          state.selectedIndex = idx;
          showDossier(state.lastPage[idx]);
          Array.prototype.forEach.call(
            tableWrap.querySelectorAll("tr.audit-row"),
            (tr, i) => { tr.classList.toggle("audit-row--active", i === idx); }
          );
          revealDossier();
        });
        renderAuditPager(pagerBar, state, resp, load);
      } catch (err) {
        clear(tableWrap);
        const msg = (err && err.message) || "";
        if (/audit ledger is not enabled/i.test(msg) || /admin audit is not enabled/i.test(msg) || /chat request audit is not enabled/i.test(msg)) {
          tableWrap.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Audit ledger is not enabled."),
            el("p", { className: "muted" },
              "Set ",
              el("code", null, "internal_services.audit.enabled: true"),
              " for chat request auditing, and ",
              el("code", null, "internal_services.audit.admin_events.enabled: true"),
              " if you also want admin/auth events, then restart the server.")
          ));
        } else {
          tableWrap.appendChild(el("div", { className: "empty-state" },
            el("p", null, "Failed to load audit events."),
            el("p", { className: "muted" }, (err && err.message) || "Unknown error")
          ));
        }
      } finally {
        state.loading = false;
      }
    }

    load();
  }

  return { render };
}
