#!/usr/bin/env python3
"""
Game bridge — Triage Rush decision-model demo
===============================================

A small local HTTP bridge between the Triage Rush browser game
(examples/triage-rush-game/) and ORBIT's broker-native async surface. A
browser can't speak AMQP, so this bridge:

- POST /publish  publishes each ticket the game spawns onto `orbit.requests`
                 (a SURGE is one call with many tickets, published back-to-back
                 without waiting — the same burst injection as
                 examples/threat-telemetry-mq/sensor_burst_producer.py)
- GET  /events   streams each correlated reply back to the game as
                 Server-Sent Events, with the measured publish -> reply latency
                 and the typed `decision` from the decision-model adapter
- GET  /health   reports broker connectivity plus the depth and consumer
                 (worker) count of `orbit.requests`, so the game can show
                 "NO WORKER" instead of pretending

Nothing here decides anything: every answer comes from ORBIT's real worker
running a ticket-triage decision adapter. This is not part of ORBIT — it is
a demo-only bridge, like the threat-telemetry bridges.

It binds to 127.0.0.1 by default because it publishes with your ORBIT API key.

Requires the messaging dependency profile (aio-pika); aiohttp is a core ORBIT
dependency:
    ./install/setup.sh --profile messaging

Example:
    export ORBIT_API_KEY=orbit_abcd1234
    python examples/triage-rush-mq/game_bridge.py
"""

import argparse
import asyncio
import json
import os
import sys
import time

MAX_ITEMS_PER_PUBLISH = 50
MAX_TEXT_LENGTH = 1000
MAX_ID_LENGTH = 64
MAX_DECISION_INPUT_LENGTH = 4000


class Bridge:
    """Holds the AMQP connection, the in-flight tickets, and the SSE subscribers."""

    def __init__(self, args):
        self.args = args
        self.allowed_adapters = [a.strip() for a in args.allowed_adapters.split(",") if a.strip()]
        if args.adapter not in self.allowed_adapters:
            self.allowed_adapters.insert(0, args.adapter)
        self.connection = None
        self.channel = None
        self.health_channel = None
        self.reply_queue = None
        self.pending = {}  # correlation id -> (published monotonic time, adapter)
        self.subscribers = set()

    async def connect(self, aio_pika):
        self.aio_pika = aio_pika
        self.connection = await aio_pika.connect_robust(self.args.url)
        self.channel = await self.connection.channel()
        self.reply_queue = await self.channel.declare_queue(exclusive=True)
        await self.reply_queue.consume(self.on_reply)

    async def close(self):
        if self.connection:
            await self.connection.close()

    def broadcast(self, event: dict):
        for queue in self.subscribers:
            queue.put_nowait(event)

    async def publish(self, items: list[dict], adapter: str) -> None:
        for item in items:
            message = item["text"]
            if "state" in item:
                message = json.dumps({"state": item["state"], "questions": item["questions"]})
            request = {"id": item["id"], "message": message, "adapter": adapter}
            if self.args.api_key:
                request["api_key"] = self.args.api_key
            self.pending[item["id"]] = (time.monotonic(), adapter)
            await self.channel.default_exchange.publish(
                self.aio_pika.Message(
                    body=json.dumps(request).encode(),
                    correlation_id=item["id"],
                    reply_to=self.reply_queue.name,
                    content_type="application/json",
                ),
                routing_key=self.args.requests_queue,
            )

    async def on_reply(self, message):
        async with message.process():
            entry = self.pending.pop(message.correlation_id, None)
            if entry is None:
                return  # timed out already, or not ours
            try:
                envelope = json.loads(message.body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                envelope = {"status": "failed", "error": "unparseable reply envelope"}
        published_at, adapter = entry
        decision = envelope.get("decision")
        self.broadcast(
            {
                "type": "decision",
                "id": message.correlation_id,
                "status": envelope.get("status"),
                "adapter": adapter,
                "model": (decision or {}).get("model"),
                "answers": (decision or {}).get("answers"),
                "error": envelope.get("error"),
                "latency_ms": round((time.monotonic() - published_at) * 1000),
            }
        )

    async def expire_pending(self):
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            expired = [cid for cid, (at, _) in self.pending.items() if now - at > self.args.timeout]
            for cid in expired:
                _, adapter = self.pending.pop(cid)
                self.broadcast(
                    {
                        "type": "decision",
                        "id": cid,
                        "status": "timeout",
                        "adapter": adapter,
                        "error": f"no reply within {self.args.timeout:g}s",
                        "latency_ms": None,
                    }
                )

    async def queue_stats(self) -> dict:
        # A passive declare reports depth and consumer count without the RabbitMQ
        # management API. A failed passive declare closes its channel, so it gets its own.
        try:
            if self.health_channel is None or self.health_channel.is_closed:
                self.health_channel = await self.connection.channel()
            # Declare on the underlying aiormq channel: a robust channel reuses its first result.
            raw = await self.health_channel.get_underlay_channel()
            result = await raw.queue_declare(self.args.requests_queue, passive=True)
            return {"available": True, "messages": result.message_count, "consumers": result.consumer_count}
        except Exception as exc:  # noqa: BLE001 - report any failure to the game, don't crash the bridge
            self.health_channel = None
            return {"available": False, "reason": str(exc)}


def validate_publish(body, allowed_adapters: list[str], default_adapter: str) -> tuple[list, str, str | None]:
    """Return (items, adapter, error)."""
    if not isinstance(body, dict):
        return [], default_adapter, "body must be a JSON object"
    adapter = body.get("adapter") or default_adapter
    if adapter not in allowed_adapters:
        return [], adapter, f"adapter {adapter!r} is not allowed (allowed: {', '.join(allowed_adapters)})"
    items = body.get("items")
    if not isinstance(items, list) or not items:
        return [], adapter, "items must be a non-empty list"
    if len(items) > MAX_ITEMS_PER_PUBLISH:
        return [], adapter, f"at most {MAX_ITEMS_PER_PUBLISH} items per publish"
    ids = set()
    for item in items:
        if not isinstance(item, dict):
            return [], adapter, "each item must be an object with id and text"
        item_id, text = item.get("id"), item.get("text")
        if not isinstance(item_id, str) or not item_id or len(item_id) > MAX_ID_LENGTH:
            return [], adapter, f"item id must be a string of 1-{MAX_ID_LENGTH} characters"
        if item_id in ids:
            return [], adapter, f"duplicate item id: {item_id}"
        ids.add(item_id)
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return [], adapter, f"item text must be a non-empty string of at most {MAX_TEXT_LENGTH} characters"
        if "state" in item or "questions" in item:
            state, questions = item.get("state"), item.get("questions")
            if not isinstance(state, dict) or not isinstance(questions, dict) or not questions:
                return [], adapter, "state and questions must both be non-empty JSON objects"
            if state.get("ticket") != text:
                return [], adapter, "state.ticket must match item text"
            try:
                encoded = json.dumps({"state": state, "questions": questions})
            except (TypeError, ValueError):
                return [], adapter, "state and questions must contain JSON values"
            if len(encoded) > MAX_DECISION_INPUT_LENGTH:
                return [], adapter, f"structured decision input exceeds {MAX_DECISION_INPUT_LENGTH} characters"
    return items, adapter, None


def make_app(bridge: Bridge, web):
    @web.middleware
    async def preflight(request, handler):
        if request.method == "OPTIONS":
            return web.Response(status=204)
        return await handler(request)

    # Added on prepare rather than in the middleware: the /events stream sends its headers
    # before its handler returns, so a middleware would add them too late for the browser.
    async def cors_headers(_request, response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Cache-Control"] = "no-store"

    async def publish(request):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "body must be JSON"}, status=400)
        items, adapter, error = validate_publish(body, bridge.allowed_adapters, bridge.args.adapter)
        if error:
            return web.json_response({"error": error}, status=400)
        duplicates = [item["id"] for item in items if item["id"] in bridge.pending]
        if duplicates:
            return web.json_response({"error": f"ids already in flight: {', '.join(duplicates)}"}, status=409)
        await bridge.publish(items, adapter)
        return web.json_response({"published": len(items), "adapter": adapter})

    async def events(request):
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        queue = asyncio.Queue()
        bridge.subscribers.add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    await response.write(f"data: {json.dumps(event)}\n\n".encode())
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            bridge.subscribers.discard(queue)
        return response

    async def health(_request):
        return web.json_response(
            {
                "broker": bridge.connection is not None and not bridge.connection.is_closed,
                "requests_queue": bridge.args.requests_queue,
                "queue": await bridge.queue_stats(),
                "in_flight": len(bridge.pending),
                "adapter": bridge.args.adapter,
                "allowed_adapters": bridge.allowed_adapters,
                "api_key_configured": bool(bridge.args.api_key),
            }
        )

    app = web.Application(middlewares=[preflight])
    app.on_response_prepare.append(cors_headers)
    app.router.add_post("/publish", publish)
    app.router.add_get("/events", events)
    app.router.add_get("/health", health)
    return app


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
    from aiohttp import web

    if not args.api_key:
        print("Warning: no API key (set $ORBIT_API_KEY or pass --api-key); ORBIT will reply 'Missing API key'.\n")

    bridge = Bridge(args)
    try:
        await bridge.connect(aio_pika)
    except Exception as exc:  # noqa: BLE001 - print a friendly hint instead of a traceback
        print(f"Could not connect to RabbitMQ at {args.url}: {exc}", file=sys.stderr)
        return 2

    runner = web.AppRunner(make_app(bridge, web))
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()
    expiry = asyncio.create_task(bridge.expire_pending())

    print(f"Triage Rush bridge: http://{args.host}:{args.port}  (adapter: {args.adapter})")
    print(f"Publishing to '{args.requests_queue}'. Point the game's presenter panel at this URL.")
    print("Press Ctrl+C to stop.")
    try:
        await asyncio.Event().wait()
    finally:
        expiry.cancel()
        await runner.cleanup()
        await bridge.close()
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="HTTP/SSE bridge between the Triage Rush game and ORBIT's MQ surface")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ORBIT_API_KEY"),
        help="ORBIT API key (defaults to $ORBIT_API_KEY). Omit only if the server has API-key auth disabled.",
    )
    parser.add_argument("--adapter", default="ticket-triage-typesafe", help="Default decision adapter for the game")
    parser.add_argument(
        "--allowed-adapters",
        default="ticket-triage,ticket-triage-typesafe",
        help="Comma-separated adapters the game may switch between",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MESSAGING_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        help="AMQP broker URL (defaults to $MESSAGING_RABBITMQ_URL or amqp://guest:guest@localhost:5672/)",
    )
    parser.add_argument("--requests-queue", default="orbit.requests", help="Queue ORBIT consumes requests from")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (use 0.0.0.0 to serve other machines)")
    parser.add_argument("--port", type=int, default=8795, help="Port for the bridge")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds before an unanswered ticket times out")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        pass
