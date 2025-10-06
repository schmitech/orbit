"""
Dashboard Routes for Real-time Monitoring

Provides web-based dashboard and metrics endpoints.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pathlib import Path

logger = logging.getLogger(__name__)


def get_metrics_service(request: Request):
    """Get metrics service from app state"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service:
        raise HTTPException(status_code=503, detail="Metrics service not available")
    if not metrics_service.is_enabled():
        raise HTTPException(status_code=503, detail="Monitoring is disabled")
    return metrics_service

def get_metrics_service_for_dashboard(request: Request):
    """Get metrics service for dashboard endpoints"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service or not metrics_service.is_dashboard_enabled():
        raise HTTPException(status_code=503, detail="Dashboard is disabled")
    return metrics_service

def get_metrics_service_for_prometheus(request: Request):
    """Get metrics service for Prometheus endpoints"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service or not metrics_service.is_prometheus_enabled():
        raise HTTPException(status_code=503, detail="Prometheus metrics are disabled")
    return metrics_service


def get_adapter_manager(request: Request):
    """Get adapter manager from app state"""
    manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request.app.state, 'adapter_manager', None)
    return manager


def create_dashboard_router() -> APIRouter:
    """Create dashboard router with monitoring endpoints"""
    
    router = APIRouter(tags=["dashboard"])
    
    # Store active WebSocket connections
    active_connections: list[WebSocket] = []
    
    @router.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard(metrics_service = Depends(get_metrics_service_for_dashboard)):
        """Serve the monitoring dashboard"""
        dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORBIT Operations Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {
            color-scheme: dark;
        }
        body {
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        .surface-card {
            background: rgba(15, 23, 42, 0.88);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 18px;
            box-shadow: 0 25px 65px -45px rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(12px);
            transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }
        .surface-card:hover {
            transform: translateY(-2px);
            border-color: rgba(148, 163, 184, 0.28);
            box-shadow: 0 25px 70px -45px rgba(56, 189, 248, 0.25);
        }
        .metric-card .metric-value {
            font-size: 2.75rem;
            font-weight: 600;
            letter-spacing: -0.04em;
        }
        .metric-card .metric-unit {
            font-size: 1.25rem;
            margin-left: 0.25rem;
            color: rgba(226, 232, 240, 0.6);
        }
        .metric-label {
            font-size: 0.75rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: rgba(148, 163, 184, 0.75);
            font-weight: 500;
        }
        .section-title {
            font-size: 1.25rem;
            font-weight: 600;
        }
        .section-subtitle {
            font-size: 0.85rem;
            color: rgba(148, 163, 184, 0.75);
        }
        .status-dot {
            width: 0.75rem;
            height: 0.75rem;
            border-radius: 999px;
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.12);
        }
        .progress-track {
            height: 0.375rem;
            background: rgba(148, 163, 184, 0.12);
            border-radius: 999px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            border-radius: 999px;
            transition: width 0.35s ease;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.75rem;
            font-weight: 500;
            padding: 0.35rem 0.6rem;
            border-radius: 999px;
            border: 1px solid transparent;
            text-transform: capitalize;
        }
        .adapter-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.25rem;
            padding: 0.85rem 1rem;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.12);
            background: rgba(15, 23, 42, 0.7);
            transition: border-color 0.2s ease, transform 0.2s ease;
        }
        .adapter-card:hover {
            border-color: rgba(148, 163, 184, 0.28);
            transform: translateX(2px);
        }
        .pulse {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.55; }
            100% { opacity: 1; }
        }
        @media (max-width: 640px) {
            .metric-card .metric-value {
                font-size: 2.1rem;
            }
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 antialiased">
    <div class="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-br from-sky-500/10 via-transparent to-indigo-500/10 blur-3xl -z-10"></div>
    <div class="max-w-7xl mx-auto px-6 py-10 space-y-10">
        <header class="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div class="space-y-3">
                <p class="text-xs font-medium tracking-[0.32em] text-slate-400 uppercase">Operational Insights</p>
                <h1 class="text-3xl md:text-4xl font-semibold text-slate-100">ORBIT Operations Console</h1>
                <p class="text-sm text-slate-400 max-w-2xl">Real-time service health, throughput, and reliability telemetry.</p>
            </div>
            <div class="flex items-center gap-5">
                <div class="flex items-center gap-3 rounded-full border border-slate-800 bg-slate-900/60 px-5 py-3 shadow-lg shadow-slate-900/30">
                    <span id="status-indicator" class="status-dot bg-emerald-400/80 pulse"></span>
                    <div class="flex flex-col">
                        <span id="status-text" class="text-sm font-medium text-slate-100">Connected</span>
                        <span class="text-xs text-slate-400">WebSocket Stream</span>
                    </div>
                </div>
                <div class="text-xs text-slate-500 text-right">
                    Last Update
                    <div id="last-update" class="text-sm font-semibold text-slate-200">Never</div>
                </div>
            </div>
        </header>

        <section class="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            <article class="surface-card metric-card p-6">
                <div class="flex items-start justify-between">
                    <div class="space-y-2">
                        <span class="metric-label">CPU Usage</span>
                        <div class="metric-value"><span id="cpu-usage">0</span><span class="metric-unit">%</span></div>
                    </div>
                    <svg class="w-10 h-10 text-sky-400/80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"/>
                    </svg>
                </div>
                <div class="mt-6 space-y-2">
                    <div class="flex items-center justify-between text-xs text-slate-400">
                        <span>Utilization</span>
                        <span id="cpu-usage-label" class="text-slate-200 font-medium">0%</span>
                    </div>
                    <div class="progress-track">
                        <div id="cpu-usage-bar" class="progress-bar bg-sky-500/80" style="width: 0%;"></div>
                    </div>
                </div>
            </article>

            <article class="surface-card metric-card p-6">
                <div class="flex items-start justify-between">
                    <div class="space-y-2">
                        <span class="metric-label">Memory Usage</span>
                        <div class="metric-value"><span id="memory-usage">0</span><span class="metric-unit">GB</span></div>
                    </div>
                    <svg class="w-10 h-10 text-emerald-400/80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 17v1a1 1 0 001 1h4a1 1 0 001-1v-1m3-2V10a2 2 0 00-2-2H8a2 2 0 00-2 2v5m3-2h6"/>
                    </svg>
                </div>
                <div class="mt-6 space-y-4">
                    <div class="progress-track">
                        <div id="memory-usage-bar" class="progress-bar bg-emerald-400/80" style="width: 0%;"></div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 text-xs text-slate-400">
                        <div>
                            <p class="uppercase tracking-[0.15em]">Utilization</p>
                            <p class="text-sm font-semibold text-slate-200"><span id="memory-percent">0</span>%</p>
                        </div>
                        <div>
                            <p class="uppercase tracking-[0.15em]">Status</p>
                            <p id="memory-health" class="text-sm font-semibold text-emerald-300">Stable</p>
                        </div>
                    </div>
                </div>
            </article>

            <article class="surface-card metric-card p-6">
                <div class="flex items-start justify-between">
                    <div class="space-y-2">
                        <span class="metric-label">Throughput</span>
                        <div class="metric-value"><span id="requests-per-second">0</span><span class="metric-unit">rps</span></div>
                    </div>
                    <svg class="w-10 h-10 text-amber-300/90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                    </svg>
                </div>
                <div class="mt-6 space-y-3 text-xs text-slate-400">
                    <div class="flex items-center justify-between">
                        <span>Total Requests</span>
                        <span id="total-requests" class="text-sm text-slate-200 font-medium">0</span>
                    </div>
                    <div class="flex items-center justify-between">
                        <span>Error Rate</span>
                        <span id="requests-error-rate" class="text-sm text-slate-200 font-medium">0%</span>
                    </div>
                </div>
            </article>

            <article class="surface-card metric-card p-6">
                <div class="flex items-start justify-between">
                    <div class="space-y-2">
                        <span class="metric-label">Reliability</span>
                        <div class="metric-value"><span id="error-rate">0</span><span class="metric-unit">%</span></div>
                    </div>
                    <svg class="w-10 h-10 text-rose-300/80" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                </div>
                <div class="mt-6 space-y-2">
                    <div class="progress-track">
                        <div id="error-rate-bar" class="progress-bar bg-rose-400/80" style="width: 0%;"></div>
                    </div>
                    <div class="flex items-center justify-between text-xs text-slate-400">
                        <span>Uptime</span>
                        <span id="uptime" class="text-sm font-medium text-slate-200">0m</span>
                    </div>
                </div>
            </article>
        </section>

        <section>
            <div class="flex flex-col gap-2 mb-6">
                <h2 class="section-title text-slate-100">Live Signals</h2>
                <p class="section-subtitle">System resources, throughput, and latency trends update as telemetry streams in.</p>
            </div>
            <div id="charts-grid" class="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <article class="surface-card chart-card p-6 h-[320px]">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-lg font-semibold text-slate-100">System Resources</h3>
                        <span class="badge bg-sky-500/10 text-sky-300 border-sky-500/30">CPU &amp; Memory</span>
                    </div>
                    <div class="h-[240px]">
                        <canvas id="system-chart"></canvas>
                    </div>
                </article>
                <article class="surface-card chart-card p-6 h-[320px]">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-lg font-semibold text-slate-100">Request Metrics</h3>
                        <span class="badge bg-amber-400/10 text-amber-200 border-amber-400/30">Throughput</span>
                    </div>
                    <div class="h-[240px]">
                        <canvas id="request-chart"></canvas>
                    </div>
                </article>
                <article class="surface-card chart-card p-6 h-[320px]">
                    <div class="flex items-center justify-between mb-4">
                        <h3 class="text-lg font-semibold text-slate-100">Response Time (ms)</h3>
                        <span class="badge bg-indigo-400/10 text-indigo-200 border-indigo-400/30">Latency</span>
                    </div>
                    <div class="h-[240px]">
                        <canvas id="response-chart"></canvas>
                    </div>
                </article>
                <article id="adapter-status-container" class="surface-card p-6 space-y-4 hidden">
                    <div class="flex items-center justify-between">
                        <div>
                            <h3 class="text-lg font-semibold text-slate-100">Adapter Health</h3>
                            <p class="text-sm text-slate-400">Circuit breaker states and failure counters.</p>
                        </div>
                        <span class="badge bg-emerald-400/10 text-emerald-200 border-emerald-400/30">Resilience</span>
                    </div>
                    <div id="adapter-status" class="space-y-3">
                        <p class="text-sm text-slate-400">Loading adapter status...</p>
                    </div>
                </article>
            </div>
        </section>

        <section class="surface-card p-6">
            <div class="flex flex-col gap-2 mb-6">
                <h2 class="section-title text-slate-100">Thread Pool Utilization</h2>
                <p class="section-subtitle">Monitor executor saturation to stay ahead of queue buildup and latency drift.</p>
            </div>
            <div id="thread-pools" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <p class="text-sm text-slate-400">Loading thread pool status...</p>
            </div>
        </section>
    </div>

    <script>
        // WebSocket connection
        let ws = null;
        let reconnectInterval = null;

        // Chart configurations
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
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
                    pointRadius: 0
                }, {
                    label: 'Memory %',
                    data: [],
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0
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
                    pointRadius: 0
                }, {
                    label: 'Error Rate %',
                    data: [],
                    borderColor: 'rgb(244, 114, 182)',
                    backgroundColor: 'rgba(244, 114, 182, 0.12)',
                    tension: 0.25,
                    fill: true,
                    pointRadius: 0
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
                    pointRadius: 0
                }]
            },
            options: chartOptions
        });

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
            const errorBar = document.getElementById('error-rate-bar');
            if (errorBar) {
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

                systemChart.data.labels = labels.slice(startIdx);
                systemChart.data.datasets[0].data = data.time_series.cpu.slice(startIdx);
                systemChart.data.datasets[1].data = data.time_series.memory.slice(startIdx);
                systemChart.update('none');

                requestChart.data.labels = labels.slice(startIdx);
                requestChart.data.datasets[0].data = data.time_series.requests_per_second.slice(startIdx);
                requestChart.data.datasets[1].data = data.time_series.error_rate.slice(startIdx);
                requestChart.update('none');

                responseChart.data.labels = labels.slice(startIdx);
                responseChart.data.datasets[0].data = data.time_series.response_time.slice(startIdx);
                responseChart.update('none');
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

                    let barColor = 'bg-emerald-400/80';
                    let badgeClass = 'badge bg-emerald-400/15 text-emerald-200 border-emerald-400/25';
                    if (clampedUtil >= 90) {
                        barColor = 'bg-rose-500/80';
                        badgeClass = 'badge bg-rose-500/15 text-rose-200 border-rose-500/30';
                    } else if (clampedUtil >= 75) {
                        barColor = 'bg-amber-400/80';
                        badgeClass = 'badge bg-amber-400/15 text-amber-200 border-amber-400/30';
                    }

                    return `
                        <div class="surface-card p-5 space-y-4">
                            <div class="flex items-center justify-between">
                                <h3 class="text-sm font-semibold text-slate-100">${name}</h3>
                                <span class="${badgeClass}">${clampedUtil.toFixed(1)}%</span>
                            </div>
                            <div class="space-y-2 text-xs text-slate-400">
                                <div class="flex items-center justify-between">
                                    <span>Active Threads</span>
                                    <span class="text-sm text-slate-200 font-medium">${pool.active_threads}</span>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Max Workers</span>
                                    <span class="text-sm text-slate-200 font-medium">${pool.max_workers}</span>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Queued Tasks</span>
                                    <span class="text-sm text-slate-200 font-medium">${pool.queued_tasks}</span>
                                </div>
                            </div>
                            <div class="progress-track h-1.5">
                                <div class="progress-bar ${barColor}" style="width: ${clampedUtil.toFixed(1)}%;"></div>
                            </div>
                        </div>
                    `;
                }).join('');
                container.innerHTML = html;
            } else {
                container.innerHTML = '<p class="text-sm text-slate-400">No thread pool data available</p>';
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

                if (data.server_mode && data.server_mode.inference_only) {
                    document.getElementById('adapter-status-container').classList.add('hidden');
                    document.getElementById('charts-grid').className = 'grid grid-cols-1 gap-6 xl:grid-cols-3';
                } else if (data.adapters) {
                    updateAdapterStatus({ adapters: data.adapters });
                } else {
                    updateAdapterStatus({ adapters: {} });
                }

                if (data.thread_pools) {
                    updateThreadPools(data.thread_pools);
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
    </script>
</body>
</html>

        """
        return dashboard_html
    
    @router.websocket("/ws/metrics")
    async def websocket_metrics(websocket: WebSocket):
        """WebSocket endpoint for real-time metrics streaming"""
        await websocket.accept()
        active_connections.append(websocket)
        # Track websocket connections metric if available
        try:
            ms = getattr(websocket.app.state, 'metrics_service', None)
            if ms and getattr(ms, 'websocket_connections', None):
                ms.websocket_connections.inc()
        except Exception:
            pass
        
        try:
            # Get services from app state
            metrics_service = getattr(websocket.app.state, 'metrics_service', None)
            adapter_manager = get_adapter_manager(websocket)
            thread_pool_manager = getattr(websocket.app.state, 'thread_pool_manager', None)
            
            # Helper to extract stats from a ThreadPoolExecutor
            def _stats_from_executor(executor) -> Dict[str, Any]:
                try:
                    max_workers = getattr(executor, '_max_workers', None)
                    threads = getattr(executor, '_threads', None)
                    work_q = getattr(executor, '_work_queue', None)
                    active_threads = len(threads) if threads is not None else 0
                    queued = work_q.qsize() if hasattr(work_q, 'qsize') else 0
                    return {
                        'max_workers': int(max_workers) if isinstance(max_workers, int) else 0,
                        'active_threads': int(active_threads),
                        'queued_tasks': int(queued),
                    }
                except Exception:
                    return {'max_workers': 0, 'active_threads': 0, 'queued_tasks': 0}

            while True:
                data: Dict[str, Any] = {}
                
                # Get metrics data
                if metrics_service:
                    data['metrics'] = metrics_service.get_dashboard_metrics()
                
                # Get adapter health status - only if not in inference_only mode
                config = getattr(websocket.app.state, 'config', {})
                inference_only = config.get('general', {}).get('inference_only', False)
                
                if not inference_only and adapter_manager:
                    try:
                        if hasattr(adapter_manager, 'get_health_status'):
                            health = adapter_manager.get_health_status()
                            adapters = health.get('circuit_breakers', {})
                            # Only include adapter data if we actually have adapters
                            if adapters:
                                data['adapters'] = adapters
                            else:
                                # Set empty adapters to trigger hiding the section
                                data['adapters'] = {}
                        elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                            # Try both methods for backward compatibility
                            if hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_status'):
                                adapters = adapter_manager.parallel_executor.get_circuit_breaker_status()
                                if adapters:
                                    data['adapters'] = adapters
                            elif hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_states'):
                                adapters = adapter_manager.parallel_executor.get_circuit_breaker_states()
                                if adapters:
                                    data['adapters'] = adapters
                        else:
                            data['adapters'] = {}
                    except Exception as e:
                        logger.debug(f"Error getting adapter status: {e}")
                        data['adapters'] = {}
                else:
                    # Explicitly set to empty if in inference_only mode or no adapter manager
                    data['adapters'] = {}
                
                # Get thread pool statistics
                # Always start with any central manager stats when available
                pools: Dict[str, Any] = {}
                if thread_pool_manager:
                    try:
                        pools.update(thread_pool_manager.get_pool_stats())
                        # Push thread pool stats into Prometheus gauges if available
                        if metrics_service and hasattr(metrics_service, 'update_thread_pool_metrics'):
                            try:
                                metrics_service.update_thread_pool_metrics(pools)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Error getting thread pool stats: {e}")
                # Add service-specific executors if present (parallel executor, dynamic manager)
                try:
                    if adapter_manager:
                        # Parallel executor pool
                        pe = getattr(adapter_manager, 'parallel_executor', None)
                        if pe and hasattr(pe, 'thread_pool') and pe.thread_pool:
                            pools['parallel_executor'] = _stats_from_executor(pe.thread_pool)
                        # Dynamic adapter manager initialization pool
                        base_mgr = getattr(adapter_manager, 'base_adapter_manager', None)
                        if base_mgr and hasattr(base_mgr, '_thread_pool') and base_mgr._thread_pool:
                            pools['adapter_init'] = _stats_from_executor(base_mgr._thread_pool)
                except Exception as e:
                    logger.debug(f"Error collecting service executor stats: {e}")
                if pools:
                    data['thread_pools'] = pools
                
                # Add server mode information for dashboard display
                data['server_mode'] = {
                    'inference_only': inference_only,
                    'adapters_available': bool(data.get('adapters'))
                }
                
                # Send data to client
                await websocket.send_json(data)
                
                # Wait before next update (use configured interval)
                metrics_service = getattr(websocket.app.state, 'metrics_service', None)
                update_interval = 5  # default
                if metrics_service:
                    update_interval = getattr(metrics_service, 'websocket_update_interval', 5)
                
                await asyncio.sleep(update_interval)
                
        except WebSocketDisconnect:
            active_connections.remove(websocket)
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if websocket in active_connections:
                active_connections.remove(websocket)
        finally:
            try:
                ms = getattr(websocket.app.state, 'metrics_service', None)
                if ms and getattr(ms, 'websocket_connections', None):
                    ms.websocket_connections.dec()
            except Exception:
                pass
    
    @router.get("/metrics")
    async def get_prometheus_metrics(metrics_service = Depends(get_metrics_service_for_prometheus)):
        """Prometheus metrics endpoint"""
        metrics_data = metrics_service.get_prometheus_metrics()
        return Response(content=metrics_data, media_type="text/plain")
    
    @router.get("/metrics/json")
    async def get_json_metrics(metrics_service = Depends(get_metrics_service_for_dashboard)):
        """JSON metrics endpoint for custom integrations"""
        return metrics_service.get_dashboard_metrics()
    
    return router
