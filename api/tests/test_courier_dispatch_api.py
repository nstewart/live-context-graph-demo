"""API endpoint tests for courier dispatch routes."""

import pytest
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.routes.freshmart import get_freshmart_service
from src.freshmart.models import (
    CourierAvailable,
    OrderAwaitingCourier,
    TaskReadyToAdvance,
    StoreCourierMetrics,
)


@pytest.fixture
def mock_freshmart_service():
    """Create a mock FreshMartService."""
    service = AsyncMock()
    service.list_available_couriers = AsyncMock(return_value=[])
    service.list_orders_awaiting_courier = AsyncMock(return_value=[])
    service.list_tasks_ready_to_advance = AsyncMock(return_value=[])
    service.list_store_courier_metrics = AsyncMock(return_value=[])
    return service


class TestDispatchCouriersAvailableEndpoint:
    """Tests for GET /freshmart/dispatch/couriers/available."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_freshmart_service):
        """Test endpoint returns empty list when no couriers available."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/freshmart/dispatch/couriers/available")

            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_couriers(self, mock_freshmart_service):
        """Test endpoint returns list of available couriers."""
        mock_freshmart_service.list_available_couriers = AsyncMock(
            return_value=[
                CourierAvailable(
                    courier_id="courier:C-0001",
                    courier_name="John Courier",
                    home_store_id="store:1",
                    vehicle_type="BIKE",
                    courier_status="AVAILABLE",
                )
            ]
        )

        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/freshmart/dispatch/couriers/available")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["courier_id"] == "courier:C-0001"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, mock_freshmart_service):
        """Test endpoint accepts store_id filter."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/couriers/available",
                    params={"store_id": "store:1"},
                )

            assert response.status_code == 200
            mock_freshmart_service.list_available_couriers.assert_called_once_with(
                store_id="store:1", limit=100
            )
        finally:
            app.dependency_overrides.clear()


class TestDispatchOrdersAwaitingCourierEndpoint:
    """Tests for GET /freshmart/dispatch/orders/awaiting-courier."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_freshmart_service):
        """Test endpoint returns empty list when no orders pending."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/orders/awaiting-courier"
                )

            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_orders(self, mock_freshmart_service):
        """Test endpoint returns list of pending orders."""
        mock_freshmart_service.list_orders_awaiting_courier = AsyncMock(
            return_value=[
                OrderAwaitingCourier(
                    order_id="order:FM-10001",
                    order_number="FM-10001",
                    store_id="store:1",
                    customer_id="customer:1001",
                )
            ]
        )

        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/orders/awaiting-courier"
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["order_id"] == "order:FM-10001"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, mock_freshmart_service):
        """Test endpoint accepts store_id filter."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/orders/awaiting-courier",
                    params={"store_id": "store:1"},
                )

            assert response.status_code == 200
            mock_freshmart_service.list_orders_awaiting_courier.assert_called_once_with(
                store_id="store:1", limit=100
            )
        finally:
            app.dependency_overrides.clear()


class TestDispatchTasksReadyToAdvanceEndpoint:
    """Tests for GET /freshmart/dispatch/tasks/ready-to-advance."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_freshmart_service):
        """Test endpoint returns empty list when no tasks ready."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/tasks/ready-to-advance"
                )

            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_tasks(self, mock_freshmart_service):
        """Test endpoint returns list of tasks ready to advance."""
        mock_freshmart_service.list_tasks_ready_to_advance = AsyncMock(
            return_value=[
                TaskReadyToAdvance(
                    task_id="task:FM-10001",
                    order_id="order:FM-10001",
                    courier_id="courier:C-0001",
                    task_status="PICKING",
                    store_id="store:1",
                )
            ]
        )

        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/tasks/ready-to-advance"
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["task_id"] == "task:FM-10001"
            assert data[0]["task_status"] == "PICKING"
        finally:
            app.dependency_overrides.clear()


class TestDispatchMetricsEndpoint:
    """Tests for GET /freshmart/dispatch/metrics."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, mock_freshmart_service):
        """Test endpoint returns empty list when no stores."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/freshmart/dispatch/metrics")

            assert response.status_code == 200
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_returns_metrics(self, mock_freshmart_service):
        """Test endpoint returns store courier metrics."""
        mock_freshmart_service.list_store_courier_metrics = AsyncMock(
            return_value=[
                StoreCourierMetrics(
                    store_id="store:1",
                    store_name="FreshMart Manhattan",
                    store_zone="MAN",
                    total_couriers=10,
                    available_couriers=5,
                    busy_couriers=4,
                    off_shift_couriers=1,
                    orders_in_queue=3,
                    orders_picking=2,
                    orders_delivering=2,
                    estimated_wait_minutes=2.4,
                    courier_utilization_pct=40.0,
                )
            ]
        )

        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/freshmart/dispatch/metrics")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["store_id"] == "store:1"
            assert data[0]["total_couriers"] == 10
            assert data[0]["available_couriers"] == 5
            assert data[0]["orders_in_queue"] == 3
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_filters_by_store_id(self, mock_freshmart_service):
        """Test endpoint accepts store_id filter."""
        app.dependency_overrides[get_freshmart_service] = lambda: mock_freshmart_service
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/freshmart/dispatch/metrics", params={"store_id": "store:1"}
                )

            assert response.status_code == 200
            mock_freshmart_service.list_store_courier_metrics.assert_called_once_with(
                store_id="store:1"
            )
        finally:
            app.dependency_overrides.clear()
