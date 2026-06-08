"""Propagation tap entry point.

Runs two things in one process:
  - the aiohttp propagation API on :8083 (reused verbatim from the old
    search-sync service — same endpoints the web PropagationContext polls), and
  - a background thread running the blocking Kafka consumer (tap.py) that feeds
    the shared in-memory PropagationEventStore.
"""

import asyncio
import logging
import signal
import threading

from src.propagation_api import start_api_server
from src.tap import run_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting propagation tap...")

    stop_flag = threading.Event()
    consumer_thread = threading.Thread(
        target=run_consumer, args=(stop_flag,), name="kafka-tap", daemon=True
    )
    consumer_thread.start()

    api_runner = await start_api_server(port=8083)

    loop = asyncio.get_event_loop()
    shutdown = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    try:
        await shutdown.wait()
    finally:
        logger.info("Shutting down propagation tap...")
        stop_flag.set()
        await api_runner.cleanup()
        consumer_thread.join(timeout=5)
        logger.info("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
