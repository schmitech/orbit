        // WebSocket connection
        let ws = null;
        let reconnectInterval = null;

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

        function updateMetrics(data) {
            const cpuPercent = clampPercentage(data.system.cpu_percent);
            const memoryPercent = clampPercentage(data.system.memory_percent);
            const errorPercent = clampPercentage(data.requests.error_rate);

            document.getElementById('cpu-usage').textContent = formatNumber(cpuPercent, 1);
            document.getElementById('cpu-usage-label').textContent = formatNumber(cpuPercent, 1) + '%';
            const cpuBar = document.getElementById('cpu-usage-bar');
            if (cpuBar) {
                cpuBar.style.width = cpuPercent.toFixed(1) + '%';
            }

            document.getElementById('memory-usage').textContent = formatNumber(data.system.memory_gb, 2);
            document.getElementById('memory-percent').textContent = formatNumber(memoryPercent, 1);
            const memoryBar = document.getElementById('memory-usage-bar');
            if (memoryBar) {
                memoryBar.style.width = memoryPercent.toFixed(1) + '%';
            }
            const memoryHealth = document.getElementById('memory-health');
            if (memoryHealth) {
                if (memoryPercent >= 85) {
                    memoryHealth.textContent = 'Critical';
                    memoryHealth.className = 'text-sm font-semibold text-rose-300';
                } else if (memoryPercent >= 70) {
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

            document.getElementById('error-rate').textContent = formatNumber(errorPercent, 2);

            const reliabilityStatusEl = document.getElementById('reliability-status');
            let reliabilityStatus = 'Nominal';
            let reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300';
            let reliabilityBarClass = 'bg-emerald-400/80';

            if (errorPercent >= 5) {
                reliabilityStatus = 'Critical';
                reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-rose-300';
                reliabilityBarClass = 'bg-rose-500/85';
            } else if (errorPercent >= 1) {
                reliabilityStatus = 'Degraded';
                reliabilityStatusClass = 'text-sm font-semibold uppercase tracking-[0.18em] text-amber-300';
                reliabilityBarClass = 'bg-amber-400/80';
            }

            if (reliabilityStatusEl) {
                reliabilityStatusEl.textContent = reliabilityStatus;
                reliabilityStatusEl.className = reliabilityStatusClass;
            }

            const errorBar = document.getElementById('error-rate-bar');
            if (errorBar) {
                errorBar.className = `progress-bar ${reliabilityBarClass}`;
                errorBar.style.width = errorPercent.toFixed(2) + '%';
            }
            document.getElementById('uptime').textContent = data.system.uptime;

            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

            if (data.time_series && data.time_series.timestamps.length > 0) {
                const labels = data.time_series.timestamps.map(t =>
                    new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                );
                const maxPoints = 30;
                const startIdx = Math.max(0, labels.length - maxPoints);
                const trimmedLabels = labels.slice(startIdx);

                updateChartWithActiveTooltip(systemChart, trimmedLabels, [
                    data.time_series.cpu.slice(startIdx),
                    data.time_series.memory.slice(startIdx)
                ]);

                updateChartWithActiveTooltip(requestChart, trimmedLabels, [
                    data.time_series.requests_per_second.slice(startIdx),
                    data.time_series.error_rate.slice(startIdx)
                ]);

                updateChartWithActiveTooltip(responseChart, trimmedLabels, [
                    data.time_series.response_time.slice(startIdx)
                ]);
            }
        }

        function updateAdapterStatus(data) {
            const container = document.getElementById('adapter-status');
            const containerDiv = document.getElementById('adapter-status-container');
            const chartsGrid = document.getElementById('charts-grid');

            if (data.adapters && Object.keys(data.adapters).length > 0) {
                containerDiv.classList.remove('hidden');
                chartsGrid.className = 'grid grid-cols-1 gap-6 xl:grid-cols-2';

                const stateStyles = {
                    closed: 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/30',
                    open: 'badge bg-rose-500/15 text-rose-200 border-rose-500/30',
                    half_open: 'badge bg-amber-400/15 text-amber-200 border-amber-400/30'
                };

                const html = Object.entries(data.adapters).map(([name, status]) => {
                    const state = (status.state || 'unknown').toLowerCase();
                    const badgeClass = stateStyles[state] || 'badge bg-slate-500/15 text-slate-200 border-slate-500/30';
                    const failures = status.failure_count || 0;

                    return `
                        <div class="adapter-card">
                            <div>
                                <p class="text-sm font-semibold text-slate-100">${name}</p>
                                <p class="text-xs text-slate-400">Failures: ${failures}</p>
                            </div>
                            <span class="${badgeClass}">${state.replace('_', ' ')}</span>
                        </div>
                    `;
                }).join('');
                container.innerHTML = html;
            } else {
                containerDiv.classList.add('hidden');
                chartsGrid.className = 'grid grid-cols-1 gap-6 xl:grid-cols-3';
                container.innerHTML = '<p class="text-sm text-slate-400">No adapter telemetry available</p>';
            }
        }

        function updateThreadPools(data) {
            const container = document.getElementById('thread-pools');
            if (data.pools && Object.keys(data.pools).length > 0) {
                const html = Object.entries(data.pools).map(([name, pool]) => {
                    const utilization = pool.max_workers > 0 ?
                        ((pool.active_threads / pool.max_workers) * 100) : 0;
                    const clampedUtil = clampPercentage(utilization);

                    // Determine if pool is idle
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
                                <h3 class="text-sm font-semibold text-slate-100">${name}</h3>
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

        function updateDatasourcePool(data) {
            const section = document.getElementById('datasource-pool-section');
            const container = document.getElementById('datasource-connections');

            if (data && data.total_cached_datasources > 0) {
                // Show the section
                section.classList.remove('hidden');

                // Update summary metrics
                const totalDatasources = data.total_cached_datasources || 0;
                const totalReferences = data.total_references || 0;

                document.getElementById('pool-total-datasources').textContent = formatNumber(totalDatasources);
                document.getElementById('pool-total-references').textContent = formatNumber(totalReferences);

                // Calculate pooling efficiency (what % of connections are saved)
                // If we have 5 references but only 2 datasources, we saved 3 connections = 60% efficiency
                const efficiency = totalReferences > 0 ?
                    (((totalReferences - totalDatasources) / totalReferences) * 100) : 0;
                document.getElementById('pool-efficiency').textContent = formatNumber(Math.max(0, efficiency), 1);

                // Estimate memory savings (rough estimate: 5MB per connection saved)
                const connectionsSaved = Math.max(0, totalReferences - totalDatasources);
                const memorySavedMB = connectionsSaved * 5;
                document.getElementById('pool-memory-saved').textContent =
                    memorySavedMB >= 1024 ?
                        `${formatNumber(memorySavedMB / 1024, 2)} GB` :
                        `${formatNumber(memorySavedMB)} MB`;

                // Build the datasource list
                if (data.datasource_keys && data.reference_counts) {
                    const html = data.datasource_keys.map(key => {
                        const refCount = data.reference_counts[key] || 0;

                        // Extract datasource type and connection info
                        const parts = key.split(':');
                        const dsType = parts[0] || 'unknown';
                        const connInfo = parts.slice(1).join(':') || 'default';

                        // Color based on reference count (higher = better pooling)
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
                                        <p class="text-sm font-semibold text-slate-100">${dsType}</p>
                                        <span class="${badgeClass}">${refCount} ref${refCount !== 1 ? 's' : ''}</span>
                                    </div>
                                    <p class="text-xs text-slate-400 font-mono truncate">${connInfo}</p>
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
                // Hide the section if no datasources
                section.classList.add('hidden');
            }
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/metrics`;

            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                document.getElementById('status-indicator').className = 'status-dot bg-emerald-400/80 pulse';
                document.getElementById('status-text').textContent = 'Connected';
                clearInterval(reconnectInterval);
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateMetrics(data.metrics);

                // Always show adapter status
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
            };

            ws.onclose = () => {
                document.getElementById('status-indicator').className = 'status-dot bg-rose-500/80';
                document.getElementById('status-text').textContent = 'Disconnected';

                clearInterval(reconnectInterval);
                reconnectInterval = setInterval(() => {
                    connectWebSocket();
                }, 5000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        connectWebSocket();

        window.addEventListener('beforeunload', () => {
            if (ws) {
                ws.close();
            }
            clearInterval(reconnectInterval);
        });
    