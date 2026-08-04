import { el } from "./dom.js";

function clampPercentage(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

/** Render the standard summary card used by Feedback and Costs. */
export function renderMetricCard(value, label, detail, progress, tone) {
  return el("div", { className: "metric-card" },
    el("div", { className: "metric-value" }, value),
    el("div", { className: "metric-label" }, label),
    el("div", { className: "metric-sub" }, detail || ""),
    progress == null ? null : el("div", { className: "monitoring-progress-track" },
      el("div", {
        className: "monitoring-progress-bar " + (tone || "sky"),
        style: "width:" + clampPercentage(progress) + "%"
      })
    )
  );
}
