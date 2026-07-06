"""
Tests for MetricsService dashboard aggregation.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.metrics_service import MetricsService


def test_dashboard_total_requests_is_lifetime_count():
    service = MetricsService({"monitoring": {"enabled": True}})

    for _ in range(1005):
        service.record_request("GET", "/test", 200, 0.01)

    dashboard_metrics = service.get_dashboard_metrics()

    assert len(service.request_timestamps) == 1000
    assert dashboard_metrics["requests"]["total"] == 1005


def test_dashboard_metrics_excludes_unmatched_route_label():
    service = MetricsService({"monitoring": {"enabled": True}})

    service.record_request("GET", "__unmatched_route__", 404, 0.01)
    service.record_request("GET", "/v1/chat/completions", 200, 0.02)

    dashboard_metrics = service.get_dashboard_metrics()

    assert dashboard_metrics["requests"]["total"] == 1
    assert dashboard_metrics["endpoint_stats"] == [
        {
            "endpoint": "/v1/chat/completions",
            "method": "GET",
            "total_requests": 1,
            "avg_latency_ms": 20.0,
            "error_rate": 0.0,
        }
    ]
