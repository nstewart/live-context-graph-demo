"""Unit tests for CourierDispatchScenario."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from loadgen.api_client import FreshMartAPIClient
from loadgen.scenarios.courier_dispatch import CourierDispatchScenario


@pytest.fixture
def mock_api_client():
    """Create a mock API client for courier dispatch tests."""
    client = MagicMock(spec=FreshMartAPIClient)
    client.get_stores = AsyncMock(
        return_value=[
            {"store_id": "store:1", "store_name": "Test Store 1"},
            {"store_id": "store:2", "store_name": "Test Store 2"},
        ]
    )
    client.get_available_couriers = AsyncMock(return_value=[])
    client.get_orders_awaiting_courier = AsyncMock(return_value=[])
    client.get_tasks_ready_to_advance = AsyncMock(return_value=[])
    client.create_triples_batch = AsyncMock(return_value={"success": True})
    client.update_triples_batch = AsyncMock(return_value={"success": True})
    return client


@pytest.fixture
def sample_couriers():
    """Sample available couriers."""
    return [
        {
            "courier_id": "courier:C-0001",
            "courier_name": "John Courier",
            "home_store_id": "store:1",
            "vehicle_type": "BIKE",
            "courier_status": "AVAILABLE",
        },
        {
            "courier_id": "courier:C-0002",
            "courier_name": "Jane Courier",
            "home_store_id": "store:1",
            "vehicle_type": "CAR",
            "courier_status": "AVAILABLE",
        },
    ]


@pytest.fixture
def sample_pending_orders():
    """Sample orders awaiting courier."""
    return [
        {
            "order_id": "order:FM-10001",
            "order_number": "FM-10001",
            "store_id": "store:1",
            "customer_id": "customer:1001",
            "created_at": "2024-01-15T10:00:00Z",
        },
        {
            "order_id": "order:FM-10002",
            "order_number": "FM-10002",
            "store_id": "store:1",
            "customer_id": "customer:1002",
            "created_at": "2024-01-15T10:01:00Z",
        },
    ]


@pytest.fixture
def sample_ready_tasks():
    """Sample tasks ready to advance."""
    return [
        {
            "task_id": "task:FM-10001",
            "order_id": "order:FM-10001",
            "courier_id": "courier:C-0001",
            "task_status": "PICKING",
            "store_id": "store:1",
            "task_started_at": "2024-01-15T10:00:00Z",
            "expected_completion_at": "2024-01-15T10:02:00Z",
        },
        {
            "task_id": "task:FM-10002",
            "order_id": "order:FM-10002",
            "courier_id": "courier:C-0002",
            "task_status": "DELIVERING",
            "store_id": "store:1",
            "task_started_at": "2024-01-15T10:02:00Z",
            "expected_completion_at": "2024-01-15T10:04:00Z",
        },
    ]


class TestCourierDispatchScenarioInitialize:
    """Tests for CourierDispatchScenario initialization."""

    @pytest.mark.asyncio
    async def test_initialize_loads_stores(self, mock_api_client):
        """Test that initialize loads stores from API."""
        scenario = CourierDispatchScenario(mock_api_client)

        await scenario.initialize()

        mock_api_client.get_stores.assert_called_once_with(limit=100)
        assert len(scenario.stores) == 2
        assert scenario.stores[0]["store_id"] == "store:1"

    @pytest.mark.asyncio
    async def test_initialize_handles_empty_stores(self, mock_api_client):
        """Test that initialize handles empty store list."""
        mock_api_client.get_stores = AsyncMock(return_value=[])

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        assert len(scenario.stores) == 0


class TestCourierDispatchScenarioExecute:
    """Tests for CourierDispatchScenario execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_result_structure(self, mock_api_client):
        """Test that execute returns proper result structure."""
        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert "tasks_advanced" in result
        assert "picking_started" in result
        assert "deliveries_started" in result
        assert "deliveries_completed" in result
        assert "assignments_made" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_execute_with_no_work(self, mock_api_client):
        """Test execute when no tasks or orders are available."""
        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["tasks_advanced"] == 0
        assert result["assignments_made"] == 0
        assert result["errors"] == []


class TestCourierDispatchScenarioAdvanceTasks:
    """Tests for task advancement logic."""

    @pytest.mark.asyncio
    async def test_advance_picking_to_delivering(
        self, mock_api_client, sample_ready_tasks
    ):
        """Test advancing PICKING task to DELIVERING."""
        # Only return the PICKING task
        mock_api_client.get_tasks_ready_to_advance = AsyncMock(
            return_value=[sample_ready_tasks[0]]
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["deliveries_started"] == 1
        assert result["tasks_advanced"] == 1

        # Verify update_triples_batch was called
        mock_api_client.update_triples_batch.assert_called()

    @pytest.mark.asyncio
    async def test_advance_delivering_to_completed(
        self, mock_api_client, sample_ready_tasks
    ):
        """Test advancing DELIVERING task to COMPLETED."""
        # Only return the DELIVERING task
        mock_api_client.get_tasks_ready_to_advance = AsyncMock(
            return_value=[sample_ready_tasks[1]]
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["deliveries_completed"] == 1
        assert result["tasks_advanced"] == 1

        # Verify update_triples_batch was called
        mock_api_client.update_triples_batch.assert_called()

    @pytest.mark.asyncio
    async def test_advance_multiple_tasks(self, mock_api_client, sample_ready_tasks):
        """Test advancing multiple tasks in one cycle."""
        mock_api_client.get_tasks_ready_to_advance = AsyncMock(
            return_value=sample_ready_tasks
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["tasks_advanced"] == 2
        assert result["deliveries_started"] == 1
        assert result["deliveries_completed"] == 1


class TestCourierDispatchScenarioAssignments:
    """Tests for courier assignment logic."""

    @pytest.mark.asyncio
    async def test_assign_courier_to_order(
        self, mock_api_client, sample_couriers, sample_pending_orders
    ):
        """Test assigning an available courier to a pending order."""
        # Set up single store to avoid doubling
        mock_api_client.get_stores = AsyncMock(
            return_value=[{"store_id": "store:1", "store_name": "Test Store 1"}]
        )
        mock_api_client.get_available_couriers = AsyncMock(
            return_value=[sample_couriers[0]]
        )
        mock_api_client.get_orders_awaiting_courier = AsyncMock(
            return_value=[sample_pending_orders[0]]
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["assignments_made"] == 1
        assert result["picking_started"] == 1

        # Verify update_triples_batch was called
        mock_api_client.update_triples_batch.assert_called()

    @pytest.mark.asyncio
    async def test_assign_multiple_couriers(
        self, mock_api_client, sample_couriers, sample_pending_orders
    ):
        """Test assigning multiple couriers to multiple orders."""
        # Set up single store to avoid doubling
        mock_api_client.get_stores = AsyncMock(
            return_value=[{"store_id": "store:1", "store_name": "Test Store 1"}]
        )
        mock_api_client.get_available_couriers = AsyncMock(return_value=sample_couriers)
        mock_api_client.get_orders_awaiting_courier = AsyncMock(
            return_value=sample_pending_orders
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        # Should assign 2 couriers to 2 orders (limited by available couriers)
        assert result["assignments_made"] == 2

    @pytest.mark.asyncio
    async def test_no_assignment_without_couriers(
        self, mock_api_client, sample_pending_orders
    ):
        """Test no assignments when no couriers available."""
        mock_api_client.get_available_couriers = AsyncMock(return_value=[])
        mock_api_client.get_orders_awaiting_courier = AsyncMock(
            return_value=sample_pending_orders
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["assignments_made"] == 0
        mock_api_client.update_triples_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_assignment_without_orders(
        self, mock_api_client, sample_couriers
    ):
        """Test no assignments when no orders pending."""
        mock_api_client.get_available_couriers = AsyncMock(return_value=sample_couriers)
        mock_api_client.get_orders_awaiting_courier = AsyncMock(return_value=[])

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        assert result["assignments_made"] == 0

    @pytest.mark.asyncio
    async def test_assignment_creates_correct_triples(
        self, mock_api_client, sample_couriers, sample_pending_orders
    ):
        """Test that courier assignment creates the correct triples."""
        mock_api_client.get_available_couriers = AsyncMock(
            return_value=[sample_couriers[0]]
        )
        mock_api_client.get_orders_awaiting_courier = AsyncMock(
            return_value=[sample_pending_orders[0]]
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        await scenario.execute()

        # Verify the triples created
        call_args = mock_api_client.update_triples_batch.call_args
        triples = call_args[0][0]

        # Should have 7 triples for a new assignment (including courier_status_changed_at)
        assert len(triples) == 7

        # Check for key predicates
        predicates = {t["predicate"] for t in triples}
        assert "task_of_order" in predicates
        assert "assigned_to" in predicates
        assert "task_status" in predicates
        assert "task_started_at" in predicates
        assert "courier_status" in predicates
        assert "courier_status_changed_at" in predicates
        assert "order_status" in predicates

        # Verify task status is PICKING
        task_status_triple = next(t for t in triples if t["predicate"] == "task_status")
        assert task_status_triple["object_value"] == "PICKING"


class TestCourierDispatchScenarioErrorHandling:
    """Tests for error handling in dispatch scenario."""

    @pytest.mark.asyncio
    async def test_handles_api_error_on_tasks(self, mock_api_client):
        """Test that API errors are handled gracefully."""
        mock_api_client.get_tasks_ready_to_advance = AsyncMock(
            side_effect=Exception("API error")
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        # Should not raise, but return empty result
        assert result["tasks_advanced"] == 0

    @pytest.mark.asyncio
    async def test_handles_api_error_on_assignment(
        self, mock_api_client, sample_couriers, sample_pending_orders
    ):
        """Test that assignment errors are handled gracefully."""
        mock_api_client.get_available_couriers = AsyncMock(
            return_value=[sample_couriers[0]]
        )
        mock_api_client.get_orders_awaiting_courier = AsyncMock(
            return_value=[sample_pending_orders[0]]
        )
        mock_api_client.update_triples_batch = AsyncMock(
            side_effect=Exception("Write error")
        )

        scenario = CourierDispatchScenario(mock_api_client)
        await scenario.initialize()

        result = await scenario.execute()

        # Should handle error and continue
        assert result["assignments_made"] == 0
