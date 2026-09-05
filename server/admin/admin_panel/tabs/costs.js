const GROUP_BY_LABELS = {
  model: "Model",
  provider: "Provider",
  adapter_name: "Adapter",
  user_id: "User",
  call_type: "Call type",
  api_key: "API key",
};

export function createCostsTab({ api, endpoints, el, clear, skeleton, refreshButton, formatNum, chartOptions, renderMetricCard, createSelect, getActiveTab }) {
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

    const tokensCanvas = document.getElementById("obs-tokens-chart");
    if (tokensCanvas && data.series.length) {
      const opts = chartOptions();
      charts.tokens = new Chart(tokensCanvas, {
        type: "bar",
        data: {
          labels: data.series.map((item) => formatBucketLabel(item.bucket, data.window.bucket === "hour")),
          datasets: [
            { label: "Prompt tokens", data: data.series.map((item) => item.prompt_tokens), backgroundColor: "#5794f2", stack: "tokens" },
            { label: "Completion tokens", data: data.series.map((item) => item.completion_tokens), backgroundColor: "#28a66a", stack: "tokens" }
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
            { label: "Cost / bucket", data: data.series.map((item) => item.cost_usd), borderColor: "#e0a22f", backgroundColor: "rgba(224,162,47,0.10)", fill: true, tension: 0.25 },
            { label: "Cumulative", data: data.series.map((item) => { cumulative += item.cost_usd; return cumulative; }), borderColor: "#5794f2", backgroundColor: "transparent", borderDash: [5, 4], yAxisID: "y1", tension: 0.2 }
          ]
        },
        options: Object.assign(costOpts, {
          scales: Object.assign(costOpts.scales, {
            y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, ticks: { color: "#526684", font: { size: 12 } } }
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
        color: "#3d4f6f",
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
          datasets: [{ data: groupRows.map((row) => row.cost_usd), backgroundColor: "#5794f2" }]
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
          datasets: [{ data: groupRows.map((row) => row.cost_usd), backgroundColor: ["#5794f2", "#28a66a", "#e0a22f", "#e05260", "#9b7ede", "#4fb8b0", "#f28cb1", "#c0ca33", "#8d6e63", "#78909c"], borderWidth: 0, hoverOffset: 4 }]
        },
        options: doughnutOptions
      });
    }
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
      options: [["all", "All call types"], ["chat", "Chat"], ["embedding", "Embedding"], ["reranking", "Reranking"], ["image", "Image"], ["video", "Video"], ["audio", "Audio"], ["document", "Document"]]
        .map(([value, label]) => ({ value, label })),
      value: selectedCallType
    });
    callTypeSelect.addEventListener("change", () => { selectedCallType = callTypeSelect.value; load(); });
    const header = el("div", { className: "panel" },
      el("div", { className: "panel-header-row" },
        el("div", null,
          el("h2", null, "Costs"),
          el("p", { className: "muted" }, "Usage and estimated cost across chat, embedding, and media providers. Cost is an estimate from the local rate table in config/pricing.yaml, not a provider invoice.")
        ),
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
        )
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
        if (selectedCallType !== "all") params.set("call_type", selectedCallType);
        if (selectedApiKey) params.set("api_key", selectedApiKey);
        const data = await api("GET", endpoints.costsUsage + "?" + params.toString());
        if (version !== requestVersion || getActiveTab() !== "costs") return;
        clear(content);

        if (data.pricing && data.pricing.stale) {
          content.appendChild(el("div", {
            className: "panel",
            style: "border-color:#e0a22f;background:rgba(224,162,47,0.08);font-size:var(--text-sm)"
          }, "Pricing table last updated " + data.pricing.updated + " — cost estimates may be stale."));
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
