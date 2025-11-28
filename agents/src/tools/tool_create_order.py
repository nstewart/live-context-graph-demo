"""Tool for creating orders."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def create_order(
    customer_id: str,
    store_id: str = "store:BK-01",
    items: list[dict] = None,
    delivery_window_hours: int = 2,
) -> dict:
    """
    Create a new order for a customer in FreshMart.

    IMPORTANT:
    - Orders are ALWAYS created in the CREATED state initially.
    - This tool automatically validates that items are available in the store's inventory
    - Only items that are in stock will be added to the order
    - Items not available will be reported but won't prevent order creation
    - Unit prices are AUTOMATICALLY set to the current live_price from inventory (dynamic pricing)

    Use this tool after:
    1. Customer has been created (or exists)
    2. Customer has approved the order

    Args:
        customer_id: The customer placing the order (e.g., "customer:abc123")
        store_id: The store fulfilling the order (default: store:BK-01)
        items: List of items with product_id and quantity
               Example: [{"product_id": "product:PROD-001", "quantity": 2}]
               Note: unit_price is automatically determined from inventory's live_price
        delivery_window_hours: Hours from now for delivery window (default: 2)

    Returns:
        Order information including order_id, order_number, total_amount, and inventory validation details

    Example:
        create_order(
            customer_id="customer:abc123",
            store_id="store:BK-01",
            items=[
                {"product_id": "product:PROD-001", "quantity": 2},
                {"product_id": "product:PROD-002", "quantity": 1}
            ]
        )
    """
    settings = get_settings()

    if not items:
        return {
            "success": False,
            "error": "Cannot create order without items",
        }

    # Validate items against store inventory
    async with httpx.AsyncClient() as client:
        try:
            # Query inventory for this store
            inventory_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"store_id": store_id}}
                        ]
                    }
                },
                "size": 1000,
            }

            inventory_response = await client.post(
                f"{settings.agent_os_base}/inventory/_search",
                json=inventory_query,
                timeout=10.0,
            )
            inventory_response.raise_for_status()
            inventory_data = inventory_response.json()

            # Build map of available products with stock levels and live pricing
            available_inventory = {}
            for hit in inventory_data.get("hits", {}).get("hits", []):
                source = hit["_source"]
                product_id = source.get("product_id")
                stock_level = source.get("stock_level", 0)
                if product_id and stock_level > 0:
                    available_inventory[product_id] = {
                        "stock_level": stock_level,
                        "inventory_id": source.get("inventory_id"),
                        "live_price": source.get("live_price"),
                        "base_price": source.get("base_price"),
                        "is_perishable": source.get("perishable", False),
                    }

            # Filter items to only those available in inventory
            valid_items = []
            skipped_items = []
            insufficient_stock_items = []

            for item in items:
                product_id = item.get("product_id")
                requested_qty = item.get("quantity", 1)

                if product_id not in available_inventory:
                    skipped_items.append({
                        "product_id": product_id,
                        "reason": "not available at this store",
                    })
                elif available_inventory[product_id]["stock_level"] < requested_qty:
                    insufficient_stock_items.append({
                        "product_id": product_id,
                        "requested": requested_qty,
                        "available": available_inventory[product_id]["stock_level"],
                    })
                    # Add item with available quantity and live price from inventory
                    valid_items.append({
                        "product_id": product_id,
                        "quantity": available_inventory[product_id]["stock_level"],
                        "unit_price": available_inventory[product_id]["live_price"],
                        "is_perishable": available_inventory[product_id]["is_perishable"],
                    })
                else:
                    # Use live price from inventory, not the price passed by the agent
                    valid_items.append({
                        "product_id": product_id,
                        "quantity": requested_qty,
                        "unit_price": available_inventory[product_id]["live_price"],
                        "is_perishable": available_inventory[product_id]["is_perishable"],
                    })

            # If no valid items, return error
            if not valid_items:
                return {
                    "success": False,
                    "error": "No requested items are available in stock at this store",
                    "store_id": store_id,
                    "skipped_items": skipped_items,
                    "available_products": list(available_inventory.keys()),
                }

            # Use valid_items for order creation
            items = valid_items

        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"Failed to validate inventory: {str(e)}",
            }

    # Generate unique order ID and number
    order_uuid = uuid4().hex[:8]
    order_id = f"order:FM-{order_uuid}"
    order_number = f"FM-{order_uuid.upper()}"

    # Calculate total
    total_amount = sum(item["quantity"] * item["unit_price"] for item in items)

    # Calculate delivery window
    now = datetime.utcnow()
    window_start = now + timedelta(hours=1)
    window_end = window_start + timedelta(hours=delivery_window_hours)

    # Build triples for order
    # IMPORTANT: order_status is ALWAYS set to "CREATED" initially
    order_triples = [
        {
            "subject_id": order_id,
            "predicate": "order_number",
            "object_value": order_number,
            "object_type": "string",
        },
        {
            "subject_id": order_id,
            "predicate": "placed_by",
            "object_value": customer_id,
            "object_type": "entity_ref",
        },
        {
            "subject_id": order_id,
            "predicate": "order_store",
            "object_value": store_id,
            "object_type": "entity_ref",
        },
        {
            "subject_id": order_id,
            "predicate": "order_status",
            "object_value": "CREATED",  # Always CREATED initially
            "object_type": "string",
        },
        {
            "subject_id": order_id,
            "predicate": "delivery_window_start",
            "object_value": window_start.isoformat() + "Z",
            "object_type": "timestamp",
        },
        {
            "subject_id": order_id,
            "predicate": "delivery_window_end",
            "object_value": window_end.isoformat() + "Z",
            "object_type": "timestamp",
        },
        {
            "subject_id": order_id,
            "predicate": "order_total_amount",
            "object_value": str(round(total_amount, 2)),
            "object_type": "float",
        },
    ]

    # Add line items as triples
    for idx, item in enumerate(items, start=1):
        line_item_id = f"orderline:{order_uuid}-{idx}"
        line_amount = item["quantity"] * item["unit_price"]

        order_triples.extend(
            [
                {
                    "subject_id": line_item_id,
                    "predicate": "line_of_order",
                    "object_value": order_id,
                    "object_type": "entity_ref",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "line_product",
                    "object_value": item["product_id"],
                    "object_type": "entity_ref",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "quantity",
                    "object_value": str(item["quantity"]),
                    "object_type": "int",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "order_line_unit_price",
                    "object_value": str(item["unit_price"]),
                    "object_type": "float",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "line_amount",
                    "object_value": str(round(line_amount, 2)),
                    "object_type": "float",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "line_sequence",
                    "object_value": str(idx),
                    "object_type": "int",
                },
                {
                    "subject_id": line_item_id,
                    "predicate": "perishable_flag",
                    "object_value": str(item.get("is_perishable", False)).lower(),
                    "object_type": "bool",
                },
            ]
        )

    # Create order via batch API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.agent_api_base}/triples/batch",
                json=order_triples,
                params={"validate": True},
                timeout=15.0,
            )
            response.raise_for_status()

            result = {
                "success": True,
                "order_id": order_id,
                "order_number": order_number,
                "order_status": "CREATED",  # Always CREATED
                "customer_id": customer_id,
                "store_id": store_id,
                "total_amount": round(total_amount, 2),
                "item_count": len(items),
                "delivery_window_start": window_start.isoformat() + "Z",
                "delivery_window_end": window_end.isoformat() + "Z",
            }

            # Add inventory validation details if any items were skipped or adjusted
            if skipped_items:
                result["skipped_items"] = skipped_items
                result["message"] = f"Order created with {len(items)} items. {len(skipped_items)} items were not available at this store."

            if insufficient_stock_items:
                result["adjusted_quantities"] = insufficient_stock_items
                if "message" in result:
                    result["message"] += f" {len(insufficient_stock_items)} items had quantities adjusted to match available stock."
                else:
                    result["message"] = f"Order created with {len(items)} items. {len(insufficient_stock_items)} items had quantities adjusted to match available stock."

            return result

        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"Failed to create order: {str(e)}",
            }
