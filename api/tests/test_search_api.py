"""Integration tests for Search API endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

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
