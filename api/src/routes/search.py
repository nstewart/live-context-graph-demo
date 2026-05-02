"""Search API routes for OpenSearch queries.

These endpoints proxy search requests to OpenSearch, allowing the frontend
to perform semantic searches across denormalized order documents.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException

from src.config import get_settings
from src.freshmart.service import FreshMartService
from src.routes.freshmart import get_freshmart_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])

settings = get_settings()

# Constants for search configuration
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20
OPENSEARCH_TIMEOUT = 10.0


# Module-level lazy-init embedder singleton. The fastembed model is heavyweight,
# so we only construct it on first use and reuse it across requests.
_query_embedder = None


def get_query_embedder():
    """Return a lazy-initialized fastembed text embedder.

    Returns an object with an `embed(texts: list[str]) -> list[list[float]]`
    method producing 384-dim vectors using BAAI/bge-small-en-v1.5.
    """
    global _query_embedder
    if _query_embedder is None:
        try:
            from fastembed import TextEmbedding

            class _Embedder:
                def __init__(self):
                    self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

                def embed(self, texts):
                    return [[float(x) for x in v] for v in self._model.embed(texts)]

            _query_embedder = _Embedder()
        except ImportError as e:
            raise RuntimeError(
                "fastembed not installed - run: pip install fastembed"
            ) from e
    return _query_embedder


@router.get("/orders")
async def search_orders(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT, description="Max results to return"),
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
        async with httpx.AsyncClient(timeout=OPENSEARCH_TIMEOUT) as client:
            response = await client.post(
                f"{settings.os_url}/orders/_search",
                json=search_body,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 404:
                # Index doesn't exist yet - return empty response structure
                logger.info("OpenSearch index 'orders' does not exist yet, returning empty results")
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

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to OpenSearch: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="OpenSearch is not available. Ensure the search-sync service is running.",
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenSearch returned error status {e.response.status_code}: {e.response.text}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"OpenSearch error: {e.response.text}",
        )
    except Exception as e:
        logger.error(f"Unexpected error during search: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/vector/orders")
async def vector_search_orders(
    q: str = Query(..., min_length=1, description="Natural language search query"),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
    service: FreshMartService = Depends(get_freshmart_service),
) -> dict[str, Any]:
    """
    Vector (kNN) search across orders, hydrated with live data from Materialize.

    Pipeline:
        1. Embed the query text with fastembed (BAAI/bge-small-en-v1.5, 384-dim).
        2. Run an OpenSearch knn search against the `orders` index — this
           answers "which orders are semantically relevant?".
        3. For each hit, look up the *current* order state in Materialize
           (orders_with_lines_mv) — this answers "what does the order
           contain right now?".
        4. Merge the OS scoring metadata with the live Materialize fields
           and return a unified result list.

    Orders that no longer exist in Materialize (e.g. deleted) are dropped.
    """
    # 1. Embed query
    embedder = get_query_embedder()
    vector = embedder.embed([q])[0]

    # 2. Build OpenSearch knn body
    search_body = {
        "query": {
            "knn": {
                "embedding": {
                    "vector": list(vector),
                    "k": limit,
                }
            }
        },
        "_source": ["order_id", "embedding_text", "embedded_at"],
        "size": limit,
    }

    try:
        async with httpx.AsyncClient(timeout=OPENSEARCH_TIMEOUT) as client:
            response = await client.post(
                f"{settings.os_url}/orders/_search",
                json=search_body,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 404:
                logger.info(
                    "OpenSearch index 'orders' does not exist yet, returning empty vector results"
                )
                return {"results": [], "query": q, "total": 0}

            response.raise_for_status()
            os_result = response.json()

    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to OpenSearch: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="OpenSearch is not available. Ensure the search-sync service is running.",
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"OpenSearch returned error status {e.response.status_code}: {e.response.text}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail=f"OpenSearch error: {e.response.text}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during vector search: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Vector search failed: {str(e)}",
        )

    # 3 + 4. Hydrate each hit from Materialize and merge
    hits = os_result.get("hits", {}).get("hits", []) or []
    results: list[dict[str, Any]] = []

    for hit in hits:
        source = hit.get("_source", {}) or {}
        order_id = source.get("order_id") or hit.get("_id")
        if not order_id:
            continue

        # Live hydration via Materialize
        try:
            order = await service.get_order(order_id)
        except Exception as e:
            logger.warning(
                f"Failed to hydrate order {order_id} from Materialize: {e}",
                exc_info=True,
            )
            continue

        if order is None:
            # Order was deleted between indexing and now - skip
            logger.debug(f"Skipping {order_id}: not found in Materialize")
            continue

        merged: dict[str, Any] = {
            "order_id": order_id,
            "score": hit.get("_score"),
            "embedding_text": source.get("embedding_text"),
            "embedded_at": source.get("embedded_at"),
        }
        # Merge live fields (Pydantic v2). Live values win over OS source on
        # conflicts because Materialize represents the current truth.
        live = order.model_dump(mode="json")
        merged.update(live)
        # Re-pin the score / OS-only fields so they aren't clobbered if the
        # OrderFlat ever grows fields with the same names.
        merged["order_id"] = order_id
        merged["score"] = hit.get("_score")
        merged["embedding_text"] = source.get("embedding_text")
        merged["embedded_at"] = source.get("embedded_at")
        results.append(merged)

    return {"results": results, "query": q, "total": len(results)}
