        // WebSocket connection
        let ws = null;
        let reconnectInterval = null;

        // Time window state (minutes)
        let selectedWindowMinutes = 5;
        let lastMetricsSnapshot = null;

        // Server-sent thresholds (defaults until first message)
        let thresholds = { cpu: 90, memory: 85, error_rate: 5, response_time_ms: 5000 };
        const announcer = document.getElementById('dashboard-announcer');

        // Chart configurations
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
                axis: 'x'
            },
            elements: {
                point: {
                    radius: 0,
                    hoverRadius: 5,
                    hitRadius: 18
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(148, 163, 184, 0.08)' },
                    ticks: { color: 'rgba(226, 232, 240, 0.75)' }
                },
                x: {
                    grid: { color: 'rgba(148, 163, 184, 0.08)' },
                    ticks: { color: 'rgba(226, 232, 240, 0.65)', maxRotation: 0, minRotation: 0 }
                }
            },
            plugins: {
                legend: {
                    labels: { color: 'rgba(226, 232, 240, 0.9)' }
                }
            }
        };

        // Initialize charts
        const systemChart = new Chart(document.getElementById('system-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'CPU %',
                    data: [],
                    borderColor: 'rgb(56, 189, 248)',
                    backgroundColor: 'rgba(56, 189, 248, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }, {
                    label: 'Memory %',
                    data: [],
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }]
            },
            options: chartOptions
        });

        const requestChartOptions = {
            ...chartOptions,
            scales: {
                ...chartOptions.scales,
                y: {
                    ...chartOptions.scales.y,
                    ticks: {
                        ...chartOptions.scales.y.ticks,
                        stepSize: 1,
                        precision: 0
                    },
                    min: 0
                }
            },
            plugins: {
                ...chartOptions.plugins,
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.datasetIndex === 0) {
                                label += Math.round(context.parsed.y);
                            } else {
                                label += context.parsed.y.toFixed(2) + '%';
                            }
                            return label;
                        }
                    }
                }
            }
        };

        const requestChart = new Chart(document.getElementById('request-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Requests/sec',
                    data: [],
                    borderColor: 'rgb(251, 191, 36)',
                    backgroundColor: 'rgba(251, 191, 36, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }, {
                    label: 'Error Rate %',
                    data: [],
                    borderColor: 'rgb(244, 114, 182)',
                    backgroundColor: 'rgba(244, 114, 182, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }]
            },
            options: requestChartOptions
        });

        const responseChart = new Chart(document.getElementById('response-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Avg Response Time',
                    data: [],
                    borderColor: 'rgb(129, 140, 248)',
                    backgroundColor: 'rgba(129, 140, 248, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }]
            },
            options: chartOptions
        });

        const percentileChart = new Chart(document.getElementById('percentile-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'P50',
                    data: [],
                    borderColor: 'rgb(34, 197, 94)',
                    backgroundColor: 'rgba(34, 197, 94, 0.08)',
                    tension: 0.25,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }, {
                    label: 'P95',
                    data: [],
                    borderColor: 'rgb(251, 146, 60)',
                    backgroundColor: 'rgba(251, 146, 60, 0.08)',
                    tension: 0.25,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }, {
                    label: 'P99',
                    data: [],
                    borderColor: 'rgb(244, 63, 94)',
                    backgroundColor: 'rgba(244, 63, 94, 0.08)',
                    tension: 0.25,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHitRadius: 18
                }]
            },
            options: chartOptions
        });

        // Adapter state
        let adapterSearchFilter = '';
        let adapterStateFilter = 'all';
        let lastAdapterSnapshot = null;

        const adapterSearchInput = document.getElementById('adapter-search');
        const adapterStateButtons = document.querySelectorAll('[data-adapter-state]');

        if (adapterSearchInput) {
            adapterSearchInput.addEventListener('input', (event) => {
                adapterSearchFilter = (event.target.value || '').trim().toLowerCase();
                if (lastAdapterSnapshot) {
                    renderAdapterList(lastAdapterSnapshot);
                }
            });
        }

        adapterStateButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const state = button.getAttribute('data-adapter-state') || 'all';
                if (state === adapterStateFilter) {
                    return;
                }
                adapterStateFilter = state;
                adapterStateButtons.forEach((btn) => {
                    const isActive = btn === button;
                    btn.classList.toggle('active', isActive);
                    btn.setAttribute('aria-pressed', isActive);
                });
                if (lastAdapterSnapshot) {
                    renderAdapterList(lastAdapterSnapshot);
                }
            });
        });

        // Time window selector
        document.querySelectorAll('.time-window-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const minutes = parseInt(btn.getAttribute('data-window'), 10);
                if (minutes === selectedWindowMinutes) return;
                selectedWindowMinutes = minutes;
                document.querySelectorAll('.time-window-btn').forEach((b) => {
                    b.setAttribute('aria-pressed', b === btn);
                });
                if (lastMetricsSnapshot) {
                    updateMetrics(lastMetricsSnapshot);
                }
                announce(`Chart window set to ${minutes} minute${minutes === 1 ? '' : 's'}.`);
            });
        });

        // Export button
        document.getElementById('export-btn').addEventListener('click', () => {
            window.open('/dashboard/export', '_blank');
            announce('Export opened in a new tab.');
        });

        document.getElementById('logout-btn').addEventListener('click', async () => {
            announce('Logging out of the dashboard.');
            try {
                await fetch('/dashboard/logout', {
                    method: 'POST',
                    credentials: 'same-origin'
                });
            } catch (error) {
                console.error('Dashboard logout failed:', error);
            } finally {
                window.location.href = '/dashboard/login';
            }
        });

        function updateChartWithActiveTooltip(chart, labels, datasetValues) {
            const active = chart.getActiveElements();

            chart.data.labels = labels;
            chart.data.datasets.forEach((dataset, idx) => {
                dataset.data = datasetValues[idx] || [];
            });

            chart.update('none');

            if (!labels.length) {
                chart.setActiveElements([]);
                chart.tooltip?.setActiveElements([], { x: 0, y: 0 });
                return;
            }

            if (active.length) {
                const reactivated = active
                    .map(({ datasetIndex, index }) => ({
                        datasetIndex,
                        index: Math.min(labels.length - 1, Math.max(0, index))
                    }))
                    .filter(({ datasetIndex, index }) => {
                        const meta = chart.getDatasetMeta(datasetIndex);
                        return meta && meta.data && meta.data[index];
                    });

                if (reactivated.length) {
                    chart.setActiveElements(reactivated);
                    const first = reactivated[0];
                    const meta = chart.getDatasetMeta(first.datasetIndex);
                    const element = meta?.data?.[first.index];
                    if (element) {
                        chart.tooltip?.setActiveElements(reactivated, { x: element.x, y: element.y });
                        chart.tooltip?.update();
                    }
                    chart.draw();
                }
            }
        }

        function clampPercentage(value) {
            if (typeof value !== 'number' || isNaN(value)) {
                return 0;
            }
            return Math.min(100, Math.max(0, value));
        }

        function announce(message) {
            if (!announcer) {
                return;
            }
            announcer.textContent = '';
            requestAnimationFrame(() => {
                announcer.textContent = message;
            });
        }

        function formatNumber(value, fractionDigits = null) {
            const num = Number(value);
            if (Number.isNaN(num)) {
                return value ?? '0';
            }
            if (fractionDigits === null) {
                return num.toLocaleString();
            }
            return num.toLocaleString(undefined, {
                minimumFractionDigits: fractionDigits,
                maximumFractionDigits: fractionDigits
            });
        }

        function escapeHtml(value) {
            if (value === null || value === undefined) {
                return '';
            }
            const lookup = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            };
            return String(value).replace(/[&<>"']/g, (char) => lookup[char] || char);
        }

        function updateChartSummary(id, text) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = text;
            }
        }

        function getChartDensityConfig() {
            if (selectedWindowMinutes <= 5) {
                return { targetPoints: 60, maxTicks: 6 };
            }
            if (selectedWindowMinutes <= 15) {
                return { targetPoints: 45, maxTicks: 7 };
            }
            if (selectedWindowMinutes <= 30) {
                return { targetPoints: 36, maxTicks: 7 };
            }
            return { targetPoints: 24, maxTicks: 8 };
        }

        function updateChartAxisDensity(chart) {
            const density = getChartDensityConfig();
            if (chart?.options?.scales?.x?.ticks) {
                chart.options.scales.x.ticks.maxTicksLimit = density.maxTicks;
            }
        }

        function aggregateSeries(labels, seriesList) {
            if (!labels.length) {
                return { labels, seriesList };
            }

            const density = getChartDensityConfig();
            if (labels.length <= density.targetPoints) {
                return { labels, seriesList };
            }

            const bucketSize = Math.ceil(labels.length / density.targetPoints);
            const aggregatedLabels = [];
            const aggregatedSeries = seriesList.map(() => []);

            for (let start = 0; start < labels.length; start += bucketSize) {
                const end = Math.min(start + bucketSize, labels.length);
                aggregatedLabels.push(labels[end - 1]);

                seriesList.forEach((series, index) => {
                    const bucket = series.slice(start, end).filter((value) => typeof value === 'number' && !Number.isNaN(value));
                    if (!bucket.length) {
                        aggregatedSeries[index].push(null);
                        return;
                    }
                    const avg = bucket.reduce((sum, value) => sum + value, 0) / bucket.length;
                    aggregatedSeries[index].push(avg);
                });
            }

            return { labels: aggregatedLabels, seriesList: aggregatedSeries };
        }

        function getMaxPoints(timestamps) {
            if (!Array.isArray(timestamps) || timestamps.length < 2) {
                return Math.ceil((selectedWindowMinutes * 60) / 5);
            }

            const intervals = [];
            for (let i = 1; i < timestamps.length; i += 1) {
                const prev = new Date(timestamps[i - 1]).getTime();
                const curr = new Date(timestamps[i]).getTime();
                const deltaSeconds = (curr - prev) / 1000;
                if (Number.isFinite(deltaSeconds) && deltaSeconds > 0) {
                    intervals.push(deltaSeconds);
                }
            }

            if (!intervals.length) {
                return Math.ceil((selectedWindowMinutes * 60) / 5);
            }

            const avgIntervalSeconds = intervals.reduce((sum, value) => sum + value, 0) / intervals.length;
            return Math.max(1, Math.ceil((selectedWindowMinutes * 60) / avgIntervalSeconds));
        }

        function updateMetrics(data) {
            lastMetricsSnapshot = data;
            const cpuPercent = clampPercentage(data.system.cpu_percent);
            const memoryPercent = clampPercentage(data.system.memory_percent);
            const errorPercent = clampPercentage(data.requests.error_rate);

            // Update thresholds from server if present
            if (data.thresholds) {
                thresholds = { ...thresholds, ...data.thresholds };
            }

            document.getElementById('cpu-usage').textContent = formatNumber(cpuPercent, 1);
            document.getElementById('cpu-usage-label').textContent = formatNumber(cpuPercent, 1) + '%';
            const cpuBar = document.getElementById('cpu-usage-bar');
            if (cpuBar) {
                cpuBar.style.width = cpuPercent.toFixed(1) + '%';
                cpuBar.setAttribute('aria-valuenow', Math.round(cpuPercent));
            }

            document.getElementById('memory-usage').textContent = formatNumber(data.system.memory_gb, 2);
            document.getElementById('memory-percent').textContent = formatNumber(memoryPercent, 1);
            const memoryBar = document.getElementById('memory-usage-bar');
            if (memoryBar) {
                memoryBar.style.width = memoryPercent.toFixed(1) + '%';
                memoryBar.setAttribute('aria-valuenow', Math.round(memoryPercent));
            }
            const memoryHealth = document.getElementById('memory-health');
            if (memoryHealth) {
                if (memoryPercent >= thresholds.memory) {
                    memoryHealth.textContent = 'Critical';
                    memoryHealth.className = 'text-sm font-semibold text-rose-300';
                } else if (memoryPercent >= thresholds.memory * 0.82) {
                    memoryHealth.textContent = 'Elevated';
                    memoryHealth.className = 'text-sm font-semibold text-amber-300';
                } else {
                    memoryHealth.textContent = 'Stable';
                    memoryHealth.className = 'text-sm font-semibold text-emerald-300';
                }
            }

            document.getElementById('requests-per-second').textContent = formatNumber(data.requests.per_second, 1);
            document.getElementById('total-requests').textContent = formatNumber(data.requests.total);
            document.getElementById('requests-error-rate').textContent = formatNumber(errorPercent, 2) + '%';

            // Reliability = 100% - error rate
            const reliabilityPercent = clampPercentage(100 - errorPercent);
            document.getElementById('reliability-percent').textContent = formatNumber(reliabilityPercent, 2);

            const reliabilityStatusEl = document.getElementById('reliability-status');
            let reliabilityStatus = 'Nominal';
            let reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300';
            let reliabilityBarClass = 'bg-emerald-400/80';

            if (errorPercent >= thresholds.error_rate) {
                reliabilityStatus = 'Critical';
                reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-rose-300';
                reliabilityBarClass = 'bg-rose-500/85';
            } else if (errorPercent >= thresholds.error_rate * 0.2) {
                reliabilityStatus = 'Degraded';
                reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-amber-300';
                reliabilityBarClass = 'bg-amber-400/80';
            }

            if (reliabilityStatusEl) {
                reliabilityStatusEl.textContent = reliabilityStatus;
                reliabilityStatusEl.className = reliabilityStatusClass;
            }

            const reliabilityBar = document.getElementById('reliability-bar');
            if (reliabilityBar) {
                reliabilityBar.className = `progress-bar ${reliabilityBarClass}`;
                reliabilityBar.style.width = reliabilityPercent.toFixed(2) + '%';
                reliabilityBar.setAttribute('aria-valuenow', Math.round(reliabilityPercent));
            }
            document.getElementById('uptime').textContent = data.system.uptime;

            // Disk usage
            const diskEl = document.getElementById('disk-usage');
            if (diskEl && data.system.disk_usage_percent !== undefined) {
                const diskPct = data.system.disk_usage_percent;
                diskEl.textContent = formatNumber(diskPct, 1) + '%';
                if (diskPct >= 90) {
                    diskEl.className = 'text-sm font-medium text-rose-300';
                } else if (diskPct >= 75) {
                    diskEl.className = 'text-sm font-medium text-amber-300';
                } else {
                    diskEl.className = 'text-sm font-medium text-slate-200';
                }
            }

            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

            // Endpoint stats
            if (data.endpoint_stats && data.endpoint_stats.length > 0) {
                updateEndpointStats(data.endpoint_stats);
            }

            if (data.time_series && data.time_series.timestamps.length > 0) {
                const labels = data.time_series.timestamps.map(t =>
                    new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                );
                const maxPoints = getMaxPoints(data.time_series.timestamps);
                const startIdx = Math.max(0, labels.length - maxPoints);
                const trimmedLabels = labels.slice(startIdx);

                const systemSeries = aggregateSeries(trimmedLabels, [
                    data.time_series.cpu.slice(startIdx),
                    data.time_series.memory.slice(startIdx)
                ]);
                const requestSeries = aggregateSeries(trimmedLabels, [
                    data.time_series.requests_per_second.slice(startIdx),
                    data.time_series.error_rate.slice(startIdx)
                ]);
                const responseSeries = aggregateSeries(trimmedLabels, [
                    data.time_series.response_time.slice(startIdx)
                ]);
                const percentileSeries = aggregateSeries(trimmedLabels, [
                    data.time_series.response_time_p50.slice(startIdx),
                    data.time_series.response_time_p95.slice(startIdx),
                    data.time_series.response_time_p99.slice(startIdx)
                ]);

                updateChartAxisDensity(systemChart);
                updateChartAxisDensity(requestChart);
                updateChartAxisDensity(responseChart);
                updateChartAxisDensity(percentileChart);

                updateChartWithActiveTooltip(systemChart, systemSeries.labels, systemSeries.seriesList);
                updateChartWithActiveTooltip(requestChart, requestSeries.labels, requestSeries.seriesList);
                updateChartWithActiveTooltip(responseChart, responseSeries.labels, responseSeries.seriesList);
                updateChartWithActiveTooltip(percentileChart, percentileSeries.labels, percentileSeries.seriesList);

                updateChartSummary(
                    'system-chart-summary',
                    `CPU and memory usage over time. Latest CPU: ${formatNumber(cpuPercent, 1)} percent. Latest memory: ${formatNumber(memoryPercent, 1)} percent.`
                );
                updateChartSummary(
                    'request-chart-summary',
                    `Request throughput and error rate over time. Latest throughput: ${formatNumber(data.requests.per_second, 1)} requests per second. Latest error rate: ${formatNumber(errorPercent, 2)} percent.`
                );
                updateChartSummary(
                    'response-chart-summary',
                    `Average response time over time. Latest response time: ${formatNumber(data.time_series.response_time[data.time_series.response_time.length - 1] ?? 0, 1)} milliseconds.`
                );
                updateChartSummary(
                    'percentile-chart-summary',
                    `Response time percentiles over time. Latest P50: ${formatNumber(data.time_series.response_time_p50[data.time_series.response_time_p50.length - 1] ?? 0, 1)} milliseconds. Latest P95: ${formatNumber(data.time_series.response_time_p95[data.time_series.response_time_p95.length - 1] ?? 0, 1)} milliseconds. Latest P99: ${formatNumber(data.time_series.response_time_p99[data.time_series.response_time_p99.length - 1] ?? 0, 1)} milliseconds.`
                );
            }
        }

        // --- Endpoint latency table ---
        function updateEndpointStats(endpoints) {
            const section = document.getElementById('endpoint-stats-section');
            const tbody = document.getElementById('endpoint-table-body');
            if (!section || !tbody) return;

            if (!endpoints || endpoints.length === 0) {
                section.classList.add('hidden');
                return;
            }
            section.classList.remove('hidden');

            const methodColors = { GET: 'method-get', POST: 'method-post', PUT: 'method-put', DELETE: 'method-delete' };

            tbody.innerHTML = endpoints.map(ep => {
                const method = (ep.method || 'GET').toUpperCase();
                const methodClass = methodColors[method] || 'method-get';
                const latencyClass = ep.avg_latency_ms >= (thresholds.response_time_ms || 5000) ? 'text-rose-300' :
                                     ep.avg_latency_ms >= 1000 ? 'text-amber-300' : 'text-slate-200';
                const errorClass = ep.error_rate >= 5 ? 'text-rose-300' :
                                   ep.error_rate >= 1 ? 'text-amber-300' : 'text-slate-200';
                return `<tr>
                    <td><span class="method-badge ${methodClass}">${method}</span></td>
                    <td class="font-mono text-xs">${escapeHtml(ep.endpoint)}</td>
                    <td class="text-right font-medium">${formatNumber(ep.total_requests)}</td>
                    <td class="text-right font-medium ${latencyClass}">${formatNumber(ep.avg_latency_ms, 1)} ms</td>
                    <td class="text-right font-medium ${errorClass}">${formatNumber(ep.error_rate, 2)}%</td>
                </tr>`;
            }).join('');
        }

        // --- Pipeline steps ---
        function updatePipelineSteps(steps, summary) {
            const section = document.getElementById('pipeline-steps-section');
            const container = document.getElementById('pipeline-steps');
            const summaryContainer = document.getElementById('pipeline-summary');
            if (!section || !container) return;

            if (!steps || Object.keys(steps).length === 0) {
                section.classList.add('hidden');
                return;
            }
            section.classList.remove('hidden');

            // Summary cards
            if (summaryContainer && summary) {
                summaryContainer.innerHTML = [
                    { label: 'Total Executions', value: formatNumber(summary.total_executions) },
                    { label: 'Success Rate', value: formatNumber((summary.success_rate * 100), 1) + '%' },
                    { label: 'Avg Pipeline Time', value: formatNumber(summary.avg_time_ms, 1) + ' ms' },
                ].map(({ label, value }) => `
                    <div class="adapter-summary-card">
                        <p class="label">${label}</p>
                        <p class="value" style="font-size:1.5rem">${value}</p>
                    </div>
                `).join('');
            }

            // Step cards
            const entries = Object.entries(steps).sort((a, b) => b[1].total_executions - a[1].total_executions);
            container.innerHTML = entries.map(([name, s]) => {
                const successPct = (s.success_rate * 100);
                let badgeClass = 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/25';
                if (successPct < 80) {
                    badgeClass = 'badge bg-rose-500/15 text-rose-200 border-rose-500/30';
                } else if (successPct < 95) {
                    badgeClass = 'badge bg-amber-400/15 text-amber-200 border-amber-400/30';
                }

                return `
                    <div class="adapter-card">
                        <div class="flex items-start justify-between gap-3">
                            <p class="text-sm font-semibold text-slate-100">${escapeHtml(name)}</p>
                            <span class="${badgeClass}">${formatNumber(successPct, 1)}%</span>
                        </div>
                        <div class="grid grid-cols-3 gap-3 text-xs text-slate-400">
                            <div>
                                <p class="uppercase tracking-[0.16em] text-[0.65rem]">Avg</p>
                                <p class="text-sm text-slate-200 font-semibold">${formatNumber(s.avg_time_ms, 1)} ms</p>
                            </div>
                            <div>
                                <p class="uppercase tracking-[0.16em] text-[0.65rem]">Min</p>
                                <p class="text-sm text-slate-200 font-semibold">${formatNumber(s.min_time_ms, 1)} ms</p>
                            </div>
                            <div>
                                <p class="uppercase tracking-[0.16em] text-[0.65rem]">Max</p>
                                <p class="text-sm text-slate-200 font-semibold">${formatNumber(s.max_time_ms, 1)} ms</p>
                            </div>
                        </div>
                        <div class="text-xs text-slate-400">${formatNumber(s.total_executions)} executions</div>
                    </div>
                `;
            }).join('');
        }

        // --- Connections info ---
        function updateConnections(conn) {
            if (!conn) return;
            const wsEl = document.getElementById('ws-clients');
            const wsPlural = document.getElementById('ws-clients-s');
            const sessEl = document.getElementById('active-sessions');
            if (wsEl) {
                const count = conn.websocket_clients || 0;
                wsEl.textContent = count;
                if (wsPlural) wsPlural.textContent = count === 1 ? '' : 's';
            }
            if (sessEl) sessEl.textContent = conn.active_sessions || 0;
        }

        const adapterStateStyles = {
            closed: 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/30',
            open: 'badge bg-rose-500/15 text-rose-200 border-rose-500/30',
            half_open: 'badge bg-amber-400/15 text-amber-200 border-amber-400/30',
            unknown: 'badge bg-slate-500/15 text-slate-200 border-slate-500/30'
        };

        const adapterStateSortOrder = {
            open: 0,
            half_open: 1,
            closed: 2,
            unknown: 3
        };

        function renderAdapterList(adapters) {
            const container = document.getElementById('adapter-status');
            const summaryContainer = document.getElementById('adapter-summary');
            if (!container || !summaryContainer) {
                return;
            }

            const entries = Object.entries(adapters || {});
            if (!entries.length) {
                summaryContainer.innerHTML = '<p class="text-sm text-slate-400">No adapter telemetry available</p>';
                container.innerHTML = '<p class="text-sm text-slate-400">No adapter telemetry available</p>';
                return;
            }

            const counts = entries.reduce((acc, [, status]) => {
                const state = (status?.state || 'unknown').toLowerCase();
                acc[state] = (acc[state] || 0) + 1;
                acc.total += 1;
                return acc;
            }, { total: 0, open: 0, half_open: 0, closed: 0, unknown: 0 });

            const summaryCards = [
                { label: 'Total', key: 'total', hint: 'Adapters monitored' },
                { label: 'Open', key: 'open', hint: 'Tripped breakers' },
                { label: 'Half-open', key: 'half_open', hint: 'Testing health' },
                { label: 'Closed', key: 'closed', hint: 'Healthy adapters' }
            ].map(({ label, key, hint }) => `
                <div class="adapter-summary-card">
                    <p class="label">${label}</p>
                    <p class="value">${counts[key] ?? 0}</p>
                    <p class="hint">${hint}</p>
                </div>
            `).join('');
            summaryContainer.innerHTML = summaryCards;

            const filtered = entries
                .filter(([name, status]) => {
                    const normalizedState = (status?.state || 'unknown').toLowerCase();
                    const matchesState = adapterStateFilter === 'all' || adapterStateFilter === normalizedState;
                    const normalizedName = (name || '').toLowerCase();
                    const matchesSearch = !adapterSearchFilter || normalizedName.includes(adapterSearchFilter);
                    return matchesState && matchesSearch;
                })
                .sort((a, b) => {
                    const stateA = (a[1]?.state || 'unknown').toLowerCase();
                    const stateB = (b[1]?.state || 'unknown').toLowerCase();
                    const orderA = adapterStateSortOrder[stateA] ?? adapterStateSortOrder.unknown;
                    const orderB = adapterStateSortOrder[stateB] ?? adapterStateSortOrder.unknown;
                    if (orderA !== orderB) {
                        return orderA - orderB;
                    }
                    return a[0].localeCompare(b[0]);
                });

            if (!filtered.length) {
                container.innerHTML = '<p class="text-sm text-slate-400">No adapters match the current filters.</p>';
                return;
            }

            const html = filtered.map(([name, status]) => {
                const state = (status?.state || 'unknown').toLowerCase();
                const badgeClass = adapterStateStyles[state] || adapterStateStyles.unknown;
                const failures = status?.failure_count ?? 0;
                const requestCount = status?.request_count ?? status?.success_count ?? 0;
                const latency = status?.average_latency_ms;
                const latencyDisplay = typeof latency === 'number'
                    ? `${formatNumber(latency, latency >= 100 ? 0 : 1)} ms`
                    : '\u2014';

                return `
                    <div class="adapter-card">
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0">
                                <p class="text-sm font-semibold text-slate-100 truncate" title="${escapeHtml(name)}">${escapeHtml(name)}</p>
                                <p class="text-xs text-slate-400">Failures: ${formatNumber(failures)}</p>
                            </div>
                            <span class="${badgeClass}">${state.replace('_', ' ')}</span>
                        </div>
                        <div class="grid grid-cols-2 gap-3 text-xs text-slate-400">
                            <div>
                                <p class="uppercase tracking-[0.16em] text-[0.65rem]">Requests</p>
                                <p class="text-sm text-slate-200 font-semibold">${formatNumber(requestCount)}</p>
                            </div>
                            <div>
                                <p class="uppercase tracking-[0.16em] text-[0.65rem]">Latency</p>
                                <p class="text-sm text-slate-200 font-semibold">${latencyDisplay}</p>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = html;
        }

        function updateAdapterStatus(data) {
            const containerDiv = document.getElementById('adapter-status-container');
            const summaryContainer = document.getElementById('adapter-summary');
            const container = document.getElementById('adapter-status');
            if (!containerDiv) {
                return;
            }

            if (data.adapters && Object.keys(data.adapters).length > 0) {
                containerDiv.classList.remove('hidden');
                lastAdapterSnapshot = data.adapters;
                renderAdapterList(lastAdapterSnapshot);
            } else {
                containerDiv.classList.add('hidden');
                lastAdapterSnapshot = null;
                if (summaryContainer) {
                    summaryContainer.innerHTML = '<p class="text-sm text-slate-400">No adapter telemetry available</p>';
                }
                if (container) {
                    container.innerHTML = '<p class="text-sm text-slate-400">No adapter telemetry available</p>';
                }
            }
        }

        function updateThreadPools(pools) {
            const container = document.getElementById('thread-pools');
            if (pools && Object.keys(pools).length > 0) {
                const html = Object.entries(pools).map(([name, pool]) => {
                    const utilization = pool.max_workers > 0 ?
                        ((pool.active_threads / pool.max_workers) * 100) : 0;
                    const clampedUtil = clampPercentage(utilization);

                    const isIdle = pool.active_threads === 0 && pool.queued_tasks === 0;

                    let barColor = 'bg-emerald-400/80';
                    let badgeClass = 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/25';
                    let statusText = '';

                    if (isIdle) {
                        barColor = 'bg-slate-500/50';
                        badgeClass = 'badge bg-slate-500/15 text-slate-300 border-slate-500/25';
                        statusText = '<div class="text-xs text-slate-500 mt-1">Pool idle - threads spawn on demand</div>';
                    } else if (clampedUtil >= 90) {
                        barColor = 'bg-rose-500/80';
                        badgeClass = 'badge bg-rose-500/15 text-rose-200 border-rose-500/30';
                    } else if (clampedUtil >= 75) {
                        barColor = 'bg-amber-400/80';
                        badgeClass = 'badge bg-amber-400/15 text-amber-200 border-amber-400/30';
                    }

                    const queuedDisplay = pool.queued_tasks === 'N/A' ? '0' : pool.queued_tasks;

                    return `
                        <div class="surface-card p-5 space-y-4">
                            <div class="flex items-center justify-between">
                                <h3 class="text-sm font-semibold text-slate-100">${escapeHtml(name)}</h3>
                                <span class="${badgeClass}">${clampedUtil.toFixed(1)}%</span>
                            </div>
                            <div class="space-y-2 text-xs text-slate-400">
                                <div class="flex items-center justify-between">
                                    <span>Active Threads</span>
                                    <span class="text-sm text-slate-200 font-medium">${pool.active_threads} / ${pool.max_workers}</span>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Queued Tasks</span>
                                    <span class="text-sm text-slate-200 font-medium">${queuedDisplay}</span>
                                </div>
                            </div>
                            <div class="progress-track h-1.5">
                                <div class="progress-bar ${barColor}" style="width: ${Math.max(clampedUtil, 2).toFixed(1)}%;"></div>
                            </div>
                            ${statusText}
                        </div>
                    `;
                }).join('');
                container.innerHTML = html;
            } else {
                container.innerHTML = '<p class="text-sm text-slate-400">No thread pool data available</p>';
            }
        }

        function updateRedisHealth(data) {
            const section = document.getElementById('redis-health-section');
            if (!section) return;

            if (!data || !data.enabled) {
                section.classList.add('hidden');
                return;
            }

            section.classList.remove('hidden');

            const statusEl = document.getElementById('redis-status');
            const hintEl = document.getElementById('redis-status-hint');
            if (data.initialized) {
                statusEl.textContent = 'Connected';
                statusEl.className = 'text-2xl font-semibold text-emerald-300';
                hintEl.textContent = 'Healthy';
            } else {
                statusEl.textContent = 'Disconnected';
                statusEl.className = 'text-2xl font-semibold text-rose-300';
                hintEl.textContent = 'Not initialized';
            }

            const cb = data.circuit_breaker || {};
            const cbStateEl = document.getElementById('redis-cb-state');
            const cbState = (cb.state || 'unknown').toLowerCase();
            const cbStyles = {
                closed:    'text-2xl font-semibold text-emerald-300',
                open:      'text-2xl font-semibold text-rose-300',
                half_open: 'text-2xl font-semibold text-amber-300',
                unknown:   'text-2xl font-semibold text-slate-400'
            };
            cbStateEl.textContent = cbState.replace('_', '-');
            cbStateEl.className = cbStyles[cbState] || cbStyles.unknown;
            document.getElementById('redis-cb-failures').textContent = cb.failure_count ?? 0;
            document.getElementById('redis-cb-max').textContent = cb.max_failures ?? 5;

            const pool = data.pool || {};
            const inUse = pool.in_use_connections || 0;
            const maxConn = pool.max_connections || 0;
            document.getElementById('redis-pool-in-use').textContent = inUse;
            document.getElementById('redis-pool-max').textContent = maxConn;

            const utilPct = maxConn > 0 ? ((inUse / maxConn) * 100) : 0;
            const clampedUtil = clampPercentage(utilPct);
            document.getElementById('redis-pool-util').textContent = formatNumber(clampedUtil, 1);

            const utilBar = document.getElementById('redis-pool-util-bar');
            if (utilBar) {
                utilBar.style.width = clampedUtil.toFixed(1) + '%';
                utilBar.setAttribute('aria-valuenow', Math.round(clampedUtil));
                if (clampedUtil >= 90) {
                    utilBar.className = 'progress-bar bg-rose-500/80';
                } else if (clampedUtil >= 70) {
                    utilBar.className = 'progress-bar bg-amber-400/80';
                } else {
                    utilBar.className = 'progress-bar bg-emerald-400/80';
                }
            }
        }

        function updateDatasourcePool(data) {
            const section = document.getElementById('datasource-pool-section');
            const container = document.getElementById('datasource-connections');

            if (data && data.total_cached_datasources > 0) {
                section.classList.remove('hidden');

                const totalDatasources = data.total_cached_datasources || 0;
                const totalReferences = data.total_references || 0;

                document.getElementById('pool-total-datasources').textContent = formatNumber(totalDatasources);
                document.getElementById('pool-total-references').textContent = formatNumber(totalReferences);

                const efficiency = totalReferences > 0 ?
                    (((totalReferences - totalDatasources) / totalReferences) * 100) : 0;
                document.getElementById('pool-efficiency').textContent = formatNumber(Math.max(0, efficiency), 1);

                const connectionsSaved = Math.max(0, totalReferences - totalDatasources);
                const memorySavedMB = connectionsSaved * 5;
                document.getElementById('pool-memory-saved').textContent =
                    memorySavedMB >= 1024 ?
                        `${formatNumber(memorySavedMB / 1024, 2)} GB` :
                        `${formatNumber(memorySavedMB)} MB`;

                if (data.datasource_keys && data.reference_counts) {
                    const html = data.datasource_keys.map(key => {
                        const refCount = data.reference_counts[key] || 0;

                        const parts = key.split(':');
                        const dsType = parts[0] || 'unknown';
                        const connInfo = parts.slice(1).join(':') || 'default';

                        let badgeClass = 'badge bg-slate-500/15 text-slate-200 border-slate-500/30';
                        let statusText = 'Single use';
                        let statusClass = 'text-slate-400';

                        if (refCount >= 5) {
                            badgeClass = 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/30';
                            statusText = 'High reuse';
                            statusClass = 'text-emerald-300';
                        } else if (refCount >= 3) {
                            badgeClass = 'badge bg-cyan-400/15 text-cyan-200 border-cyan-400/30';
                            statusText = 'Good reuse';
                            statusClass = 'text-cyan-300';
                        } else if (refCount === 2) {
                            badgeClass = 'badge bg-amber-400/15 text-amber-200 border-amber-400/30';
                            statusText = 'Shared';
                            statusClass = 'text-amber-300';
                        }

                        return `
                            <div class="adapter-card">
                                <div class="flex-1">
                                    <div class="flex items-center gap-2 mb-1">
                                        <p class="text-sm font-semibold text-slate-100">${escapeHtml(dsType)}</p>
                                        <span class="${badgeClass}">${refCount} ref${refCount !== 1 ? 's' : ''}</span>
                                    </div>
                                    <p class="text-xs text-slate-400 font-mono truncate">${escapeHtml(connInfo)}</p>
                                </div>
                                <div class="text-right">
                                    <p class="text-xs ${statusClass} font-medium">${statusText}</p>
                                </div>
                            </div>
                        `;
                    }).join('');
                    container.innerHTML = html;
                } else {
                    container.innerHTML = '<p class="text-sm text-slate-400">No datasource details available</p>';
                }
            } else {
                section.classList.add('hidden');
            }
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/metrics`;

            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                const indicator = document.getElementById('status-indicator');
                indicator.className = 'status-dot bg-emerald-400/80 pulse';
                indicator.setAttribute('aria-label', 'Connection active');
                document.getElementById('status-text').textContent = 'Connected';
                clearInterval(reconnectInterval);
                announce('Dashboard connected. Live telemetry resumed.');
            };

            ws.onmessage = (event) => {
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                    announce('Received invalid telemetry data. Some metrics may be stale.');
                    return;
                }

                updateMetrics(data.metrics);

                if (data.adapters) {
                    updateAdapterStatus({ adapters: data.adapters });
                } else {
                    updateAdapterStatus({ adapters: {} });
                }

                if (data.thread_pools) {
                    updateThreadPools(data.thread_pools);
                }

                if (data.datasource_pool) {
                    updateDatasourcePool(data.datasource_pool);
                }

                if (data.redis_health) {
                    updateRedisHealth(data.redis_health);
                }

                if (data.pipeline_steps) {
                    updatePipelineSteps(data.pipeline_steps, data.pipeline_summary);
                }

                if (data.connections) {
                    updateConnections(data.connections);
                }
            };

            ws.onclose = () => {
                const indicator = document.getElementById('status-indicator');
                indicator.className = 'status-dot bg-rose-500/80';
                indicator.setAttribute('aria-label', 'Connection lost');
                document.getElementById('status-text').textContent = 'Reconnecting...';
                announce('Connection lost. Attempting to reconnect every 5 seconds.');

                clearInterval(reconnectInterval);
                let attempt = 0;
                reconnectInterval = setInterval(() => {
                    attempt++;
                    document.getElementById('status-text').textContent = `Reconnecting... (${attempt})`;
                    connectWebSocket();
                }, 5000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                announce('Telemetry connection error. Data may be stale.');
            };
        }

        connectWebSocket();

        window.addEventListener('beforeunload', () => {
            if (ws) {
                ws.close();
            }
            clearInterval(reconnectInterval);
        });
