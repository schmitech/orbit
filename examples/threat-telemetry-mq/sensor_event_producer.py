#!/usr/bin/env python3
"""
Sensor event producer — real-time threat-analysis demo
=========================================================

Simulates a live sensor feed: publishes raw JSON detection events (not NL
questions) to a durable queue, at a configurable rate. Pair this with
`telemetry_ingest_consumer.py`, which persists each event into
threat_telemetry.db — after which ORBIT (chat, the dashboard, or
`sensor_burst_producer.py`'s NL queries) can find and analyze the new data.

This is the "sensors publish, a service ingests" half of the demo;
`sensor_burst_producer.py` is the separate "operator/system asks ORBIT
questions" half. Both go over the broker, but to different queues and for
different purposes.

Requires the messaging dependency profile (aio-pika):
    ./install/setup.sh --profile messaging

Example:
    # Publish 10 events, one every 2 seconds, simulating a live trickle
    python examples/threat-telemetry-mq/sensor_event_producer.py --count 10 --interval 2

    # Publish 50 events as fast as possible, simulating a burst
    python examples/threat-telemetry-mq/sensor_event_producer.py --count 50 --interval 0
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import UTC, datetime

SENSORS = ["sen_001", "sen_002", "sen_003", "sen_004", "sen_005", "sen_006"]
SENSOR_BASE_COORDS = {
    "sen_001": (38.9012, -77.0653),
    "sen_002": (38.8977, -77.0365),
    "sen_003": (38.8721, -77.0028),
    "sen_004": (38.9210, -77.0891),
    "sen_005": (38.8654, -77.0512),
    "sen_006": (38.9345, -77.0203),
}
OBJECT_TYPES = ["aircraft", "vehicle", "person", "unknown"]
SEVERITIES = ["low", "medium", "high", "critical"]


def make_event(rng: random.Random) -> dict:
    sensor_id = rng.choice(SENSORS)
    base_lat, base_lon = SENSOR_BASE_COORDS[sensor_id]
    object_type = rng.choices(OBJECT_TYPES, weights=[3, 4, 2, 1])[0]
    severity = rng.choices(SEVERITIES, weights=[4, 3, 2, 2])[0]  # skew toward high/critical for a lively demo
    return {
        "sensor_id": sensor_id,
        "object_type": object_type,
        "confidence": round(rng.uniform(0.6, 0.99), 2),
        "severity": severity,
        "lat": round(base_lat + rng.uniform(-0.01, 0.01), 6),
        "lon": round(base_lon + rng.uniform(-0.01, 0.01), 6),
        "detected_at": datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" "),
    }


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

    rng = random.Random(args.seed)
    conn = await aio_pika.connect_robust(args.url)
    try:
        channel = await conn.channel()
        await channel.declare_queue(
            args.events_queue,
            durable=True,
            arguments={"x-dead-letter-exchange": "", "x-dead-letter-routing-key": args.dead_letter_queue},
        )

        print(f"Publishing {args.count} sensor events to '{args.events_queue}' (interval={args.interval}s)...\n")

        for i in range(args.count):
            event = make_event(rng)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(event).encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=args.events_queue,
            )
            print(f"[{i + 1}/{args.count}] published {event['sensor_id']} {event['object_type']}/{event['severity']}")
            if args.interval > 0 and i < args.count - 1:
                await asyncio.sleep(args.interval)

        print(
            "\nDone. Run telemetry_ingest_consumer.py to persist these into threat_telemetry.db, "
            "then ask ORBIT about the new detections."
        )
        return 0
    finally:
        await conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Publish synthetic sensor detection events to the broker")
    parser.add_argument("--count", type=int, default=10, help="Number of events to publish")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between events (0 = publish all at once)")
    parser.add_argument("--seed", type=int, help="Optional RNG seed for reproducible events")
    parser.add_argument(
        "--url",
        default="amqp://guest:guest@localhost:5672/",
        help="AMQP broker URL (or set $MESSAGING_RABBITMQ_URL and pass it explicitly)",
    )
    parser.add_argument("--events-queue", default="orbit.telemetry.events", help="Queue to publish raw detection events to")
    parser.add_argument("--dead-letter-queue", default="orbit.telemetry.dlq", help="Queue for malformed events")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
