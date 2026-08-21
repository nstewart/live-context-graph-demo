"""Tool for managing order line items (add/update/delete)."""

import uuid
from typing import Optional

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def manage_order_lines(
    order_id: str,
    action: str,
    line_id: Optional[str] = None,
    product_id: Optional[str] = None,
    quantity: Optional[int] = None,
    unit_price: Optional[float] = None,
) -> dict:
    """
    Manage order line items - add, update, or delete products from an order.

    Use this tool to modify an existing order's line items. The order's total
    amount will be automatically recalculated by the materialized views.

    Args:
        order_id: The order ID (e.g., "order:FM-1001")
        action: The action to perform - "add", "update", or "delete"
        line_id: The line item ID (required for "update" and "delete" actions)
        product_id: The product ID (required for "add" action)
        quantity: The quantity (required for "add" and "update" actions)
        unit_price: The unit price (required for "add" action)

    Returns:
        Success status or error details

    Examples:
        # Add a new item
        manage_order_lines(
            order_id="order:FM-1001",
            action="add",
            product_id="product:P-0001",
            quantity=2,
            unit_price=3.99
        )

        # Update quantity
        manage_order_lines(
            order_id="order:FM-1001",
            action="update",
            line_id="orderline:FM-1001-001",
            quantity=5
        )

        # Delete an item
        manage_order_lines(
            order_id="order:FM-1001",
            action="delete",
            line_id="orderline:FM-1001-001"
        )
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        try:
            if action == "delete":
                if not line_id:
                    return {"success": False, "error": "line_id is required for delete action"}

                response = await client.delete(
                    f"{settings.agent_api_base}/freshmart/orders/{order_id}/line-items/{line_id}",
                    timeout=10.0,
                )

                if response.status_code == 204:
                    return {
                        "success": True,
                        "message": f"Line item {line_id} deleted from order {order_id}",
                        "action": "deleted",
                        "order_id": order_id,
                        "line_id": line_id,
                    }
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "error": "Line item not found or does not belong to this order",
                        "order_id": order_id,
                        "line_id": line_id,
                    }
                elif response.status_code == 400:
                    error_detail = response.json().get("detail", "Bad request")
                    return {
                        "success": False,
                        "error": error_detail,
                        "order_id": order_id,
                        "line_id": line_id,
                    }

            elif action == "update":
                if not line_id or not quantity:
                    return {"success": False, "error": "line_id and quantity are required for update action"}

                # Validate quantity
                if quantity <= 0:
                    return {
                        "success": False,
                        "error": "Quantity must be positive"
                    }
                if quantity > 1000:
                    return {
                        "success": False,
                        "error": "Quantity exceeds maximum allowed (1000)"
                    }

                response = await client.put(
                    f"{settings.agent_api_base}/freshmart/orders/{order_id}/line-items/{line_id}",
                    json={"quantity": quantity},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": f"Line item {line_id} updated with quantity {quantity}",
                        "action": "updated",
                        "order_id": order_id,
                        "line_id": line_id,
                        "line_item": response.json(),
                    }
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "error": "Line item not found",
                        "order_id": order_id,
                        "line_id": line_id,
                    }

            elif action == "add":
                if not product_id or not quantity or not unit_price:
                    return {
                        "success": False,
                        "error": "product_id, quantity, and unit_price are required for add action"
                    }

                # Validate quantity
                if quantity <= 0:
                    return {
                        "success": False,
                        "error": "Quantity must be positive"
                    }
                if quantity > 1000:
                    return {
                        "success": False,
                        "error": "Quantity exceeds maximum allowed (1000)"
                    }

                # Verify order exists and get store_id for inventory check
                order_response = await client.get(
                    f"{settings.agent_api_base}/freshmart/orders/{order_id}",
                    timeout=10.0,
                )
                if order_response.status_code == 404:
                    return {
                        "success": False,
                        "error": f"Order {order_id} not found"
                    }
                elif order_response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Failed to verify order existence (status {order_response.status_code})"
                    }

                order_data = order_response.json()
                store_id = order_data.get("store_id")

                # Validate stock availability at the order's store
                if store_id:
                    try:
                        inventory_query = {
                            "query": {
                                "bool": {
                                    "must": [
                                        {"term": {"store_id": store_id}},
                                        {"term": {"product_id": product_id}}
                                    ]
                                }
                            },
                            "size": 1,
                        }

                        inventory_response = await client.post(
                            f"{settings.agent_os_base}/inventory/_search",
                            json=inventory_query,
                            timeout=10.0,
                        )
                        inventory_response.raise_for_status()
                        inventory_data = inventory_response.json()

                        hits = inventory_data.get("hits", {}).get("hits", [])
                        if hits:
                            inventory = hits[0]["_source"]
                            stock_level = inventory.get("stock_level", 0)

                            if stock_level < quantity:
                                return {
                                    "success": False,
                                    "error": f"Insufficient stock for {product_id}",
                                    "requested": quantity,
                                    "available": stock_level,
                                    "store_id": store_id,
                                }
                        else:
                            return {
                                "success": False,
                                "error": f"Product {product_id} not available at store {store_id}",
                                "store_id": store_id,
                            }
                    except httpx.HTTPError as e:
                        # Log the error but continue - inventory validation is best-effort
                        # The server-side might have additional validation
                        pass

                # Get product info to determine perishable flag
                product_response = await client.get(
                    f"{settings.agent_api_base}/freshmart/products/{product_id}",
                    timeout=10.0,
                )
                perishable_flag = False
                if product_response.status_code == 200:
                    product = product_response.json()
                    perishable_flag = product.get("perishable", False)
                elif product_response.status_code == 404:
                    return {
                        "success": False,
                        "error": f"Product {product_id} not found"
                    }

                # Generate a UUID-based line ID to avoid race conditions
                line_uuid = str(uuid.uuid4())
                line_id = f"orderline:{line_uuid}"

                # Create new line item using batch endpoint
                response = await client.post(
                    f"{settings.agent_api_base}/freshmart/orders/{order_id}/line-items/batch",
                    json={
                        "line_items": [{
                            "line_id": line_id,
                            "product_id": product_id,
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "perishable_flag": perishable_flag,
                        }]
                    },
                    timeout=10.0,
                )

                if response.status_code == 201:
                    line_items = response.json()
                    return {
                        "success": True,
                        "message": f"Added {quantity}x {product_id} to order {order_id}",
                        "action": "added",
                        "order_id": order_id,
                        "line_item": line_items[0] if line_items else None,
                    }

            else:
                return {
                    "success": False,
                    "error": f"Invalid action: {action}. Must be 'add', 'update', or 'delete'",
                }

            # Generic error handling for non-200/201/204 responses
            if response.status_code >= 400:
                error_detail = response.json().get("detail", "API error") if response.text else "API error"
                return {
                    "success": False,
                    "error": f"API error ({response.status_code}): {error_detail}",
                    "order_id": order_id,
                }

        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"Request failed: {str(e)}",
                "order_id": order_id,
            }
