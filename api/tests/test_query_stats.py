"""Tests for query statistics API."""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from src.routes.query_stats import (
    SourceMetrics,
    parse_effective_updated_at,
    serialize_value,
    serialize_row,
    get_state_lock,
)


class TestSourceMetrics:
    """Test SourceMetrics class for QPS tracking and statistics."""

    def test_record_sample(self):
        """Test recording a single sample."""
        metrics = SourceMetrics()
        metrics.record(response_ms=100.5, reaction_ms=50.2)

        assert len(metrics.response_times) == 1
        assert len(metrics.reaction_times) == 1
        assert len(metrics.sample_timestamps) == 1
        assert len(metrics.query_timestamps) == 1
        assert metrics.query_count == 1
        assert metrics.response_times[0] == 100.5
        assert metrics.reaction_times[0] == 50.2

    def test_calculate_qps_no_samples(self):
        """Test QPS calculation with no samples."""
        metrics = SourceMetrics()
        qps = metrics.calculate_qps()
        assert qps == 0.0

    def test_calculate_qps_single_sample(self):
        """Test QPS calculation with one sample."""
        metrics = SourceMetrics()
        metrics.record(100.0, 50.0)
        qps = metrics.calculate_qps()
        # Single sample within 1 second window = 1 QPS
        assert qps == 1.0

    def test_calculate_qps_multiple_samples(self):
        """Test QPS calculation with multiple samples."""
        metrics = SourceMetrics()
        # Record 5 samples in quick succession
        for _ in range(5):
            metrics.record(100.0, 50.0)
            time.sleep(0.01)  # Small delay to spread samples

        qps = metrics.calculate_qps()
        # Should be close to 5 QPS (depends on timing)
        assert qps > 0

    def test_stats_empty(self):
        """Test statistics calculation with no samples."""
        metrics = SourceMetrics()
        stats = metrics.stats()

        assert stats["response_time"]["median"] == 0
        assert stats["response_time"]["max"] == 0
        assert stats["response_time"]["p99"] == 0
        assert stats["reaction_time"]["median"] == 0
        assert stats["sample_count"] == 0
        assert stats["qps"] == 0.0

    def test_stats_with_samples(self):
        """Test statistics calculation with samples."""
        metrics = SourceMetrics()
        # Add various samples
        metrics.record(100.0, 50.0)
        metrics.record(200.0, 75.0)
        metrics.record(150.0, 60.0)
        metrics.record(300.0, 100.0)

        stats = metrics.stats()

        assert stats["sample_count"] == 4
        assert stats["response_time"]["median"] == 175.0  # median of [100, 150, 200, 300]
        assert stats["response_time"]["max"] == 300.0
        assert stats["reaction_time"]["median"] == 67.5  # median of [50, 60, 75, 100]

    def test_clear(self):
        """Test clearing all metrics."""
        metrics = SourceMetrics()
        metrics.record(100.0, 50.0)
        metrics.record(200.0, 75.0)

        metrics.clear()

        assert len(metrics.response_times) == 0
        assert len(metrics.reaction_times) == 0
        assert len(metrics.sample_timestamps) == 0
        assert len(metrics.query_timestamps) == 0
        assert metrics.query_count == 0

    def test_maxlen_enforcement(self):
        """Test that deques respect maxlen."""
        from src.routes.query_stats import MAX_SAMPLES

        metrics = SourceMetrics()
        # Record more than MAX_SAMPLES
        for i in range(MAX_SAMPLES + 100):
            metrics.record(float(i), float(i))

        # Should only keep MAX_SAMPLES
        assert len(metrics.response_times) == MAX_SAMPLES
        assert len(metrics.reaction_times) == MAX_SAMPLES
        assert len(metrics.sample_timestamps) == MAX_SAMPLES


class TestHelperFunctions:
    """Test helper functions for data processing."""

    def test_parse_effective_updated_at_string(self):
        """Test parsing ISO format string."""
        iso_string = "2025-01-15T12:30:45.123456Z"
        result = parse_effective_updated_at(iso_string)

        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_effective_updated_at_datetime(self):
        """Test parsing datetime object."""
        dt = datetime(2025, 1, 15, 12, 30, 45)
        result = parse_effective_updated_at(dt)

        assert isinstance(result, datetime)
        assert result.tzinfo is not None  # Should add UTC timezone
        assert result.year == 2025

    def test_parse_effective_updated_at_aware_datetime(self):
        """Test parsing timezone-aware datetime."""
        dt = datetime(2025, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        result = parse_effective_updated_at(dt)

        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc
        assert result == dt

    def test_serialize_value_decimal(self):
        """Test serializing Decimal to float."""
        from decimal import Decimal

        value = Decimal("123.456")
        result = serialize_value(value)

        assert isinstance(result, float)
        assert result == 123.456

    def test_serialize_value_datetime(self):
        """Test serializing datetime to ISO string."""
        dt = datetime(2025, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        result = serialize_value(dt)

        assert isinstance(result, str)
        assert "2025-01-15" in result

    def test_serialize_value_json_string(self):
        """Test parsing JSON strings."""
        json_str = '{"key": "value"}'
        result = serialize_value(json_str)

        assert isinstance(result, dict)
        assert result["key"] == "value"

    def test_serialize_value_regular_string(self):
        """Test regular strings pass through."""
        value = "regular string"
        result = serialize_value(value)

        assert result == value

    def test_serialize_row(self):
        """Test serializing entire database row."""
        from decimal import Decimal

        row = {
            "id": 1,
            "price": Decimal("99.99"),
            "created_at": datetime(2025, 1, 15, tzinfo=timezone.utc),
            "name": "test",
        }
        result = serialize_row(row)

        assert result["id"] == 1
        assert isinstance(result["price"], float)
        assert isinstance(result["created_at"], str)
        assert result["name"] == "test"


class TestStateLock:
    """Test state lock initialization."""

    def test_get_state_lock_creates_lock(self):
        """Test that get_state_lock creates a lock."""
        # Reset the global state_lock
        import src.routes.query_stats as query_stats_module
        query_stats_module.state_lock = None

        lock = get_state_lock()
        assert isinstance(lock, asyncio.Lock)

    def test_get_state_lock_returns_same_lock(self):
        """Test that get_state_lock returns the same lock instance."""
        lock1 = get_state_lock()
        lock2 = get_state_lock()
        assert lock1 is lock2


@pytest.mark.asyncio
class TestQueryStatsAPI:
    """Test query statistics API endpoints."""

    async def test_list_orders_endpoint(self, async_client: AsyncClient):
        """Test GET /api/query-stats/orders endpoint."""
        # Mock the database to avoid needing a real connection
        with patch("src.routes.query_stats.get_mz_session") as mock_session:
            # Create mock session and result
            mock_result = MagicMock()
            mock_result.mappings().fetchall.return_value = [
                {
                    "order_id": "order:1",
                    "order_number": "ORD-001",
                    "order_status": "pending",
                    "customer_name": "Test Customer",
                    "store_name": "Test Store",
                    "store_id": "store:1",
                }
            ]

            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.__aexit__.return_value = None
            mock_session_instance.execute = AsyncMock(return_value=mock_result)
            mock_session.return_value = mock_session_instance

            response = await async_client.get("/api/query-stats/orders")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            if len(data) > 0:
                assert "order_id" in data[0]

    async def test_get_metrics_endpoint(self, async_client: AsyncClient):
        """Test GET /api/query-stats/metrics endpoint."""
        response = await async_client.get("/api/query-stats/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "postgresql_view" in data
        assert "batch_cache" in data
        assert "materialize" in data
        assert "timestamp" in data
        assert "is_polling" in data

    async def test_get_order_data_endpoint(self, async_client: AsyncClient):
        """Test GET /api/query-stats/order-data endpoint."""
        response = await async_client.get("/api/query-stats/order-data")

        assert response.status_code == 200
        data = response.json()
        assert "postgresql_view" in data
        assert "batch_cache" in data
        assert "materialize" in data
        assert "is_polling" in data

    async def test_stop_polling_endpoint(self, async_client: AsyncClient):
        """Test POST /api/query-stats/stop endpoint."""
        response = await async_client.post("/api/query-stats/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


class TestWriteTripleMzTimestamp:
    """write_triple returns a wall-clock mz_timestamp_lower_bound before the PG write."""

    @pytest.mark.asyncio
    async def test_returns_wall_clock_lower_bound(self, async_client: AsyncClient):
        import time
        from unittest.mock import AsyncMock, MagicMock, patch

        # The route runs two queries: SELECT old object_value, then UPDATE ... RETURNING id.
        select_result = MagicMock()
        select_result.fetchone.return_value = MagicMock(object_value="PLACED")
        update_result = MagicMock()
        update_result.fetchone.return_value = (1,)
        pg_session = AsyncMock()
        pg_session.execute = AsyncMock(side_effect=[select_result, update_result])
        pg_session.commit = AsyncMock()
        pg_session.__aenter__ = AsyncMock(return_value=pg_session)
        pg_session.__aexit__ = AsyncMock(return_value=False)

        before_ms = int(time.time() * 1000)
        with patch("src.routes.query_stats.get_pg_session", return_value=pg_session):
            response = await async_client.post(
                "/api/query-stats/write-triple",
                json={"subject_id": "order:FM-001", "predicate": "order_status", "object_value": "DELIVERED"},
            )
        after_ms = int(time.time() * 1000)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "written"
        lb = data["mz_timestamp_lower_bound"]
        assert lb is not None
        assert isinstance(lb, int)
        # Lower bound must fall within the request window
        assert before_ms <= lb <= after_ms

    @pytest.mark.asyncio
    async def test_lower_bound_always_set(self, async_client: AsyncClient):
        """Lower bound is always a wall-clock int — no Materialize dependency."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # The route runs two queries: SELECT old object_value, then UPDATE ... RETURNING id.
        select_result = MagicMock()
        select_result.fetchone.return_value = MagicMock(object_value="PLACED")
        update_result = MagicMock()
        update_result.fetchone.return_value = (1,)
        pg_session = AsyncMock()
        pg_session.execute = AsyncMock(side_effect=[select_result, update_result])
        pg_session.commit = AsyncMock()
        pg_session.__aenter__ = AsyncMock(return_value=pg_session)
        pg_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.routes.query_stats.get_pg_session", return_value=pg_session):
            response = await async_client.post(
                "/api/query-stats/write-triple",
                json={"subject_id": "order:FM-001", "predicate": "order_status", "object_value": "DELIVERED"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["mz_timestamp_lower_bound"] is not None
        # Sanity: epoch ms for dates after 2020-01-01
        assert data["mz_timestamp_lower_bound"] > 1_577_836_800_000


@pytest.mark.asyncio
class TestViewDefinitionCache:
    """View definitions are prefetched and cached so demo clicks never wait."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Each test starts from a cold cache (it's process-global)."""
        from src.routes.query_stats import _view_definition_cache

        _view_definition_cache.clear()
        yield
        _view_definition_cache.clear()

    def _mock_session(self, catalog_rows, create_rows):
        """Build a mock Materialize session for one _fetch_view_definitions call.

        First execute() is SET CLUSTER, second is the catalog lookup, then one
        SHOW CREATE per object.
        """
        catalog_result = MagicMock()
        catalog_result.fetchall.return_value = catalog_rows

        show_results = []
        for row in create_rows:
            result = MagicMock()
            result.fetchone.return_value = row
            show_results.append(result)

        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        session.execute = AsyncMock(
            side_effect=[MagicMock(), catalog_result, *show_results]
        )
        return session

    async def test_batch_endpoint_returns_all_definitions(self, async_client: AsyncClient):
        """GET /view-definitions fetches every allowlisted object in one session."""
        from src.routes.query_stats import ALLOWED_VIEWS

        names = sorted(ALLOWED_VIEWS)
        catalog_rows = [(name, "view") for name in names]
        create_rows = [(name, f"CREATE VIEW {name} AS SELECT 1") for name in names]
        session = self._mock_session(catalog_rows, create_rows)

        with patch("src.routes.query_stats.get_mz_session", return_value=session):
            response = await async_client.get("/api/query-stats/view-definitions")

        assert response.status_code == 200
        data = response.json()
        assert data["cached_count"] == len(ALLOWED_VIEWS)
        assert data["expected_count"] == len(ALLOWED_VIEWS)
        assert set(data["definitions"]) == ALLOWED_VIEWS
        assert data["definitions"][names[0]]["sql"].startswith("CREATE VIEW")

        # One pool checkout for the whole batch, not one per view
        assert session.__aenter__.await_count == 1

    async def test_second_batch_call_hits_no_database(self, async_client: AsyncClient):
        """A warm cache serves the batch endpoint without touching Materialize."""
        from src.routes.query_stats import ALLOWED_VIEWS

        names = sorted(ALLOWED_VIEWS)
        session = self._mock_session(
            [(name, "view") for name in names],
            [(name, f"CREATE VIEW {name} AS SELECT 1") for name in names],
        )
        with patch("src.routes.query_stats.get_mz_session", return_value=session):
            await async_client.get("/api/query-stats/view-definitions")

        # Any DB access on the second call would raise, since the mock is exhausted
        with patch("src.routes.query_stats.get_mz_session") as never_called:
            response = await async_client.get("/api/query-stats/view-definitions")
            assert never_called.call_count == 0

        assert response.status_code == 200
        assert response.json()["cached_count"] == len(ALLOWED_VIEWS)

    async def test_single_view_served_from_prefetched_cache(self, async_client: AsyncClient):
        """After a prefetch, a per-view click never queries Materialize."""
        from src.routes.query_stats import _view_definition_cache

        _view_definition_cache["orders_with_lines_mv"] = {
            "view_name": "orders_with_lines_mv",
            "object_type": "materialized_view",
            "sql": "CREATE MATERIALIZED VIEW orders_with_lines_mv AS SELECT 1",
        }

        with patch("src.routes.query_stats.get_mz_session") as never_called:
            response = await async_client.get(
                "/api/query-stats/view-definition/orders_with_lines_mv"
            )
            assert never_called.call_count == 0

        assert response.status_code == 200
        assert response.json()["object_type"] == "materialized_view"

    async def test_single_view_falls_back_to_query_on_cache_miss(self, async_client: AsyncClient):
        """A cold cache still serves the per-view endpoint, and warms itself."""
        from src.routes.query_stats import _view_definition_cache

        session = self._mock_session(
            [("stores_flat", "view")],
            [("stores_flat", "CREATE VIEW stores_flat AS SELECT 1")],
        )
        with patch("src.routes.query_stats.get_mz_session", return_value=session):
            response = await async_client.get("/api/query-stats/view-definition/stores_flat")

        assert response.status_code == 200
        assert response.json()["sql"] == "CREATE VIEW stores_flat AS SELECT 1"
        # The fetched definition is now cached for the next click
        assert "stores_flat" in _view_definition_cache

    async def test_unknown_view_still_rejected(self, async_client: AsyncClient):
        """The allowlist still guards the interpolated SHOW CREATE identifier."""
        response = await async_client.get(
            "/api/query-stats/view-definition/pg_sleep(10);DROP"
        )
        assert response.status_code == 400

    async def test_missing_catalog_object_is_skipped_not_fatal(self, async_client: AsyncClient):
        """One object missing from the catalog doesn't fail the whole prefetch."""
        from src.routes.query_stats import ALLOWED_VIEWS

        present = sorted(ALLOWED_VIEWS)[:-1]
        session = self._mock_session(
            [(name, "view") for name in present],
            [(name, f"CREATE VIEW {name} AS SELECT 1") for name in present],
        )
        with patch("src.routes.query_stats.get_mz_session", return_value=session):
            response = await async_client.get("/api/query-stats/view-definitions")

        assert response.status_code == 200
        data = response.json()
        assert data["cached_count"] == len(ALLOWED_VIEWS) - 1
        assert data["expected_count"] == len(ALLOWED_VIEWS)
