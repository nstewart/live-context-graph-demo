"""Search API routes for OpenSearch queries.

These endpoints proxy search requests to OpenSearch, allowing the frontend
to perform semantic searches across denormalized order documents.
"""

import asyncio
import logging
from typing import Any, Optional

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
EMBEDDING_TIMEOUT = 30.0

# The knn_vector field the embedding SMT writes into the orders index:
# embedded column `embedding_text` + default `_embedding` suffix.
EMBEDDING_FIELD = "embedding_text_embedding"


async def embed_query(text: str) -> list[float]:
    """Embed a query string via the embedding service (OpenAI-compatible).

    The same service backs the ingest-time SMT, so query and document vectors
    come from the identical model (BAAI/bge-small-en-v1.5, 384-dim).
    """
    url = f"{settings.embedding_service_url}/v1/embeddings"
    async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT) as client:
        response = await client.post(
            url,
            json={"input": text, "model": "bge-small"},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


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
            detail="OpenSearch is not available. Ensure the Kafka Connect sink pipeline is running.",
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
    store_zone: Optional[str] = Query(default=None),
    order_status: Optional[str] = Query(default=None),
    service: FreshMartService = Depends(get_freshmart_service),
) -> dict[str, Any]:
    """
    Vector (kNN) search across orders, hydrated with live data from Materialize.

    Pipeline:
        1. Embed the query text via the embedding service (BAAI/bge-small-en-v1.5, 384-dim).
        2. Run an OpenSearch knn search against the `orders` index — this
           answers "which orders are semantically relevant?".
        3. For each hit, look up the *current* order state in Materialize
           (orders_with_lines_mv) — this answers "what does the order
           contain right now?".
        4. Merge the OS scoring metadata with the live Materialize fields
           and return a unified result list.

    Orders that no longer exist in Materialize (e.g. deleted) are dropped.
    """
    # 1. Embed query via the embedding service (same model as ingest-time SMT).
    try:
        vector = await embed_query(q)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.error(f"Embedding service unavailable: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Embedding service unavailable — check the embedding-service container.")
    except Exception as e:
        logger.error(f"Failed to embed query: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to embed query.")

    # 2. Build OpenSearch knn body
    filters = []
    if store_zone:
        filters.append({"term": {"store_zone": store_zone}})
    if order_status:
        filters.append({"term": {"order_status": order_status}})

    if filters:
        search_body = {
            "query": {
                "bool": {
                    "must": {"knn": {EMBEDDING_FIELD: {"vector": list(vector), "k": limit}}},
                    "filter": filters,
                }
            },
            "_source": ["order_id", EMBEDDING_FIELD, "embedding_text", "mz_timestamp"],
            "size": limit,
        }
    else:
        search_body = {
            "query": {
                "knn": {
                    EMBEDDING_FIELD: {
                        "vector": list(vector),
                        "k": limit,
                    }
                }
            },
            "_source": ["order_id", EMBEDDING_FIELD, "embedding_text", "mz_timestamp"],
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
            detail="OpenSearch is not available. Ensure the Kafka Connect sink pipeline is running.",
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

    # 3. Hydrate all hits from Materialize concurrently (avoid N+1 round-trips).
    hits = os_result.get("hits", {}).get("hits", []) or []

    async def _hydrate(hit: dict) -> dict | None:
        source = hit.get("_source", {}) or {}
        order_id = source.get("order_id") or hit.get("_id")
        if not order_id:
            return None
        try:
            # Hydrate from orders_with_lines_mv so line_items carry live
            # dynamic pricing (live_price/base_price) straight from Materialize,
            # rather than from the (potentially staler) search index.
            order = await service.get_order_with_lines(order_id)
        except Exception as e:
            logger.warning(f"Failed to hydrate order {order_id} from Materialize: {e}", exc_info=True)
            return None
        if order is None:
            logger.debug(f"Skipping {order_id}: not found in Materialize")
            return None

        # model_dump(mode="json") serializes Decimal as str; convert to float.
        live = order.model_dump(mode="json")
        if live.get("order_total_amount") is not None:
            live["order_total_amount"] = float(live["order_total_amount"])

        # Start from live Materialize fields (including line_items); then layer
        # in OS-only fields that must survive (embedding vector, score).
        merged: dict[str, Any] = {**live}
        merged.update({
            "order_id": order_id,
            "score": hit.get("_score"),
            "embedding": source.get(EMBEDDING_FIELD) or [],
            "embedding_text": source.get("embedding_text"),
        })
        return merged

    hydrated = await asyncio.gather(*[_hydrate(h) for h in hits])
    results = [r for r in hydrated if r is not None]

    return {"results": results, "query": q, "total": len(results)}


@router.get("/index-stats")
async def get_index_stats() -> dict[str, Any]:
    """Return total document count for the orders index."""
    try:
        async with httpx.AsyncClient(timeout=OPENSEARCH_TIMEOUT) as client:
            response = await client.get(f"{settings.os_url}/orders/_count")
            if response.status_code == 404:
                return {"doc_count": 0}
            response.raise_for_status()
            return {"doc_count": response.json().get("count", 0)}
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to OpenSearch: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="OpenSearch is not available.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


IMPACT_INDEXES = ["orders", "inventory"]


@router.get("/impact")
async def get_index_impact(
    since_mz_timestamp: int = Query(..., description="mz_timestamp lower bound from write-triple"),
) -> dict[str, Any]:
    """Count documents re-indexed across all indexes at or after a given mz_timestamp.

    Queries both the orders and inventory indexes. Returns combined impacted/total
    counts plus a per-index breakdown.
    """
    range_query = {"query": {"range": {"mz_timestamp": {"gte": since_mz_timestamp}}}}
    try:
        async with httpx.AsyncClient(timeout=OPENSEARCH_TIMEOUT) as client:
            async def fetch_index(index: str) -> tuple[str, dict]:
                total_r, impact_r = await asyncio.gather(
                    client.get(f"{settings.os_url}/{index}/_count"),
                    client.post(
                        f"{settings.os_url}/{index}/_count",
                        json=range_query,
                        headers={"Content-Type": "application/json"},
                    ),
                )
                if total_r.status_code == 404:
                    return index, {"impacted": 0, "total": 0}
                total_r.raise_for_status()
                if impact_r.status_code == 404:
                    idx_impacted = 0
                else:
                    impact_r.raise_for_status()
                    idx_impacted = impact_r.json().get("count", 0)
                return index, {"impacted": idx_impacted, "total": total_r.json().get("count", 0)}

            results = await asyncio.gather(*[fetch_index(idx) for idx in IMPACT_INDEXES])
            breakdown = dict(results)
            total = sum(v["total"] for v in breakdown.values())
            impacted = sum(v["impacted"] for v in breakdown.values())
            pct = round(impacted / total * 100, 1) if total > 0 else 0.0
            return {"impacted": impacted, "total": total, "pct": pct, "breakdown": breakdown}
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to OpenSearch: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="OpenSearch is not available.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
