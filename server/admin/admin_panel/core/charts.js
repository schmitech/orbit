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

/** Shared Chart.js defaults for dashboard-style visualizations. */
export function standardChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    elements: { point: { radius: 2, hoverRadius: 5 }, line: { borderWidth: 2 } },
    scales: {
      y: { beginAtZero: true, grid: { color: "rgba(15,29,51,0.06)" }, ticks: { color: "#526684", precision: 0, font: { size: 12 } } },
      x: { grid: { display: false }, ticks: { color: "#526684", maxRotation: 0, autoSkip: true, maxTicksLimit: 10, font: { size: 12 } } },
    },
    plugins: {
      legend: { labels: { color: "#3d4f6f", usePointStyle: true, pointStyle: "circle", pointStyleWidth: 8, boxWidth: 8, boxHeight: 8, font: { size: 12 } } },
      tooltip: { backgroundColor: "rgba(10,14,23,0.96)", titleColor: "#f4f6fa", bodyColor: "#e4e8f0", padding: 16, cornerRadius: 6, titleFont: { family: "'JetBrains Mono', monospace", size: 18, weight: "500" }, bodyFont: { family: "'JetBrains Mono', monospace", size: 17, weight: "400" } },
    },
  };
}
