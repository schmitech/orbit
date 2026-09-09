// chartjs-plugin-datalabels registers itself globally on every chart and
// defaults to display: true. Tabs like Feedback and Overview build their own
// chart options rather than calling standardChartOptions() below, so an
// off-switch there wouldn't reach them — the only place that covers every
// chart is Chart.defaults itself. Callers that want on-chart labels (e.g.
// costs.js) opt in per-chart via `plugins: { datalabels: { display: true, ... } }`.
if (typeof Chart !== "undefined" && typeof ChartDataLabels !== "undefined") {
  Chart.register(ChartDataLabels);
  Chart.defaults.set("plugins.datalabels", { display: false });
}

// Chart.js options are plain JS values baked in at chart-creation time, so
// they can't pick up CSS custom properties on their own the way the rest of
// the page does. This reads the current theme's tokens off the root element
// so every chart built after a theme switch (tabs re-render their charts from
// scratch when the theme toggles — see admin_panel.js toggleTheme) gets
// colors that are actually legible against the current --surface-raised.
export function chartTheme() {
  const style = getComputedStyle(document.documentElement);
  const read = (name, fallback) => (style.getPropertyValue(name) || "").trim() || fallback;
  return {
    axisText: read("--ink-muted", "#637189"),
    legendText: read("--ink-secondary", "#3d4f6f"),
    grid: read("--border-light", "rgba(127,127,127,0.12)"),
    tooltipBg: read("--surface-sunken", "rgba(10,14,23,0.96)"),
    tooltipTitle: read("--ink", "#f4f6fa"),
    tooltipBody: read("--ink-secondary", "#e4e8f0"),
  };
}

/** Shared Chart.js defaults for dashboard-style visualizations. */
export function standardChartOptions() {
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
      legend: { labels: { color: t.legendText, usePointStyle: true, pointStyle: "circle", pointStyleWidth: 8, boxWidth: 8, boxHeight: 8, font: { size: 12 } } },
      tooltip: { backgroundColor: t.tooltipBg, titleColor: t.tooltipTitle, bodyColor: t.tooltipBody, padding: 16, cornerRadius: 6, titleFont: { family: "'JetBrains Mono', monospace", size: 18, weight: "500" }, bodyFont: { family: "'JetBrains Mono', monospace", size: 17, weight: "400" } },
    },
  };
}
