"""Search sync worker main entry point."""

import asyncio
import logging
import signal
import sys

from src.config import get_settings
from src.opensearch_client import OpenSearchClient
from src.orders_sync import OrdersSyncWorker
from src.inventory_sync import InventorySyncWorker

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Reduce opensearch client logging verbosity (bulk request logs)
logging.getLogger("opensearch").setLevel(logging.WARNING)


async def main():
    """Main entry point."""
    logger.info("Initializing search sync worker...")

    # Initialize OpenSearch client
    os_client = OpenSearchClient()

    # Wait for OpenSearch to be ready
    logger.info("Waiting for OpenSearch...")
    for attempt in range(30):
        if await os_client.health_check():
            logger.info("OpenSearch is ready")
            break
        logger.info(f"OpenSearch not ready, attempt {attempt + 1}/30")
        await asyncio.sleep(2)
    else:
        logger.error("OpenSearch failed to become ready")
        sys.exit(1)

    # Create workers (MaterializeClient is created inside each worker for SUBSCRIBE mode)
    orders_worker = OrdersSyncWorker(os_client)
    inventory_worker = InventorySyncWorker(os_client)

    # Set up signal handlers
    loop = asyncio.get_event_loop()

    def handle_shutdown():
        logger.info("Shutdown signal received")
        orders_worker.stop()
        inventory_worker.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_shutdown)

    # Run both workers concurrently
    try:
        await asyncio.gather(
            orders_worker.run(),
            inventory_worker.run(),
        )
    finally:
        logger.info("Cleaning up...")

        # Flush any pending events before shutdown
        try:
            logger.info("Flushing pending events from both workers...")
            await asyncio.gather(
                orders_worker._flush_batch(),
                inventory_worker._flush_batch(),
            )
        except Exception as e:
            logger.error(f"Error flushing on shutdown: {e}")

        # Close OpenSearch client
        await os_client.close()

        logger.info("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
