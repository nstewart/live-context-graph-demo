"""Search API routes for OpenSearch queries.

These endpoints proxy search requests to OpenSearch, allowing the frontend
to perform semantic searches across denormalized order documents.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

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
# Single budget covering both the embedding model's lazy load and inference,
# so a query-time embed can't hang the route for two back-to-back timeouts.
EMBED_TIMEOUT = 30.0


def _parse_line_items(value: Any) -> list:
    """Normalize the OpenSearch line_items field into a list.

    Materialize sinks the jsonb line_items column to Kafka as a JSON string
    (Avro string), so the OpenSearch _source carries a string. Older/other
    paths may carry an actual list. Handle both; never raise.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


# Module-level lazy-init embedder singleton. The fastembed model is heavyweight,
# so we only construct it on first use and reuse it across requests.
_query_embedder = None
_embedder_lock = threading.Lock()


def get_query_embedder():
    """Return a lazy-initialized fastembed text embedder.

    Returns an object with an `embed(texts: list[str]) -> list[list[float]]`
    method producing 384-dim vectors using BAAI/bge-small-en-v1.5.
    """
    global _query_embedder
    with _embedder_lock:
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
            detail="OpenSearch is not available. Ensure the opensearch and kafka-connect services are running.",
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
    # 1. Embed query — run in a thread so the model load/inference doesn't block the event loop.
    try:
        async with asyncio.timeout(EMBED_TIMEOUT):
            embedder = await asyncio.to_thread(get_query_embedder)
            vector = (await asyncio.to_thread(embedder.embed, [q]))[0]
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Embedding model unavailable — check API logs.")

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
                    # Vector field is produced by the perfect-embeddings SMT,
                    # which names its output <column>_embedding — here the
                    # embedding_text column becomes embedding_text_embedding.
                    "must": {"knn": {"embedding_text_embedding": {"vector": list(vector), "k": limit}}},
                    "filter": filters,
                }
            },
            "_source": ["order_id", "embedding_text_embedding", "embedding_text", "line_items"],
            "size": limit,
        }
    else:
        search_body = {
            "query": {
                "knn": {
                    "embedding_text_embedding": {
                        "vector": list(vector),
                        "k": limit,
                    }
                }
            },
            "_source": ["order_id", "embedding_text_embedding", "embedding_text", "line_items"],
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
            detail="OpenSearch is not available. Ensure the opensearch and kafka-connect services are running.",
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
            order = await service.get_order(order_id)
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

        # Start from live Materialize fields; then layer in OS-only fields that
        # must survive (embedding, line_items, score — not present in OrderFlat).
        merged: dict[str, Any] = {**live}
        merged.update({
            "order_id": order_id,
            "score": hit.get("_score"),
            # Response key stays "embedding" for the web; the source field is
            # the SMT's embedding_text_embedding vector.
            "embedding": source.get("embedding_text_embedding") or [],
            "embedding_text": source.get("embedding_text"),
            # Line items come from OpenSearch (indexed from Materialize CDC via
            # the Kafka sink). They carry live_price, base_price, etc. because
            # orders_with_lines_mv joins inventory_items_with_dynamic_pricing_mv.
            # Materialize sinks the jsonb column as a JSON string, so parse it
            # back into a list here.
            "line_items": _parse_line_items(source.get("line_items")),
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
    since_mz_timestamp: int = Query(..., description="epoch-ms lower bound from write-triple"),
) -> dict[str, Any]:
    """Count documents re-indexed across all indexes at or after a given timestamp.

    Queries both the orders and inventory indexes. Returns combined impacted/total
    counts plus a per-index breakdown.

    `mz_timestamp` is stamped onto every doc by the Kafka Connect InsertField
    transform from the Kafka record timestamp, which Materialize sets to the
    change's logical timestamp (epoch ms). It advances on every re-index — including
    cascade updates where a view's own `effective_updated_at` would not — so it
    counts the true set of docs touched by a write. `since_mz_timestamp` is a
    wall-clock epoch-ms lower bound captured just before the write.
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


# ── Embedding SMT metrics (via Jolokia) ───────────────────────────────────────

JOLOKIA_TIMEOUT = 5.0

# Stable ObjectName: the orders connector sets transforms.embed.metrics.id=orders.
EMBEDDING_MBEAN = 'com.materialize.connect.smt.embedding:type=EmbeddingDiff,id="orders"'
EMBEDDING_MBEAN_ATTRS = [
    "EmbeddingsComputed",
    "EmbeddingsSkipped",
    "EmbeddingsPossible",
    "SkipRatio",
]

_UNAVAILABLE = {"computed": 0, "skipped": 0, "possible": 0, "skip_ratio": 0.0, "available": False}


class EmbeddingMetrics(BaseModel):
    """Diff counters from the embedding SMT. `available` is False when the
    MBean can't be read (Connect/Jolokia down, or connector not yet running)."""
    computed: int
    skipped: int
    possible: int
    skip_ratio: float
    available: bool


@router.get("/embedding-metrics", response_model=EmbeddingMetrics)
async def embedding_metrics() -> EmbeddingMetrics:
    """Read the embedding SMT's diff counters from the Connect worker via Jolokia.

    Degrades gracefully: returns available=False with zeroed counters rather
    than erroring, so the UI can render a neutral state.
    """
    url = f"{settings.jolokia_url}/jolokia/"
    body = {"type": "read", "mbean": EMBEDDING_MBEAN, "attribute": EMBEDDING_MBEAN_ATTRS}
    try:
        async with httpx.AsyncClient(timeout=JOLOKIA_TIMEOUT) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Jolokia embedding-metrics read failed: %s", e)
        return EmbeddingMetrics(**_UNAVAILABLE)

    # Guard the shape: a 200 with a non-dict value (or non-dict payload) must
    # still degrade to available=False, not raise.
    if not isinstance(payload, dict) or payload.get("status") != 200:
        return EmbeddingMetrics(**_UNAVAILABLE)
    value = payload.get("value")
    if not isinstance(value, dict):
        return EmbeddingMetrics(**_UNAVAILABLE)

    return EmbeddingMetrics(
        computed=int(value.get("EmbeddingsComputed", 0)),
        skipped=int(value.get("EmbeddingsSkipped", 0)),
        possible=int(value.get("EmbeddingsPossible", 0)),
        skip_ratio=float(value.get("SkipRatio", 0.0)),
        available=True,
    )


# ── Cross-encoder reranking ───────────────────────────────────────────────────

RERANK_TIMEOUT = 30.0
DEFAULT_RERANK_CANDIDATES = 25


def _build_rerank_doc_parts(live: dict, line_items: list) -> dict:
    """Assemble the document the cross-encoder reads, split by provenance so the
    UI can show which parts came from where:

      - ``mz``    — the order head (number + status), read live from Materialize
                    at query time (the ``feature_fetch_ms`` stage).
      - ``index`` — the line items (name, category, live price, stock), served
                    from the OpenSearch ``_source`` retrieved in the kNN stage.

    ``doc`` is the exact concatenation handed to the model (``mz`` + ``index``).
    The business signals ride along in the input on purpose; a cross-encoder
    weights query↔text relevance and may not act on them, but they are present.
    """
    items = []
    for it in line_items:
        name = it.get("product_name")
        if not name:
            continue
        cat = it.get("category") or ""
        price = it.get("live_price") if it.get("live_price") is not None else it.get("unit_price")
        stock = it.get("current_stock")
        attrs = []
        if cat:
            attrs.append(cat)
        if price is not None:
            try:
                attrs.append(f"${float(price):.2f}")
            except (TypeError, ValueError):
                pass
        if isinstance(stock, (int, float)):
            attrs.append("in stock" if stock > 0 else "out of stock")
        items.append(f"{name} ({', '.join(attrs)})" if attrs else name)

    head = f"Order {live.get('order_number', '')}".strip()
    status = live.get("order_status")
    if status:
        head += f", status {status}"

    index_seg = "Items: " + "; ".join(items) if items else ""
    doc = f"{head}. {index_seg}" if index_seg else head
    return {"doc": doc, "mz": head, "index": index_seg}


def _build_rerank_doc(live: dict, line_items: list) -> str:
    """The exact string handed to the cross-encoder (mz head + indexed items)."""
    return _build_rerank_doc_parts(live, line_items)["doc"]


@router.get("/vector/orders/reranked")
async def reranked_vector_search_orders(
    q: str = Query(..., min_length=1, description="Natural language search query"),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT),
    candidates: int = Query(default=DEFAULT_RERANK_CANDIDATES, ge=5, le=100),
    service: FreshMartService = Depends(get_freshmart_service),
) -> dict[str, Any]:
    """Two-stage retrieval: kNN recall → cross-encoder rerank.

    1. Embed `q`, kNN the top-`candidates` orders from OpenSearch (recall).
    2. Hydrate each candidate from Materialize and build a fresh document
       (items + category + live price + stock + status). [feature_fetch_ms]
    3. Score (query, doc) pairs with the shim's cross-encoder; reorder. [rerank_ms]

    Returns both orderings + each candidate's rerank input/score + stage timings,
    so the UI can compare kNN vs reranked and show exactly what the model read.
    """
    t0 = time.perf_counter()
    try:
        async with asyncio.timeout(EMBED_TIMEOUT):
            embedder = await asyncio.to_thread(get_query_embedder)
            vector = (await asyncio.to_thread(embedder.embed, [q]))[0]
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Embedding model unavailable — check API logs.")

    search_body = {
        "query": {"knn": {"embedding_text_embedding": {"vector": list(vector), "k": candidates}}},
        "_source": ["order_id", "embedding_text", "line_items"],
        "size": candidates,
    }
    try:
        async with httpx.AsyncClient(timeout=OPENSEARCH_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.os_url}/orders/_search",
                json=search_body,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 404:
                return {"query": q, "model": None, "results": [], "timings": {}}
            resp.raise_for_status()
            os_result = resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="OpenSearch is not available.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch error: {e.response.text}")
    retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)

    hits = os_result.get("hits", {}).get("hits", []) or []
    if not hits:
        return {"query": q, "model": None, "results": [], "timings": {"retrieval_ms": retrieval_ms}}

    # Stage 2a: hydrate candidates from Materialize — the fresh feature fetch.
    t1 = time.perf_counter()

    async def _hydrate(rank: int, hit: dict) -> dict | None:
        source = hit.get("_source", {}) or {}
        order_id = source.get("order_id") or hit.get("_id")
        if not order_id:
            return None
        try:
            order = await service.get_order(order_id)
        except Exception as e:
            logger.warning(f"Failed to hydrate order {order_id} from Materialize: {e}", exc_info=True)
            return None
        if order is None:
            return None
        live = order.model_dump(mode="json")
        line_items = _parse_line_items(source.get("line_items"))
        parts = _build_rerank_doc_parts(live, line_items)
        return {
            "order_id": order_id,
            "order_number": live.get("order_number") or order_id,
            "status": live.get("order_status"),
            "knn_score": round(float(hit.get("_score", 0.0)), 4),
            "original_rank": rank,  # 1-based, in kNN order
            "doc": parts["doc"],          # exact string the model scored
            "doc_mz": parts["mz"],        # order head — live from Materialize
            "doc_index": parts["index"],  # line items — from the search index
        }

    hydrated = await asyncio.gather(*[_hydrate(i + 1, h) for i, h in enumerate(hits)])
    cand = [c for c in hydrated if c is not None]
    feature_fetch_ms = round((time.perf_counter() - t1) * 1000, 1)
    if not cand:
        return {"query": q, "model": None, "results": [],
                "timings": {"retrieval_ms": retrieval_ms, "feature_fetch_ms": feature_fetch_ms}}

    # Stage 2b: cross-encoder rerank over the fresh docs.
    t2 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=RERANK_TIMEOUT) as client:
            rr = await client.post(settings.rerank_url, json={"query": q, "documents": [c["doc"] for c in cand]})
            rr.raise_for_status()
            payload = rr.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("Rerank call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Reranker unavailable: {e}")
    rerank_ms = round((time.perf_counter() - t2) * 1000, 1)

    scores = payload.get("scores") or []
    if len(scores) != len(cand):
        raise HTTPException(status_code=502, detail="Reranker returned a mismatched number of scores")
    for c, s in zip(cand, scores):
        c["rerank_score"] = round(float(s), 4)

    reranked = sorted(cand, key=lambda c: c["rerank_score"], reverse=True)
    for new_rank, c in enumerate(reranked, start=1):
        c["new_rank"] = new_rank
        c["delta"] = c["original_rank"] - new_rank  # >0 = moved up vs kNN

    return {
        "query": q,
        "model": payload.get("model"),
        "candidate_count": len(cand),
        "limit": limit,
        "timings": {"retrieval_ms": retrieval_ms, "feature_fetch_ms": feature_fetch_ms, "rerank_ms": rerank_ms},
        "results": reranked,  # full candidate set in reranked order; UI shows top `limit`
    }
