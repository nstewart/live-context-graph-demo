"""Inventory sync worker - syncs store_inventory_mv to OpenSearch using SUBSCRIBE streaming."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.config import get_settings
from src.mz_client_subscribe import MaterializeSubscribeClient, SubscribeEvent
from src.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


class InventorySyncWorker:
    """Worker that syncs inventory from Materialize to OpenSearch using SUBSCRIBE streaming."""

    INDEX_NAME = "inventory"
    VIEW_NAME = "store_inventory_mv"

    def __init__(
        self,
        os_client: OpenSearchClient,
    ):
        self.os = os_client
        self.settings = get_settings()
        self._shutdown = asyncio.Event()

        # SUBSCRIBE client
        self.subscribe_client: Optional[MaterializeSubscribeClient] = None

        # Pending batches
        self.pending_upserts: list[dict] = []
        self.pending_deletes: list[str] = []

        # Metrics
        self.events_received = 0
        self.events_processed = 0
        self.flush_count = 0

        # Backpressure tracking
        self._backpressure_active = False

    def stop(self):
        """Signal the worker to stop."""
        logger.info("Stop signal received")
        self._shutdown.set()

    async def run(self):
        """Main sync loop with SUBSCRIBE."""
        logger.info("Starting inventory sync worker with SUBSCRIBE streaming")

        # Ensure OpenSearch index exists
        await self._ensure_inventory_index()

        # Perform initial hydration from Materialize
        await self._initial_hydration()

        if self.settings.use_subscribe:
            await self._run_subscribe_mode()
        else:
            logger.error("Polling mode not implemented. Set use_subscribe=True")
            raise NotImplementedError("Polling mode removed in favor of SUBSCRIBE")

        logger.info("Inventory sync worker stopped")

    async def _ensure_inventory_index(self):
        """Create inventory index in OpenSearch if it doesn't exist."""
        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "1s",
            },
            "mappings": {
                "properties": {
                    "inventory_id": {"type": "keyword"},
                    "store_id": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "stock_level": {"type": "integer"},
                    "replenishment_eta": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
                    "effective_updated_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
                    # Product details (denormalized from products_flat)
                    "product_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "category": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "unit_price": {"type": "float"},
                    "perishable": {"type": "boolean"},
                    "unit_weight_grams": {"type": "integer"},
                    # Store details (denormalized from stores_flat)
                    "store_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "store_zone": {"type": "keyword"},
                    "store_address": {"type": "text"},
                    # Computed fields
                    "availability_status": {"type": "keyword"},
                    "low_stock": {"type": "boolean"},
                }
            }
        }
        await self.os.ensure_index(self.INDEX_NAME, mapping)

    async def _initial_hydration(self):
        """Perform initial bulk load of data from Materialize to OpenSearch."""
        logger.info(f"Starting initial hydration from {self.VIEW_NAME}...")

        try:
            # Create temporary client to query Materialize
            temp_client = MaterializeSubscribeClient()

            query = f"""
                SELECT
                    inventory_id,
                    store_id,
                    product_id,
                    stock_level,
                    replenishment_eta,
                    effective_updated_at,
                    product_name,
                    category,
                    unit_price,
                    perishable,
                    unit_weight_grams,
                    store_name,
                    store_zone,
                    store_address,
                    availability_status,
                    low_stock
                FROM {self.VIEW_NAME}
            """

            rows = await temp_client.query(query)
            await temp_client.close()

            if not rows:
                logger.info("No existing inventory records to hydrate")
                return

            # Transform rows to OpenSearch documents
            documents = []
            for row in rows:
                doc = {
                    "inventory_id": row["inventory_id"],
                    "store_id": row["store_id"],
                    "product_id": row["product_id"],
                    "stock_level": row["stock_level"],
                    "replenishment_eta": row["replenishment_eta"],
                    "effective_updated_at": row["effective_updated_at"].isoformat() if row["effective_updated_at"] else None,
                    "product_name": row.get("product_name"),
                    "category": row.get("category"),
                    "unit_price": float(row["unit_price"]) if row.get("unit_price") else None,
                    "perishable": row.get("perishable"),
                    "unit_weight_grams": row.get("unit_weight_grams"),
                    "store_name": row.get("store_name"),
                    "store_zone": row.get("store_zone"),
                    "store_address": row.get("store_address"),
                    "availability_status": row.get("availability_status"),
                    "low_stock": row.get("low_stock"),
                }
                documents.append(doc)

            # Bulk insert to OpenSearch
            success_count, error_count = await self.os.bulk_upsert(self.INDEX_NAME, documents)
            logger.info(
                f"Initial hydration complete: {success_count} records synced, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Initial hydration failed: {e}")
            raise

    async def _run_subscribe_mode(self):
        """Run in SUBSCRIBE streaming mode with retry logic."""
        retry_delay = self.settings.retry_initial_delay

        while not self._shutdown.is_set():
            try:
                logger.info(f"Connecting to Materialize SUBSCRIBE for {self.VIEW_NAME}...")

                # Create new client for this connection attempt
                self.subscribe_client = MaterializeSubscribeClient()
                await self.subscribe_client.connect()

                logger.info(f"Starting SUBSCRIBE to {self.VIEW_NAME}")

                # This will block until stream ends or error occurs
                await self.subscribe_client.subscribe_to_view(
                    self.VIEW_NAME,
                    self._handle_events
                )

                # If we get here, stream ended normally
                logger.warning(f"SUBSCRIBE stream ended for {self.VIEW_NAME}")

                # Flush any pending events
                await self._flush_batch()

                # Reset retry delay on successful connection
                retry_delay = self.settings.retry_initial_delay

            except Exception as e:
                logger.error(f"SUBSCRIBE error: {e}")

                # Flush any pending events before retry
                await self._flush_batch()

                # Exponential backoff retry
                logger.info(f"Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, self.settings.retry_max_delay)

            finally:
                if self.subscribe_client:
                    await self.subscribe_client.close()
                    self.subscribe_client = None

    async def _handle_events(self, events: list[SubscribeEvent]):
        """Handle a batch of SUBSCRIBE events.

        Called by MaterializeSubscribeClient when timestamp advances.
        Events are batched by timestamp for efficient processing.
        """
        for event in events:
            self.events_received += 1

            # Data event - process insert or delete
            if event.mz_diff == 1:
                # Insert - add to upsert batch
                doc = {
                    "inventory_id": event.data["inventory_id"],
                    "store_id": event.data.get("store_id"),
                    "product_id": event.data.get("product_id"),
                    "stock_level": event.data.get("stock_level"),
                    "replenishment_eta": event.data.get("replenishment_eta"),
                    "effective_updated_at": event.data.get("effective_updated_at"),
                    "product_name": event.data.get("product_name"),
                    "category": event.data.get("category"),
                    "unit_price": event.data.get("unit_price"),
                    "perishable": event.data.get("perishable"),
                    "unit_weight_grams": event.data.get("unit_weight_grams"),
                    "store_name": event.data.get("store_name"),
                    "store_zone": event.data.get("store_zone"),
                    "store_address": event.data.get("store_address"),
                    "availability_status": event.data.get("availability_status"),
                    "low_stock": event.data.get("low_stock"),
                }
                self.pending_upserts.append(doc)

            elif event.mz_diff == -1:
                # Delete - add to delete batch
                inventory_id = event.data["inventory_id"]
                self.pending_deletes.append(inventory_id)

            self.events_processed += 1

        # Flush batch after processing all events in this timestamp
        await self._flush_batch()

        # Check backpressure
        pending_count = len(self.pending_upserts) + len(self.pending_deletes)
        if pending_count > self.settings.backpressure_threshold:
            if not self._backpressure_active:
                logger.warning(f"Backpressure activated: {pending_count} pending events")
                self._backpressure_active = True
        elif self._backpressure_active:
            logger.info("Backpressure cleared")
            self._backpressure_active = False

    async def _flush_batch(self):
        """Flush pending upserts and deletes to OpenSearch."""
        if not self.pending_upserts and not self.pending_deletes:
            return

        try:
            # Execute bulk operations
            if self.pending_upserts:
                success, errors = await self.os.bulk_upsert(
                    self.INDEX_NAME, self.pending_upserts
                )
                logger.info(
                    f"Flushed {success} upserts to OpenSearch ({errors} errors)"
                )

            if self.pending_deletes:
                success, errors = await self.os.bulk_delete(
                    self.INDEX_NAME, self.pending_deletes
                )
                logger.info(
                    f"Flushed {success} deletes to OpenSearch ({errors} errors)"
                )

            self.flush_count += 1

            # Clear batches
            self.pending_upserts.clear()
            self.pending_deletes.clear()

        except Exception as e:
            logger.error(f"Flush failed: {e}")
            # Don't clear batches on error - will retry on next flush

    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "events_received": self.events_received,
            "events_processed": self.events_processed,
            "flush_count": self.flush_count,
            "pending_upserts": len(self.pending_upserts),
            "pending_deletes": len(self.pending_deletes),
            "backpressure_active": self._backpressure_active,
        }
