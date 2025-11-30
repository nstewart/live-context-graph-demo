"""Abstract base class for SUBSCRIBE-based sync workers.

This module provides a reusable foundation for syncing Materialize views to
OpenSearch using SUBSCRIBE streaming. It implements common patterns like:
- Connection management with exponential backoff retry
- Initial hydration from materialized views
- Event batching and backpressure handling
- Flush logic with retry attempts
- Metrics tracking and logging

Worker implementations only need to provide view-specific configuration
and transformation logic through abstract methods.

Architecture:
    BaseSubscribeWorker (abstract)
        ├── OrdersSyncWorker (concrete, uses consolidation)
        └── InventorySyncWorker (concrete, simple processing)

Example:
    Creating a new sync worker::

        class ProductsSyncWorker(BaseSubscribeWorker):
            def get_view_name(self) -> str:
                return "products_mv"

            def get_index_name(self) -> str:
                return "products"

            def get_doc_id(self, data: dict) -> str:
                return data.get("product_id")

            def transform_event_to_doc(self, data: dict) -> Optional[dict]:
                return {
                    "product_id": data.get("product_id"),
                    "product_name": data.get("product_name"),
                    "unit_price": float(data.get("unit_price", 0)),
                }

            def get_index_mapping(self) -> dict:
                return {"mappings": {"properties": {...}}}
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.config import get_settings
from src.mz_client_subscribe import MaterializeSubscribeClient, SubscribeEvent
from src.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


class BaseSubscribeWorker(ABC):
    """Abstract base class for SUBSCRIBE-based sync workers.

    Provides common SUBSCRIBE streaming infrastructure while allowing
    worker-specific customization through abstract methods and hooks.

    Lifecycle:
        1. run() → ensure_index() → create OpenSearch index
        2. run() → _initial_hydration() → bulk load existing data
        3. run() → _run_subscribe_mode() → start SUBSCRIBE stream
        4. _handle_events() → transform and batch events
        5. _flush_batch() → bulk write to OpenSearch
        6. On error: exponential backoff retry

    Subclass Responsibilities:
        Implement abstract methods:
        - get_view_name(): Materialize view to subscribe to
        - get_index_name(): OpenSearch index name
        - get_index_mapping(): OpenSearch index schema
        - get_doc_id(): Extract document ID from event data
        - transform_event_to_doc(): Transform event to OpenSearch document

        Optional overrides:
        - should_consolidate_events(): Enable UPDATE consolidation (default: False)
        - ensure_index(): Custom index setup logic

    Attributes:
        os: OpenSearch client for bulk operations
        settings: Configuration from environment
        subscribe_client: Materialize SUBSCRIBE client (per connection)
        pending_upserts: Buffer of documents to upsert
        pending_deletes: Buffer of document IDs to delete
        events_received: Total events from SUBSCRIBE stream
        events_processed: Total events flushed to OpenSearch
        flush_count: Number of flush operations
    """

    def __init__(self, os_client: OpenSearchClient):
        """Initialize base worker with OpenSearch client.

        Args:
            os_client: OpenSearch client for bulk indexing
        """
        self.os = os_client
        self.settings = get_settings()
        self._shutdown = asyncio.Event()

        # SUBSCRIBE client (created per connection)
        self.subscribe_client: Optional[MaterializeSubscribeClient] = None

        # Event batching buffers
        self.pending_upserts: list[dict] = []
        self.pending_deletes: list[str] = []

        # Metrics
        self.events_received = 0
        self.events_processed = 0
        self.flush_count = 0

        # Backpressure tracking
        self._backpressure_active = False

    # ========================================================================
    # Abstract methods (must be implemented by subclasses)
    # ========================================================================

    @abstractmethod
    def get_view_name(self) -> str:
        """Return Materialize view name to subscribe to.

        Example:
            return "orders_search_source_mv"
        """
        pass

    @abstractmethod
    def get_index_name(self) -> str:
        """Return OpenSearch index name.

        Example:
            return "orders"
        """
        pass

    @abstractmethod
    def get_index_mapping(self) -> dict:
        """Return OpenSearch index mapping configuration.

        Example:
            return {
                "settings": {
                    "number_of_shards": 1,
                    "refresh_interval": "1s"
                },
                "mappings": {
                    "properties": {
                        "order_id": {"type": "keyword"},
                        "order_status": {"type": "keyword"}
                    }
                }
            }
        """
        pass

    @abstractmethod
    def get_doc_id(self, data: dict) -> str:
        """Extract document ID from event data.

        Args:
            data: Raw event data from Materialize

        Returns:
            Document ID for OpenSearch (e.g., "order:FM-1001")

        Example:
            return data.get("order_id")
        """
        pass

    @abstractmethod
    def transform_event_to_doc(self, data: dict) -> Optional[dict]:
        """Transform SUBSCRIBE event data to OpenSearch document.

        Converts raw Materialize row data into properly formatted
        OpenSearch document with type conversions and null handling.

        Args:
            data: Raw event data from Materialize

        Returns:
            OpenSearch document as dict, or None to skip this event

        Example:
            return {
                "order_id": data.get("order_id"),
                "order_status": data.get("order_status"),
                "order_total": float(data.get("order_total", 0))
            }
        """
        pass

    # ========================================================================
    # Customization hooks (optional override)
    # ========================================================================

    def should_consolidate_events(self) -> bool:
        """Whether to consolidate events at same timestamp.

        When True, enables complex UPDATE handling where DELETE + INSERT
        at the same timestamp is consolidated into a single UPDATE operation.
        This is useful for tables with frequent updates.

        When False, uses simple processing where each INSERT/DELETE is
        handled independently. This is more efficient for append-only data.

        Returns:
            True to enable consolidation, False for simple processing

        Default:
            False (simple processing)

        Example:
            # Orders have frequent updates, enable consolidation
            return True
        """
        return False

    async def ensure_index(self):
        """Ensure OpenSearch index exists with proper mapping.

        Default implementation creates index with mapping from
        get_index_mapping(). Override for custom initialization logic.

        Example override:
            async def ensure_index(self):
                mapping = self.get_index_mapping()
                # Custom logic before/after index creation
                await self.os.ensure_index(self.get_index_name(), mapping)
        """
        mapping = self.get_index_mapping()
        await self.os.ensure_index(self.get_index_name(), mapping)

    # ========================================================================
    # Public API
    # ========================================================================

    def stop(self):
        """Signal the worker to stop gracefully."""
        logger.info("Stop signal received")
        self._shutdown.set()

    def get_stats(self) -> dict:
        """Get worker statistics for monitoring.

        Returns:
            Dict with metrics:
            - events_received: Total events from SUBSCRIBE
            - events_processed: Total events flushed to OpenSearch
            - flush_count: Number of flush operations
            - pending_upserts: Current buffer size (upserts)
            - pending_deletes: Current buffer size (deletes)
            - backpressure_active: Whether backpressure threshold reached
        """
        return {
            "events_received": self.events_received,
            "events_processed": self.events_processed,
            "flush_count": self.flush_count,
            "pending_upserts": len(self.pending_upserts),
            "pending_deletes": len(self.pending_deletes),
            "backpressure_active": self._backpressure_active,
        }

    async def run(self):
        """Main entry point - runs sync worker indefinitely.

        Standard flow:
            1. Ensure OpenSearch index exists
            2. Perform initial hydration from Materialize
            3. Start SUBSCRIBE streaming mode
            4. Handle events and flush to OpenSearch
            5. Retry on errors with exponential backoff

        Raises:
            NotImplementedError: If use_subscribe is disabled
        """
        logger.info(f"Starting {self.__class__.__name__} with SUBSCRIBE streaming")

        # Ensure OpenSearch index exists
        await self.ensure_index()

        # Perform initial hydration
        await self._initial_hydration()

        # Start SUBSCRIBE mode
        if self.settings.use_subscribe:
            await self._run_subscribe_mode()
        else:
            logger.error("Polling mode not implemented. Set use_subscribe=True")
            raise NotImplementedError("Polling mode removed in favor of SUBSCRIBE")

        logger.info(f"{self.__class__.__name__} stopped")

    # ========================================================================
    # Common implementation (private methods)
    # ========================================================================

    async def _initial_hydration(self):
        """Perform initial bulk load of data from Materialize to OpenSearch.

        Queries the materialized view for all existing data and bulk loads
        it into OpenSearch before starting the SUBSCRIBE stream. This ensures
        OpenSearch is in sync before incremental updates begin.
        """
        view_name = self.get_view_name()
        index_name = self.get_index_name()

        logger.info(f"Starting initial hydration from {view_name}...")

        try:
            # Create temporary client for query
            temp_client = MaterializeSubscribeClient()

            try:
                await temp_client.connect()

                # Query all existing data
                query = f"SELECT * FROM {view_name}"
                rows = await temp_client.query(query)

                if not rows:
                    logger.info("No existing data to hydrate")
                    return

                logger.info(f"Retrieved {len(rows)} rows from Materialize")

                # Transform rows to documents
                documents = []
                for row in rows:
                    doc = self.transform_event_to_doc(row)
                    if doc:
                        documents.append(doc)

                if documents:
                    # Bulk insert to OpenSearch
                    logger.info(f"Bulk loading {len(documents)} documents into OpenSearch...")
                    success, errors = await self.os.bulk_upsert(index_name, documents)

                    if errors > 0:
                        logger.warning(f"Initial hydration completed with {errors} errors")
                    else:
                        logger.info(f"✅ Initial hydration complete: {success} documents loaded")

                    self.events_processed += success
                else:
                    logger.warning("No valid documents after transformation")

            finally:
                await temp_client.close()

        except Exception as e:
            logger.error(f"Initial hydration failed: {e}", exc_info=True)
            logger.warning("Continuing with SUBSCRIBE streaming despite hydration failure")

    async def _run_subscribe_mode(self):
        """Run SUBSCRIBE streaming mode with retry logic.

        Establishes SUBSCRIBE connection to Materialize and streams events
        indefinitely. Implements exponential backoff retry on failures.
        """
        backoff = self.settings.retry_initial_delay
        view_name = self.get_view_name()

        while not self._shutdown.is_set():
            try:
                logger.info(f"Connecting to Materialize SUBSCRIBE for {view_name}...")

                # Create new client for this connection attempt
                self.subscribe_client = MaterializeSubscribeClient()
                await self.subscribe_client.connect()

                logger.info(f"Starting SUBSCRIBE to {view_name}")

                # This blocks until stream ends or error occurs
                await self.subscribe_client.subscribe_to_view(
                    view_name,
                    self._handle_events
                )

                # Stream ended normally
                logger.warning(f"SUBSCRIBE stream ended for {view_name}")

                # Flush any pending events
                await self._flush_batch()

                # Reset backoff on successful connection
                backoff = self.settings.retry_initial_delay

            except Exception as e:
                logger.error(f"SUBSCRIBE error for {view_name}: {e}", exc_info=True)

                # Flush pending events before retry
                try:
                    await self._flush_batch()
                except Exception as flush_error:
                    logger.error(f"Error flushing on error: {flush_error}")

                # Clean up client
                if self.subscribe_client:
                    try:
                        await self.subscribe_client.close()
                    except:
                        pass
                    self.subscribe_client = None

                # Exponential backoff
                if not self._shutdown.is_set():
                    logger.warning(f"Retrying SUBSCRIBE in {backoff:.1f}s...")
                    try:
                        await asyncio.wait_for(
                            self._shutdown.wait(),
                            timeout=backoff
                        )
                    except asyncio.TimeoutError:
                        # Normal timeout, continue to retry
                        pass

                    # Increase backoff for next retry
                    backoff = min(backoff * 2, self.settings.retry_max_delay)

        # Cleanup on shutdown
        if self.subscribe_client:
            await self.subscribe_client.close()

    async def _handle_events(self, events: list[SubscribeEvent]):
        """Process batch of events from SUBSCRIBE stream.

        Called by MaterializeSubscribeClient when timestamp advances.
        Routes to simple or consolidated processing based on
        should_consolidate_events().

        Args:
            events: List of SubscribeEvent from Materialize
        """
        if not events:
            return

        self.events_received += len(events)

        # Route to appropriate handler
        if self.should_consolidate_events():
            await self._handle_events_with_consolidation(events)
        else:
            await self._handle_events_simple(events)

        # Check backpressure
        total_pending = len(self.pending_upserts) + len(self.pending_deletes)
        if total_pending >= self.settings.backpressure_threshold:
            if not self._backpressure_active:
                logger.warning(
                    f"Backpressure threshold reached: {total_pending} pending events. "
                    f"Consider optimizing OpenSearch or increasing batch size."
                )
                self._backpressure_active = True
        elif total_pending <= self.settings.backpressure_resume:
            if self._backpressure_active:
                logger.info(f"Backpressure resolved: {total_pending} pending events")
                self._backpressure_active = False

        # Flush batch to OpenSearch
        await self._flush_batch()

    async def _handle_events_simple(self, events: list[SubscribeEvent]):
        """Simple event processing: direct insert/delete handling.

        Used when should_consolidate_events() returns False.
        Each INSERT/DELETE is processed independently.

        Args:
            events: List of SubscribeEvent to process
        """
        insert_ids = []
        delete_ids = []

        for event in events:
            if event.is_insert():
                # Insert - transform and queue for upsert
                doc = self.transform_event_to_doc(event.data)
                if doc:
                    self.pending_upserts.append(doc)
                    doc_id = self.get_doc_id(event.data)
                    if doc_id:
                        insert_ids.append(doc_id)
            elif event.is_delete():
                # Delete - extract ID and queue for deletion
                doc_id = self.get_doc_id(event.data)
                if doc_id:
                    self.pending_deletes.append(doc_id)
                    delete_ids.append(doc_id)

        # Log operations grouped by type for easy filtering
        if insert_ids:
            logger.info(f"  ➕ Inserts: {insert_ids}")
        if delete_ids:
            logger.info(f"  ❌ Deletes: {delete_ids}")

    async def _handle_events_with_consolidation(self, events: list[SubscribeEvent]):
        """Complex event processing: consolidate DELETE + INSERT = UPDATE.

        Used when should_consolidate_events() returns True.
        Events at the same timestamp are consolidated to handle updates
        efficiently (DELETE + INSERT = UPDATE).

        Args:
            events: List of SubscribeEvent to consolidate
        """
        # Consolidate by document ID: sum diffs, keep latest data
        consolidated: dict[str, tuple[int, dict]] = {}

        for event in events:
            doc_id = self.get_doc_id(event.data)
            if not doc_id:
                logger.warning("Skipping event without document ID")
                continue

            if doc_id not in consolidated:
                # First event for this document
                consolidated[doc_id] = (event.diff, event.data)
            else:
                # Consolidate with previous events
                prev_diff, prev_data = consolidated[doc_id]
                net_diff = prev_diff + event.diff
                # Keep insert data if we have one (has complete data)
                latest_data = event.data if event.is_insert() else prev_data
                consolidated[doc_id] = (net_diff, latest_data)

        # Process consolidated events and track document IDs by operation type
        upsert_ids = []
        delete_ids = []
        update_ids = []

        for doc_id, (net_diff, data) in consolidated.items():
            if net_diff > 0:
                # Net insert
                doc = self.transform_event_to_doc(data)
                if doc:
                    self.pending_upserts.append(doc)
                    upsert_ids.append(doc_id)
            elif net_diff < 0:
                # Net delete
                self.pending_deletes.append(doc_id)
                delete_ids.append(doc_id)
            else:
                # net_diff == 0: UPDATE (delete + insert cancelled out)
                # Treat as upsert with latest data
                doc = self.transform_event_to_doc(data)
                if doc:
                    self.pending_upserts.append(doc)
                    update_ids.append(doc_id)

        # Log operations grouped by type for easy filtering
        if upsert_ids:
            logger.info(f"  ➕ Inserts: {upsert_ids}")
        if update_ids:
            logger.info(f"  🔄 Updates: {update_ids}")
        if delete_ids:
            logger.info(f"  ❌ Deletes: {delete_ids}")

    async def _flush_batch(self):
        """Flush pending upserts and deletes to OpenSearch with retry logic.

        Performs bulk operations to sync accumulated events. Implements
        retry with exponential backoff for transient failures.
        """
        if not self.pending_upserts and not self.pending_deletes:
            return

        index_name = self.get_index_name()
        upsert_count = len(self.pending_upserts)
        delete_count = len(self.pending_deletes)

        # Capture pending lists for retry
        upserts_to_flush = self.pending_upserts
        deletes_to_flush = self.pending_deletes

        # Clear buffers immediately to accept new events
        self.pending_upserts = []
        self.pending_deletes = []

        # Flush with retry
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Flush upserts first
                if upserts_to_flush:
                    success, errors = await self.os.bulk_upsert(
                        index_name,
                        upserts_to_flush
                    )
                    logger.info(f"Upsert result: {success} succeeded, {errors} errors")
                    if errors > 0:
                        logger.warning(f"{errors} documents failed to upsert")

                # Flush deletes second
                if deletes_to_flush:
                    success, errors = await self.os.bulk_delete(
                        index_name,
                        deletes_to_flush
                    )
                    logger.info(f"Delete result: {success} succeeded, {errors} errors")
                    if errors > 0:
                        logger.warning(f"{errors} documents failed to delete")

                # Success
                self.events_processed += upsert_count + delete_count
                self.flush_count += 1

                logger.info(
                    f"Flush #{self.flush_count} complete. "
                    f"Total events processed: {self.events_processed}"
                )

                return

            except Exception as e:
                if attempt < max_attempts - 1:
                    retry_delay = (attempt + 1) * 2  # 2s, 4s
                    logger.warning(
                        f"Flush attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"Flush failed after {max_attempts} attempts: {e}",
                        exc_info=True
                    )
                    # Re-queue events for next flush attempt
                    self.pending_upserts.extend(upserts_to_flush)
                    self.pending_deletes.extend(deletes_to_flush)
                    raise
