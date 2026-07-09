#!/usr/bin/env python3
"""
ORBIT Message-Queue test client
===============================

Publishes one request to ORBIT's broker-native async surface and prints the
correlated response envelope. Use it to manually exercise the MQ surface against
a local RabbitMQ (see rabbitmq-local-setup.md) while an ORBIT worker / server
consumes `orbit.requests`.

Requires the messaging dependency profile (aio-pika):
    ./install/setup.sh --profile messaging

Examples:
    # API key from the ORBIT_API_KEY env var
    export ORBIT_API_KEY=orbit_abcd1234
    python server/tests/messaging/mq_client.py "What can you help me with?"

    # Explicit key + adapter override, custom broker
    python server/tests/messaging/mq_client.py "Hello" \
        --api-key orbit_abcd1234 --adapter my-adapter \
        --url amqp://guest:guest@localhost:5672/
"""

import argparse
import asyncio
import json
import os
import sys
import uuid


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

    conn = await aio_pika.connect_robust(args.url)
    try:
        channel = await conn.channel()
        # Temporary, exclusive reply queue that is cleaned up when we disconnect.
        replies = await channel.declare_queue(exclusive=True)

        corr_id = str(uuid.uuid4())
        request = {"id": corr_id, "message": args.message}
        if args.api_key:
            request["api_key"] = args.api_key
        if args.adapter:
            request["adapter"] = args.adapter
        if args.session_id:
            request["session_id"] = args.session_id

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(request).encode(),
                correlation_id=corr_id,
                reply_to=replies.name,
                content_type="application/json",
            ),
            routing_key=args.requests_queue,
        )
        print(f"published corr_id={corr_id} to '{args.requests_queue}', waiting up to {args.timeout}s...")

        async def wait_for_reply():
            async with replies.iterator() as it:
                async for msg in it:
                    if msg.correlation_id == corr_id:
                        async with msg.process():
                            return json.loads(msg.body)
            return None

        try:
            envelope = await asyncio.wait_for(wait_for_reply(), timeout=args.timeout)
        except asyncio.TimeoutError:
            print(
                f"\nTimed out after {args.timeout}s with no reply.\n"
                "Is a consumer running? Start one with:  ./bin/orbit.sh worker\n"
                "Or check the broker: http://localhost:15672 (guest/guest).",
                file=sys.stderr,
            )
            return 1

        print(json.dumps(envelope, indent=2))
        return 0 if envelope and envelope.get("status") == "completed" else 1
    finally:
        await conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Publish one request to ORBIT's MQ surface and print the reply")
    parser.add_argument("message", help="The user message to send")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ORBIT_API_KEY"),
        help="ORBIT API key (defaults to $ORBIT_API_KEY). Omit only if the server has API-key auth disabled.",
    )
    parser.add_argument("--adapter", help="Optional per-message adapter override")
    parser.add_argument("--session-id", help="Optional session id (defaults server-side to the correlation id)")
    parser.add_argument(
        "--url",
        default=os.environ.get("MESSAGING_RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"),
        help="AMQP broker URL (defaults to $MESSAGING_RABBITMQ_URL or amqp://guest:guest@localhost:5672/)",
    )
    parser.add_argument("--requests-queue", default="orbit.requests", help="Queue ORBIT consumes requests from")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for the reply")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
