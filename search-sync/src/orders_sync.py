"""Orders sync worker - syncs orders_search_source_mv to OpenSearch using SUBSCRIBE streaming.

This worker extends BaseSubscribeWorker to sync order data from Materialize
to OpenSearch with real-time streaming and UPDATE consolidation.

Architecture:
    PostgreSQL → Materialize (CDC) → SUBSCRIBE Stream → Worker → OpenSearch
       (write)     (real-time)        (differential)    (batch)    (index)

Key Features:
    - Real-time streaming with < 2 second latency
    - UPDATE consolidation (DELETE + INSERT at same timestamp = UPDATE)
    - Enriched order data with customer, store, and delivery details
    - Line items as nested documents for efficient querying

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

import logging
from datetime import datetime
from typing import Optional

from src.base_subscribe_worker import BaseSubscribeWorker
from src.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


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
                },
            },
            "line_item_count": {"type": "integer"},
            "has_perishable_items": {"type": "boolean"},
            "search_text": {"type": "text"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


class OrdersSyncWorker(BaseSubscribeWorker):
    """Worker that syncs orders from Materialize to OpenSearch.

    Extends BaseSubscribeWorker with orders-specific transformation logic
    and UPDATE consolidation for efficient handling of order updates.

    Configuration:
        - View: orders_search_source_mv
        - Index: orders
        - Consolidation: Enabled (handles UPDATE = DELETE + INSERT)

    The worker syncs enriched order data including customer info, store
    details, delivery tasks, and line items as nested documents.
    """

    def get_view_name(self) -> str:
        """Return Materialize view name."""
        return "orders_search_source_mv"

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

    def _format_datetime(self, value) -> Optional[str]:
        """Format datetime value for OpenSearch.

        Handles multiple input types:
        - None → None
        - str → unchanged (already ISO format)
        - datetime → ISO format string
        - other → str(value)

        Args:
            value: Datetime value to format

        Returns:
            ISO format string or None
        """
        if value is None:
            return None

        # Already a string, return as-is
        if isinstance(value, str):
            return value

        # Convert datetime to ISO format
        if isinstance(value, datetime):
            return value.isoformat()

        # Fallback: convert to string
        return str(value)
