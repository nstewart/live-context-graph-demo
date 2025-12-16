"""Tool for searching store inventory with dynamic pricing."""

from typing import Optional

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def search_inventory(
    query: str,
    store_id: str = "store:BK-01",
    limit: int = 10,
) -> list[dict]:
    """
    Search for products available in a store's inventory with dynamic pricing.

    IMPORTANT: This tool ONLY returns products that are actually in stock at the specified store.
    If a product is not in the results, it means the store does NOT have it available.

    Use this tool to:
    - Find products by name or description
    - Check product availability and current prices
    - See dynamic pricing adjustments (zone-based, perishable discounts, low stock premiums)
    - Verify what items are actually in stock before creating orders

    Args:
        query: Product name or description to search for (e.g., "milk", "chicken", "bread")
        store_id: Store to search in (default: store:BK-01)
        limit: Maximum number of results (default: 10)

    Returns:
        List of matching products ONLY from store inventory with:
        - product_id: Unique product identifier
        - product_name: Full product name
        - category: Product category (Dairy, Produce, Meat, etc.)
        - base_price: Original unit price
        - live_price: Current dynamic price (includes all 7 pricing factors)
        - price_change: Dollar difference between live and base price
        - quantity_available: Current stock level
        - is_perishable: Whether product requires refrigeration
        - store_id: The store where item is available
        - store_zone: Store neighborhood (MAN=Manhattan, BK=Brooklyn, etc.)
        - zone_adjustment: Zone-based pricing multiplier (if available)
        - perishable_adjustment: Perishable discount multiplier (if available)
        - local_stock_adjustment: Store-level scarcity multiplier (if available)
        - popularity_adjustment: Sales ranking multiplier (if available)
        - scarcity_adjustment: Global stock scarcity multiplier (if available)
        - demand_multiplier: Recent sales trends multiplier (if available)
        - demand_premium: High demand premium multiplier (if available)

    Example:
        search_inventory(query="chicken", store_id="store:BK-01")
        # Returns only chicken products actually in stock at BK-01 with dynamic pricing
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        try:
            # Step 1: Search inventory in OpenSearch
            inventory_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"store_id": store_id}}
                        ]
                    }
                },
                "size": 1000,  # Get all inventory for the store
            }

            inventory_response = await client.post(
                f"{settings.agent_os_base}/inventory/_search",
                json=inventory_query,
                timeout=10.0,
            )
            inventory_response.raise_for_status()
            inventory_data = inventory_response.json()

            # Extract inventory records with all product and pricing data
            inventory_items = {}
            for hit in inventory_data.get("hits", {}).get("hits", []):
                source = hit["_source"]
                product_id = source.get("product_id")
                if product_id:
                    inventory_items[product_id] = {
                        "product_name": source.get("product_name"),
                        "category": source.get("category"),
                        "stock_level": source.get("stock_level", 0),
                        "replenishment_eta": source.get("replenishment_eta"),
                        "perishable": source.get("perishable", False),
                        # Dynamic pricing fields
                        "base_price": source.get("base_price"),
                        "live_price": source.get("live_price"),
                        "price_change": source.get("price_change"),
                        # All 7 pricing adjustments
                        "zone_adjustment": source.get("zone_adjustment"),
                        "perishable_adjustment": source.get("perishable_adjustment"),
                        "local_stock_adjustment": source.get("local_stock_adjustment"),
                        "popularity_adjustment": source.get("popularity_adjustment"),
                        "scarcity_adjustment": source.get("scarcity_adjustment"),
                        "demand_multiplier": source.get("demand_multiplier"),
                        "demand_premium": source.get("demand_premium"),
                        # Store info
                        "store_zone": source.get("store_zone"),
                        "store_name": source.get("store_name"),
                    }

            if not inventory_items:
                return []

            # Step 2: Filter products by search query (all data is now in inventory_items)
            results = []
            query_lower = query.lower()

            for product_id, inv_info in inventory_items.items():
                product_name = inv_info.get("product_name", product_id)
                category = inv_info.get("category", "Unknown")

                # Search in product name, category, or product_id
                if (query_lower in product_name.lower() or
                    query_lower in category.lower() or
                    query_lower in product_id.lower()):

                    result = {
                        "product_id": product_id,
                        "product_name": product_name,
                        "category": category,
                        # Dynamic pricing fields
                        "base_price": inv_info.get("base_price"),
                        "live_price": inv_info.get("live_price"),
                        "price_change": inv_info.get("price_change"),
                        # Inventory details
                        "store_id": store_id,
                        "store_zone": inv_info.get("store_zone"),
                        "quantity_available": inv_info.get("stock_level", 0),
                        "replenishment_eta": inv_info.get("replenishment_eta"),
                        "is_perishable": inv_info.get("perishable", False),
                    }

                    # Add all 7 pricing adjustments if available (optional, for detailed queries)
                    if inv_info.get("zone_adjustment") is not None:
                        result["zone_adjustment"] = inv_info.get("zone_adjustment")
                    if inv_info.get("perishable_adjustment") is not None:
                        result["perishable_adjustment"] = inv_info.get("perishable_adjustment")
                    if inv_info.get("local_stock_adjustment") is not None:
                        result["local_stock_adjustment"] = inv_info.get("local_stock_adjustment")
                    if inv_info.get("popularity_adjustment") is not None:
                        result["popularity_adjustment"] = inv_info.get("popularity_adjustment")
                    if inv_info.get("scarcity_adjustment") is not None:
                        result["scarcity_adjustment"] = inv_info.get("scarcity_adjustment")
                    if inv_info.get("demand_multiplier") is not None:
                        result["demand_multiplier"] = inv_info.get("demand_multiplier")
                    if inv_info.get("demand_premium") is not None:
                        result["demand_premium"] = inv_info.get("demand_premium")

                    # Add warning if price is missing
                    if inv_info.get("live_price") is None:
                        result["warning"] = "Price information unavailable for this product"

                    results.append(result)

            # Return top results up to limit
            return results[:limit]

        except httpx.HTTPError as e:
            return [{"error": f"Search failed: {str(e)}"}]
