"""Tests for OpenSearchClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOpenSearchClient:
    """Tests for OpenSearchClient."""

    @pytest.fixture
    def client(self):
        """Create OpenSearch client with mocked settings."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch"):
                from src.opensearch_client import OpenSearchClient

                return OpenSearchClient()

    @pytest.fixture
    def client_with_auth(self):
        """Create OpenSearch client with authentication."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user="admin",
                os_password="secret",
            )
            with patch("src.opensearch_client.AsyncOpenSearch") as mock_os:
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                # Verify auth was passed
                call_kwargs = mock_os.call_args.kwargs
                assert call_kwargs["http_auth"] == ("admin", "secret")
                return client


class TestEnsureIndex:
    """Tests for OpenSearchClient.ensure_index."""

    @pytest.fixture
    def client(self):
        """Create client with mocked internal client."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch") as mock_os:
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                client.client = AsyncMock()
                return client

    @pytest.mark.asyncio
    async def test_creates_index_when_not_exists(self, client):
        """Creates index when it doesn't exist."""
        client.client.indices.exists = AsyncMock(return_value=False)
        client.client.indices.create = AsyncMock()

        await client.ensure_index("test_index", {"mappings": {}})

        client.client.indices.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_creation_when_index_exists(self, client):
        """Skips creation when index already exists."""
        client.client.indices.exists = AsyncMock(return_value=True)
        client.client.indices.create = AsyncMock()

        await client.ensure_index("test_index", {"mappings": {}})

        client.client.indices.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_on_error(self, client):
        """Raises exception on error."""
        client.client.indices.exists = AsyncMock(side_effect=Exception("Test error"))

        with pytest.raises(Exception):
            await client.ensure_index("test_index", {"mappings": {}})


class TestBulkUpsert:
    """Tests for OpenSearchClient.bulk_upsert."""

    @pytest.fixture
    def client(self):
        """Create client with mocked internal client."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch"):
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                client.client = AsyncMock()
                return client

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_list(self, client):
        """Returns (0, 0) for empty document list."""
        success, errors = await client.bulk_upsert("test_index", [])

        assert success == 0
        assert errors == 0

    @pytest.mark.asyncio
    async def test_creates_actions_for_each_document(self, client):
        """Creates bulk actions for each document."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (2, [])

            documents = [
                {"order_id": "order:1", "status": "CREATED"},
                {"order_id": "order:2", "status": "DELIVERED"},
            ]

            success, errors = await client.bulk_upsert("test_index", documents)

            assert success == 2
            assert errors == 0
            mock_bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_order_id_as_document_id(self, client):
        """Uses order_id as document _id."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (1, [])

            documents = [{"order_id": "order:FM-1001", "status": "CREATED"}]

            await client.bulk_upsert("test_index", documents)

            call_args = mock_bulk.call_args
            actions = list(call_args.args[1])
            assert actions[0]["_id"] == "order:FM-1001"

    @pytest.mark.asyncio
    async def test_returns_error_count(self, client):
        """Returns error count from bulk operation."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            # 2 successful, 1 error
            mock_bulk.return_value = (2, [{"error": "test"}])

            documents = [
                {"order_id": "order:1"},
                {"order_id": "order:2"},
                {"order_id": "order:3"},
            ]

            success, errors = await client.bulk_upsert("test_index", documents)

            assert success == 2
            assert errors == 1

    @pytest.mark.asyncio
    async def test_handles_bulk_exception(self, client):
        """Handles exception during bulk operation."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.side_effect = Exception("Bulk failed")

            documents = [{"order_id": "order:1"}]

            success, errors = await client.bulk_upsert("test_index", documents)

            assert success == 0
            assert errors == 1


class TestBulkPatch:
    """Tests for OpenSearchClient.bulk_patch."""

    @pytest.fixture
    def client(self):
        """Create client with mocked internal client."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch"):
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                client.client = AsyncMock()
                return client

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_list(self, client):
        """Returns (0, 0) for empty patch list and does not call helpers."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            success, errors = await client.bulk_patch("test_index", [])

            assert success == 0
            assert errors == 0
            mock_bulk.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_update_op_type(self, client):
        """Uses update _op_type (not index)."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (1, [])

            patches = [
                {
                    "_id": "order:FM-1001",
                    "doc": {"order_total_amount": 49.99},
                }
            ]

            await client.bulk_patch("test_index", patches)

            actions = list(mock_bulk.call_args.args[1])
            assert actions[0]["_op_type"] == "update"

    @pytest.mark.asyncio
    async def test_passes_doc_as_upsert_true(self, client):
        """Sets doc_as_upsert: True so first patch creates the doc."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (1, [])

            patches = [{"_id": "order:FM-1001", "doc": {"order_status": "DELIVERED"}}]

            await client.bulk_patch("test_index", patches)

            actions = list(mock_bulk.call_args.args[1])
            assert actions[0]["doc_as_upsert"] is True

    @pytest.mark.asyncio
    async def test_passes_doc_field(self, client):
        """Forwards the patch's `doc` field to the bulk action."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (1, [])

            patch_doc = {"order_status": "DELIVERED", "order_total_amount": 12.34}
            patches = [{"_id": "order:FM-1001", "doc": patch_doc}]

            await client.bulk_patch("test_index", patches)

            actions = list(mock_bulk.call_args.args[1])
            assert actions[0]["doc"] == patch_doc
            assert actions[0]["_id"] == "order:FM-1001"
            assert actions[0]["_index"] == "test_index"

    @pytest.mark.asyncio
    async def test_returns_success_and_error_counts(self, client):
        """Returns (success_count, error_count) tuple from helpers.async_bulk."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            # 2 succeeded, 1 errored
            mock_bulk.return_value = (2, [{"error": "boom"}])

            patches = [
                {"_id": "order:1", "doc": {"order_status": "DELIVERED"}},
                {"_id": "order:2", "doc": {"order_status": "DELIVERED"}},
                {"_id": "order:3", "doc": {"order_status": "DELIVERED"}},
            ]

            success, errors = await client.bulk_patch("test_index", patches)

            assert success == 2
            assert errors == 1

    @pytest.mark.asyncio
    async def test_creates_one_action_per_patch(self, client):
        """Builds exactly one bulk action per patch entry."""
        with patch("src.opensearch_client.helpers.async_bulk") as mock_bulk:
            mock_bulk.return_value = (3, [])

            patches = [
                {"_id": "order:1", "doc": {"a": 1}},
                {"_id": "order:2", "doc": {"a": 2}},
                {"_id": "order:3", "doc": {"a": 3}},
            ]

            await client.bulk_patch("test_index", patches)

            actions = list(mock_bulk.call_args.args[1])
            assert len(actions) == 3


class TestSearchOrders:
    """Tests for OpenSearchClient.search_orders."""

    @pytest.fixture
    def client(self):
        """Create client with mocked internal client."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch"):
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                client.client = AsyncMock()
                return client

    @pytest.mark.asyncio
    async def test_returns_matching_orders(self, client):
        """Returns orders matching search query."""
        client.client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {"_source": {"order_id": "order:1", "customer_name": "Alex"}},
                        {"_source": {"order_id": "order:2", "customer_name": "Alexander"}},
                    ]
                }
            }
        )

        results = await client.search_orders("Alex")

        assert len(results) == 2
        assert results[0]["customer_name"] == "Alex"

    @pytest.mark.asyncio
    async def test_includes_status_filter_when_provided(self, client):
        """Includes status filter in query when provided."""
        client.client.search = AsyncMock(return_value={"hits": {"hits": []}})

        await client.search_orders("Alex", status="OUT_FOR_DELIVERY")

        call_args = client.client.search.call_args
        query_body = call_args.kwargs["body"]
        must_clauses = query_body["query"]["bool"]["must"]
        assert any(
            clause.get("term", {}).get("order_status") == "OUT_FOR_DELIVERY"
            for clause in must_clauses
        )

    @pytest.mark.asyncio
    async def test_respects_size_parameter(self, client):
        """Respects size parameter in search."""
        client.client.search = AsyncMock(return_value={"hits": {"hits": []}})

        await client.search_orders("Alex", size=5)

        call_args = client.client.search.call_args
        query_body = call_args.kwargs["body"]
        assert query_body["size"] == 5

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, client):
        """Returns empty list on search error."""
        client.client.search = AsyncMock(side_effect=Exception("Search failed"))

        results = await client.search_orders("Alex")

        assert results == []

    @pytest.mark.asyncio
    async def test_sorts_by_updated_at_desc(self, client):
        """Sorts results by effective_updated_at descending."""
        client.client.search = AsyncMock(return_value={"hits": {"hits": []}})

        await client.search_orders("Alex")

        call_args = client.client.search.call_args
        query_body = call_args.kwargs["body"]
        assert query_body["sort"] == [{"effective_updated_at": {"order": "desc"}}]


class TestHealthCheck:
    """Tests for OpenSearchClient.health_check."""

    @pytest.fixture
    def client(self):
        """Create client with mocked internal client."""
        with patch("src.opensearch_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                os_host="localhost",
                os_port=9200,
                os_user=None,
                os_password=None,
            )
            with patch("src.opensearch_client.AsyncOpenSearch"):
                from src.opensearch_client import OpenSearchClient

                client = OpenSearchClient()
                client.client = AsyncMock()
                return client

    @pytest.mark.asyncio
    async def test_returns_true_when_healthy(self, client):
        """Returns True when cluster is healthy."""
        client.client.cluster.health = AsyncMock(return_value={"status": "green"})

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_yellow_status(self, client):
        """Returns True for yellow cluster status."""
        client.client.cluster.health = AsyncMock(return_value={"status": "yellow"})

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_red_status(self, client):
        """Returns False for red cluster status."""
        client.client.cluster.health = AsyncMock(return_value={"status": "red"})

        result = await client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, client):
        """Returns False on connection error."""
        client.client.cluster.health = AsyncMock(side_effect=Exception("Connection error"))

        result = await client.health_check()

        assert result is False
