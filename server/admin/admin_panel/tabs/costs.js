import { chartTheme } from "../core/charts.js";

const GROUP_BY_LABELS = {
  model: "Model",
  provider: "Provider",
  adapter_name: "Adapter",
  user_id: "User",
  call_type: "Call type",
  api_key: "API key",
};

export function createCostsTab({ api, endpoints, el, clear, wrapTable, skeleton, refreshButton, formatNum, chartOptions, renderMetricCard, createSelect, getActiveTab }) {
  let charts = {};
  let selectedWindowDays = 7;
  let selectedGroupBy = "model";
  let selectedCallType = "all";
  let selectedApiKey = null;
  let selectedApiKeyLabel = null;

  function dispose() {
    Object.keys(charts).forEach((key) => { try { charts[key].destroy(); } catch (_) {} });
    charts = {};
  }

  function obsCost(value) {
    if (value == null) return "—";
    if (value === 0) return "$0.00";
    // Scale precision to magnitude — a per-request average can be a few
    // hundredths of a cent, and 4 decimal places (the old fixed precision)
    // rounds anything below $0.00005 down to a misleading "$0.0000".
    const frac = value < 0.001 ? 8 : value < 1 ? 4 : 2;
    return "$" + formatNum(value, frac);
  }

  // Chart.js's built-in numeric formatter rounds very small values to "0".
  // Cost data commonly includes micro-dollar embedding and reranking calls,
  // so charts must use the same magnitude-aware formatter as the summary
  // cards and audit detail rather than implying those calls were free.
  function costTooltipCallbacks() {
    return {
      label: function (tooltipItem) {
        const parsed = tooltipItem.parsed;
        // Horizontal bars encode their numeric value on X; Y is only the
        // category index (which previously made the fourth row look like
        // "$3.00"). Lines use Y, and doughnut charts expose a scalar.
        const horizontal = tooltipItem.chart && tooltipItem.chart.options.indexAxis === "y";
        const value = typeof parsed === "number" ? parsed :
          (parsed && horizontal && parsed.x != null ? parsed.x :
            (parsed && parsed.y != null ? parsed.y :
              (parsed && parsed.x != null ? parsed.x : tooltipItem.raw)));
        const datasetLabel = tooltipItem.dataset && tooltipItem.dataset.label;
        return (datasetLabel ? datasetLabel + ": " : "") + obsCost(value);
      }
    };
  }

  function configureCostTooltip(options) {
    const tooltip = options.plugins.tooltip;
    tooltip.callbacks = costTooltipCallbacks();
    // Costs are names and currency, not console output: use the panel's UI
    // typeface at a compact, readable scale instead of the feedback chart's
    // intentionally prominent monospace tooltip style.
    tooltip.titleFont = { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 13, weight: "600" };
    tooltip.bodyFont = { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 12, weight: "500" };
    tooltip.padding = 12;
    tooltip.titleMarginBottom = 6;
    tooltip.boxPadding = 5;
    return options;
  }

  // Chart colors read from the same design tokens the rest of the admin
  // panel uses, so they track the light/dark theme instead of a fixed
  // palette tuned for one background. The 10-color categorical set reuses
  // the audit-log "content source" palette (already designed as a
  // theme-aware categorical family) rather than inventing a second one.
  function costsPalette() {
    const style = getComputedStyle(document.documentElement);
    const read = (name, fallback) => (style.getPropertyValue(name) || "").trim() || fallback;
    return {
      prompt: read("--brand-400", "#5b9bdc"),
      completion: read("--success-500", "#34d399"),
      cost: read("--warning-500", "#f2b84c"),
      cumulative: read("--brand-400", "#5b9bdc"),
      categorical: [
        read("--brand-400", "#5b9bdc"), read("--audit-chat-text", "#f3ac6d"),
        read("--audit-decision-text", "#5fd9cb"), read("--audit-moderation-text", "#f2918a"),
        read("--audit-embedding-text", "#c4a9f7"), read("--audit-image-text", "#6fd6ec"),
        read("--audit-video-text", "#f18cbb"), read("--audit-audio-text", "#7fe3a3"),
        read("--audit-document-text", "#e8d271"), read("--success-500", "#34d399"),
      ],
    };
  }

  function hexToRgba(hex, alpha) {
    const h = hex.replace("#", "");
    const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const value = parseInt(full, 16);
    if (isNaN(value)) return hex;
    const r = (value >> 16) & 255, g = (value >> 8) & 255, b = value & 255;
    return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
  }

  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // Bucket keys are wall-clock values in the audit log's storage timezone
  // (naive local, not UTC) — never run them through `new Date(string)`.
  // JS parses a date-only string ("2026-07-29") as UTC midnight, which
  // renders as the previous day in any timezone behind UTC; a bucket key
  // carrying an explicit UTC marker (Elasticsearch's "Z"-suffixed
  // key_as_string) is equally misleading here, since the underlying value
  // was naive-local, not a real UTC instant. Parse the numeric components
  // directly and format them as literal text instead of converting through
  // any timezone at all.
  function formatBucketLabel(bucketKey, isHourly) {
    const match = String(bucketKey).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}))?/);
    if (!match) return String(bucketKey);
    const month = parseInt(match[2], 10);
    const day = parseInt(match[3], 10);
    let label = MONTH_NAMES[month - 1] + " " + day;
    if (isHourly && match[4] != null) {
      const hour = parseInt(match[4], 10);
      const hour12 = hour % 12 || 12;
      label += " " + hour12 + (hour >= 12 ? "PM" : "AM");
    }
    return label;
  }

  function initCharts(data, onGroupRowClick) {
    dispose();
    if (typeof Chart === "undefined") return;

    const palette = costsPalette();

    const tokensCanvas = document.getElementById("obs-tokens-chart");
    if (tokensCanvas && data.series.length) {
      const opts = chartOptions();
      charts.tokens = new Chart(tokensCanvas, {
        type: "bar",
        data: {
          labels: data.series.map((item) => formatBucketLabel(item.bucket, data.window.bucket === "hour")),
          datasets: [
            { label: "Prompt tokens", data: data.series.map((item) => item.prompt_tokens), backgroundColor: palette.prompt, stack: "tokens" },
            { label: "Completion tokens", data: data.series.map((item) => item.completion_tokens), backgroundColor: palette.completion, stack: "tokens" }
          ]
        },
        options: Object.assign(opts, { scales: Object.assign(opts.scales, { x: Object.assign(opts.scales.x, { stacked: true }), y: Object.assign(opts.scales.y, { stacked: true }) }) })
      });
    }

    const costCanvas = document.getElementById("obs-cost-chart");
    if (costCanvas && data.series.length) {
      const costOpts = configureCostTooltip(chartOptions());
      let cumulative = 0;
      charts.cost = new Chart(costCanvas, {
        type: "line",
        data: {
          labels: data.series.map((item) => formatBucketLabel(item.bucket, data.window.bucket === "hour")),
          datasets: [
            { label: "Cost / bucket", data: data.series.map((item) => item.cost_usd), borderColor: palette.cost, backgroundColor: hexToRgba(palette.cost, 0.1), fill: true, tension: 0.25 },
            { label: "Cumulative", data: data.series.map((item) => { cumulative += item.cost_usd; return cumulative; }), borderColor: palette.cumulative, backgroundColor: "transparent", borderDash: [5, 4], yAxisID: "y1", tension: 0.2 }
          ]
        },
        options: Object.assign(costOpts, {
          scales: Object.assign(costOpts.scales, {
            // Chart.js's default tick formatter falls back to scientific
            // notation ("4.000000E-5") for the sub-cent values common here
            // (embedding/reranking calls priced in micro-dollars) - reuse the
            // same magnitude-aware formatter as the tooltip and summary cards.
            y: Object.assign(costOpts.scales.y, {
              ticks: Object.assign(costOpts.scales.y.ticks, { precision: undefined, callback: (value) => obsCost(value) })
            }),
            y1: {
              beginAtZero: true, position: "right", grid: { drawOnChartArea: false },
              ticks: { color: chartTheme().axisText, font: { size: 12 }, callback: (value) => obsCost(value) }
            }
          })
        })
      });
    }

    const modelsCanvas = document.getElementById("obs-models-chart");
    const groupRows = data.groups.slice(0, 10);
    // Rows are only clickable-to-filter when grouped by api_key — a group
    // row's `key` is the masked value the `api_key` filter param expects,
    // which is only true for this dimension.
    const clickable = typeof onGroupRowClick === "function" && selectedGroupBy === "api_key";
    const handleElementClick = (elements) => {
      if (!clickable || !elements.length) return;
      const row = groupRows[elements[0].index];
      if (row) onGroupRowClick(row);
    };
    if (modelsCanvas && groupRows.length) {
      const modelOpts = configureCostTooltip(chartOptions());
      modelOpts.indexAxis = "y";
      modelOpts.plugins.legend.display = false;
      // Bars are already sorted and capped at 10 rows, so a label per bar
      // reads as a value list rather than clutter — no per-bar hover needed
      // to answer "how much did the top model cost".
      modelOpts.plugins.datalabels = {
        display: true,
        anchor: "end",
        align: "end",
        clip: false,
        color: chartTheme().legendText,
        font: { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 11, weight: "600" },
        formatter: (value) => obsCost(value)
      };
      modelOpts.layout = { padding: { right: 48 } };
      if (clickable) {
        modelOpts.onClick = (_evt, elements) => handleElementClick(elements);
        modelOpts.onHover = (evt, elements) => { evt.native.target.style.cursor = elements.length ? "pointer" : "default"; };
      }
      charts.models = new Chart(modelsCanvas, {
        type: "bar",
        data: {
          labels: groupRows.map((row) => row.label || row.key || "(unknown)"),
          datasets: [{ data: groupRows.map((row) => row.cost_usd), backgroundColor: palette.prompt }]
        },
        options: modelOpts
      });
    }

    const providerCanvas = document.getElementById("obs-provider-chart");
    if (providerCanvas && groupRows.length) {
      const providerOpts = configureCostTooltip(chartOptions());
      const groupTotal = groupRows.reduce((sum, row) => sum + row.cost_usd, 0);
      providerOpts.plugins.datalabels = {
        display: (ctx) => groupTotal > 0 && ctx.dataset.data[ctx.dataIndex] / groupTotal >= 0.06,
        color: "#fff",
        font: { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 11, weight: "600" },
        formatter: (value) => groupTotal ? Math.round((value / groupTotal) * 100) + "%" : ""
      };
      const doughnutOptions = { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: providerOpts.plugins };
      if (clickable) {
        doughnutOptions.onClick = (_evt, elements) => handleElementClick(elements);
        doughnutOptions.onHover = (evt, elements) => { evt.native.target.style.cursor = elements.length ? "pointer" : "default"; };
      }
      charts.provider = new Chart(providerCanvas, {
        type: "doughnut",
        data: {
          labels: groupRows.map((row) => row.label || row.key || "(unknown)"),
          datasets: [{ data: groupRows.map((row) => row.cost_usd), backgroundColor: palette.categorical, borderWidth: 0, hoverOffset: 4 }]
        },
        options: doughnutOptions
      });
    }
  }

  // Charts cap at the top 10 rows for readability; the table underneath
  // lists every group so a long tail (e.g. many API keys) stays reachable
  // and, for the api_key dimension, every row - not just a chart bar -
  // can filter the page down to that key.
  function breakdownTable(container, rows, totalCost, groupBy, onRowClick) {
    if (!rows.length) {
      container.appendChild(el("p", { className: "muted" }, "No usage in this window to break down."));
      return;
    }
    // The endpoint caps a single request at 100 groups - at that cap there
    // may be more beyond what's shown, with no further groups fetchable
    // from here, so say so rather than implying this is the full set.
    if (rows.length >= 100) {
      container.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
        "Showing the top 100 groups by cost. Narrow the time window or call type filter to see others."));
    }
    const clickable = groupBy === "api_key" && typeof onRowClick === "function";
    const table = el("table", { className: "monitoring-table" });
    table.appendChild(el("thead", null, el("tr", null,
      el("th", null, GROUP_BY_LABELS[groupBy] || "Group"),
      el("th", { style: "text-align:right" }, "Cost"),
      el("th", null, "Share"),
      el("th", { style: "text-align:right" }, "Requests"),
      el("th", { style: "text-align:right" }, "Tokens"),
      clickable ? el("th", { style: "text-align:right" }, "Actions") : null
    )));
    const body = el("tbody");
    rows.forEach((row) => {
      const label = row.label || row.key || "(unknown)";
      const share = totalCost > 0 ? (row.cost_usd / totalCost) * 100 : 0;
      const shareCell = el("div", { style: "display:flex;align-items:center;gap:var(--sp-2);min-width:7rem" },
        el("span", null, formatNum(share, 1) + "%"),
        el("div", { className: "monitoring-progress-track", style: "flex:1;margin-top:0" },
          el("div", { className: "monitoring-progress-bar sky", style: "width:" + Math.min(100, Math.max(0, share)) + "%" })));
      const cells = [
        el("td", null, el("div", { className: "monitoring-table-primary", title: label }, label)),
        el("td", { style: "text-align:right;font-weight:600" }, obsCost(row.cost_usd)),
        el("td", null, shareCell),
        el("td", { style: "text-align:right" }, formatNum(row.requests)),
        el("td", { style: "text-align:right" }, formatNum(row.total_tokens)),
      ];
      if (clickable) {
        const filterBtn = el("button", { type: "button", className: "secondary" }, "Filter");
        filterBtn.addEventListener("click", () => onRowClick(row));
        cells.push(el("td", { style: "text-align:right" }, filterBtn));
      }
      body.appendChild(el("tr", null, cells));
    });
    table.appendChild(body);
    container.appendChild(wrapTable(table, clickable
      ? ["fluid", "number", "label", "number", "number", "actions"]
      : ["fluid", "number", "label", "number", "number"]));
  }

  async function render(container) {
    let requestVersion = 0;
    const groupBySelect = createSelect({
      className: "select-input",
      ariaLabel: "Group by",
      options: ["model", "provider", "adapter_name", "user_id", "call_type", "api_key"].map((opt) => ({ value: opt, label: GROUP_BY_LABELS[opt] })),
      value: selectedGroupBy
    });
    groupBySelect.addEventListener("change", () => { selectedGroupBy = groupBySelect.value; load(); });
    const callTypeSelect = createSelect({
      className: "select-input",
      ariaLabel: "Call type",
      options: [["all", "All call types"], ["chat", "Chat"], ["decision", "Decision"], ["moderation", "Moderation"], ["embedding", "Embedding"], ["reranking", "Reranking"], ["image", "Image"], ["video", "Video"], ["audio", "Audio"], ["document", "Document"]]
        .map(([value, label]) => ({ value, label })),
      value: selectedCallType
    });
    callTypeSelect.addEventListener("change", () => { selectedCallType = callTypeSelect.value; load(); });
    const header = el("div", { className: "panel-header-row costs-page-header" },
      el("div", { className: "monitoring-toolbar-right", id: "obs-window-controls" },
        [1, 7, 30].map((days) => {
          const button = el("button", {
            type: "button",
            className: "time-window-btn",
            "aria-pressed": days === selectedWindowDays ? "true" : "false"
          }, days === 1 ? "24h" : days + "d");
          button.addEventListener("click", () => {
            if (selectedWindowDays === days) return;
            selectedWindowDays = days;
            load();
          });
          return button;
        }),
        groupBySelect,
        callTypeSelect,
        refreshButton("Refresh costs data", () => load())
      ),
      el("div", null,
        el("h2", null, "Costs"),
        el("p", { className: "muted" }, "Usage and estimated cost across chat, embedding, and media providers. Cost is an estimate from the local rate table in config/pricing.yaml, not a provider invoice.")
      )
    );
    const chipRow = el("div", { id: "obs-filter-chip-row", style: "display:none" });
    const content = el("div", { style: "display:grid;gap:var(--sp-4)" }, skeleton());
    container.appendChild(header);
    container.appendChild(chipRow);
    container.appendChild(content);

    function renderApiKeyChip() {
      clear(chipRow);
      if (!selectedApiKey) {
        chipRow.style.display = "none";
        return;
      }
      chipRow.style.display = "block";
      const chip = el("span", {
        className: "select-input",
        style: "display:inline-flex;align-items:center;gap:var(--sp-2);padding:4px 10px;border-radius:999px"
      },
        el("span", null, "Filtered to: " + (selectedApiKeyLabel || selectedApiKey)),
        el("button", {
          type: "button",
          "aria-label": "Clear API key filter",
          style: "border:none;background:none;cursor:pointer;font-weight:600;padding:0 0 0 4px"
        }, "×")
      );
      chip.querySelector("button").addEventListener("click", () => {
        selectedApiKey = null;
        selectedApiKeyLabel = null;
        load();
      });
      chipRow.appendChild(chip);
    }
    renderApiKeyChip();

    function onGroupRowClick(row) {
      selectedApiKey = row.key;
      selectedApiKeyLabel = row.label || row.key;
      load();
    }

    async function load() {
      const version = ++requestVersion;
      header.querySelectorAll(".time-window-btn").forEach((button) => {
        const label = selectedWindowDays === 1 ? "24h" : selectedWindowDays + "d";
        button.setAttribute("aria-pressed", button.textContent === label ? "true" : "false");
      });
      dispose();
      renderApiKeyChip();
      clear(content);
      content.appendChild(skeleton());
      try {
        const params = new URLSearchParams();
        params.set("days", String(selectedWindowDays));
        params.set("bucket", selectedWindowDays <= 1 ? "hour" : "day");
        params.set("group_by", selectedGroupBy);
        // The breakdown table (unlike the top-10 chart) wants every group
        // it can get - 100 is the endpoint's hard cap (`limit_groups` is
        // 1-100), not a choice made here.
        params.set("limit_groups", "100");
        if (selectedCallType !== "all") params.set("call_type", selectedCallType);
        if (selectedApiKey) params.set("api_key", selectedApiKey);
        const data = await api("GET", endpoints.costsUsage + "?" + params.toString());
        if (version !== requestVersion || getActiveTab() !== "costs") return;
        clear(content);

        if (data.pricing && data.pricing.stale) {
          content.appendChild(el("div", { className: "admin-warning-banner" },
            "Pricing table last updated " + data.pricing.updated + " — cost estimates may be stale."));
        }

        const totals = data.totals;
        content.appendChild(el("div", { className: "metric-cards-grid" },
          renderMetricCard(formatNum(totals.total_tokens), "Total tokens", formatNum(totals.prompt_tokens) + " prompt / " + formatNum(totals.completion_tokens) + " completion"),
          renderMetricCard(obsCost(totals.cost_usd), "Estimated cost", "Across " + formatNum(totals.requests) + " requests"),
          renderMetricCard(obsCost(totals.requests ? totals.cost_usd / totals.requests : null), "Avg cost / request", ""),
          renderMetricCard(formatNum(totals.unpriced_requests), "Unpriced requests", formatNum(totals.unreported_requests) + " with no usage reported")
        ));

        if (data.series.length) {
          content.appendChild(el("div", { className: "charts-grid" },
            el("div", { className: "chart-card" }, el("h3", null, "Tokens over time"), el("canvas", { id: "obs-tokens-chart" })),
            el("div", { className: "chart-card" }, el("h3", null, "Cost over time"), el("canvas", { id: "obs-cost-chart" })),
            el("div", { className: "chart-card" }, el("h3", null, "Top " + GROUP_BY_LABELS[selectedGroupBy] + " by cost"), el("canvas", { id: "obs-models-chart" })),
            el("div", { className: "chart-card feedback-distribution-card" },
              el("h3", null, "Cost share"),
              el("div", { className: "feedback-donut-wrap cost-share-donut-wrap" }, el("canvas", { id: "obs-provider-chart" }))
            )
          ));
        } else {
          content.appendChild(el("div", { className: "panel empty-state" },
            el("p", null, "No usage recorded for this selection in this time window.")));
        }

        if (data.groups.length) {
          const breakdownPanel = el("div", { className: "panel" },
            el("h2", null, "Breakdown by " + GROUP_BY_LABELS[selectedGroupBy]),
            el("p", { className: "muted" }, selectedGroupBy === "api_key"
              ? "Filter the whole page to one key's usage from any row."
              : "Every group in this window, ranked by cost."));
          breakdownTable(breakdownPanel, data.groups, totals.cost_usd, selectedGroupBy, onGroupRowClick);
          content.appendChild(breakdownPanel);
        }

        initCharts(data, onGroupRowClick);
      } catch (err) {
        if (version !== requestVersion || getActiveTab() !== "costs") return;
        clear(content);
        const msg = (err && err.message) || "Failed to load costs data.";
        content.appendChild(el("div", { className: "panel empty-state" }, el("p", null, msg)));
      }
    }

    load();
  }

  return { render, dispose };
}
