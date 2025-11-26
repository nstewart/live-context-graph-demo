"""OpenSearch client for indexing documents."""

import logging
from typing import Optional

from opensearchpy import AsyncOpenSearch, helpers

from src.config import get_settings

logger = logging.getLogger(__name__)

# Orders index mapping
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

# Inventory index mapping
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


class OpenSearchClient:
    """Client for OpenSearch operations."""

    def __init__(self):
        settings = get_settings()

        # Build auth if credentials provided
        http_auth = None
        if settings.os_user and settings.os_password:
            http_auth = (settings.os_user, settings.os_password)

        self.client = AsyncOpenSearch(
            hosts=[{"host": settings.os_host, "port": settings.os_port}],
            http_auth=http_auth,
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False,
        )
        self.orders_index = "orders"
        self.inventory_index = "inventory"

    async def close(self):
        """Close the client."""
        await self.client.close()

    async def ensure_index(self, index_name: str, mapping: dict):
        """Ensure an index exists with the correct mapping."""
        try:
            exists = await self.client.indices.exists(index=index_name)
            if not exists:
                logger.info(f"Creating index: {index_name}")
                await self.client.indices.create(index=index_name, body=mapping)
            else:
                logger.info(f"Index already exists: {index_name}")
        except Exception as e:
            logger.error(f"Error ensuring index {index_name}: {e}")
            raise

    async def setup_indices(self):
        """Set up all required indices."""
        await self.ensure_index(self.orders_index, ORDERS_INDEX_MAPPING)
        await self.ensure_index(self.inventory_index, INVENTORY_INDEX_MAPPING)

    async def bulk_upsert(self, index_name: str, documents: list[dict]) -> tuple[int, int]:
        """
        Bulk upsert documents into an index.

        Args:
            index_name: Target index
            documents: List of documents to upsert

        Returns:
            Tuple of (success_count, error_count)
        """
        if not documents:
            return 0, 0

        actions = []
        for doc in documents:
            doc_id = doc.get("order_id") or doc.get("inventory_id") or doc.get("id")
            actions.append(
                {
                    "_index": index_name,
                    "_id": doc_id,
                    "_source": doc,
                }
            )

        try:
            success, errors = await helpers.async_bulk(
                self.client,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
            )
            error_count = len(errors) if errors else 0

            # Log detailed errors for debugging
            if errors:
                for error in errors[:5]:  # Log first 5 errors
                    logger.error(f"Bulk upsert error detail: {error}")

            return success, error_count
        except Exception as e:
            logger.error(f"Bulk upsert failed: {e}")
            return 0, len(documents)

    async def bulk_delete(self, index_name: str, doc_ids: list[str]) -> tuple[int, int]:
        """
        Bulk delete documents from an index.

        Args:
            index_name: Target index
            doc_ids: List of document IDs to delete

        Returns:
            Tuple of (success_count, error_count)
        """
        if not doc_ids:
            return 0, 0

        actions = []
        for doc_id in doc_ids:
            actions.append(
                {
                    "_op_type": "delete",
                    "_index": index_name,
                    "_id": doc_id,
                }
            )

        try:
            success, errors = await helpers.async_bulk(
                self.client,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
            )
            error_count = len(errors) if errors else 0
            return success, error_count
        except Exception as e:
            logger.error(f"Bulk delete failed: {e}")
            return 0, len(doc_ids)

    async def search_orders(
        self,
        query: str,
        status: Optional[str] = None,
        size: int = 10,
    ) -> list[dict]:
        """
        Search orders using full-text search.

        Args:
            query: Search query string
            status: Optional status filter
            size: Maximum results to return

        Returns:
            List of matching order documents
        """
        # Build search query with support for product searches in line items
        # Use "should" to match either order fields OR product fields
        should_clauses = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["search_text", "order_number^2", "customer_name^1.5"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            {
                "nested": {
                    "path": "line_items",
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": ["line_items.product_name^2", "line_items.category"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        }
                    },
                }
            }
        ]

        must_clauses = [{"bool": {"should": should_clauses, "minimum_should_match": 1}}]

        if status:
            must_clauses.append({"term": {"order_status": status}})

        search_body = {
            "query": {"bool": {"must": must_clauses}},
            "size": size,
            "sort": [{"effective_updated_at": {"order": "desc"}}],
        }

        try:
            response = await self.client.search(index=self.orders_index, body=search_body)
            hits = response.get("hits", {}).get("hits", [])
            return [hit["_source"] for hit in hits]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def health_check(self) -> bool:
        """Check OpenSearch connectivity."""
        try:
            health = await self.client.cluster.health()
            return health.get("status") in ("green", "yellow")
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
