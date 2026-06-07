"""Integration tests for Search API endpoints."""

from datetime import datetime, timezone
from typing import Optional

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import requires_db


class TestSearchOrdersAPI:
    """Tests for /api/search/orders endpoint."""

    @pytest.mark.asyncio
    async def test_search_orders_valid_query(self, async_client: AsyncClient):
        """GET /api/search/orders with valid query returns search results."""
        mock_response = {
            "took": 5,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "max_score": 1.5,
                "hits": [
                    {
                        "_index": "orders",
                        "_id": "order:FM-1001",
                        "_score": 1.5,
                        "_source": {
                            "order_id": "order:FM-1001",
                            "customer_name": "John Doe",
                            "order_status": "PLACED",
                        },
                    }
                ],
            },
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            response = await async_client.get("/api/search/orders", params={"q": "john"})
            assert response.status_code == 200
            data = response.json()
            assert "hits" in data
            assert data["hits"]["total"]["value"] == 2

    @pytest.mark.asyncio
    async def test_search_orders_empty_query_rejected(self, async_client: AsyncClient):
        """GET /api/search/orders with empty query returns 422."""
        response = await async_client.get("/api/search/orders", params={"q": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_orders_missing_query_rejected(self, async_client: AsyncClient):
        """GET /api/search/orders without query parameter returns 422."""
        response = await async_client.get("/api/search/orders")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_orders_limit_parameter(self, async_client: AsyncClient):
        """GET /api/search/orders respects limit parameter."""
        mock_response = {
            "took": 5,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": 10, "relation": "eq"},
                "max_score": 1.5,
                "hits": [],
            },
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            response = await async_client.get(
                "/api/search/orders", params={"q": "test", "limit": 10}
            )
            assert response.status_code == 200

            # Verify the request body sent to OpenSearch
            call_args = mock_post.call_args
            assert call_args is not None
            request_body = call_args.kwargs["json"]
            assert request_body["size"] == 10

    @pytest.mark.asyncio
    async def test_search_orders_limit_validation(self, async_client: AsyncClient):
        """GET /api/search/orders validates limit parameter bounds."""
        # Test limit too small
        response = await async_client.get(
            "/api/search/orders", params={"q": "test", "limit": 0}
        )
        assert response.status_code == 422

        # Test limit too large
        response = await async_client.get(
            "/api/search/orders", params={"q": "test", "limit": 21}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_orders_opensearch_unavailable(self, async_client: AsyncClient):
        """GET /api/search/orders returns 503 when OpenSearch is unavailable."""
        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            response = await async_client.get("/api/search/orders", params={"q": "test"})
            assert response.status_code == 503
            assert "not available" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_search_orders_index_does_not_exist(self, async_client: AsyncClient):
        """GET /api/search/orders returns empty results when index doesn't exist."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=404)

            response = await async_client.get("/api/search/orders", params={"q": "test"})
            assert response.status_code == 200
            data = response.json()
            assert data["hits"]["total"]["value"] == 0
            assert data["hits"]["hits"] == []

    @pytest.mark.asyncio
    async def test_search_orders_opensearch_error(self, async_client: AsyncClient):
        """GET /api/search/orders returns 502 for OpenSearch errors."""
        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx
            from unittest.mock import MagicMock

            # Use MagicMock for the response so that .text returns a string, not a coroutine
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal error"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=mock_response
            )
            # Wrap in AsyncMock for awaitable post()
            mock_post.return_value = mock_response

            response = await async_client.get("/api/search/orders", params={"q": "test"})
            assert response.status_code == 502
            assert "opensearch error" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_search_orders_query_structure(self, async_client: AsyncClient):
        """GET /api/search/orders sends correct query structure to OpenSearch."""
        mock_response = {
            "took": 5,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {"total": {"value": 0, "relation": "eq"}, "max_score": None, "hits": []},
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            await async_client.get("/api/search/orders", params={"q": "downtown"})

            # Verify the query structure
            call_args = mock_post.call_args
            assert call_args is not None
            request_body = call_args.kwargs["json"]

            assert "query" in request_body
            assert "multi_match" in request_body["query"]
            multi_match = request_body["query"]["multi_match"]

            assert multi_match["query"] == "downtown"
            assert "fuzziness" in multi_match
            assert "fields" in multi_match
            assert "customer_name^2" in multi_match["fields"]
            assert "store_name^2" in multi_match["fields"]
            assert "order_number^3" in multi_match["fields"]

    @pytest.mark.asyncio
    async def test_search_orders_default_limit(self, async_client: AsyncClient):
        """GET /api/search/orders uses default limit of 5."""
        mock_response = {
            "took": 5,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {"total": {"value": 0, "relation": "eq"}, "max_score": None, "hits": []},
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: mock_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            await async_client.get("/api/search/orders", params={"q": "test"})

            call_args = mock_post.call_args
            assert call_args is not None
            request_body = call_args.kwargs["json"]
            assert request_body["size"] == 5


# =============================================================================
# Vector Search Tests
# =============================================================================


def _make_mock_order(order_id: str = "order:FM-1001"):
    """Build a representative OrderFlat for mocking Materialize hydration."""
    from src.freshmart.models import OrderFlat

    return OrderFlat(
        order_id=order_id,
        order_number="FM-1001",
        order_status="OUT_FOR_DELIVERY",
        store_id="store:BK-01",
        customer_id="customer:101",
        customer_name="Alex Thompson",
        customer_email="alex@example.com",
        customer_address="123 Main St",
        store_name="FreshMart Brooklyn",
        store_zone="Brooklyn",
        store_address="100 Court St",
        order_total_amount=45.99,
        delivery_window_start=None,
        delivery_window_end=None,
        assigned_courier_id=None,
        delivery_task_status=None,
        delivery_eta=None,
        effective_updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )


def _make_knn_response(
    order_ids: Optional[list] = None,
    embedding_text: str = "Order containing organic produce for Alex",
) -> dict:
    """Build a representative OpenSearch knn response."""
    if order_ids is None:
        order_ids = ["order:FM-1001"]
    hits = []
    for i, oid in enumerate(order_ids):
        hits.append(
            {
                "_index": "orders",
                "_id": oid,
                "_score": 0.95 - (i * 0.05),
                "_source": {
                    "order_id": oid,
                    "embedding_text": embedding_text,
                    "embedded_at": "2024-01-15T12:00:00Z",
                },
            }
        )
    return {
        "took": 4,
        "timed_out": False,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {
            "total": {"value": len(hits), "relation": "eq"},
            "max_score": hits[0]["_score"] if hits else None,
            "hits": hits,
        },
    }


class TestVectorSearchOrdersAPI:
    """Tests for /api/search/vector/orders endpoint."""

    @pytest.mark.asyncio
    async def test_vector_search_valid_query(self, async_client: AsyncClient):
        """GET /api/search/vector/orders with valid query returns merged results."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        os_response = _make_knn_response(["order:FM-1001"])
        mock_order = _make_mock_order("order:FM-1001")

        async def mock_service():
            svc = AsyncMock()
            svc.get_order_with_lines = AsyncMock(return_value=mock_order)
            return svc

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: os_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "organic produce"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_vector_search_empty_query_rejected(self, async_client: AsyncClient):
        """GET /api/search/vector/orders without `q` param returns 422."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        async def mock_service():
            return AsyncMock()

        app.dependency_overrides[get_freshmart_service] = mock_service
        try:
            response = await async_client.get("/api/search/vector/orders")
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_vector_search_query_too_short(self, async_client: AsyncClient):
        """GET /api/search/vector/orders with empty `q` returns 422."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        async def mock_service():
            return AsyncMock()

        app.dependency_overrides[get_freshmart_service] = mock_service
        try:
            response = await async_client.get(
                "/api/search/vector/orders", params={"q": ""}
            )
        finally:
            app.dependency_overrides.clear()
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_vector_search_opensearch_unavailable(self, async_client: AsyncClient):
        """GET /api/search/vector/orders returns 503 when OpenSearch is down."""
        import httpx

        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        async def mock_service():
            return AsyncMock()

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "anything"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 503
        assert "not available" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_vector_search_index_not_found(self, async_client: AsyncClient):
        """GET /api/search/vector/orders returns 200 with empty results when OS 404s."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        async def mock_service():
            return AsyncMock()

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.return_value = AsyncMock(status_code=404)

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "anything"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_vector_search_response_shape(self, async_client: AsyncClient):
        """Each result item has order_id, score, embedding_text."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        os_response = _make_knn_response(["order:FM-1001"])
        mock_order = _make_mock_order("order:FM-1001")

        async def mock_service():
            svc = AsyncMock()
            svc.get_order_with_lines = AsyncMock(return_value=mock_order)
            return svc

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: os_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "produce"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) >= 1

        item = data["results"][0]
        assert "order_id" in item
        assert "score" in item
        assert "embedding_text" in item

    @pytest.mark.asyncio
    async def test_vector_search_merges_live_data(self, async_client: AsyncClient):
        """Live fields from Materialize are merged into each result item."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        # OS hit only has the minimal source fields (no order_status/customer_name)
        os_response = _make_knn_response(["order:FM-1001"])
        mock_order = _make_mock_order("order:FM-1001")

        async def mock_service():
            svc = AsyncMock()
            svc.get_order_with_lines = AsyncMock(return_value=mock_order)
            return svc

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: os_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "produce"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        item = data["results"][0]
        # Live fields from Materialize must be present
        assert item.get("order_status") == "OUT_FOR_DELIVERY"
        assert item.get("customer_name") == "Alex Thompson"
        assert item.get("store_name") == "FreshMart Brooklyn"

    @pytest.mark.asyncio
    async def test_vector_search_handles_no_mz_match(self, async_client: AsyncClient):
        """If Materialize returns None for an order_id, that result is omitted."""
        from src.main import app
        from src.routes.freshmart import get_freshmart_service

        # Two hits: one will resolve, the other will not
        os_response = _make_knn_response(["order:FM-1001", "order:FM-DELETED"])
        mock_order = _make_mock_order("order:FM-1001")

        async def mock_service():
            svc = AsyncMock()

            async def get_order(oid: str):
                if oid == "order:FM-1001":
                    return mock_order
                return None

            svc.get_order_with_lines = AsyncMock(side_effect=get_order)
            return svc

        with patch("src.routes.search.embed_query", AsyncMock(return_value=[0.1] * 384)), \
                patch("httpx.AsyncClient.post") as mock_post:

            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: os_response,
            )
            mock_post.return_value.raise_for_status = lambda: None

            app.dependency_overrides[get_freshmart_service] = mock_service
            try:
                response = await async_client.get(
                    "/api/search/vector/orders", params={"q": "produce"}
                )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["order_id"] == "order:FM-1001"
        # The deleted one must not be present
        for item in data["results"]:
            assert item["order_id"] != "order:FM-DELETED"


# ---------------------------------------------------------------------------
# Helpers for mocking httpx.AsyncClient inside routes without affecting the
# ASGI test client (which also uses httpx under the hood).
# ---------------------------------------------------------------------------

def _make_mock_httpx_client(
    get_response=None, post_response=None,
    get_side_effect=None, post_side_effect=None,
):
    inner = MagicMock()
    inner.get = AsyncMock(side_effect=get_side_effect) if get_side_effect else AsyncMock(return_value=get_response)
    inner.post = AsyncMock(side_effect=post_side_effect) if post_side_effect else AsyncMock(return_value=post_response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm), inner


class TestIndexStatsAPI:
    """Tests for GET /api/search/index-stats."""

    @pytest.mark.asyncio
    async def test_returns_doc_count(self, async_client: AsyncClient):
        resp = AsyncMock(status_code=200, json=lambda: {"count": 1203})
        resp.raise_for_status = lambda: None
        factory, _ = _make_mock_httpx_client(get_response=resp)
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get("/api/search/index-stats")
        assert response.status_code == 200
        assert response.json() == {"doc_count": 1203}

    @pytest.mark.asyncio
    async def test_index_not_found_returns_zero(self, async_client: AsyncClient):
        resp = AsyncMock(status_code=404)
        factory, _ = _make_mock_httpx_client(get_response=resp)
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get("/api/search/index-stats")
        assert response.status_code == 200
        assert response.json() == {"doc_count": 0}

    @pytest.mark.asyncio
    async def test_opensearch_unavailable_returns_503(self, async_client: AsyncClient):
        import httpx
        factory, _ = _make_mock_httpx_client(get_side_effect=httpx.ConnectError("refused"))
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get("/api/search/index-stats")
        assert response.status_code == 503


class TestIndexImpactAPI:
    """Tests for GET /api/search/impact."""

    @pytest.mark.asyncio
    async def test_returns_impacted_total_and_pct(self, async_client: AsyncClient):
        # IMPACT_INDEXES has 2 entries; each returns count=1000 (total) / count=47 (impacted).
        # The endpoint sums across all indexes: total=2000, impacted=94, pct=4.7.
        total_resp = AsyncMock(status_code=200, json=lambda: {"count": 1000})
        total_resp.raise_for_status = lambda: None
        impact_resp = AsyncMock(status_code=200, json=lambda: {"count": 47})
        impact_resp.raise_for_status = lambda: None
        factory, _ = _make_mock_httpx_client(get_response=total_resp, post_response=impact_resp)
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get(
                "/api/search/impact", params={"since_mz_timestamp": 1746000000000}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2000
        assert data["impacted"] == 94
        assert data["pct"] == 4.7

    @pytest.mark.asyncio
    async def test_missing_param_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/search/impact")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_index_not_found_returns_zeros(self, async_client: AsyncClient):
        resp = AsyncMock(status_code=404)
        factory, _ = _make_mock_httpx_client(get_response=resp)
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get(
                "/api/search/impact", params={"since_mz_timestamp": 1746000000000}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["impacted"] == 0
        assert data["total"] == 0
        assert data["pct"] == 0.0

    @pytest.mark.asyncio
    async def test_opensearch_unavailable_returns_503(self, async_client: AsyncClient):
        import httpx
        factory, _ = _make_mock_httpx_client(get_side_effect=httpx.ConnectError("refused"))
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get(
                "/api/search/impact", params={"since_mz_timestamp": 1746000000000}
            )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_zero_total_returns_zero_pct(self, async_client: AsyncClient):
        total_resp = AsyncMock(status_code=200, json=lambda: {"count": 0})
        total_resp.raise_for_status = lambda: None
        impact_resp = AsyncMock(status_code=200, json=lambda: {"count": 0})
        impact_resp.raise_for_status = lambda: None
        factory, _ = _make_mock_httpx_client(get_response=total_resp, post_response=impact_resp)
        with patch("src.routes.search.httpx.AsyncClient", factory):
            response = await async_client.get(
                "/api/search/impact", params={"since_mz_timestamp": 1746000000000}
            )
        assert response.status_code == 200
        assert response.json()["pct"] == 0.0
