"""Tool for listing couriers and their schedules."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def list_couriers(store_id: str = None, status: str = None) -> list[dict]:
    """
    List couriers with their current status and task information.

    Use this tool to find couriers, check their availability, or see their delivery schedules.
    Can filter by home store or current status.

    Args:
        store_id: Optional store ID filter (e.g., "store:QNS-01"). Returns only couriers assigned to that store.
        status: Optional status filter. One of: OFF_SHIFT, AVAILABLE, ON_DELIVERY

    Returns:
        List of couriers with:
        - courier_id: Unique courier identifier (e.g., "courier:C-0001")
        - courier_name: Full name of the courier
        - home_store_id: The store this courier is assigned to
        - home_store_name: Name of the home store
        - vehicle_type: WALKING, BIKE, or SCOOTER
        - courier_status: Current status (OFF_SHIFT, AVAILABLE, ON_DELIVERY)
        - active_tasks: Number of currently active delivery tasks
        - completed_tasks: Number of completed tasks

    Status values:
        - OFF_SHIFT: Courier is not currently working
        - AVAILABLE: Courier is on shift and ready for deliveries
        - ON_DELIVERY: Courier is currently delivering an order

    Example workflows:
        1. "Who's available at the Queens store?"
           -> list_couriers(store_id="store:QNS-01", status="AVAILABLE")

        2. "Show me all couriers on delivery"
           -> list_couriers(status="ON_DELIVERY")

        3. "List couriers for Manhattan stores"
           -> First call list_stores(zone="MAN") to get store IDs
           -> Then call list_couriers(store_id="store:MAN-01") for each store
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        try:
            params = {"limit": 100}
            if store_id:
                params["store_id"] = store_id
            if status:
                params["status"] = status

            response = await client.get(
                f"{settings.agent_api_base}/freshmart/couriers",
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            couriers = response.json()

            # Return simplified courier info with task counts
            result = []
            for courier in couriers:
                tasks = courier.get("tasks", [])
                active_tasks = sum(1 for t in tasks if t.get("task_status") in ("ASSIGNED", "IN_PROGRESS"))
                completed_tasks = sum(1 for t in tasks if t.get("task_status") == "COMPLETED")

                result.append({
                    "courier_id": courier.get("courier_id"),
                    "courier_name": courier.get("courier_name"),
                    "home_store_id": courier.get("home_store_id"),
                    "home_store_name": courier.get("home_store_name"),
                    "vehicle_type": courier.get("vehicle_type"),
                    "courier_status": courier.get("courier_status"),
                    "active_tasks": active_tasks,
                    "completed_tasks": completed_tasks,
                })

            return result

        except httpx.HTTPError as e:
            return [{"error": f"Failed to fetch couriers: {str(e)}"}]
