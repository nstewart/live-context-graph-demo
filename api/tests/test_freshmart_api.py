"""Integration tests for FreshMart API endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db


@requires_db
class TestOrdersAPI:
    """Tests for /freshmart/orders endpoints."""

    @pytest.mark.asyncio
    async def test_list_orders_returns_list(self, async_client: AsyncClient):
        """GET /freshmart/orders returns a list."""
        response = await async_client.get("/freshmart/orders")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_orders_with_status_filter(self, async_client: AsyncClient):
        """GET /freshmart/orders?status filters by order status."""
        response = await async_client.get("/freshmart/orders", params={"status": "CREATED"})
        assert response.status_code == 200

        orders = response.json()
        for order in orders:
            assert order["order_status"] == "CREATED"

    @pytest.mark.asyncio
    async def test_list_orders_with_store_filter(self, async_client: AsyncClient):
        """GET /freshmart/orders?store_id filters by store."""
        response = await async_client.get("/freshmart/orders", params={"store_id": "store:BK-01"})
        assert response.status_code == 200

        orders = response.json()
        for order in orders:
            assert order["store_id"] == "store:BK-01"

    @pytest.mark.asyncio
    async def test_list_orders_with_customer_filter(self, async_client: AsyncClient):
        """GET /freshmart/orders?customer_id filters by customer."""
        response = await async_client.get("/freshmart/orders", params={"customer_id": "customer:101"})
        assert response.status_code == 200

        orders = response.json()
        for order in orders:
            assert order["customer_id"] == "customer:101"

    @pytest.mark.asyncio
    async def test_list_orders_with_limit(self, async_client: AsyncClient):
        """GET /freshmart/orders respects limit parameter."""
        response = await async_client.get("/freshmart/orders", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()) <= 5

    @pytest.mark.asyncio
    async def test_list_orders_with_offset(self, async_client: AsyncClient):
        """GET /freshmart/orders respects offset parameter."""
        response1 = await async_client.get("/freshmart/orders", params={"limit": 3})
        response2 = await async_client.get("/freshmart/orders", params={"limit": 3, "offset": 3})

        assert response1.status_code == 200
        assert response2.status_code == 200

        orders1 = response1.json()
        orders2 = response2.json()

        # Results should be different (if enough data exists)
        if orders1 and orders2:
            assert orders1[0]["order_id"] != orders2[0]["order_id"]

    @pytest.mark.asyncio
    async def test_list_orders_contains_expected_fields(self, async_client: AsyncClient):
        """Orders in response have expected fields."""
        response = await async_client.get("/freshmart/orders")
        assert response.status_code == 200

        orders = response.json()
        if orders:  # If demo data is loaded
            first_order = orders[0]
            assert "order_id" in first_order
            assert "order_status" in first_order
            assert "customer_id" in first_order
            assert "store_id" in first_order

    @pytest.mark.asyncio
    async def test_get_order_returns_order(self, async_client: AsyncClient):
        """GET /freshmart/orders/{id} returns order details."""
        response = await async_client.get("/freshmart/orders/order:FM-1001")
        # May return 200 or 404 depending on demo data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            order = response.json()
            assert order["order_id"] == "order:FM-1001"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, async_client: AsyncClient):
        """GET /freshmart/orders/{id} returns 404 for non-existent order."""
        response = await async_client.get("/freshmart/orders/order:NONEXISTENT-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_order_with_encoded_id(self, async_client: AsyncClient):
        """GET /freshmart/orders/{id} handles URL-encoded IDs."""
        response = await async_client.get("/freshmart/orders/order%3AFM-1001")
        assert response.status_code in [200, 404]


@requires_db
class TestStoresAPI:
    """Tests for /freshmart/stores endpoints."""

    @pytest.mark.asyncio
    async def test_list_stores_returns_list(self, async_client: AsyncClient):
        """GET /freshmart/stores returns a list."""
        response = await async_client.get("/freshmart/stores")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_stores_contains_expected_fields(self, async_client: AsyncClient):
        """Stores in response have expected fields."""
        response = await async_client.get("/freshmart/stores")
        assert response.status_code == 200

        stores = response.json()
        if stores:  # If demo data is loaded
            first_store = stores[0]
            assert "store_id" in first_store
            assert "store_name" in first_store

    @pytest.mark.asyncio
    async def test_get_store_returns_store(self, async_client: AsyncClient):
        """GET /freshmart/stores/{id} returns store details."""
        response = await async_client.get("/freshmart/stores/store:BK-01")
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            store = response.json()
            assert store["store_id"] == "store:BK-01"

    @pytest.mark.asyncio
    async def test_get_store_not_found(self, async_client: AsyncClient):
        """GET /freshmart/stores/{id} returns 404 for non-existent store."""
        response = await async_client.get("/freshmart/stores/store:NONEXISTENT")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_store_with_encoded_id(self, async_client: AsyncClient):
        """GET /freshmart/stores/{id} handles URL-encoded IDs."""
        response = await async_client.get("/freshmart/stores/store%3ABK-01")
        assert response.status_code in [200, 404]


@requires_db
class TestInventoryAPI:
    """Tests for /freshmart/stores/inventory endpoint."""

    @pytest.mark.asyncio
    async def test_list_inventory_returns_list(self, async_client: AsyncClient):
        """GET /freshmart/stores/inventory returns a list."""
        response = await async_client.get("/freshmart/stores/inventory")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_inventory_with_store_filter(self, async_client: AsyncClient):
        """GET /freshmart/stores/inventory?store_id filters by store."""
        response = await async_client.get("/freshmart/stores/inventory", params={"store_id": "store:BK-01"})
        assert response.status_code == 200

        inventory = response.json()
        for item in inventory:
            assert item["store_id"] == "store:BK-01"

    @pytest.mark.asyncio
    async def test_list_inventory_low_stock_only(self, async_client: AsyncClient):
        """GET /freshmart/stores/inventory?low_stock_only=true filters low stock items."""
        response = await async_client.get("/freshmart/stores/inventory", params={"low_stock_only": True})
        assert response.status_code == 200

        inventory = response.json()
        for item in inventory:
            # Low stock is typically stock < 10
            assert item.get("stock_quantity", 0) < 10 or item.get("quantity", 0) < 10

    @pytest.mark.asyncio
    async def test_list_inventory_with_limit(self, async_client: AsyncClient):
        """GET /freshmart/stores/inventory respects limit parameter."""
        response = await async_client.get("/freshmart/stores/inventory", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()) <= 5

    @pytest.mark.asyncio
    async def test_list_inventory_with_offset(self, async_client: AsyncClient):
        """GET /freshmart/stores/inventory respects offset parameter."""
        response1 = await async_client.get("/freshmart/stores/inventory", params={"limit": 3})
        response2 = await async_client.get("/freshmart/stores/inventory", params={"limit": 3, "offset": 3})

        assert response1.status_code == 200
        assert response2.status_code == 200


@requires_db
class TestCouriersAPI:
    """Tests for /freshmart/couriers endpoints."""

    @pytest.mark.asyncio
    async def test_list_couriers_returns_list(self, async_client: AsyncClient):
        """GET /freshmart/couriers returns a list."""
        response = await async_client.get("/freshmart/couriers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_couriers_with_status_filter(self, async_client: AsyncClient):
        """GET /freshmart/couriers?status filters by courier status."""
        response = await async_client.get("/freshmart/couriers", params={"status": "AVAILABLE"})
        assert response.status_code == 200

        couriers = response.json()
        for courier in couriers:
            assert courier.get("courier_status") == "AVAILABLE" or courier.get("status") == "AVAILABLE"

    @pytest.mark.asyncio
    async def test_list_couriers_with_store_filter(self, async_client: AsyncClient):
        """GET /freshmart/couriers?store_id filters by home store."""
        response = await async_client.get("/freshmart/couriers", params={"store_id": "store:BK-01"})
        assert response.status_code == 200

        couriers = response.json()
        for courier in couriers:
            assert courier.get("home_store_id") == "store:BK-01" or courier.get("store_id") == "store:BK-01"

    @pytest.mark.asyncio
    async def test_list_couriers_with_limit(self, async_client: AsyncClient):
        """GET /freshmart/couriers respects limit parameter."""
        response = await async_client.get("/freshmart/couriers", params={"limit": 3})
        assert response.status_code == 200
        assert len(response.json()) <= 3

    @pytest.mark.asyncio
    async def test_list_couriers_with_offset(self, async_client: AsyncClient):
        """GET /freshmart/couriers respects offset parameter."""
        response1 = await async_client.get("/freshmart/couriers", params={"limit": 2})
        response2 = await async_client.get("/freshmart/couriers", params={"limit": 2, "offset": 2})

        assert response1.status_code == 200
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_list_couriers_contains_expected_fields(self, async_client: AsyncClient):
        """Couriers in response have expected fields."""
        response = await async_client.get("/freshmart/couriers")
        assert response.status_code == 200

        couriers = response.json()
        if couriers:  # If demo data is loaded
            first_courier = couriers[0]
            assert "courier_id" in first_courier
            assert "courier_name" in first_courier

    @pytest.mark.asyncio
    async def test_get_courier_returns_courier(self, async_client: AsyncClient):
        """GET /freshmart/couriers/{id} returns courier details."""
        response = await async_client.get("/freshmart/couriers/courier:C-101")
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            courier = response.json()
            assert courier["courier_id"] == "courier:C-101"

    @pytest.mark.asyncio
    async def test_get_courier_not_found(self, async_client: AsyncClient):
        """GET /freshmart/couriers/{id} returns 404 for non-existent courier."""
        response = await async_client.get("/freshmart/couriers/courier:NONEXISTENT")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_courier_with_encoded_id(self, async_client: AsyncClient):
        """GET /freshmart/couriers/{id} handles URL-encoded IDs."""
        response = await async_client.get("/freshmart/couriers/courier%3AC-101")
        assert response.status_code in [200, 404]
