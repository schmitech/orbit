import { chartTheme } from "../core/charts.js";

export function createFeedbackTab({
  api, endpoints, el, clear, wrapTable, skeleton, refreshButton,
  formatNum, clampPercentage, getActiveTab
}) {
  let charts = {};
  let selectedWindowDays = 30;

  function dispose() {
    Object.keys(charts).forEach((key) => { try { charts[key].destroy(); } catch (_) {} });
    charts = {};
  }

  function percent(value) {
    return value == null ? "—" : formatNum(value, 1) + "%";
  }

  function satisfactionTone(rate) {
    return rate >= 80 ? "green" : rate >= 60 ? "amber" : "red";
  }

  function metricCard(value, label, detail, progress, tone) {
    return el("div", { className: "metric-card" },
      el("div", { className: "metric-value" }, value),
      el("div", { className: "metric-label" }, label),
      el("div", { className: "metric-sub" }, detail || ""),
      progress == null ? null : el("div", { className: "monitoring-progress-track" },
        el("div", { className: "monitoring-progress-bar " + (tone || "sky"), style: "width:" + clampPercentage(progress) + "%" }))
    );
  }

  // Chart colors are read from the same design tokens the rest of the admin
  // panel uses for success/danger/brand, so they adapt with the light/dark
  // theme instead of a fixed palette picked once for a dark background.
  function feedbackPalette() {
    const style = getComputedStyle(document.documentElement);
    const read = (name, fallback) => (style.getPropertyValue(name) || "").trim() || fallback;
    return {
      positive: read("--success-500", "#34d399"),
      negative: read("--danger-500", "#e5675a"),
      neutral: read("--brand-400", "#5b9bdc"),
      warning: read("--warning-500", "#f2b84c"),
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

  function chartOptions() {
    const t = chartTheme();
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: { point: { radius: 2, hoverRadius: 5 }, line: { borderWidth: 2 } },
      scales: {
        y: { beginAtZero: true, grid: { color: t.grid }, ticks: { color: t.axisText, precision: 0, font: { size: 12 } } },
        x: { grid: { display: false }, ticks: { color: t.axisText, maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: { size: 12 } } },
      },
      plugins: {
        legend: { labels: { color: t.legendText, usePointStyle: true, pointStyle: "rect", boxWidth: 10, boxHeight: 10, font: { size: 12 } } },
        tooltip: {
          backgroundColor: t.tooltipBg, titleColor: t.tooltipTitle, bodyColor: t.tooltipBody,
          padding: 16, cornerRadius: 6,
          titleFont: { family: "'JetBrains Mono', monospace", size: 18, weight: "500" },
          bodyFont: { family: "'JetBrains Mono', monospace", size: 17, weight: "400" },
        },
      },
    };
  }

  function initCharts(data) {
    dispose();
    if (typeof Chart === "undefined" || !data.summary.total) return;
    const palette = feedbackPalette();

    const trendCanvas = document.getElementById("feedback-trend-chart");
    if (trendCanvas) {
      const options = chartOptions();
      options.scales.y1 = {
        beginAtZero: true, min: 0, max: 100, position: "right",
        grid: { drawOnChartArea: false },
        ticks: { color: chartTheme().axisText, callback: (value) => value + "%", font: { size: 10 } },
      };
      charts.trend = new Chart(trendCanvas, {
        type: "line",
        data: {
          labels: data.trend.map((item) => new Date(item.date + "T00:00:00Z").toLocaleDateString(undefined, { month: "short", day: "numeric" })),
          datasets: [
            { label: "Positive", data: data.trend.map((item) => item.positive), borderColor: palette.positive, backgroundColor: hexToRgba(palette.positive, 0.1), fill: true, tension: 0.25 },
            { label: "Negative", data: data.trend.map((item) => item.negative), borderColor: palette.negative, backgroundColor: hexToRgba(palette.negative, 0.08), fill: true, tension: 0.25 },
            { label: "Satisfaction %", data: data.trend.map((item) => item.satisfaction_rate), borderColor: palette.neutral, backgroundColor: "transparent", borderDash: [5, 4], yAxisID: "y1", spanGaps: true, tension: 0.2 },
          ],
        },
        options,
      });
    }

    const distributionCanvas = document.getElementById("feedback-distribution-chart");
    if (distributionCanvas) {
      charts.distribution = new Chart(distributionCanvas, {
        type: "doughnut",
        data: {
          labels: ["Positive", "Negative"],
          datasets: [{ data: [data.summary.positive, data.summary.negative], backgroundColor: [palette.positive, palette.negative], borderWidth: 0, hoverOffset: 4 }],
        },
        options: { responsive: true, maintainAspectRatio: false, cutout: "68%", plugins: chartOptions().plugins },
      });
    }

    const adapterCanvas = document.getElementById("feedback-adapter-chart");
    const rows = data.adapters.slice(0, 10);
    if (adapterCanvas && rows.length) {
      const options = chartOptions();
      options.indexAxis = "y";
      options.scales.x.max = 100;
      options.scales.x.ticks.callback = (value) => value + "%";
      options.plugins.legend.display = false;
      options.plugins.tooltip.callbacks = {
        afterLabel: (context) => {
          const row = rows[context.dataIndex];
          return row.total + " ratings (" + row.positive + " positive, " + row.negative + " negative)";
        },
      };
      charts.adapters = new Chart(adapterCanvas, {
        type: "bar",
        data: {
          labels: rows.map((item) => item.adapter),
          datasets: [{
            label: "Satisfaction",
            data: rows.map((item) => item.satisfaction_rate || 0),
            backgroundColor: rows.map((item) => {
              const tone = satisfactionTone(item.satisfaction_rate);
              return tone === "green" ? palette.positive : tone === "amber" ? palette.warning : palette.negative;
            }),
            borderRadius: 4,
          }],
        },
        options,
      });
    }
  }

  function adapterTable(container, adapters) {
    const table = el("table", { className: "monitoring-table" });
    table.appendChild(el("thead", null, el("tr", null,
      el("th", null, "Adapter"),
      el("th", { style: "text-align:right" }, "Ratings"),
      el("th", { style: "text-align:right" }, "Positive"),
      el("th", { style: "text-align:right" }, "Negative"),
      el("th", null, "Satisfaction"),
      el("th", { style: "text-align:right" }, "Comments")
    )));
    const body = el("tbody");
    adapters.forEach((item) => {
      const tone = satisfactionTone(item.satisfaction_rate);
      const satisfactionCell = el("div", { style: "display:flex;align-items:center;gap:var(--sp-2);min-width:7rem" },
        el("span", { className: "monitoring-badge " + tone }, percent(item.satisfaction_rate)),
        el("div", { className: "monitoring-progress-track", style: "flex:1;margin-top:0" },
          el("div", { className: "monitoring-progress-bar " + tone, style: "width:" + clampPercentage(item.satisfaction_rate || 0) + "%" }))
      );
      body.appendChild(el("tr", null,
        el("td", null, el("div", { className: "monitoring-table-primary" }, item.adapter)),
        el("td", { style: "text-align:right" }, formatNum(item.total)),
        el("td", { style: "text-align:right;color:var(--success-text)" }, formatNum(item.positive)),
        el("td", { style: "text-align:right;color:var(--danger-text)" }, formatNum(item.negative)),
        el("td", null, satisfactionCell),
        el("td", { style: "text-align:right" }, formatNum(item.comments))
      ));
    });
    table.appendChild(body);
    container.appendChild(wrapTable(table, ["fluid", "number", "number", "number", "label", "number"]));
  }

  function recentNegative(container, rows) {
    if (!rows.length) {
      container.appendChild(el("div", { className: "empty-state" },
        el("p", null, "No negative feedback was recorded in this window.")));
      return;
    }
    const table = el("table", { className: "monitoring-table" });
    table.appendChild(el("thead", null, el("tr", null,
      el("th", null, "When"),
      el("th", null, "Adapter / user"),
      el("th", null, "User prompt"),
      el("th", null, "Assistant response"),
      el("th", null, "Feedback comment")
    )));
    const body = el("tbody");
    rows.forEach((item) => {
      const timestamp = item.created_at ? new Date(item.created_at).toLocaleString() : "Unknown";
      body.appendChild(el("tr", null,
        el("td", { style: "white-space:nowrap" }, timestamp),
        el("td", null,
          el("div", { className: "monitoring-table-primary" }, item.adapter || "Unknown"),
          el("div", { className: "muted", style: "font-size:var(--text-xs);margin-top:2px" }, item.user || "Anonymous")),
        el("td", null, el("span", { className: "feedback-cell-clamp", title: item.user_prompt || "" }, item.user_prompt || "Unavailable")),
        el("td", null, el("span", { className: "feedback-cell-clamp", title: item.assistant_response || "" }, item.assistant_response || "Unavailable")),
        el("td", null, el("span", { className: "feedback-cell-clamp", title: item.comment || "" }, item.comment || "No comment"))
      ));
    });
    table.appendChild(body);
    container.appendChild(wrapTable(table, ["date", "label", "fluid", "fluid", "fluid"]));
  }

  async function render(container) {
    let requestVersion = 0;

    const header = el("div", { className: "panel-header-row feedback-page-header" },
      el("div", null,
        el("h2", null, "Feedback intelligence"),
        el("p", { className: "muted" }, "Track satisfaction, compare adapters, and inspect the conversations behind negative ratings.")),
      el("div", { className: "monitoring-toolbar-right", id: "feedback-window-controls" },
        [7, 30, 90, 365].map((days) => {
          const button = el("button", {
            type: "button",
            className: "time-window-btn",
            "aria-pressed": days === selectedWindowDays ? "true" : "false",
          }, days === 365 ? "1y" : days + "d");
          button.addEventListener("click", () => {
            if (selectedWindowDays !== days) { selectedWindowDays = days; load(); }
          });
          return button;
        }),
        refreshButton("Refresh feedback analytics", () => load())));

    const content = el("div", { style: "display:grid;gap:var(--sp-4)" }, skeleton());
    container.appendChild(header);
    container.appendChild(content);

    async function load() {
      const version = ++requestVersion;
      header.querySelectorAll(".time-window-btn").forEach((button) => {
        const label = selectedWindowDays === 365 ? "1y" : selectedWindowDays + "d";
        button.setAttribute("aria-pressed", button.textContent === label ? "true" : "false");
      });
      dispose();
      clear(content);
      content.appendChild(skeleton());

      try {
        const data = await api("GET", endpoints.feedbackAnalytics + "?days=" + selectedWindowDays);
        if (version !== requestVersion || getActiveTab() !== "feedback") return;
        clear(content);

        if (data.meta.truncated) {
          content.appendChild(el("div", { className: "admin-warning-banner" },
            "This view uses the newest " + formatNum(data.meta.record_limit) + " ratings in the selected window."));
        }

        const summary = data.summary;
        const coverageDetail = summary.eligible_messages == null
          ? "Chat history unavailable"
          : summary.response_rate == null
            ? "Chat retention prevents a reliable denominator"
            : formatNum(summary.total) + " of " + formatNum(summary.eligible_messages) + " retained responses";

        content.appendChild(el("div", { className: "metric-cards-grid" },
          metricCard(percent(summary.satisfaction_rate), "Satisfaction",
            formatNum(summary.positive) + " positive / " + formatNum(summary.negative) + " negative",
            summary.satisfaction_rate, satisfactionTone(summary.satisfaction_rate)),
          metricCard(formatNum(summary.total), "Ratings",
            formatNum(summary.sessions) + " sessions · " + formatNum(summary.users) + " identified users"),
          metricCard(percent(summary.response_rate), "Feedback coverage", coverageDetail, summary.response_rate, "sky"),
          metricCard(percent(summary.negative_comment_rate), "Negative detail rate",
            formatNum(summary.comments) + " comments on negative ratings", summary.negative_comment_rate, "amber")));

        if (summary.total) {
          content.appendChild(el("div", { className: "charts-grid" },
            el("div", { className: "chart-card" },
              el("h3", null, "Ratings and satisfaction over time"),
              el("canvas", { id: "feedback-trend-chart" })),
            el("div", { className: "chart-card feedback-distribution-card" },
              el("h3", null, "Overall distribution"),
              el("div", { className: "feedback-donut-wrap" }, el("canvas", { id: "feedback-distribution-chart" }))),
            el("div", { className: "chart-card" },
              el("h3", null, "Satisfaction by adapter (top 10 by volume)"),
              el("canvas", { id: "feedback-adapter-chart" }))));
        } else {
          content.appendChild(el("div", { className: "panel empty-state" },
            el("p", null, "No feedback has been recorded in this time window.")));
        }

        const adapterPanel = el("div", { className: "panel" },
          el("h2", null, "Adapter performance"),
          el("p", { className: "muted" }, "Compare rating volume and satisfaction together; low-volume percentages should be treated cautiously."));
        if (data.adapters.length) adapterTable(adapterPanel, data.adapters);
        else adapterPanel.appendChild(el("p", { className: "muted" }, "No adapter feedback in this window."));
        content.appendChild(adapterPanel);

        const negativePanel = el("div", { className: "panel" },
          el("h2", null, "Recent negative feedback"),
          el("p", { className: "muted" }, "The linked prompt and response provide context for triage. Unavailable content may have expired under chat-history retention."));
        recentNegative(negativePanel, data.recent_negative);
        content.appendChild(negativePanel);

        content.appendChild(el("p", { className: "muted", style: "font-size:var(--text-xs)" },
          data.window.basis + ". Generated " + new Date(data.meta.generated_at).toLocaleString() + "."));

        initCharts(data);
      } catch (err) {
        if (version !== requestVersion || getActiveTab() !== "feedback") return;
        clear(content);
        content.appendChild(el("div", { className: "panel empty-state" },
          el("p", null, "Failed to load feedback analytics: " + err.message)));
      }
    }

    load();
  }

  return { render, dispose };
}
