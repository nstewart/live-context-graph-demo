"""Search API routes for OpenSearch queries.

These endpoints proxy search requests to OpenSearch, allowing the frontend
to perform semantic searches across denormalized order documents.
"""

from typing import Any

import httpx
from fastapi import APIRouter, Query, HTTPException

from src.config import get_settings

router = APIRouter(prefix="/api/search", tags=["Search"])

settings = get_settings()


@router.get("/orders")
async def search_orders(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, ge=1, le=20, description="Max results to return"),
) -> dict[str, Any]:
    """
    Search orders in OpenSearch using multi_match query.

    Searches across multiple fields: customer_name, store_name, store_zone,
    order_number, order_status. Uses fuzzy matching for typo tolerance.

    Returns the raw OpenSearch response for educational purposes.
    """
    # Build OpenSearch multi_match query
    search_body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": [
                    "customer_name^2",
                    "store_name^2",
                    "store_zone",
                    "order_number^3",
                    "order_status",
                ],
                "fuzziness": "AUTO",
                "operator": "or",
            }
        },
        "size": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.os_url}/orders/_search",
                json=search_body,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 404:
                # Index doesn't exist yet - return empty response structure
                return {
                    "took": 0,
                    "timed_out": False,
                    "_shards": {"total": 0, "successful": 0, "skipped": 0, "failed": 0},
                    "hits": {
                        "total": {"value": 0, "relation": "eq"},
                        "max_score": None,
                        "hits": [],
                    },
                }

            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="OpenSearch is not available. Ensure the search-sync service is running.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenSearch error: {e.response.text}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )
