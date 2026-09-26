#!/usr/bin/env python3
"""
Sensor burst producer — real-time threat-analysis demo
========================================================

Simulates a burst of sensor-network traffic (a spike of NL questions an
operator or an automated triage system would ask) and drops it onto ORBIT's
broker-native async surface all at once, then listens for the correlated
replies as they arrive. Demonstrates the "spiky / bursty ingestion" fit
described in docs/message-queue-architecture.md: the queue absorbs the burst
and `prefetch` meters it into the pipeline instead of overwhelming the LLM
provider.

Also runs a tiny local read-only HTTP status server (default
http://localhost:8787/status) so the threat-telemetry dashboard can poll and
display each reply live as it arrives, instead of only being visible in this
terminal. This server is not part of ORBIT — it's a demo-only bridge, since
a browser can't speak AMQP directly. Disable it with --no-status-server.

Requires the messaging dependency profile (aio-pika):
    ./install/setup.sh --profile messaging

Prerequisites:
    - A running RabbitMQ broker (see docs/message-queue-architecture.md quick start)
    - ORBIT server/worker running with `messaging.enabled: true`
    - The `intent-sql-sqlite-threat-telemetry` adapter registered (config/adapters/threat-telemetry.yaml)

Example:
    export ORBIT_API_KEY=orbit_abcd1234
    python examples/threat-telemetry-mq/sensor_burst_producer.py --burst-size 20
"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

QUESTIONS = [
    "Show critical detections in the last hour",
    "How many open alerts are there right now?",
    "Which sensors reported detections today?",
    "List unresolved alerts by severity",
    "What detections happened near North Perimeter?",
    "Show sensor status",
    "Which sensors are offline?",
    "Break down detections by object type in the last 24 hours",
    "Show alerts assigned to J. Alvarez",
    "What detections happened near Harbor Watch?",
]


class BurstState:
    """Thread-safe state for the burst, polled by the dashboard over HTTP."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "burst_size": 0,
            "adapter": None,
            "started_at": None,
            "completed": 0,
            "failed": 0,
            "outstanding": 0,
            "results": [],
        }

    def start(self, burst_size: int, adapter: str):
        with self._lock:
            self._state.update(
                burst_size=burst_size,
                adapter=adapter,
                started_at=time.time(),
                completed=0,
                failed=0,
                outstanding=burst_size,
                results=[],
            )

    def record_reply(self, question: str, status: str, response: str | None, error: str | None):
        with self._lock:
            self._state["results"].append(
                {
                    "question": question,
                    "status": status,
                    "response": response,
                    "error": error,
                    "received_at": time.time(),
                }
            )
            if status == "completed":
                self._state["completed"] += 1
            else:
                self._state["failed"] += 1
            self._state["outstanding"] = max(0, self._state["outstanding"] - 1)

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._state))


def make_status_handler(state: BurstState):
    class StatusHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.rstrip("/") != "/status":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(state.snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, log_format, *args):
            pass

    return StatusHandler


def start_status_server(state: BurstState, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), make_status_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


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

    state = BurstState()
    status_server = None
    if not args.no_status_server:
        status_server = start_status_server(state, args.status_port)
        print(f"Live status for the dashboard: http://localhost:{args.status_port}/status\n")

    conn = await aio_pika.connect_robust(args.url)
    try:
        channel = await conn.channel()
        replies = await channel.declare_queue(exclusive=True)

        pending = {}
        for i in range(args.burst_size):
            corr_id = str(uuid.uuid4())
            message = QUESTIONS[i % len(QUESTIONS)]
            pending[corr_id] = message

        state.start(args.burst_size, args.adapter)

        print(f"Publishing a burst of {args.burst_size} sensor queries to '{args.requests_queue}'...")

        for corr_id, message in pending.items():
            request = {"id": corr_id, "message": message}
            if args.api_key:
                request["api_key"] = args.api_key
            request["adapter"] = args.adapter

            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(request).encode(),
                    correlation_id=corr_id,
                    reply_to=replies.name,
                    content_type="application/json",
                ),
                routing_key=args.requests_queue,
            )

        print(f"Burst published. Waiting up to {args.timeout}s for {len(pending)} replies...\n")

        completed = 0
        failed = 0

        async def collect_replies():
            nonlocal completed, failed
            async with replies.iterator() as it:
                async for msg in it:
                    if msg.correlation_id not in pending:
                        continue
                    async with msg.process():
                        envelope = json.loads(msg.body)
                    question = pending.pop(msg.correlation_id)
                    status = envelope.get("status")
                    response = envelope.get("response")
                    error = envelope.get("error")
                    if status == "completed":
                        completed += 1
                    else:
                        failed += 1
                    state.record_reply(question, status, response, error)
                    print(f"[{status}] {question!r} -> {response or error}")
                    if not pending:
                        return

        try:
            await asyncio.wait_for(collect_replies(), timeout=args.timeout)
        except asyncio.TimeoutError:
            print(
                f"\nTimed out after {args.timeout}s with {len(pending)} replies still outstanding.\n"
                "Is a worker running? Start one with:  ./bin/orbit.sh worker start --config config/config.yaml",
                file=sys.stderr,
            )

        print(f"\n{completed} completed, {failed} failed, {len(pending)} outstanding.")

        if status_server and args.linger_seconds > 0:
            print(
                f"\nDashboard status server still serving the final results for {args.linger_seconds}s "
                f"(http://localhost:{args.status_port}/status). Press Ctrl+C to exit sooner."
            )
            try:
                await asyncio.sleep(args.linger_seconds)
            except asyncio.CancelledError:
                pass

        return 0 if not pending and failed == 0 else 1
    finally:
        await conn.close()
        if status_server:
            status_server.shutdown()


def parse_args():
    parser = argparse.ArgumentParser(description="Publish a burst of sensor queries to ORBIT's MQ surface")
    parser.add_argument("--burst-size", type=int, default=20, help="Number of messages to publish in the burst")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ORBIT_API_KEY"),
        help="ORBIT API key (defaults to $ORBIT_API_KEY). Omit only if the server has API-key auth disabled.",
    )
    parser.add_argument("--adapter", default="intent-sql-sqlite-threat-telemetry", help="Adapter to route the burst to")
    parser.add_argument(
        "--url",
        default=os.environ.get("MESSAGING_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        help="AMQP broker URL (defaults to $MESSAGING_RABBITMQ_URL or amqp://guest:guest@localhost:5672/)",
    )
    parser.add_argument("--requests-queue", default="orbit.requests", help="Queue ORBIT consumes requests from")
    parser.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for all replies")
    parser.add_argument("--status-port", type=int, default=8787, help="Port for the local dashboard status server")
    parser.add_argument(
        "--no-status-server", action="store_true", help="Disable the local HTTP status server for the dashboard"
    )
    parser.add_argument(
        "--linger-seconds",
        type=float,
        default=120.0,
        help="Keep the status server up this long after the burst finishes, so the dashboard keeps showing "
        "the final tally instead of reverting to 'no producer detected' (0 = shut down immediately)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
