#!/usr/bin/env python3
"""Generate threat_telemetry.db — sensors, detections, and alerts for the
real-time threat-analysis demo.
"""

import argparse
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SENSORS = [
    ("sen_001", "North Perimeter Radar", "radar", "North Perimeter", 38.9012, -77.0653),
    ("sen_002", "East Gate Camera Array", "perimeter", "East Gate", 38.8977, -77.0365),
    ("sen_003", "Harbor Watch Acoustic", "acoustic", "Harbor Watch", 38.8721, -77.0028),
    ("sen_004", "West Ridge Drone Patrol", "drone", "West Ridge", 38.9210, -77.0891),
    ("sen_005", "South Fence Line", "perimeter", "South Fence", 38.8654, -77.0512),
    ("sen_006", "Overwatch Radar Site B", "radar", "Overwatch B", 38.9345, -77.0203),
]

OBJECT_TYPES = ["aircraft", "vehicle", "person", "unknown"]
SEVERITIES = ["low", "medium", "high", "critical"]
OPERATORS = ["J. Alvarez", "M. Chen", "R. Singh", "K. Novak"]


def build_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).with_name("threat_telemetry_schema.sql")
    conn.executescript(schema_path.read_text())


def generate(conn: sqlite3.Connection, seed: int, num_detections: int) -> None:
    rng = random.Random(seed)
    cur = conn.cursor()
    # Anchored to real wall-clock time (not a fixed date) so "last hour" /
    # "today" queries stay meaningful whenever this generator is re-run.
    # UTC, to match SQLite's datetime('now') used by the intent templates.
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for sensor_id, name, sensor_type, location_name, lat, lon in SENSORS:
        status = rng.choices(["online", "degraded", "offline"], weights=[8, 1, 1])[0]
        cur.execute(
            """INSERT OR IGNORE INTO sensors
               (sensor_id, name, type, location_name, lat, lon, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sensor_id, name, sensor_type, location_name, lat, lon, status),
        )

    detection_seq = 1
    alert_seq = 1

    for i in range(num_detections):
        sensor_id, _name, _type, _location, base_lat, base_lon = rng.choice(SENSORS)
        # Skew heavily toward recent times (half the spread is within the last
        # ~4.5 hours) so "last hour" / "today" demo queries reliably return
        # results no matter when the generator is re-run, while still leaving
        # a long tail out to 72 hours for the broader time-window templates.
        minutes_ago = int(rng.random() ** 3 * 60 * 72)
        detected_at = now - timedelta(minutes=minutes_ago)
        object_type = rng.choices(OBJECT_TYPES, weights=[3, 4, 2, 1])[0]
        confidence = round(rng.uniform(0.55, 0.99), 2)
        severity = rng.choices(SEVERITIES, weights=[5, 4, 2, 1])[0]
        # Guarantee a handful of critical detections within the last hour,
        # since that's the headline demo query.
        if i < 5:
            minutes_ago = rng.randint(0, 55)
            detected_at = now - timedelta(minutes=minutes_ago)
            severity = "critical"
        lat = round(base_lat + rng.uniform(-0.01, 0.01), 6)
        lon = round(base_lon + rng.uniform(-0.01, 0.01), 6)

        detection_id = f"det_{detection_seq:05d}"
        detection_seq += 1
        cur.execute(
            """INSERT OR IGNORE INTO detections
               (detection_id, sensor_id, detected_at, object_type, confidence, severity, lat, lon, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (detection_id, sensor_id, detected_at.isoformat(sep=" "), object_type,
             confidence, severity, lat, lon, f"{object_type} contact, confidence {confidence}"),
        )

        if severity in ("high", "critical"):
            raised_at = detected_at + timedelta(minutes=rng.randint(0, 5))
            alert_status = rng.choices(["open", "acknowledged", "resolved"], weights=[4, 3, 3])[0]
            assigned_to = rng.choice(OPERATORS) if alert_status != "open" else None

            alert_id = f"alr_{alert_seq:05d}"
            alert_seq += 1
            cur.execute(
                """INSERT OR IGNORE INTO alerts
                   (alert_id, detection_id, raised_at, status, assigned_to)
                   VALUES (?, ?, ?, ?, ?)""",
                (alert_id, detection_id, raised_at.isoformat(sep=" "), alert_status, assigned_to),
            )

    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(Path(__file__).with_name("threat_telemetry.db")))
    parser.add_argument("--seed", type=int, default=7331)
    parser.add_argument("--num-detections", type=int, default=400)
    parser.add_argument("--force", action="store_true", help="Delete existing db file before generating")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if args.force and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        build_schema(conn)
        generate(conn, args.seed, args.num_detections)
    finally:
        conn.close()

    print(f"Generated {db_path}")


if __name__ == "__main__":
    main()
