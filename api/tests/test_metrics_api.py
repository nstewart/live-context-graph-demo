"""Tests for metrics API endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


class MockRow:
    """Mock database row result."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockResult:
    """Mock database query result."""
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


@pytest.mark.asyncio
async def test_get_timeseries_without_store_filter(async_client: AsyncClient):
    """Test getting timeseries data without store filter."""
    # Mock the database session and results
    with patch("src.routes.metrics.get_mz_session_factory") as mock_factory:
        mock_session = AsyncMock()

        # Mock transaction context manager
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_transaction

        # Mock SET CLUSTER execution
        mock_set_result = AsyncMock()

        # Mock store query result
        store_rows = [
            MockRow(
                id="store-1-1234567890",
                store_id="store-1",
                window_end=1234567890000,
                queue_depth=5,
                in_progress=2,
                total_orders=10,
                avg_wait_minutes=3.5,
                max_wait_minutes=7.2,
                orders_picked_up=8,
            ),
            MockRow(
                id="store-1-1234567880",
                store_id="store-1",
                window_end=1234567880000,
                queue_depth=3,
                in_progress=1,
                total_orders=8,
                avg_wait_minutes=2.8,
                max_wait_minutes=5.5,
                orders_picked_up=7,
            ),
        ]

        # Mock system query result
        system_rows = [
            MockRow(
                id="system-1234567890",
                window_end=1234567890000,
                total_queue_depth=5,
                total_in_progress=2,
                total_orders=10,
                avg_wait_minutes=3.5,
                max_wait_minutes=7.2,
                total_orders_picked_up=8,
            ),
        ]

        # Configure execute to return different results for different queries
        async def execute_side_effect(query, params):
            if "store_metrics_timeseries_mv" in str(query):
                return MockResult(store_rows)
            elif "system_metrics_timeseries_mv" in str(query):
                return MockResult(system_rows)
            else:
                return mock_set_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        # Mock session factory context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_context

        response = await async_client.get("/api/metrics/timeseries?limit=10")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "store_timeseries" in data
        assert "system_timeseries" in data

        # Verify store timeseries data
        assert len(data["store_timeseries"]) == 2
        assert data["store_timeseries"][0]["store_id"] == "store-1"
        assert data["store_timeseries"][0]["queue_depth"] == 5
        assert data["store_timeseries"][0]["window_end"] == 1234567890000

        # Verify system timeseries data
        assert len(data["system_timeseries"]) == 1
        assert data["system_timeseries"][0]["total_queue_depth"] == 5
        assert data["system_timeseries"][0]["window_end"] == 1234567890000


@pytest.mark.asyncio
async def test_get_timeseries_with_store_filter(async_client: AsyncClient):
    """Test getting timeseries data filtered by store."""
    with patch("src.routes.metrics.get_mz_session_factory") as mock_factory:
        mock_session = AsyncMock()

        # Mock transaction context manager
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_transaction

        mock_set_result = AsyncMock()

        store_rows = [
            MockRow(
                id="store-1-1234567890",
                store_id="store-1",
                window_end=1234567890000,
                queue_depth=5,
                in_progress=2,
                total_orders=10,
                avg_wait_minutes=3.5,
                max_wait_minutes=7.2,
                orders_picked_up=8,
            ),
        ]

        system_rows = [
            MockRow(
                id="system-1234567890",
                window_end=1234567890000,
                total_queue_depth=5,
                total_in_progress=2,
                total_orders=10,
                avg_wait_minutes=3.5,
                max_wait_minutes=7.2,
                total_orders_picked_up=8,
            ),
        ]

        async def execute_side_effect(query, params):
            if "store_metrics_timeseries_mv" in str(query):
                # Verify store_id parameter was passed
                assert params.get("store_id") == "store-1"
                return MockResult(store_rows)
            elif "system_metrics_timeseries_mv" in str(query):
                return MockResult(system_rows)
            else:
                return mock_set_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_context

        response = await async_client.get("/api/metrics/timeseries?store_id=store-1&limit=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["store_timeseries"]) == 1
        assert data["store_timeseries"][0]["store_id"] == "store-1"


@pytest.mark.asyncio
async def test_get_timeseries_with_custom_limit(async_client: AsyncClient):
    """Test getting timeseries data with custom limit."""
    with patch("src.routes.metrics.get_mz_session_factory") as mock_factory:
        mock_session = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_transaction

        mock_set_result = AsyncMock()

        async def execute_side_effect(query, params):
            if "store_metrics_timeseries_mv" in str(query):
                assert params.get("limit") == 20 * 10  # limit * 10 when no store_id
                return MockResult([])
            elif "system_metrics_timeseries_mv" in str(query):
                assert params.get("limit") == 20
                return MockResult([])
            else:
                return mock_set_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_context

        response = await async_client.get("/api/metrics/timeseries?limit=20")

        assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_timeseries_limit_validation_too_low(async_client: AsyncClient):
    """Test that limit below minimum is rejected."""
    response = await async_client.get("/api/metrics/timeseries?limit=0")

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_timeseries_limit_validation_too_high(async_client: AsyncClient):
    """Test that limit above maximum is rejected."""
    response = await async_client.get("/api/metrics/timeseries?limit=61")

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_timeseries_handles_null_values(async_client: AsyncClient):
    """Test that null values in database are handled correctly."""
    with patch("src.routes.metrics.get_mz_session_factory") as mock_factory:
        mock_session = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_transaction

        mock_set_result = AsyncMock()

        store_rows = [
            MockRow(
                id="store-1-1234567890",
                store_id="store-1",
                window_end=1234567890000,
                queue_depth=None,  # Test null handling
                in_progress=None,
                total_orders=None,
                avg_wait_minutes=None,
                max_wait_minutes=None,
                orders_picked_up=None,
            ),
        ]

        system_rows = [
            MockRow(
                id="system-1234567890",
                window_end=None,  # Test null window_end
                total_queue_depth=None,
                total_in_progress=None,
                total_orders=None,
                avg_wait_minutes=None,
                max_wait_minutes=None,
                total_orders_picked_up=None,
            ),
        ]

        async def execute_side_effect(query, params):
            if "store_metrics_timeseries_mv" in str(query):
                return MockResult(store_rows)
            elif "system_metrics_timeseries_mv" in str(query):
                return MockResult(system_rows)
            else:
                return mock_set_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_context

        response = await async_client.get("/api/metrics/timeseries?limit=10")

        assert response.status_code == 200
        data = response.json()

        # Verify null integers become 0
        assert data["store_timeseries"][0]["queue_depth"] == 0
        assert data["store_timeseries"][0]["window_end"] == 0

        # Verify null floats remain None
        assert data["store_timeseries"][0]["avg_wait_minutes"] is None
        assert data["store_timeseries"][0]["max_wait_minutes"] is None


@pytest.mark.asyncio
async def test_get_timeseries_transaction_ensures_consistency(async_client: AsyncClient):
    """Test that both queries execute within a transaction for consistency."""
    with patch("src.routes.metrics.get_mz_session_factory") as mock_factory:
        mock_session = AsyncMock()

        # Mock transaction context manager
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=None)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)
        mock_session.begin.return_value = mock_transaction

        mock_set_result = AsyncMock()

        async def execute_side_effect(query, params):
            if "store_metrics_timeseries_mv" in str(query):
                return MockResult([])
            elif "system_metrics_timeseries_mv" in str(query):
                return MockResult([])
            else:
                return mock_set_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value.return_value = mock_context

        response = await async_client.get("/api/metrics/timeseries?limit=10")

        assert response.status_code == 200

        # Verify that session.begin() was called to start a transaction
        mock_session.begin.assert_called_once()

        # Verify transaction context manager was entered and exited
        mock_transaction.__aenter__.assert_called_once()
        mock_transaction.__aexit__.assert_called_once()
