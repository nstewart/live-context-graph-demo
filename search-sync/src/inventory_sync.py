"""Inventory sync worker - syncs store_inventory_mv to OpenSearch using SUBSCRIBE streaming.

This worker extends BaseSubscribeWorker to sync inventory data from Materialize
to OpenSearch with real-time streaming and simple insert/delete processing.

Architecture:
    PostgreSQL → Materialize (CDC) → SUBSCRIBE Stream → Worker → OpenSearch
       (write)     (real-time)        (differential)    (batch)    (index)

Key Features:
    - Real-time streaming with < 2 second latency
    - Simple insert/delete processing (no consolidation needed)
    - Enriched inventory with product and store denormalization
    - Ingredient-aware search with synonyms (milk, whole milk, etc.)

Example:
    Basic usage::

        os_client = OpenSearchClient()
        worker = InventorySyncWorker(os_client)

        try:
            await worker.run()  # Runs indefinitely with retry
        except KeyboardInterrupt:
            worker.stop()
            logger.info("Graceful shutdown complete")
"""

import logging
from typing import Optional

from src.base_subscribe_worker import BaseSubscribeWorker
from src.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


# Inventory index mapping - matches INVENTORY_INDEX_MAPPING from opensearch_client.py
INVENTORY_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "inventory_id": {"type": "keyword"},
            "store_id": {"type": "keyword"},
            "product_id": {"type": "keyword"},
            "stock_level": {"type": "integer"},
            "replenishment_eta": {"type": "date"},
            "product_name": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
                "analyzer": "ingredient_analyzer",
            },
            "category": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
                "analyzer": "ingredient_analyzer",
            },
            "unit_price": {"type": "float"},
            "perishable": {"type": "boolean"},
            "unit_weight_grams": {"type": "integer"},
            "store_name": {
                "type": "text",
                "copy_to": "search_text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "store_zone": {"type": "keyword"},
            "store_address": {"type": "text"},
            "availability_status": {"type": "keyword"},
            "low_stock": {"type": "boolean"},
            "effective_updated_at": {"type": "date"},
            "search_text": {
                "type": "text",
                "analyzer": "ingredient_analyzer",
            },
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ingredient_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "ingredient_synonyms"],
                }
            },
            "filter": {
                "ingredient_synonyms": {
                    "type": "synonym",
                    "synonyms": [
                        "milk, whole milk, 2% milk, skim milk, dairy milk",
                        "eggs, egg, dozen eggs, large eggs",
                        "chicken, poultry, chicken breast, chicken thigh",
                        "beef, ground beef, steak, sirloin",
                        "bread, loaf, sourdough, whole wheat bread",
                        "pasta, penne, spaghetti, linguine, noodles",
                        "rice, white rice, brown rice, jasmine rice",
                        "cheese, cheddar, mozzarella, parmesan",
                        "tomato, tomatoes, cherry tomatoes",
                        "onion, onions, yellow onion, white onion",
                        "garlic, garlic cloves, minced garlic",
                        "olive oil, extra virgin olive oil, evoo",
                        "butter, unsalted butter, salted butter",
                        "salt, sea salt, kosher salt, table salt",
                        "pepper, black pepper, ground pepper",
                    ]
                }
            },
        },
    },
}


class InventorySyncWorker(BaseSubscribeWorker):
    """Worker that syncs inventory from Materialize to OpenSearch.

    Extends BaseSubscribeWorker with inventory-specific transformation logic.
    Uses simple insert/delete processing without consolidation since inventory
    updates are typically full replacements rather than incremental updates.

    Configuration:
        - View: store_inventory_mv
        - Index: inventory
        - Consolidation: Disabled (simple processing)

    The worker syncs enriched inventory data with denormalized product and
    store information for efficient searching by product name, category,
    and location.
    """

    def get_view_name(self) -> str:
        """Return Materialize view name."""
        return "store_inventory_mv"

    def get_index_name(self) -> str:
        """Return OpenSearch index name."""
        return "inventory"

    def should_consolidate_events(self) -> bool:
        """Disable UPDATE consolidation for inventory.

        Inventory updates are typically full record replacements (stock level
        changes, replenishment updates), so simple insert/delete processing
        is sufficient and more efficient.
        """
        return False

    def get_index_mapping(self) -> dict:
        """Return OpenSearch index mapping for inventory."""
        return INVENTORY_INDEX_MAPPING

    def get_doc_id(self, data: dict) -> str:
        """Extract inventory ID from event data."""
        return data.get("inventory_id")

    def transform_event_to_doc(self, data: dict) -> Optional[dict]:
        """Transform Materialize inventory event to OpenSearch document.

        Converts raw Materialize row data into properly formatted OpenSearch
        document with type conversions and null handling. Includes denormalized
        product and store information for efficient searching.

        Args:
            data: Raw event data from Materialize with fields:
                - inventory_id (required): Primary key
                - store_id, product_id: Foreign keys
                - stock_level: Current stock quantity
                - product_name, category, unit_price: Denormalized product info
                - store_name, store_zone: Denormalized store info
                - availability_status, low_stock: Computed availability flags

        Returns:
            OpenSearch document dict, or None if inventory_id is missing

        Example:
            Input::

                data = {
                    "inventory_id": "inventory:INV-00123",
                    "product_id": "product:prod0001",
                    "store_id": "store:MAN-01",
                    "stock_level": 45,
                    "product_name": "Organic Whole Milk 1 Gallon",
                    "unit_price": 5.99,
                    "availability_status": "IN_STOCK",
                    ...
                }

            Output::

                {
                    "inventory_id": "inventory:INV-00123",
                    "product_id": "product:prod0001",
                    "store_id": "store:MAN-01",
                    "stock_level": 45,
                    "product_name": "Organic Whole Milk 1 Gallon",
                    "unit_price": 5.99,
                    "availability_status": "IN_STOCK",
                    ...
                }
        """
        try:
            # Validate required field
            if not data.get("inventory_id"):
                logger.warning("Skipping event without inventory_id")
                return None

            # Build OpenSearch document
            doc = {
                "inventory_id": data.get("inventory_id"),
                "store_id": data.get("store_id"),
                "product_id": data.get("product_id"),
                "stock_level": data.get("stock_level"),
                "replenishment_eta": data.get("replenishment_eta"),
                "effective_updated_at": data.get("effective_updated_at"),
                # Product details (denormalized from products_flat)
                "product_name": data.get("product_name"),
                "category": data.get("category"),
                "unit_price": float(data["unit_price"]) if data.get("unit_price") else None,
                "perishable": data.get("perishable"),
                "unit_weight_grams": data.get("unit_weight_grams"),
                # Store details (denormalized from stores_flat)
                "store_name": data.get("store_name"),
                "store_zone": data.get("store_zone"),
                "store_address": data.get("store_address"),
                # Computed fields
                "availability_status": data.get("availability_status"),
                "low_stock": data.get("low_stock"),
            }

            return doc

        except Exception as e:
            logger.error(f"Error transforming inventory event: {e}", exc_info=True)
            return None
