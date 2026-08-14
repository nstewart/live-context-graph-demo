"""Tool for searching orders via OpenSearch."""

from typing import Optional

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def search_orders(
    query: str,
    status: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search for orders using natural language.

    Use this tool to find orders by:
    - Customer name (e.g., "Alex Thompson")
    - Customer address (partial match)
    - Order number (e.g., the seeded order-number prefix + digits)
    - Store name or zone
    - Promotion code (e.g., "SUMMER25")

    Args:
        query: Natural language search query
        status: Optional filter by order status (CREATED, PICKING, OUT_FOR_DELIVERY, DELIVERED, CANCELLED)
        limit: Maximum number of results to return (default 10)

    Returns:
        List of matching orders with full details including:
        - Customer and store information
        - Order status and delivery windows
        - Promotion information (code, discount, discounted total)
        - Line items with product names, quantities, and prices
        - Line item count and perishable flags
    """
    settings = get_settings()

    # Build OpenSearch query
    # Check if query is a generic "get all" type query
    generic_queries = ["all", "all orders", "*", "show all", "list all", "everything"]
    is_generic = query.lower().strip() in generic_queries

    must_clauses = []

    if not is_generic:
        # Use multi_match for specific searches
        must_clauses.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "order_number^3",
                        "customer_name^2",
                        "promo_code^2",
                        "customer_address",
                        "store_name",
                        "store_zone",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        )

    if status:
        must_clauses.append({"term": {"order_status": status}})

    # Build the final query
    if must_clauses:
        query_body = {"bool": {"must": must_clauses}}
    else:
        # Match all documents when no filters
        query_body = {"match_all": {}}

    search_body = {
        "query": query_body,
        "size": limit,
        "sort": [{"effective_updated_at": {"order": "desc"}}],
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.agent_os_base}/orders/_search",
                json=search_body,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("hits", {}).get("hits", [])
            return [
                {
                    "order_id": hit["_source"]["order_id"],
                    "order_number": hit["_source"].get("order_number"),
                    "order_status": hit["_source"].get("order_status"),
                    "customer_name": hit["_source"].get("customer_name"),
                    "customer_address": hit["_source"].get("customer_address"),
                    "store_name": hit["_source"].get("store_name"),
                    "store_zone": hit["_source"].get("store_zone"),
                    "delivery_window_start": hit["_source"].get("delivery_window_start"),
                    "delivery_window_end": hit["_source"].get("delivery_window_end"),
                    "order_total_amount": hit["_source"].get("order_total_amount"),
                    "promo_code": hit["_source"].get("promo_code"),
                    "discount_percent": hit["_source"].get("discount_percent"),
                    "order_total_amount_with_discounts": hit["_source"].get("order_total_amount_with_discounts"),
                    "line_items": hit["_source"].get("line_items", []),
                    "line_item_count": hit["_source"].get("line_item_count", 0),
                    "has_perishable_items": hit["_source"].get("has_perishable_items"),
                    "score": hit.get("_score"),
                }
                for hit in hits
            ]
        except httpx.HTTPError as e:
            return [{"error": f"Search failed: {str(e)}"}]
