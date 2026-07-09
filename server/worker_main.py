"""
ORBIT Message-Queue Worker
==========================

Standalone entry point that runs the broker-native async consumer WITHOUT serving
HTTP. It reuses the full server initialization via the FastAPI app lifespan, so the
worker sees the identical pipeline/auth/adapter wiring as the HTTP server, then runs
the message consumer until interrupted (Ctrl+C / SIGTERM).

Run with `messaging.enabled: true` and `messaging.run_in_server: false` in config.

Usage:
    python server/worker_main.py [--config CONFIG_PATH]
    ./bin/orbit.sh worker [--config CONFIG_PATH]
"""

import argparse
import asyncio
import logging
import signal

from inference_server import InferenceServer
from main import load_environment

logger = logging.getLogger(__name__)


async def _run(config_path) -> None:
    server = InferenceServer(config_path=config_path)
    app = server.app

    # Run the standard startup/shutdown lifespan so app.state holds the same service
    # graph as the HTTP server (chat service, api key service, adapter manager, ...).
    async with app.router.lifespan_context(app):
        if getattr(app.state, 'message_consumer', None) is not None:
            logger.error(
                "messaging.run_in_server is true - an in-process consumer is already "
                "running. Set run_in_server=false to use the standalone worker."
            )
            return

        consumer = server.service_factory.build_message_consumer(app)
        if consumer is None:
            logger.error("Messaging is disabled (messaging.enabled=false) - nothing to run")
            return

        await consumer.start()
        logger.info("ORBIT worker running - consuming messages. Press Ctrl+C to stop.")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # signal handlers are unavailable on some platforms (e.g. Windows)

        try:
            await stop_event.wait()
        finally:
            logger.info("Shutting down worker...")
            await consumer.stop()


def parse_arguments():
    parser = argparse.ArgumentParser(description='ORBIT message-queue worker')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    return parser.parse_args()


def main():
    args = parse_arguments()
    load_environment()
    asyncio.run(_run(args.config))


if __name__ == "__main__":
    main()
