"""Tool for searching store inventory."""

import asyncio
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
    Search for products available in a store's inventory.

    IMPORTANT: This tool ONLY returns products that are actually in stock at the specified store.
    If a product is not in the results, it means the store does NOT have it available.

    Use this tool to:
    - Find products by name or description
    - Check product availability and prices
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
        - unit_price: Price per unit
        - quantity_available: Current stock level
        - is_perishable: Whether product requires refrigeration
        - store_id: The store where item is available

    Example:
        search_inventory(query="chicken", store_id="store:BK-01")
        # Returns only chicken products actually in stock at BK-01
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

            # Extract inventory records
            inventory_items = {}
            for hit in inventory_data.get("hits", {}).get("hits", []):
                source = hit["_source"]
                product_id = source.get("product_id")
                if product_id:
                    inventory_items[product_id] = {
                        "stock_level": source.get("stock_level", 0),
                        "replenishment_eta": source.get("replenishment_eta"),
                    }

            if not inventory_items:
                return []

            # Step 2: Fetch product details for items in inventory (in parallel)
            # Query the API to get product names and details
            product_ids = list(inventory_items.keys())

            # Helper function to fetch a single product's details
            async def fetch_product_details(product_id: str) -> tuple[str, dict]:
                """Fetch details for a single product. Returns (product_id, details_dict)."""
                try:
                    detail_response = await client.get(
                        f"{settings.agent_api_base}/triples/subjects/{product_id}",
                        timeout=10.0,
                    )
                    if detail_response.status_code == 200:
                        product_data = detail_response.json()
                        # The API returns a SubjectInfo with a list of triples
                        # Parse triples into a property dict
                        props = {}
                        for triple in product_data.get("triples", []):
                            predicate = triple.get("predicate")
                            object_value = triple.get("object_value")
                            if predicate and object_value:
                                props[predicate] = object_value

                        # Extract product details from parsed properties
                        # Parse unit_price safely
                        unit_price = None
                        if "unit_price" in props:
                            try:
                                unit_price = float(props["unit_price"])
                            except (ValueError, TypeError):
                                pass

                        return (product_id, {
                            "product_name": props.get("product_name", product_id),
                            "category": props.get("category", "Unknown"),
                            "unit_price": unit_price,
                            "is_perishable": props.get("perishable", "false").lower() == "true",
                        })
                except httpx.HTTPError:
                    # If we can't fetch details, use product_id as name
                    return (product_id, {
                        "product_name": product_id,
                        "category": "Unknown",
                    })

            # Fetch all product details in parallel using asyncio.gather
            fetch_tasks = [fetch_product_details(pid) for pid in product_ids]
            product_results = await asyncio.gather(*fetch_tasks)

            # Convert results list to dict
            product_details = dict(product_results)

            # Step 3: Filter products by search query
            results = []
            query_lower = query.lower()

            for product_id, inv_info in inventory_items.items():
                product_info = product_details.get(product_id, {})
                product_name = product_info.get("product_name", product_id)
                category = product_info.get("category", "Unknown")

                # Search in product name, category, or product_id
                if (query_lower in product_name.lower() or
                    query_lower in category.lower() or
                    query_lower in product_id.lower()):

                    result = {
                        "product_id": product_id,
                        "product_name": product_name,
                        "category": category,
                        "unit_price": product_info.get("unit_price"),
                        "store_id": store_id,
                        "quantity_available": inv_info.get("stock_level", 0),
                        "replenishment_eta": inv_info.get("replenishment_eta"),
                        "is_perishable": product_info.get("is_perishable", False),
                    }

                    # Add warning if price is missing
                    if product_info.get("unit_price") is None:
                        result["warning"] = "Price information unavailable for this product"

                    results.append(result)

            # Return top results up to limit
            return results[:limit]

        except httpx.HTTPError as e:
            return [{"error": f"Search failed: {str(e)}"}]
