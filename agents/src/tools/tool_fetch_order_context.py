"""Tool for fetching detailed order context from OpenSearch."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings


async def _fetch_inventory_pricing(
    client: httpx.AsyncClient,
    settings,
    store_ids: set[str],
    product_ids: set[str],
) -> dict[tuple[str, str], dict]:
    """Fetch live pricing from inventory index for given store/product combinations.

    Returns a dict keyed by (store_id, product_id) with pricing info.
    """
    if not store_ids or not product_ids:
        return {}

    pricing_map = {}

    # Query inventory for each store (inventory is store-specific)
    for store_id in store_ids:
        try:
            inventory_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"store_id": store_id}},
                            {"terms": {"product_id": list(product_ids)}},
                        ]
                    }
                },
                "size": len(product_ids),
            }

            response = await client.post(
                f"{settings.agent_os_base}/inventory/_search",
                json=inventory_query,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            for hit in data.get("hits", {}).get("hits", []):
                source = hit["_source"]
                product_id = source.get("product_id")
                if product_id:
                    pricing_map[(store_id, product_id)] = {
                        "live_price": source.get("live_price"),
                        "base_price": source.get("base_price"),
                        "price_change": source.get("price_change"),
                    }
        except httpx.HTTPError:
            # If inventory query fails for a store, continue with others
            pass

    return pricing_map


@tool
async def fetch_order_context(order_ids: list[str]) -> list[dict]:
    """
    Fetch detailed context for one or more orders from OpenSearch.

    Use this tool after searching to get full order details including:
    - Customer information
    - Store information
    - Delivery task status
    - Order line items with both order-time and current live pricing

    Args:
        order_ids: List of order IDs to fetch (e.g., ["order:FM-1001", "order:FM-1002"])

    Returns:
        List of detailed order records with customer, store, and delivery info.
        Line items include:
        - unit_price: The price when the order was placed (historical)
        - live_price: The current dynamic price at the store
        - base_price: The product catalog base price
    """
    settings = get_settings()
    results = []

    async with httpx.AsyncClient() as client:
        try:
            # Query OpenSearch for multiple orders at once
            search_body = {
                "query": {
                    "terms": {
                        "order_id": order_ids
                    }
                },
                "size": len(order_ids),
            }

            response = await client.post(
                f"{settings.agent_os_base}/orders/_search",
                json=search_body,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            # Extract order details from hits
            found_orders = {}
            for hit in data.get("hits", {}).get("hits", []):
                source = hit["_source"]
                order_id = source.get("order_id")
                if order_id:
                    found_orders[order_id] = {
                        "order_id": order_id,
                        "order_number": source.get("order_number"),
                        "order_status": source.get("order_status"),
                        "customer_id": source.get("customer_id"),
                        "customer_name": source.get("customer_name"),
                        "customer_email": source.get("customer_email"),
                        "customer_address": source.get("customer_address"),
                        "store_id": source.get("store_id"),
                        "store_name": source.get("store_name"),
                        "store_zone": source.get("store_zone"),
                        "store_address": source.get("store_address"),
                        "delivery_window_start": source.get("delivery_window_start"),
                        "delivery_window_end": source.get("delivery_window_end"),
                        "order_total_amount": source.get("order_total_amount"),
                        "assigned_courier_id": source.get("assigned_courier_id"),
                        "delivery_task_status": source.get("delivery_task_status"),
                        "delivery_eta": source.get("delivery_eta"),
                        "line_items": source.get("line_items", []),
                        "line_item_count": source.get("line_item_count", 0),
                        "has_perishable_items": source.get("has_perishable_items"),
                        "effective_updated_at": source.get("effective_updated_at"),
                    }

            # Collect all unique store_id and product_id combinations for pricing lookup
            store_ids = set()
            product_ids = set()
            for order in found_orders.values():
                store_id = order.get("store_id")
                if store_id:
                    store_ids.add(store_id)
                for item in order.get("line_items", []):
                    product_id = item.get("product_id")
                    if product_id:
                        product_ids.add(product_id)

            # Fetch live pricing from inventory
            pricing_map = await _fetch_inventory_pricing(
                client, settings, store_ids, product_ids
            )

            # Enrich line items with live pricing
            for order in found_orders.values():
                store_id = order.get("store_id")
                for item in order.get("line_items", []):
                    product_id = item.get("product_id")
                    pricing = pricing_map.get((store_id, product_id), {})
                    item["live_price"] = pricing.get("live_price")
                    item["base_price"] = pricing.get("base_price")
                    item["price_change"] = pricing.get("price_change")

            # Return results in the same order as requested, with errors for missing orders
            for order_id in order_ids:
                if order_id in found_orders:
                    results.append(found_orders[order_id])
                else:
                    results.append({"order_id": order_id, "error": "Order not found"})

        except httpx.HTTPError as e:
            # If OpenSearch query fails, return errors for all orders
            for order_id in order_ids:
                results.append({"order_id": order_id, "error": f"Search failed: {str(e)}"})

    return results
