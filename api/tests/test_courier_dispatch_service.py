"""Unit tests for courier dispatch service methods."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.freshmart.service import FreshMartService
from src.freshmart.models import (
    CourierAvailable,
    OrderAwaitingCourier,
    TaskReadyToAdvance,
    StoreCourierMetrics,
)


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    """Create FreshMartService with mock session."""
    return FreshMartService(mock_session, use_materialize=True)


class TestListAvailableCouriers:
    """Tests for list_available_couriers method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_couriers(self, service, mock_session):
        """Test returns empty list when no couriers available."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_available_couriers()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_courier_list(self, service, mock_session):
        """Test returns list of available couriers."""
        mock_row = MagicMock()
        mock_row.courier_id = "courier:C-0001"
        mock_row.courier_name = "John Courier"
        mock_row.home_store_id = "store:1"
        mock_row.vehicle_type = "BIKE"
        mock_row.courier_status = "AVAILABLE"
        mock_row.effective_updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        result = await service.list_available_couriers()

        assert len(result) == 1
        assert isinstance(result[0], CourierAvailable)
        assert result[0].courier_id == "courier:C-0001"
        assert result[0].courier_name == "John Courier"
        assert result[0].vehicle_type == "BIKE"

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, service, mock_session):
        """Test filtering by store_id."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.list_available_couriers(store_id="store:1")

        # Verify query includes store filter
        call_args = mock_session.execute.call_args
        query_text = str(call_args[0][0])
        assert "home_store_id" in query_text

    @pytest.mark.asyncio
    async def test_respects_limit(self, service, mock_session):
        """Test that limit parameter is respected."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.list_available_couriers(limit=50)

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["limit"] == 50


class TestListOrdersAwaitingCourier:
    """Tests for list_orders_awaiting_courier method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_orders(self, service, mock_session):
        """Test returns empty list when no pending orders."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_orders_awaiting_courier()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_order_list(self, service, mock_session):
        """Test returns list of orders awaiting courier."""
        mock_row = MagicMock()
        mock_row.order_id = "order:FM-10001"
        mock_row.order_number = "FM-10001"
        mock_row.store_id = "store:1"
        mock_row.customer_id = "customer:1001"
        mock_row.order_total_amount = Decimal("45.99")
        mock_row.delivery_window_start = "2024-01-15T14:00:00Z"
        mock_row.delivery_window_end = "2024-01-15T16:00:00Z"
        mock_row.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        result = await service.list_orders_awaiting_courier()

        assert len(result) == 1
        assert isinstance(result[0], OrderAwaitingCourier)
        assert result[0].order_id == "order:FM-10001"
        assert result[0].store_id == "store:1"

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, service, mock_session):
        """Test filtering by store_id."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.list_orders_awaiting_courier(store_id="store:1")

        call_args = mock_session.execute.call_args
        query_text = str(call_args[0][0])
        assert "store_id" in query_text


class TestListTasksReadyToAdvance:
    """Tests for list_tasks_ready_to_advance method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_tasks(self, service, mock_session):
        """Test returns empty list when no tasks ready."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_tasks_ready_to_advance()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_task_list(self, service, mock_session):
        """Test returns list of tasks ready to advance."""
        mock_row = MagicMock()
        mock_row.task_id = "task:FM-10001"
        mock_row.order_id = "order:FM-10001"
        mock_row.courier_id = "courier:C-0001"
        mock_row.task_status = "PICKING"
        mock_row.task_started_at = datetime.now(timezone.utc)
        mock_row.store_id = "store:1"
        mock_row.expected_completion_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        result = await service.list_tasks_ready_to_advance()

        assert len(result) == 1
        assert isinstance(result[0], TaskReadyToAdvance)
        assert result[0].task_id == "task:FM-10001"
        assert result[0].task_status == "PICKING"

    @pytest.mark.asyncio
    async def test_queries_tasks_ready_to_advance_view(self, service, mock_session):
        """Test that query uses the correct view."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.list_tasks_ready_to_advance()

        call_args = mock_session.execute.call_args
        query_text = str(call_args[0][0])
        assert "tasks_ready_to_advance" in query_text


class TestListStoreCourierMetrics:
    """Tests for list_store_courier_metrics method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_stores(self, service, mock_session):
        """Test returns empty list when no stores."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_store_courier_metrics()

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_metrics_list(self, service, mock_session):
        """Test returns list of store courier metrics."""
        mock_row = MagicMock()
        mock_row.store_id = "store:1"
        mock_row.store_name = "FreshMart Manhattan"
        mock_row.store_zone = "MAN"
        mock_row.total_couriers = 10
        mock_row.available_couriers = 5
        mock_row.busy_couriers = 4
        mock_row.off_shift_couriers = 1
        mock_row.orders_in_queue = 3
        mock_row.orders_picking = 2
        mock_row.orders_delivering = 2
        mock_row.estimated_wait_minutes = 2.4
        mock_row.courier_utilization_pct = 40.0
        mock_row.effective_updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        result = await service.list_store_courier_metrics()

        assert len(result) == 1
        assert isinstance(result[0], StoreCourierMetrics)
        assert result[0].store_id == "store:1"
        assert result[0].total_couriers == 10
        assert result[0].available_couriers == 5
        assert result[0].orders_in_queue == 3
        assert result[0].courier_utilization_pct == 40.0

    @pytest.mark.asyncio
    async def test_handles_null_values(self, service, mock_session):
        """Test that null values are handled with defaults."""
        mock_row = MagicMock()
        mock_row.store_id = "store:1"
        mock_row.store_name = "FreshMart Manhattan"
        mock_row.store_zone = "MAN"
        mock_row.total_couriers = None
        mock_row.available_couriers = None
        mock_row.busy_couriers = None
        mock_row.off_shift_couriers = None
        mock_row.orders_in_queue = None
        mock_row.orders_picking = None
        mock_row.orders_delivering = None
        mock_row.estimated_wait_minutes = None
        mock_row.courier_utilization_pct = None
        mock_row.effective_updated_at = None

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        result = await service.list_store_courier_metrics()

        assert len(result) == 1
        assert result[0].total_couriers == 0
        assert result[0].available_couriers == 0
        assert result[0].orders_in_queue == 0

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, service, mock_session):
        """Test filtering by store_id."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.list_store_courier_metrics(store_id="store:1")

        call_args = mock_session.execute.call_args
        query_text = str(call_args[0][0])
        assert "store_id" in query_text
