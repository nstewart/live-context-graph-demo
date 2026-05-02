"""Orders sync worker - syncs orders_with_lines_mv to OpenSearch using SUBSCRIBE streaming.

This worker extends BaseSubscribeWorker to sync order data from Materialize
to OpenSearch with real-time streaming and UPDATE consolidation.

Architecture:
    PostgreSQL → Materialize (CDC) → SUBSCRIBE Stream → Worker → OpenSearch
       (write)     (real-time)        (differential)    (batch)    (index)

Key Features:
    - Real-time streaming with < 2 second latency
    - UPDATE consolidation (DELETE + INSERT at same timestamp = UPDATE)
    - Enriched order data with customer, store, and delivery details
    - Line items with dynamic pricing as nested documents for efficient querying

Example:
    Basic usage::

        os_client = OpenSearchClient()
        worker = OrdersSyncWorker(os_client)

        try:
            await worker.run()  # Runs indefinitely with retry
        except KeyboardInterrupt:
            worker.stop()
            logger.info("Graceful shutdown complete")
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from src.base_subscribe_worker import BaseSubscribeWorker
from src.embedder import Embedder, build_embedding_text, compute_hash
from src.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


# Fields that are excluded from a "patch-only" update — i.e., these are
# either the vector itself or fields whose source is the embedding pipeline.
# When line items are unchanged we patch every other field but leave these alone.
_EMBEDDING_FIELDS = {"embedding", "embedding_text", "embedded_at"}


# Orders index mapping - matches ORDERS_INDEX_MAPPING from opensearch_client.py
ORDERS_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "order_id": {"type": "keyword"},
            "order_number": {"type": "keyword", "copy_to": "search_text"},
            "order_status": {"type": "keyword"},
            "store_id": {"type": "keyword"},
            "customer_id": {"type": "keyword"},
            "delivery_window_start": {"type": "date"},
            "delivery_window_end": {"type": "date"},
            "order_total_amount": {"type": "float"},
            "customer_name": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "customer_email": {"type": "keyword"},
            "customer_address": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "store_name": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "store_zone": {"type": "keyword"},
            "store_address": {"type": "text"},
            "assigned_courier_id": {"type": "keyword"},
            "delivery_task_status": {"type": "keyword"},
            "delivery_eta": {"type": "date"},
            "effective_updated_at": {"type": "date"},
            "line_items": {
                "type": "nested",
                "properties": {
                    "line_id": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "product_name": {
                        "type": "text",
                        "copy_to": "search_text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "category": {
                        "type": "text",
                        "copy_to": "search_text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "float"},
                    "line_amount": {"type": "float"},
                    "line_sequence": {"type": "integer"},
                    "perishable_flag": {"type": "boolean"},
                    "unit_weight_grams": {"type": "integer"},
                    # Dynamic pricing fields from inventory
                    "inventory_id": {"type": "keyword"},
                    "base_price": {"type": "float"},
                    "live_price": {"type": "float"},
                    "price_change": {"type": "float"},
                    "zone_adjustment": {"type": "float"},
                    "perishable_adjustment": {"type": "float"},
                    "local_stock_adjustment": {"type": "float"},
                    "popularity_adjustment": {"type": "float"},
                    "scarcity_adjustment": {"type": "float"},
                    "demand_multiplier": {"type": "float"},
                    "demand_premium": {"type": "float"},
                    "product_sale_count": {"type": "integer"},
                    "product_total_stock": {"type": "integer"},
                    "current_stock_level": {"type": "integer"},
                },
            },
            "line_item_count": {"type": "integer"},
            "has_perishable_items": {"type": "boolean"},
            "search_text": {"type": "text"},
            # Vector embedding of the order's line items (BAAI/bge-small-en-v1.5)
            "embedding": {
                "type": "knn_vector",
                "dimension": 384,
            },
            "embedding_text": {"type": "keyword"},
            "embedded_at": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index": {
            "knn": True,
        },
    },
}


class OrdersSyncWorker(BaseSubscribeWorker):
    """Worker that syncs orders from Materialize to OpenSearch.

    Extends BaseSubscribeWorker with orders-specific transformation logic
    and UPDATE consolidation for efficient handling of order updates.

    Configuration:
        - View: orders_with_lines_mv
        - Index: orders
        - Consolidation: Enabled (handles UPDATE = DELETE + INSERT)

    The worker syncs enriched order data including customer info, store
    details, delivery tasks, and line items with dynamic pricing as nested documents.

    Vector embeddings:
        Each order document also carries a 384-dim ``knn_vector`` embedding
        of its line items (text: ``"name (category) | name (category) | ..."``).
        We use an MD5 hash of that text as a dedup key — only re-embed when
        the embedding text changes. Price/quantity-only updates use
        ``bulk_patch`` to avoid recomputing the vector.
    """

    def __init__(self, os_client: OpenSearchClient):
        super().__init__(os_client)
        # Maps order_id -> last embedded MD5 hash. Stored in memory only;
        # rebuilds naturally on restart since the next change will trigger
        # a re-embed.
        self._hash_cache: dict[str, str] = {}
        self._embedder = Embedder()

    def get_view_name(self) -> str:
        """Return Materialize view name."""
        return "orders_with_lines_mv"

    def get_index_name(self) -> str:
        """Return OpenSearch index name."""
        return "orders"

    def should_consolidate_events(self) -> bool:
        """Enable UPDATE consolidation for orders.

        Orders can be updated frequently (status changes, delivery updates),
        so we consolidate DELETE + INSERT at the same timestamp into a
        single UPDATE operation for efficiency.
        """
        return True

    def get_index_mapping(self) -> dict:
        """Return OpenSearch index mapping for orders."""
        return ORDERS_INDEX_MAPPING

    def get_doc_id(self, data: dict) -> str:
        """Extract order ID from event data."""
        return data.get("order_id")

    def transform_event_to_doc(self, data: dict) -> Optional[dict]:
        """Transform Materialize order event to OpenSearch document.

        Converts raw Materialize row data into properly formatted OpenSearch
        document with type conversions, nested line items, and null handling.

        Args:
            data: Raw event data from Materialize with fields:
                - order_id (required): Primary key
                - order_number: Human-readable order ID
                - order_status: Status enum (CREATED, PICKING, etc.)
                - customer_*: Customer information
                - store_*: Store information
                - delivery_*: Delivery details
                - line_items: JSON array of line items
                - order_total_amount: Total amount (string → float)

        Returns:
            OpenSearch document dict, or None if order_id is missing

        Example:
            Input::

                data = {
                    "order_id": "order:FM-1001",
                    "order_number": "FM-1001",
                    "order_status": "OUT_FOR_DELIVERY",
                    "order_total_amount": "45.99",
                    "line_items": [...],
                    ...
                }

            Output::

                {
                    "order_id": "order:FM-1001",
                    "order_number": "FM-1001",
                    "order_status": "OUT_FOR_DELIVERY",
                    "order_total_amount": 45.99,  # Converted to float
                    "line_items": [...],
                    ...
                }
        """
        try:
            # Validate required field
            if not data.get("order_id"):
                logger.warning("Skipping event without order_id")
                return None

            # Build OpenSearch document
            doc = {
                "order_id": data.get("order_id"),
                "order_number": data.get("order_number"),
                "order_status": data.get("order_status"),
                "store_id": data.get("store_id"),
                "customer_id": data.get("customer_id"),
                "delivery_window_start": self._format_datetime(data.get("delivery_window_start")),
                "delivery_window_end": self._format_datetime(data.get("delivery_window_end")),
                "order_total_amount": float(data["order_total_amount"]) if data.get("order_total_amount") else None,
                "customer_name": data.get("customer_name"),
                "customer_email": data.get("customer_email"),
                "customer_address": data.get("customer_address"),
                "store_name": data.get("store_name"),
                "store_zone": data.get("store_zone"),
                "store_address": data.get("store_address"),
                "assigned_courier_id": data.get("assigned_courier_id"),
                "delivery_task_status": data.get("delivery_task_status"),
                "delivery_eta": self._format_datetime(data.get("delivery_eta")),
                "line_items": data.get("line_items", []),
                "line_item_count": data.get("line_item_count", 0),
                "has_perishable_items": data.get("has_perishable_items", False),
                "effective_updated_at": self._format_datetime(data.get("effective_updated_at")),
            }

            return doc

        except Exception as e:
            logger.error(f"Error transforming order event: {e}", exc_info=True)
            return None

    async def _flush_batch(self, timestamp=None):
        """Flush pending events to OpenSearch with embedding-aware routing.

        Splits ``self.pending_upserts`` into two groups based on whether
        the order's line items have changed since we last embedded them:

        - **Hash changed (or new)**: embed the text, attach the vector
          (and ``embedding_text`` / ``embedded_at`` metadata), and
          ``bulk_upsert`` the full document.
        - **Hash unchanged**: build a patch with all fields except the
          embedding ones and ``bulk_patch`` it. The existing vector in
          OpenSearch is left untouched.

        Pending deletes still flow through ``bulk_delete`` unchanged.

        Args:
            timestamp: Optional Materialize logical timestamp for logging.
        """
        if not self.pending_upserts and not self.pending_deletes:
            return

        index_name = self.get_index_name()

        # Capture and clear pending buffers before async work so new events
        # can accumulate while we flush.
        upserts_to_process = self.pending_upserts
        deletes_to_flush = self.pending_deletes
        self.pending_upserts = []
        self.pending_deletes = []

        # Split upserts into "needs full embedding" vs "patch only"
        full_upserts: list[dict] = []
        patches: list[dict] = []

        # Bulk-embed all docs that need embedding in one shot.
        docs_needing_embedding: list[dict] = []
        texts_to_embed: list[str] = []

        for doc in upserts_to_process:
            order_id = doc.get("order_id")
            line_items = doc.get("line_items") or []
            embedding_text = build_embedding_text(line_items)
            new_hash = compute_hash(embedding_text)
            prev_hash = self._hash_cache.get(order_id)

            if prev_hash == new_hash and order_id is not None:
                # Embedding text unchanged -> patch non-vector fields only.
                patch_doc = {
                    k: v for k, v in doc.items() if k not in _EMBEDDING_FIELDS
                }
                patches.append({"_id": order_id, "doc": patch_doc})
            else:
                # New order or line items changed -> embed + full upsert.
                doc["embedding_text"] = embedding_text
                docs_needing_embedding.append(doc)
                texts_to_embed.append(embedding_text)
                # Update hash cache eagerly; if the embedding fails the
                # next event will reset it via re-embedding anyway.
                if order_id is not None:
                    self._hash_cache[order_id] = new_hash

        if docs_needing_embedding:
            vectors = self._embedder.embed(texts_to_embed)
            now_iso = datetime.now(timezone.utc).isoformat()
            for doc, vec in zip(docs_needing_embedding, vectors):
                doc["embedding"] = vec
                doc["embedded_at"] = now_iso
                full_upserts.append(doc)

        upsert_count = len(full_upserts)
        patch_count = len(patches)
        delete_count = len(deletes_to_flush)

        ts_str = f"mz_ts={timestamp} " if timestamp else ""
        ops = []
        if upsert_count:
            ops.append(f"{upsert_count} upserts (embed)")
        if patch_count:
            ops.append(f"{patch_count} patches (no-embed)")
        if delete_count:
            ops.append(f"{delete_count} deletes")
        if ops:
            logger.debug(
                f"  Bulk request @ {ts_str}-> {index_name}: {', '.join(ops)}"
            )

        # Flush with retry, mirroring the base-class behavior.
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if full_upserts:
                    success, errors = await self.os.bulk_upsert(
                        index_name, full_upserts
                    )
                    logger.info(
                        f"Upsert (with embedding) result: {success} succeeded, "
                        f"{errors} errors"
                    )

                if patches:
                    success, errors = await self.os.bulk_patch(
                        index_name, patches
                    )
                    logger.info(
                        f"Patch (no embedding) result: {success} succeeded, "
                        f"{errors} errors"
                    )

                if deletes_to_flush:
                    success, errors = await self.os.bulk_delete(
                        index_name, deletes_to_flush
                    )
                    logger.info(
                        f"Delete result: {success} succeeded, {errors} errors"
                    )

                self.events_processed += upsert_count + patch_count + delete_count
                self.flush_count += 1
                return

            except Exception as e:
                if attempt < max_attempts - 1:
                    retry_delay = (attempt + 1) * 2
                    logger.warning(
                        f"Flush attempt {attempt + 1}/{max_attempts} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        f"Flush failed after {max_attempts} attempts: {e}",
                        exc_info=True,
                    )
                    # Re-queue full upserts (unembedded form) and patches/deletes.
                    # Strip embedding-derived fields so the next attempt re-runs
                    # the embedder cleanly.
                    for doc in full_upserts:
                        for k in _EMBEDDING_FIELDS:
                            doc.pop(k, None)
                    self.pending_upserts.extend(full_upserts)
                    # Convert patches back to docs (best effort) so they retry.
                    for p in patches:
                        self.pending_upserts.append(
                            {"order_id": p["_id"], **p["doc"]}
                        )
                    self.pending_deletes.extend(deletes_to_flush)
                    raise

    async def _initial_hydration(self):
        """Override initial hydration to batch-embed all documents before indexing."""
        from src.mz_client_subscribe import MaterializeSubscribeClient

        view_name = self.get_view_name()
        index_name = self.get_index_name()

        logger.info(f"Starting initial hydration with embeddings from {view_name}...")

        try:
            temp_client = MaterializeSubscribeClient()
            try:
                await temp_client.connect()
                rows = await temp_client.query(f"SELECT * FROM {view_name}")
                if not rows:
                    logger.info("No existing data to hydrate")
                    return
                logger.info(f"Retrieved {len(rows)} rows from Materialize")

                documents = []
                for row in rows:
                    doc = self.transform_event_to_doc(row)
                    if doc:
                        documents.append(doc)

                if not documents:
                    logger.warning("No valid documents after transformation")
                    return

                # Batch-embed all documents in one shot
                self._embed_documents(documents)

                logger.info(f"Bulk loading {len(documents)} documents with embeddings into OpenSearch...")
                success, errors = await self.os.bulk_upsert(index_name, documents)
                if errors > 0:
                    logger.warning(f"Initial hydration completed with {errors} errors")
                else:
                    logger.info(f"Initial hydration complete: {success} documents loaded")
                self.events_processed += success
            finally:
                await temp_client.close()
        except Exception as e:
            logger.error(f"Initial hydration failed: {e}", exc_info=True)
            logger.warning("Continuing with SUBSCRIBE streaming despite hydration failure")

    def _embed_documents(self, documents: list[dict]) -> None:
        """Embed a batch of documents in-place, updating hash cache."""
        texts = []
        for doc in documents:
            line_items = doc.get("line_items") or []
            text = build_embedding_text(line_items)
            doc["embedding_text"] = text
            texts.append(text)

        if not texts:
            return

        vectors = self._embedder.embed(texts)
        now_iso = datetime.now(timezone.utc).isoformat()
        for doc, vec in zip(documents, vectors):
            doc["embedding"] = vec
            doc["embedded_at"] = now_iso
            order_id = doc.get("order_id")
            if order_id:
                self._hash_cache[order_id] = compute_hash(doc["embedding_text"])

    def _format_datetime(self, value) -> Optional[str]:
        """Format datetime value for OpenSearch ISO 8601."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, str):
            # Normalize PostgreSQL-style "YYYY-MM-DD HH:MM:SS+TZ" → ISO 8601
            # OpenSearch requires the T separator between date and time.
            if len(value) >= 19 and value[10] == " ":
                value = value[:10] + "T" + value[11:]
            return value

        return str(value)
