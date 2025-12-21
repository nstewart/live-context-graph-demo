"""Tool for listing available stores."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def list_stores() -> list[dict]:
    """
    List all FreshMart store locations with their IDs and details.

    Use this tool FIRST when a user mentions a store by name or zone to find the correct store_id.
    Store IDs use abbreviated zone codes (e.g., QNS for Queens, MAN for Manhattan).

    Returns:
        List of stores with:
        - store_id: The unique store identifier (e.g., "store:QNS-01", "store:MAN-01")
        - store_name: Full store name (e.g., "FreshMart Queens 1")
        - zone: Zone abbreviation (MAN, BK, QNS, BX, SI)
        - address: Store address

    Zone abbreviations:
        - MAN = Manhattan
        - BK = Brooklyn
        - QNS = Queens
        - BX = Bronx
        - SI = Staten Island

    Example workflow:
        1. User asks: "What vegetables are available at the Queens store?"
        2. Call list_stores() to find Queens store IDs (store:QNS-01, store:QNS-02)
        3. Call search_inventory(query="vegetable", store_id="store:QNS-01")
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.agent_api_base}/freshmart/stores",
                timeout=10.0,
            )
            response.raise_for_status()
            stores = response.json()

            # Return simplified store info
            return [
                {
                    "store_id": store.get("store_id"),
                    "store_name": store.get("store_name"),
                    "zone": store.get("zone"),
                    "address": store.get("address"),
                }
                for store in stores
            ]

        except httpx.HTTPError as e:
            return [{"error": f"Failed to fetch stores: {str(e)}"}]
