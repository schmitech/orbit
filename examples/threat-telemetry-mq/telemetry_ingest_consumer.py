#!/usr/bin/env python3
"""
Sensor telemetry ingest consumer — real-time threat-analysis demo
===================================================================

A standalone consumer that persists incoming sensor-detection events into
threat_telemetry.db, so new detections published to the broker actually show
up in the data ORBIT's intent-SQL adapter queries — not just a burst of
read-only questions against a frozen snapshot.

This is intentionally separate from ORBIT's own message-queue worker
(`./bin/orbit.sh worker`), which only runs NL chat requests through the
inference pipeline and never writes application data. This consumer models
the other half of a real deployment: sensors/upstream systems publish raw
detection events to a queue, and a dedicated ingest service persists them —
after which ORBIT (chat, dashboard, or the MQ query-burst demo) can answer
questions about the newly arrived data.

Requires the messaging dependency profile (aio-pika):
    ./install/setup.sh --profile messaging

Example:
    python examples/threat-telemetry-mq/telemetry_ingest_consumer.py
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent
    / "intent-templates" / "sql-intent-template" / "sqlite" / "threat-telemetry" / "threat_telemetry.db"
)

REQUIRED_FIELDS = ["sensor_id", "object_type", "confidence", "severity", "lat", "lon"]
VALID_OBJECT_TYPES = {"aircraft", "vehicle", "person", "unknown"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def validate_event(event: dict) -> str | None:
    """Return an error message if the event is malformed, else None."""
    if not isinstance(event, dict):
        return "event is not a JSON object"
    for field in REQUIRED_FIELDS:
        if field not in event:
            return f"missing required field: {field}"
    if event["object_type"] not in VALID_OBJECT_TYPES:
        return f"invalid object_type: {event['object_type']!r}"
    if event["severity"] not in VALID_SEVERITIES:
        return f"invalid severity: {event['severity']!r}"
    return None


def persist_event(conn: sqlite3.Connection, event: dict) -> tuple[str, str | None]:
    """Insert a detection (and an alert if high/critical). Returns (detection_id, alert_id)."""
    detected_at = event.get("detected_at") or datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" ")
    detection_id = f"det_evt_{uuid.uuid4().hex[:10]}"

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO detections
           (detection_id, sensor_id, detected_at, object_type, confidence, severity, lat, lon, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            detection_id,
            event["sensor_id"],
            detected_at,
            event["object_type"],
            float(event["confidence"]),
            event["severity"],
            float(event["lat"]),
            float(event["lon"]),
            event.get("notes") or f"{event['object_type']} contact (live feed), confidence {event['confidence']}",
        ),
    )

    alert_id = None
    if event["severity"] in ("high", "critical"):
        alert_id = f"alr_evt_{uuid.uuid4().hex[:10]}"
        cur.execute(
            """INSERT INTO alerts (alert_id, detection_id, raised_at, status, assigned_to)
               VALUES (?, ?, ?, ?, ?)""",
            (alert_id, detection_id, detected_at, "open", None),
        )

    conn.commit()
    return detection_id, alert_id


async def run(args) -> int:
    try:
        import aio_pika
    except ImportError:
        print(
            "aio-pika is not installed. Install the messaging profile:\n"
            "    ./install/setup.sh --profile messaging",
            file=sys.stderr,
        )
        return 2

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(
            f"Database not found at {db_path}. Generate it first:\n"
            "    cd examples/intent-templates/sql-intent-template/sqlite/threat-telemetry\n"
            "    python3 generate_threat_telemetry_data.py --force",
            file=sys.stderr,
        )
        return 2

    conn = sqlite3.connect(db_path, check_same_thread=False)

    conn_mq = await aio_pika.connect_robust(args.url)
    try:
        channel = await conn_mq.channel()
        await channel.set_qos(prefetch_count=args.prefetch)

        dlq = await channel.declare_queue(args.dead_letter_queue, durable=True)
        events_queue = await channel.declare_queue(
            args.events_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": args.dead_letter_queue},
        )

        print(f"Ingest consumer connected. Consuming '{args.events_queue}' -> {db_path}")
        print(f"Malformed events dead-letter to '{args.dead_letter_queue}' ({dlq.name}).")
        print("Press Ctrl+C to stop.\n")

        async with events_queue.iterator() as it:
            async for message in it:
                try:
                    event = json.loads(message.body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    print(f"[dead-letter] unparseable message body: {message.body[:200]!r}")
                    await message.reject(requeue=False)
                    continue

                error = validate_event(event)
                if error:
                    print(f"[dead-letter] {error}: {event!r}")
                    await message.reject(requeue=False)
                    continue

                detection_id, alert_id = persist_event(conn, event)
                async with message.process():
                    pass

                suffix = f", raised alert {alert_id}" if alert_id else ""
                print(
                    f"[persisted] {detection_id} sensor={event['sensor_id']} "
                    f"object={event['object_type']} severity={event['severity']}{suffix}"
                )
    finally:
        conn.close()
        await conn_mq.close()

    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="Persist sensor telemetry events from the broker into threat_telemetry.db")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to threat_telemetry.db")
    parser.add_argument(
        "--url",
        default="amqp://guest:guest@localhost:5672/",
        help="AMQP broker URL (or set $MESSAGING_RABBITMQ_URL and pass it explicitly)",
    )
    parser.add_argument("--events-queue", default="orbit.telemetry.events", help="Queue to consume raw detection events from")
    parser.add_argument("--dead-letter-queue", default="orbit.telemetry.dlq", help="Queue for malformed events")
    parser.add_argument("--prefetch", type=int, default=8, help="Max unacked messages in flight")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
