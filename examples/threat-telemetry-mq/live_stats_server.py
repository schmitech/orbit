#!/usr/bin/env python3
"""
Live stats server — real-time threat-analysis demo
=====================================================

A standalone read/write bridge that serves the dashboard's operational
metrics from **real sources** instead of presentation placeholders:

- Sensor status, detection counts, severity breakdown, and unresolved
  alerts come straight from threat_telemetry.db (the same database the
  ORBIT intent-SQL adapter queries).
- Queue depth and message rate come from RabbitMQ's management HTTP API
  (real `messages_ready`/`messages_unacknowledged` and delivery rate on
  `orbit.requests`) — not a random number generator.

This is not part of ORBIT itself — like the burst producer's status server
and the ingest consumer, it's a small demo-only bridge, since a browser can't
open a SQLite file or speak AMQP directly.

Requires: pip install flask (or just the stdlib http.server, used here to
avoid adding a new dependency) and the `requests` library for the RabbitMQ
management API call (already a transitive dependency of most Python
environments; falls back to reporting queue stats as unavailable if absent).

Example:
    python examples/threat-telemetry-mq/live_stats_server.py
"""

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent
    / "intent-templates" / "sql-intent-template" / "sqlite" / "threat-telemetry" / "threat_telemetry.db"
)

# Static display layout only (x/y percent position on the tactical map SVG).
# Sensor identity/status/detections are all real; this is the one piece of
# "where do I draw this on a 2D canvas" presentation math a real deployment
# would replace with an actual map projection of lat/lon.
SENSOR_LAYOUT = {
    "sen_001": {"label": "SEN-001", "x": 45, "y": 18},
    "sen_002": {"label": "SEN-002", "x": 78, "y": 43},
    "sen_003": {"label": "SEN-003", "x": 67, "y": 75},
    "sen_004": {"label": "SEN-004", "x": 21, "y": 39},
    "sen_005": {"label": "SEN-005", "x": 38, "y": 81},
    "sen_006": {"label": "SEN-006", "x": 64, "y": 29},
}


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_stats(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()

    sensors = []
    for row in cur.execute("SELECT sensor_id, name, type, location_name, status FROM sensors ORDER BY sensor_id"):
        layout = SENSOR_LAYOUT.get(row["sensor_id"], {"label": row["sensor_id"].upper(), "x": 50, "y": 50})
        sensors.append(
            {
                "sensor_id": row["sensor_id"],
                "name": row["name"],
                "type": row["type"],
                "location_name": row["location_name"],
                "status": row["status"],
                "label": layout["label"],
                "x": layout["x"],
                "y": layout["y"],
            }
        )
    sensors_online = sum(1 for s in sensors if s["status"] == "online")

    detections_last_hour = cur.execute(
        "SELECT COUNT(*) FROM detections WHERE detected_at >= datetime('now', '-1 hours')"
    ).fetchone()[0]

    severity_24h = {row["severity"]: row["count"] for row in cur.execute(
        """SELECT severity, COUNT(*) AS count FROM detections
           WHERE detected_at >= datetime('now', '-24 hours')
           GROUP BY severity"""
    )}
    total_24h = sum(severity_24h.values())
    distribution = {
        sev: {
            "count": severity_24h.get(sev, 0),
            "percent": round(severity_24h.get(sev, 0) / total_24h * 100) if total_24h else 0,
        }
        for sev in ("critical", "high", "medium", "low")
    }

    open_alerts = cur.execute("SELECT COUNT(*) FROM alerts WHERE status = 'open'").fetchone()[0]

    last_detection_at = cur.execute("SELECT MAX(detected_at) FROM detections").fetchone()[0]

    unresolved = []
    for row in cur.execute(
        """SELECT a.alert_id, a.status, a.raised_at, a.assigned_to,
                  d.sensor_id, d.object_type, d.severity, d.confidence, s.location_name
           FROM alerts a
           JOIN detections d ON d.detection_id = a.detection_id
           JOIN sensors s ON s.sensor_id = d.sensor_id
           WHERE a.status != 'resolved'
           ORDER BY CASE d.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    a.raised_at ASC
           LIMIT 8"""
    ):
        layout = SENSOR_LAYOUT.get(row["sensor_id"], {"x": 50, "y": 50})
        # Small deterministic offset so multiple alerts at the same sensor
        # don't render as a single overlapping marker on the map.
        jitter = (hash(row["alert_id"]) % 7) - 3
        unresolved.append(
            {
                "alert_id": row["alert_id"],
                "status": row["status"],
                "raised_at": row["raised_at"],
                "assigned_to": row["assigned_to"],
                "sensor_id": row["sensor_id"],
                "object_type": row["object_type"],
                "severity": row["severity"],
                "confidence": row["confidence"],
                "location_name": row["location_name"],
                "x": layout["x"] + jitter,
                "y": layout["y"] + jitter,
            }
        )

    return {
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" "),
        "last_detection_at": last_detection_at,
        "sensors": sensors,
        "sensors_online": sensors_online,
        "sensors_total": len(sensors),
        "detections_last_hour": detections_last_hour,
        "open_alerts": open_alerts,
        "distribution_24h": distribution,
        "distribution_total_24h": total_24h,
        "unresolved_alerts": unresolved,
    }


def fetch_queue_stats(rabbitmq_api: str, rabbitmq_user: str, rabbitmq_password: str, queue: str) -> dict:
    try:
        import requests
    except ImportError:
        return {"available": False, "reason": "requests library not installed"}

    try:
        res = requests.get(
            f"{rabbitmq_api.rstrip('/')}/api/queues/%2f/{queue}",
            auth=(rabbitmq_user, rabbitmq_password),
            timeout=2,
        )
        res.raise_for_status()
        body = res.json()
    except Exception as exc:  # noqa: BLE001 - report any failure to the dashboard, don't crash the server
        return {"available": False, "reason": str(exc)}

    stats = body.get("message_stats", {})
    return {
        "available": True,
        "queue": queue,
        "messages_ready": body.get("messages_ready", 0),
        "messages_unacknowledged": body.get("messages_unacknowledged", 0),
        "consumers": body.get("consumers", 0),
        "deliver_rate_per_sec": stats.get("deliver_get_details", {}).get("rate", 0.0),
        "publish_rate_per_sec": stats.get("publish_details", {}).get("rate", 0.0),
    }


def acknowledge_alert(conn: sqlite3.Connection, alert_id: str, operator: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "UPDATE alerts SET status = 'acknowledged', assigned_to = COALESCE(assigned_to, ?) WHERE alert_id = ? AND status = 'open'",
        (operator, alert_id),
    )
    conn.commit()
    return cur.rowcount > 0


def make_handler(conn: sqlite3.Connection, args):
    class StatsHandler(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, status: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/")
            if path != "/stats":
                self._json(404, {"error": "not found"})
                return
            payload = fetch_stats(conn)
            payload["queue"] = fetch_queue_stats(args.rabbitmq_api, args.rabbitmq_user, args.rabbitmq_password, args.queue)
            self._json(200, payload)

        def do_POST(self):
            parsed = urlparse(self.path)
            parts = parsed.path.rstrip("/").split("/")
            if len(parts) == 4 and parts[1] == "alerts" and parts[3] == "acknowledge":
                alert_id = parts[2]
                ok = acknowledge_alert(conn, alert_id, args.operator_name)
                if ok:
                    self._json(200, {"acknowledged": alert_id})
                else:
                    self._json(404, {"error": f"alert {alert_id} not found or not open"})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, log_format, *fmt_args):
            pass

    return StatsHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to threat_telemetry.db")
    parser.add_argument("--port", type=int, default=8790, help="Port to serve /stats on")
    parser.add_argument("--queue", default="orbit.requests", help="RabbitMQ queue to report depth/rate for")
    parser.add_argument("--rabbitmq-api", default="http://localhost:15672", help="RabbitMQ management API base URL")
    parser.add_argument("--rabbitmq-user", default="guest", help="RabbitMQ management API username")
    parser.add_argument("--rabbitmq-password", default="guest", help="RabbitMQ management API password")
    parser.add_argument("--operator-name", default="Dashboard Operator", help="Assignee recorded on acknowledge")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(
            f"Database not found at {db_path}. Generate it first:\n"
            "    cd examples/intent-templates/sql-intent-template/sqlite/threat-telemetry\n"
            "    python3 generate_threat_telemetry_data.py --force",
            file=sys.stderr,
        )
        return 2

    conn = get_conn(str(db_path))
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(conn, args))
    print(f"Live stats server: http://localhost:{args.port}/stats -> {db_path}")
    print(f"Queue stats from: {args.rabbitmq_api} ({args.queue})")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
