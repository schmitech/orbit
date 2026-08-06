export function createOverviewTab({
  api, endpoints, el, clear, formatNum, clampPercentage,
  userHasPermission, createPaginator, createColumnSorter, withButton,
  itemsPerPage, getActiveTab
}) {
  let metricsWs = null;
  let metricsReconnectTimer = null;
  let selectedWindowMinutes = 5;
  let lastMetricsSnapshot = null;
  let lastAdapters = {};
  let adapterSearchFilter = "";
  let adapterStateFilter = "all";
  let lastDatasourcePool = null;
  let datasourceSearchFilter = "";
  let lastThreadPools = {};
  let threadPoolSearchFilter = "";
  let overviewCharts = {};
  let monitoringThresholds = { cpu: 90, memory: 85, error_rate: 5, response_time_ms: 5000 };
  let overviewAdapterPaginator = null;
  let overviewDatasourcePaginator = null;
  let overviewThreadPoolPaginator = null;
  let overviewAdapterSorter = null;
  let overviewDatasourceSorter = null;
  let overviewThreadPoolSorter = null;

  function destroyOverviewCharts() {
    Object.keys(overviewCharts).forEach((k) => { try { overviewCharts[k].destroy(); } catch (_) {} });
    overviewCharts = {};
  }

  function disconnectMetricsWs() {
    if (metricsReconnectTimer) { clearInterval(metricsReconnectTimer); metricsReconnectTimer = null; }
    if (metricsWs) { try { metricsWs.close(); } catch (_) {} metricsWs = null; }
  }

  function dispose() {
    disconnectMetricsWs();
    destroyOverviewCharts();
  }

  function connectMetricsWs() {
    disconnectMetricsWs();
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(protocol + "//" + location.host + "/ws/metrics");
    metricsWs = ws;

    ws.onopen = () => {
      if (metricsReconnectTimer) { clearInterval(metricsReconnectTimer); metricsReconnectTimer = null; }
      const dot = document.getElementById("mon-status-dot");
      const txt = document.getElementById("mon-status-text");
      if (dot) { dot.className = "status-dot connected pulse"; }
      if (txt) { txt.textContent = "Connected"; }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.metrics) updateMonitoringMetrics(data.metrics);
        updateMonitoringAdapters(data.adapters || {});
        if (data.thread_pools) updateMonitoringThreadPools(data.thread_pools);
        if (data.datasource_pool) updateMonitoringDatasourcePool(data.datasource_pool);
        if (data.redis_health) updateMonitoringRedisHealth(data.redis_health);
        if (data.pipeline_steps) updateMonitoringPipeline(data.pipeline_steps, data.pipeline_summary);
        if (data.connections) updateMonitoringConnections(data.connections);
      } catch (e) { console.error("Metrics parse error:", e); }
    };

    ws.onclose = (event) => {
      const dot = document.getElementById("mon-status-dot");
      const txt = document.getElementById("mon-status-text");
      if (dot) { dot.className = "status-dot disconnected"; }
      // 4401/4403 are the auth/permission close codes from
      // authenticate_websocket_admin - retrying can never succeed.
      const denied = event && (event.code === 4401 || event.code === 4403);
      if (txt) { txt.textContent = denied ? "Not permitted" : "Reconnecting..."; }
      if (denied) {
        if (metricsReconnectTimer) { clearInterval(metricsReconnectTimer); metricsReconnectTimer = null; }
        return;
      }
      if (!metricsReconnectTimer && getActiveTab() === "overview") {
        metricsReconnectTimer = setInterval(() => { connectMetricsWs(); }, 5000);
      }
    };

    ws.onerror = () => { console.error("Metrics WebSocket error"); };
  }

  function getChartDensityConfig() {
    if (selectedWindowMinutes <= 5) return { targetPoints: 60, maxTicks: 6 };
    if (selectedWindowMinutes <= 15) return { targetPoints: 45, maxTicks: 7 };
    if (selectedWindowMinutes <= 30) return { targetPoints: 36, maxTicks: 7 };
    return { targetPoints: 24, maxTicks: 8 };
  }

  function aggregateSeries(labels, seriesList) {
    if (!labels.length) return { labels: labels, seriesList: seriesList };
    const density = getChartDensityConfig();
    if (labels.length <= density.targetPoints) return { labels: labels, seriesList: seriesList };
    const bucketSize = Math.ceil(labels.length / density.targetPoints);
    const aggLabels = [];
    const aggSeries = seriesList.map(() => []);
    for (let start = 0; start < labels.length; start += bucketSize) {
      const end = Math.min(start + bucketSize, labels.length);
      aggLabels.push(labels[end - 1]);
      seriesList.forEach((series, idx) => {
        const bucket = series.slice(start, end).filter((v) => typeof v === "number" && !isNaN(v));
        aggSeries[idx].push(bucket.length ? bucket.reduce((s, v) => s + v, 0) / bucket.length : null);
      });
    }
    return { labels: aggLabels, seriesList: aggSeries };
  }

  function getMaxPoints(timestamps) {
    if (!Array.isArray(timestamps) || timestamps.length < 2) return Math.ceil((selectedWindowMinutes * 60) / 5);
    const intervals = [];
    for (let i = 1; i < timestamps.length; i++) {
      const d = (new Date(timestamps[i]).getTime() - new Date(timestamps[i - 1]).getTime()) / 1000;
      if (isFinite(d) && d > 0) intervals.push(d);
    }
    if (!intervals.length) return Math.ceil((selectedWindowMinutes * 60) / 5);
    const avg = intervals.reduce((s, v) => s + v, 0) / intervals.length;
    return Math.max(1, Math.ceil((selectedWindowMinutes * 60) / avg));
  }

  function updateChartWithActiveTooltip(chart, labels, datasetValues) {
    const active = chart.getActiveElements();
    chart.data.labels = labels;
    chart.data.datasets.forEach((ds, idx) => { ds.data = datasetValues[idx] || []; });
    chart.update("none");
    if (!labels.length) { chart.setActiveElements([]); return; }
    if (active.length) {
      const reactivated = active.map((a) => (
        { datasetIndex: a.datasetIndex, index: Math.min(labels.length - 1, Math.max(0, a.index)) }
      )).filter((a) => { const m = chart.getDatasetMeta(a.datasetIndex); return m && m.data && m.data[a.index]; });
      if (reactivated.length) {
        chart.setActiveElements(reactivated);
        const first = reactivated[0];
        const elem = chart.getDatasetMeta(first.datasetIndex).data[first.index];
        if (elem && chart.tooltip) { chart.tooltip.setActiveElements(reactivated, { x: elem.x, y: elem.y }); chart.tooltip.update(); }
        chart.draw();
      }
    }
  }

  // --- Dark Grafana-style chart options ---
  const monitoringChartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false, axis: "x" },
    elements: { point: { radius: 0, hoverRadius: 4, hitRadius: 20 }, line: { borderWidth: 1.5 } },
    scales: {
      y: {
        beginAtZero: true,
        grid: { color: "rgba(15,29,51,0.06)", drawBorder: false },
        ticks: { color: "#6b7a96", font: { size: 10, family: "'JetBrains Mono', monospace" }, padding: 6 }
      },
      x: {
        grid: { color: "rgba(15,29,51,0.05)", drawBorder: false },
        ticks: {
          color: "#6b7a96",
          autoSkip: true,
          maxTicksLimit: 5,
          maxRotation: 0,
          minRotation: 0,
          font: { size: 10, family: "'JetBrains Mono', monospace" },
          padding: 4
        }
      }
    },
    plugins: {
      legend: {
        labels: {
          color: "#3d4f6f",
          usePointStyle: true,
          pointStyle: "line",
          boxWidth: 28,
          boxHeight: 2,
          font: { size: 11 },
          padding: 14
        }
      },
      tooltip: {
        backgroundColor: "rgba(10,14,23,0.96)",
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        titleColor: "#f4f6fa",
        bodyColor: "#e4e8f0",
        padding: 16,
        cornerRadius: 6,
        boxPadding: 8,
        titleFont: { family: "'JetBrains Mono', monospace", size: 18, weight: "500" },
        bodyFont: { family: "'JetBrains Mono', monospace", size: 17, weight: "400" }
      }
    }
  };

  function initOverviewCharts() {
    destroyOverviewCharts();
    const chartDefs = [
      { id: "mon-system-chart", series: [
          { label: "CPU %",    color: "#5794f2", rgb: [87,148,242],  fill: true },
          { label: "Memory %", color: "#73bf69", rgb: [115,191,105], fill: true }
        ]
      },
      { id: "mon-request-chart", series: [
          { label: "Requests/sec", color: "#f2a35e", rgb: [242,163,94],  fill: true, axis: "y" },
          { label: "Error Rate %", color: "#f26073", rgb: [242,96,115],  fill: true, axis: "y1" }
        ]
      },
      { id: "mon-response-chart", series: [
          { label: "Avg Response Time", color: "#b877d9", rgb: [184,119,217], fill: true }
        ]
      },
      { id: "mon-percentile-chart", series: [
          { label: "P50", color: "#73bf69", fill: false },
          { label: "P95", color: "#f2a35e", fill: false, borderDash: [4, 3] },
          { label: "P99", color: "#f26073", fill: false, borderDash: [2, 2] }
        ]
      }
    ];

    chartDefs.forEach((def, i) => {
      const canvas = document.getElementById(def.id);
      if (!canvas) return;
      const ctx = canvas.getContext("2d");

      const datasets = def.series.map((s) => {
        const bg = (s.fill && s.rgb) ? (() => {
          const g = ctx.createLinearGradient(0, 0, 0, 300);
          g.addColorStop(0, "rgba(" + s.rgb[0] + "," + s.rgb[1] + "," + s.rgb[2] + ",0.2)");
          g.addColorStop(1, "rgba(" + s.rgb[0] + "," + s.rgb[1] + "," + s.rgb[2] + ",0)");
          return g;
        })() : "transparent";
        return {
          label: s.label, borderColor: s.color, backgroundColor: bg,
          fill: s.fill || false, tension: 0.3, borderDash: s.borderDash || [],
          borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 4, pointHitRadius: 20,
          yAxisID: s.axis || "y", data: []
        };
      });

      let opts = monitoringChartOpts;
      // Request volume and error rate have different units. A second axis keeps
      // both trends readable instead of implying that req/s and percent share a scale.
      if (i === 1) {
        opts = Object.assign({}, monitoringChartOpts, {
          scales: Object.assign({}, monitoringChartOpts.scales, {
            y: Object.assign({}, monitoringChartOpts.scales.y, {
              min: 0,
              ticks: Object.assign({}, monitoringChartOpts.scales.y.ticks, { stepSize: 1, precision: 0 }),
              title: { display: true, text: "Requests/sec", color: "#6b7a96", font: { size: 10 } }
            }),
            y1: {
              beginAtZero: true,
              max: 100,
              position: "right",
              grid: { drawOnChartArea: false },
              ticks: { color: "#6b7a96", callback: (value) => value + "%", font: { size: 10, family: "'JetBrains Mono', monospace" }, padding: 6 },
              title: { display: true, text: "Error rate", color: "#6b7a96", font: { size: 10 } }
            }
          })
        });
      }

      overviewCharts[def.id] = new Chart(canvas, {
        type: "line",
        data: { labels: [], datasets: datasets },
        options: opts
      });
    });
  }

  // --- Update functions ---

  function updateMonitoringMetrics(data) {
    lastMetricsSnapshot = data;
    if (data.thresholds) monitoringThresholds = Object.assign({}, monitoringThresholds, data.thresholds);

    const cpu = clampPercentage(data.system.cpu_percent);
    const mem = clampPercentage(data.system.memory_percent);
    const errRate = clampPercentage(data.requests.error_rate);
    const reliability = clampPercentage(100 - errRate);

    const series = data.time_series || {};
    const trendValues = (values) => {
      if (!Array.isArray(values)) return values;
      return values.slice(Math.max(0, values.length - getMaxPoints(series.timestamps)));
    };
    setText("mon-cpu-value", formatNum(cpu, 1));
    setProgressBar("mon-cpu-bar", cpu, cpu >= monitoringThresholds.cpu ? "red" : cpu >= monitoringThresholds.cpu * 0.82 ? "amber" : "sky");
    setMetricStatus("mon-cpu", cpu, monitoringThresholds.cpu, "high", "CPU");
    setMetricChange("mon-cpu", trendValues(series.cpu), "%");

    setText("mon-mem-value", formatNum(data.system.memory_gb, 2));
    setProgressBar("mon-mem-bar", mem, mem >= monitoringThresholds.memory ? "red" : mem >= monitoringThresholds.memory * 0.82 ? "amber" : "green");
    setMetricStatus("mon-mem", mem, monitoringThresholds.memory, "high", "Memory");
    setMetricChange("mon-mem", trendValues(series.memory), "%");

    setText("mon-rps-value", formatNum(data.requests.per_second, 1));
    setText("mon-rps-sub", formatNum(data.requests.total) + " total requests");
    // Throughput has no meaningful healthy threshold: zero traffic can be valid.
    // Mark the card as live when a metrics snapshot arrives without judging its rate.
    setMetricLiveStatus("mon-rps");
    setMetricChange("mon-rps", trendValues(series.requests_per_second), " req/s");

    setText("mon-rel-value", formatNum(reliability, 2));
    const errorBudgetUsed = monitoringThresholds.error_rate > 0
      ? (errRate / monitoringThresholds.error_rate) * 100
      : 0;
    setProgressBar("mon-rel-bar", errorBudgetUsed, errRate >= monitoringThresholds.error_rate ? "red" : errRate > 0 ? "amber" : "green");
    setMetricStatus("mon-rel", errRate, monitoringThresholds.error_rate, "high", "Reliability", 0);
    setMetricChange("mon-rel", trendValues(series.error_rate), "% error rate");

    setText("mon-last-update", new Date().toLocaleTimeString());

    // Endpoint stats
    if (data.endpoint_stats && data.endpoint_stats.length > 0) {
      updateMonitoringEndpoints(data.endpoint_stats);
    }

    // Charts
    if (data.time_series && data.time_series.timestamps && data.time_series.timestamps.length > 0) {
      // A compact, fixed-width 24-hour time label prevents adjacent ticks from
      // colliding on narrow chart cards while retaining second-level precision.
      const labels = data.time_series.timestamps.map((t) => new Date(t).toLocaleTimeString([], {
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
      }));
      const maxPts = getMaxPoints(data.time_series.timestamps);
      const startIdx = Math.max(0, labels.length - maxPts);
      const trimmed = labels.slice(startIdx);

      const charts = [
        { key: "mon-system-chart", series: [data.time_series.cpu.slice(startIdx), data.time_series.memory.slice(startIdx)] },
        { key: "mon-request-chart", series: [data.time_series.requests_per_second.slice(startIdx), data.time_series.error_rate.slice(startIdx)] },
        { key: "mon-response-chart", series: [data.time_series.response_time.slice(startIdx)] },
        { key: "mon-percentile-chart", series: [data.time_series.response_time_p50.slice(startIdx), data.time_series.response_time_p95.slice(startIdx), data.time_series.response_time_p99.slice(startIdx)] }
      ];

      charts.forEach((c) => {
        const chart = overviewCharts[c.key];
        if (!chart) return;
        const density = getChartDensityConfig();
        if (chart.options && chart.options.scales && chart.options.scales.x && chart.options.scales.x.ticks) {
          // The overview grid can narrow individual charts below ~420px even
          // on desktop. Three fixed-width timestamps fit comfortably there;
          // wider cards keep the denser range-specific tick count.
          chart.options.scales.x.ticks.maxTicksLimit = chart.width > 0 && chart.width < 420 ? 3 : density.maxTicks;
        }
        const agg = aggregateSeries(trimmed, c.series);
        updateChartWithActiveTooltip(chart, agg.labels, agg.seriesList);
      });
    }
  }

  function setText(id, text) {
    const e = document.getElementById(id);
    if (e) e.textContent = text;
  }

  function setProgressBar(id, pct, color) {
    const bar = document.getElementById(id);
    if (!bar) return;
    bar.style.width = clampPercentage(pct).toFixed(1) + "%";
    bar.className = "monitoring-progress-bar " + color;
  }

  function setMetricStatus(id, value, threshold, direction, label, warningThreshold) {
    const isCritical = direction === "high" && value >= threshold;
    const isWarning = !isCritical && direction === "high" && (
      warningThreshold == null ? value >= threshold * 0.82 : value > warningThreshold
    );
    const state = isCritical ? "Critical" : isWarning ? "Warning" : "Healthy";
    const detail = label === "Reliability"
      ? formatNum(value, 2) + "% error rate · " + formatNum(threshold > 0 ? (value / threshold) * 100 : 0, 0) + "% of error budget (threshold " + formatNum(threshold, 2) + "%)"
      : formatNum(value, 1) + "% of " + formatNum(threshold, 0) + "% threshold";
    setText(id + "-status", state);
    setText(id + "-sub", detail);
    const card = document.getElementById(id);
    if (card) card.dataset.state = state.toLowerCase();
  }

  function setMetricLiveStatus(id) {
    setText(id + "-status", "Live");
    const card = document.getElementById(id);
    if (card) card.dataset.state = "live";
  }

  function setMetricChange(id, values, unit) {
    const change = document.getElementById(id + "-change");
    if (!change) return;
    const points = Array.isArray(values) ? values.filter((value) => typeof value === "number" && !isNaN(value)) : [];
    if (points.length < 2) { change.textContent = "Collecting trend data"; change.dataset.direction = "neutral"; return; }
    const delta = points[points.length - 1] - points[0];
    const sign = delta > 0 ? "+" : "";
    change.textContent = sign + formatNum(delta, 1) + unit + " since window start";
    change.dataset.direction = delta > 0 ? "up" : delta < 0 ? "down" : "neutral";
  }

  function updateMonitoringEndpoints(endpoints) {
    const section = document.getElementById("mon-endpoint-section");
    const tbody = document.getElementById("mon-endpoint-tbody");
    if (!section || !tbody) return;
    if (!endpoints || !endpoints.length) { section.style.display = "none"; return; }
    section.style.display = "";
    const methodColors = { GET: "method-get", POST: "method-post", PUT: "method-put", DELETE: "method-delete" };
    clear(tbody);
    endpoints.forEach((ep) => {
      const method = (ep.method || "GET").toUpperCase();
      tbody.appendChild(el("tr", null,
        el("td", null, el("span", { className: "method-badge " + (methodColors[method] || "method-get") }, method)),
        el("td", { style: "font-family:var(--font-mono);font-size:var(--text-xs)" }, ep.endpoint),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.total_requests)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.avg_latency_ms, 1) + " ms"),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(ep.error_rate, 2) + "%")
      ));
    });
  }

  function monitoringStatCell(label, value) {
    return el("div", null,
      el("div", { style: "text-transform:uppercase;letter-spacing:0.1em;font-size:0.65rem" }, label),
      el("div", { style: "font-weight:700;color:var(--ink)" }, value)
    );
  }

  function monitoringSummaryCard(label, value, hint, extraClass) {
    const children = [
      el("p", { className: "label" }, label),
      el("p", { className: "value" }, value)
    ];
    if (hint) children.push(el("p", { className: "hint" }, hint));
    return el("div", { className: "monitoring-summary-card" + (extraClass ? " " + extraClass : "") }, children);
  }

  function monitoringStateTone(state) {
    const normalized = (state || "unknown").toLowerCase();
    if (normalized === "closed" || normalized === "connected" || normalized === "healthy") return "green";
    if (normalized === "half_open" || normalized === "warning" || normalized === "degraded") return "amber";
    if (normalized === "open" || normalized === "error" || normalized === "disconnected") return "red";
    return "muted";
  }

  function monitoringStatusCell(label, tone) {
    return el("span", { className: "monitoring-status-cell" },
      el("span", { className: "monitoring-status-icon " + (tone || "muted"), "aria-hidden": "true" }),
      el("span", { className: "monitoring-status-label" }, label)
    );
  }

  function formatSeconds(value) {
    return typeof value === "number" ? formatNum(value, value >= 10 ? 0 : 1) + " s" : "—";
  }

  async function resetAdapterCircuit(adapterName, btn) {
    await withButton(btn, async () => {
      await api("POST", endpoints.healthAdapters + "/" + encodeURIComponent(adapterName) + "/reset");
      if (lastAdapters && lastAdapters[adapterName]) {
        const status = lastAdapters[adapterName];
        status.state = "closed";
        status.consecutive_failures = 0;
        status.consecutive_successes = 0;
        if (status.exponential_backoff) {
          status.exponential_backoff.recovery_attempts = 0;
          status.exponential_backoff.current_timeout = status.exponential_backoff.base_timeout || 0;
        }
        renderMonitoringAdapterList(lastAdapters);
      }
    }, "Circuit breaker reset for " + adapterName);
  }

  function renderMonitoringTable(container, columns, rows, emptyMessage, paginator, sorter) {
    clear(container);
    if (!rows.length) {
      container.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, emptyMessage));
      if (paginator) paginator.setItems([]);
      return;
    }
    const table = el("table", { className: "monitoring-table" });
    // Monitoring rows are arrays of built cells, so a column sorts on the
    // text of its own cell.
    const sortColumns = columns.map((column, index) => {
      if (column.sortable === false) return column;
      return {
        label: column.label,
        attrs: column.attrs,
        key: String(index),
        sortValue: (row) => (row[index] ? row[index].textContent : ""),
      };
    });
    table.appendChild(el("thead", null, sorter
      ? sorter.headerRow(sortColumns)
      : el("tr", null, columns.map((column) => el("th", column.attrs || null, column.label)))));
    const tbody = el("tbody");
    table.appendChild(tbody);
    container.appendChild(table);
    function renderPage(pageRows) {
      clear(tbody);
      pageRows.forEach((row) => { tbody.appendChild(el("tr", null, row)); });
    }
    if (paginator) {
      paginator.setPageChangeHandler(renderPage);
      paginator.setItems(rows, true);
    } else {
      renderPage(rows);
    }
  }

  function updateMonitoringPipeline(steps, summary) {
    const section = document.getElementById("mon-pipeline-section");
    if (!section) return;
    if (!steps || !Object.keys(steps).length) { section.style.display = "none"; return; }
    section.style.display = "";
    const summaryEl = document.getElementById("mon-pipeline-summary");
    if (summaryEl && summary) {
      clear(summaryEl);
      summaryEl.appendChild(monitoringSummaryCard("Total Executions", formatNum(summary.total_executions)));
      summaryEl.appendChild(monitoringSummaryCard("Success Rate", formatNum((summary.success_rate * 100), 1) + "%"));
      summaryEl.appendChild(monitoringSummaryCard("Avg Pipeline Time", formatNum(summary.avg_time_ms, 1) + " ms"));
    }
    const container = document.getElementById("mon-pipeline-steps");
    if (!container) return;
    const entries = Object.entries(steps).sort((a, b) => b[1].total_executions - a[1].total_executions);
    clear(container);
    entries.forEach((pair) => {
      const name = pair[0], s = pair[1];
      const pct = s.success_rate * 100;
      const badgeCls = pct < 80 ? "red" : pct < 95 ? "amber" : "green";
      container.appendChild(el("div", { className: "monitoring-adapter-card" },
        el("div", { style: "display:flex;justify-content:space-between;align-items:center" },
          el("span", { style: "font-weight:700;font-size:var(--text-sm)" }, name),
          el("span", { className: "monitoring-badge " + badgeCls }, formatNum(pct, 1) + "%")
        ),
        el("div", { style: "display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--sp-2);font-size:var(--text-xs);color:var(--ink-muted)" },
          monitoringStatCell("Avg", formatNum(s.avg_time_ms, 1) + " ms"),
          monitoringStatCell("Min", formatNum(s.min_time_ms, 1) + " ms"),
          monitoringStatCell("Max", formatNum(s.max_time_ms, 1) + " ms")
        ),
        el("div", { style: "font-size:var(--text-xs);color:var(--ink-muted)" }, formatNum(s.total_executions) + " executions")
      ));
    });
  }

  function updateMonitoringAdapters(adapters) {
    lastAdapters = adapters || {};
    const section = document.getElementById("mon-adapter-section");
    if (!section) return;
    const entries = Object.entries(lastAdapters);
    if (!entries.length) { section.style.display = "none"; return; }
    section.style.display = "";
    renderMonitoringAdapterList(lastAdapters);
  }

  function renderMonitoringAdapterList(adapters) {
    const summaryEl = document.getElementById("mon-adapter-summary");
    const container = document.getElementById("mon-adapter-list");
    if (!summaryEl || !container) return;
    const entries = Object.entries(adapters || {});
    if (!entries.length) {
      clear(summaryEl);
      summaryEl.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, "No adapter telemetry available"));
      clear(container);
      return;
    }
    const counts = entries.reduce((acc, pair) => {
      const state = (pair[1] && pair[1].state || "unknown").toLowerCase();
      acc[state] = (acc[state] || 0) + 1; acc.total += 1; return acc;
    }, { total: 0, open: 0, half_open: 0, closed: 0, unknown: 0 });
    clear(summaryEl);
    [
      { label: "Total", key: "total", hint: "Monitored" },
      { label: "Open", key: "open", hint: "Tripped" },
      { label: "Half-open", key: "half_open", hint: "Testing" },
      { label: "Closed", key: "closed", hint: "Healthy" }
    ].forEach((c) => {
      summaryEl.appendChild(monitoringSummaryCard(c.label, String(counts[c.key] || 0), c.hint, "monitoring-summary-card-compact"));
    });

    const stateOrder = { open: 0, half_open: 1, closed: 2, unknown: 3 };
    const filtered = entries.filter((pair) => {
      const st = (pair[1] && pair[1].state || "unknown").toLowerCase();
      const matchState = adapterStateFilter === "all" || adapterStateFilter === st;
      const matchSearch = !adapterSearchFilter || pair[0].toLowerCase().includes(adapterSearchFilter);
      return matchState && matchSearch;
    }).sort((a, b) => {
      const sa = (a[1] && a[1].state || "unknown").toLowerCase();
      const sb = (b[1] && b[1].state || "unknown").toLowerCase();
      const d = (stateOrder[sa] || 3) - (stateOrder[sb] || 3);
      return d !== 0 ? d : a[0].localeCompare(b[0]);
    });

    clear(container);
    if (!filtered.length) {
      container.appendChild(el("p", { style: "color:var(--ink-muted);font-size:var(--text-sm)" }, "No adapters match the current filters."));
      return;
    }
    const rows = filtered.map((pair) => {
      const name = pair[0], status = pair[1];
      const state = (status && status.state || "unknown").toLowerCase();
      const failures = (status && status.consecutive_failures) || 0;
      const reqs = (status && (status.request_count || status.success_count)) || 0;
      const latency = status && status.average_latency_ms;
      const backoff = status && status.exponential_backoff || {};
      const recoveryAttempts = backoff.recovery_attempts || 0;
      const nextRetry = state === "open" ? formatSeconds(backoff.current_timeout) : "—";
      const latencyStr = typeof latency === "number" ? formatNum(latency, latency >= 100 ? 0 : 1) + " ms" : "—";
      const resetBtn = el("button", {
        type: "button",
        className: "secondary",
        title: "Reset circuit breaker for " + name,
        "aria-label": "Reset circuit breaker for " + name,
        onclick: () => { resetAdapterCircuit(name, resetBtn); }
      }, "Reset");
      return [
        el("td", null, el("div", { className: "monitoring-table-primary", title: name }, name)),
        el("td", null, monitoringStatusCell(state.replace("_", " "), monitoringStateTone(state))),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(reqs)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(failures)),
        el("td", { style: "text-align:right;font-weight:600" }, formatNum(recoveryAttempts)),
        el("td", { style: "text-align:right;font-weight:600" }, nextRetry),
        el("td", { style: "text-align:right;font-weight:600" }, latencyStr),
        el("td", { style: "text-align:right" }, resetBtn)
      ];
    });
    renderMonitoringTable(container, [
      { label: "Adapter" },
      { label: "State" },
      { label: "Requests", attrs: { style: "text-align:right" } },
      { label: "Failures", attrs: { style: "text-align:right" } },
      { label: "Recovery Attempts", attrs: { style: "text-align:right" } },
      { label: "Next Retry", attrs: { style: "text-align:right" } },
      { label: "Avg Latency", attrs: { style: "text-align:right" } },
      { label: "Actions", attrs: { style: "text-align:right" }, sortable: false }
    ], rows, "No adapters match the current filters.", overviewAdapterPaginator, overviewAdapterSorter);
  }

  function updateMonitoringThreadPools(pools) {
    lastThreadPools = pools || {};
    const section = document.getElementById("mon-threadpool-section");
    if (!section) return;
    const entries = Object.entries(lastThreadPools);
    if (!entries.length) { section.style.display = "none"; return; }
    section.style.display = "";
    const container = document.getElementById("mon-threadpool-list");
    if (!container) return;
    const filtered = entries.filter((pair) => {
      if (!threadPoolSearchFilter) return true;
      return pair[0].toLowerCase().includes(threadPoolSearchFilter);
    }).sort((a, b) => a[0].localeCompare(b[0]));
    const rows = filtered.map((pair) => {
      const name = pair[0], pool = pair[1];
      const util = pool.max_workers > 0 ? clampPercentage((pool.active_threads / pool.max_workers) * 100) : 0;
      const isIdle = pool.active_threads === 0 && pool.queued_tasks === 0;
      const tone = isIdle ? "muted" : util >= 90 ? "red" : util >= 75 ? "amber" : "green";
      const statusLabel = isIdle ? "Idle" : util >= 90 ? "Busy" : util >= 75 ? "Active" : "Healthy";
      return [
        el("td", null, el("div", { className: "monitoring-table-primary", title: name }, name)),
        el("td", null, monitoringStatusCell(statusLabel, tone)),
        el("td", { style: "text-align:right;font-weight:600" }, pool.active_threads + " / " + pool.max_workers),
        el("td", { style: "text-align:right;font-weight:600" }, String(pool.queued_tasks === "N/A" ? "0" : pool.queued_tasks)),
        el("td", { style: "text-align:right;font-weight:600" }, util.toFixed(1) + "%")
      ];
    });
    renderMonitoringTable(container, [
      { label: "Pool" },
      { label: "Status" },
      { label: "Active Threads", attrs: { style: "text-align:right" } },
      { label: "Queued", attrs: { style: "text-align:right" } },
      { label: "Utilization", attrs: { style: "text-align:right" } }
    ], rows, "No thread pools match the current filter.", overviewThreadPoolPaginator, overviewThreadPoolSorter);
  }

  function updateMonitoringRedisHealth(data) {
    const section = document.getElementById("mon-redis-section");
    if (!section) return;
    if (!data || !data.enabled) { section.style.display = "none"; return; }
    section.style.display = "";
    const statusEl = document.getElementById("mon-redis-status");
    if (statusEl) {
      statusEl.textContent = data.initialized ? "Connected" : "Disconnected";
      statusEl.style.color = data.initialized ? "var(--success-text)" : "var(--danger-text)";
    }
    const cb = data.circuit_breaker || {};
    setText("mon-redis-cb", (cb.state || "unknown").replace("_", "-"));
    setText("mon-redis-failures", (cb.failure_count || 0) + " / " + (cb.max_failures || 5));
    const pool = data.pool || {};
    const inUse = pool.in_use_connections || 0;
    const maxC = pool.max_connections || 0;
    setText("mon-redis-pool", inUse + " / " + maxC);
    const util = maxC > 0 ? clampPercentage((inUse / maxC) * 100) : 0;
    setProgressBar("mon-redis-bar", util, util >= 90 ? "red" : util >= 70 ? "amber" : "green");
  }

  function updateMonitoringDatasourcePool(data) {
    lastDatasourcePool = data || null;
    const section = document.getElementById("mon-datasource-section");
    if (!section) return;
    if (!data || !(data.total_cached_datasources > 0)) { section.style.display = "none"; return; }
    section.style.display = "";
    setText("mon-ds-total", formatNum(data.total_cached_datasources || 0));
    setText("mon-ds-refs", formatNum(data.total_references || 0));
    const eff = data.total_references > 0 ? ((data.total_references - data.total_cached_datasources) / data.total_references * 100) : 0;
    setText("mon-ds-efficiency", formatNum(Math.max(0, eff), 1) + "%");
    const container = document.getElementById("mon-ds-list");
    if (!container || !data.datasource_keys) return;
    const filteredKeys = data.datasource_keys.filter((key) => {
      if (!datasourceSearchFilter) return true;
      return key.toLowerCase().includes(datasourceSearchFilter);
    }).sort();
    const rows = filteredKeys.map((key) => {
      const refCount = (data.reference_counts && data.reference_counts[key]) || 0;
      const parts = key.split(":");
      const dsType = parts[0] || "unknown";
      const connInfo = parts.slice(1).join(":") || "default";
      const statusTone = refCount >= 3 ? "green" : refCount === 2 ? "amber" : "muted";
      const statusLabel = refCount >= 3 ? "Shared" : refCount === 2 ? "Warm" : "Idle";
      return [
        el("td", null, el("div", { className: "monitoring-table-primary" }, dsType)),
        el("td", null, el("code", { className: "monitoring-table-code", title: connInfo }, connInfo)),
        el("td", { style: "text-align:right;font-weight:600" }, refCount),
        el("td", null, monitoringStatusCell(statusLabel, statusTone))
      ];
    });
    renderMonitoringTable(container, [
      { label: "Datasource" },
      { label: "Connection" },
      { label: "References", attrs: { style: "text-align:right" } },
      { label: "Status" }
    ], rows, "No datasource pool entries match the current filter.", overviewDatasourcePaginator, overviewDatasourceSorter);
  }

  function updateMonitoringConnections(conn) {
    setText("mon-ws-clients", (conn.websocket_clients || 0).toString());
    setText("mon-active-sessions", (conn.active_sessions || 0).toString());
  }

  // --- Render Overview ---
  async function render(container) {
    // Live metrics arrive over the /ws/metrics WebSocket, which requires
    // metrics.read (analyst and user-manager, for example, don't have it).
    // Skip building the dashboard - and opening a socket the server will
    // refuse - rather than showing charts stuck on "Reconnecting...".
    if (!userHasPermission("metrics.read")) {
      clear(container);
      container.appendChild(el("p", { className: "muted" },
        "Live metrics require the metrics.read permission (the operator or auditor role, for example)."
      ));
      return;
    }

    overviewAdapterPaginator = createPaginator({ pageSize: itemsPerPage, onPageChange: () => {} });
    overviewDatasourcePaginator = createPaginator({ pageSize: itemsPerPage, onPageChange: () => {} });
    overviewThreadPoolPaginator = createPaginator({ pageSize: itemsPerPage, onPageChange: () => {} });
    overviewAdapterSorter = createColumnSorter(overviewAdapterPaginator);
    overviewDatasourceSorter = createColumnSorter(overviewDatasourcePaginator);
    overviewThreadPoolSorter = createColumnSorter(overviewThreadPoolPaginator);

    // 1. Toolbar
    const toolbar = el("div", { className: "monitoring-toolbar" },
      el("div", { className: "monitoring-toolbar-left" },
        el("div", { id: "mon-status-dot", className: "status-dot disconnected" }),
        el("span", { id: "mon-status-text", style: "font-size:var(--text-sm);color:var(--ink-muted)" }, "Connecting..."),
        el("span", { style: "font-size:var(--text-xs);color:var(--ink-muted)" }, "Last update: "),
        el("span", { id: "mon-last-update", style: "font-size:var(--text-xs);font-family:var(--font-mono);color:var(--ink-muted)" }, "—")
      ),
      el("div", { className: "monitoring-toolbar-right" },
        [1, 5, 15, 30, 60].map((m) => {
          const btn = el("button", {
            className: "time-window-btn",
            "aria-pressed": m === selectedWindowMinutes ? "true" : "false",
            dataset: { window: String(m) }
          }, m + "m");
          btn.addEventListener("click", () => {
            if (m === selectedWindowMinutes) return;
            selectedWindowMinutes = m;
            document.querySelectorAll(".time-window-btn").forEach((b) => { b.setAttribute("aria-pressed", b.dataset.window === String(m)); });
            if (lastMetricsSnapshot) updateMonitoringMetrics(lastMetricsSnapshot);
          });
          return btn;
        }),
        el("button", { className: "monitoring-export-btn", onClick: () => { window.open(endpoints.adminExport, "_blank"); } }, "Export")
      )
    );
    container.appendChild(toolbar);

    // 2. Metric cards
    function metricCard(id, label, unit, showProgress) {
      return el("div", { id: id, className: "metric-card", dataset: { state: "unknown" } },
        el("div", { className: "metric-card-header" },
          el("div", { className: "metric-label" }, label),
          el("span", { id: id + "-status", className: "metric-status" }, "Waiting")
        ),
        el("div", { className: "metric-reading" }, el("span", { id: id + "-value", className: "metric-value" }, "—"), unit ? el("span", { className: "metric-unit" }, unit) : null),
        el("div", { id: id + "-sub", className: "metric-sub" }, ""),
        el("div", { id: id + "-change", className: "metric-change", dataset: { direction: "neutral" } }, "Collecting trend data"),
        showProgress === false ? null : el("div", { className: "monitoring-progress-track" }, el("div", { id: id + "-bar", className: "monitoring-progress-bar muted", style: "width:0%" }))
      );
    }
    const metricsGrid = el("div", { className: "metric-cards-grid" },
      metricCard("mon-cpu", "CPU", "%"),
      metricCard("mon-mem", "Memory", "GB"),
      metricCard("mon-rps", "Throughput", "req/s", false),
      metricCard("mon-rel", "Reliability", "%")
    );
    container.appendChild(metricsGrid);

    // 4. Charts
    const chartsGrid = el("div", { className: "charts-grid" });
    [["mon-system-chart", "System Resources"], ["mon-request-chart", "Request Metrics"],
     ["mon-response-chart", "Response Time (ms)"], ["mon-percentile-chart", "Percentiles (ms)"]
    ].forEach((pair) => {
      const card = el("div", { className: "chart-card" },
        el("h3", null, pair[1]),
        el("canvas", { id: pair[0] })
      );
      chartsGrid.appendChild(card);
    });
    container.appendChild(chartsGrid);

    // 5. Endpoint latency table
    const endpointSection = el("div", { id: "mon-endpoint-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Endpoint Latency"),
      el("div", { className: "endpoint-table-wrap" },
        el("table", { className: "endpoint-table" },
          el("thead", null, el("tr", null,
            el("th", null, "Method"), el("th", null, "Endpoint"), el("th", { style: "text-align:right" }, "Requests"),
            el("th", { style: "text-align:right" }, "Avg Latency"), el("th", { style: "text-align:right" }, "Error Rate")
          )),
          el("tbody", { id: "mon-endpoint-tbody" })
        )
      )
    );
    container.appendChild(endpointSection);

    // 6. Pipeline steps
    const pipelineSection = el("div", { id: "mon-pipeline-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Pipeline Steps"),
      el("div", { id: "mon-pipeline-summary", style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2);margin-bottom:var(--sp-3)" }),
      el("div", { id: "mon-pipeline-steps", className: "adapter-health-grid" })
    );
    container.appendChild(pipelineSection);

    // 7. Adapter Health
    const adapterToolbar = el("div", { className: "adapter-health-toolbar" });
    const searchWrap = el("div", { className: "monitoring-search-field" });
    const searchInput = el("input", { type: "text", placeholder: "Search adapters...", "aria-label": "Search adapters" });
    searchInput.addEventListener("input", (e) => {
      adapterSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (overviewAdapterPaginator) overviewAdapterPaginator.goToPage(1);
      if (lastMetricsSnapshot) renderMonitoringAdapterList(lastAdapters);
    });
    searchWrap.appendChild(searchInput);
    adapterToolbar.appendChild(searchWrap);
    ["all", "closed", "half_open", "open"].forEach((state) => {
      const btn = el("button", { className: "state-filter" + (state === adapterStateFilter ? " active" : ""), "aria-pressed": state === adapterStateFilter ? "true" : "false" }, state === "all" ? "All" : state.replace("_", " "));
      btn.addEventListener("click", () => {
        adapterStateFilter = state;
        if (overviewAdapterPaginator) overviewAdapterPaginator.goToPage(1);
        adapterToolbar.querySelectorAll(".state-filter").forEach((b) => {
          const isActive = b === btn;
          b.classList.toggle("active", isActive);
          b.setAttribute("aria-pressed", isActive);
        });
        renderMonitoringAdapterList(lastAdapters);
      });
      adapterToolbar.appendChild(btn);
    });

    const adapterSection = el("div", { id: "mon-adapter-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Adapter Health"),
      adapterToolbar,
      el("div", { id: "mon-adapter-summary", style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2);margin:var(--sp-3) 0" }),
      el("div", { id: "mon-adapter-list", className: "table-wrap monitoring-table-wrap" }),
      overviewAdapterPaginator.getControlsEl()
    );
    container.appendChild(adapterSection);

    // 8. Datasource Pool
    const dsToolbar = el("div", { className: "monitoring-table-toolbar" });
    const dsSearchWrap = el("div", { className: "monitoring-search-field" });
    const dsSearchInput = el("input", { type: "text", placeholder: "Search datasource pool...", "aria-label": "Search datasource pool" });
    dsSearchInput.addEventListener("input", (e) => {
      datasourceSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (overviewDatasourcePaginator) overviewDatasourcePaginator.goToPage(1);
      if (lastDatasourcePool) updateMonitoringDatasourcePool(lastDatasourcePool);
    });
    dsSearchWrap.appendChild(dsSearchInput);
    dsToolbar.appendChild(dsSearchWrap);
    const dsSection = el("div", { id: "mon-datasource-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Datasource Pool"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2);margin-bottom:var(--sp-3)" },
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "Cached"), el("p", { id: "mon-ds-total", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "References"), el("p", { id: "mon-ds-refs", className: "value" }, "0")),
        el("div", { className: "monitoring-summary-card monitoring-summary-card-compact" }, el("p", { className: "label" }, "Reuse Rate"), el("p", { id: "mon-ds-efficiency", className: "value" }, "0%"))
      ),
      dsToolbar,
      el("div", { id: "mon-ds-list", className: "table-wrap monitoring-table-wrap" }),
      overviewDatasourcePaginator.getControlsEl()
    );
    container.appendChild(dsSection);

    // 9. Redis Health
    const redisSection = el("div", { id: "mon-redis-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Redis Health"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2)" },
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Status"), el("p", { id: "mon-redis-status", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Circuit Breaker"), el("p", { id: "mon-redis-cb", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Failures"), el("p", { id: "mon-redis-failures", className: "value" }, "—")),
        el("div", { className: "monitoring-summary-card" }, el("p", { className: "label" }, "Pool"), el("p", { id: "mon-redis-pool", className: "value" }, "—"))
      ),
      el("div", { className: "monitoring-progress-track", style: "margin-top:var(--sp-2)" }, el("div", { id: "mon-redis-bar", className: "monitoring-progress-bar muted", style: "width:0%" }))
    );
    container.appendChild(redisSection);

    // 10. Thread Pools
    const threadToolbar = el("div", { className: "monitoring-table-toolbar" });
    const threadSearchWrap = el("div", { className: "monitoring-search-field" });
    const threadSearchInput = el("input", { type: "text", placeholder: "Search thread pools...", "aria-label": "Search thread pools" });
    threadSearchInput.addEventListener("input", (e) => {
      threadPoolSearchFilter = (e.target.value || "").trim().toLowerCase();
      if (overviewThreadPoolPaginator) overviewThreadPoolPaginator.goToPage(1);
      updateMonitoringThreadPools(lastThreadPools);
    });
    threadSearchWrap.appendChild(threadSearchInput);
    threadToolbar.appendChild(threadSearchWrap);
    const threadSection = el("div", { id: "mon-threadpool-section", className: "monitoring-section", style: "display:none" },
      el("h3", null, "Thread Pools"),
      threadToolbar,
      el("div", { id: "mon-threadpool-list", className: "table-wrap monitoring-table-wrap" }),
      overviewThreadPoolPaginator.getControlsEl()
    );
    container.appendChild(threadSection);

    // Initialize charts after DOM insertion
    initOverviewCharts();

    // Connect WebSocket for live monitoring
    connectMetricsWs();
  }

  return { render, dispose };
}
