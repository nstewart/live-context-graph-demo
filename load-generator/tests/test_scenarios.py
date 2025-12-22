"""Integration tests for scenario classes."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from loadgen.api_client import FreshMartAPIClient
from loadgen.data_generators import DataGenerator
from loadgen.scenarios import (
    CustomerScenario,
    InventoryScenario,
    OrderCreationScenario,
    OrderLifecycleScenario,
)


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    client = MagicMock(spec=FreshMartAPIClient)
    client.get_stores = AsyncMock(return_value=[{"store_id": "store:1", "store_name": "Test Store"}])
    client.get_customers = AsyncMock(return_value=[{"customer_id": "customer:1", "customer_name": "Test Customer"}])
    client.get_products = AsyncMock(
        return_value=[{"product_id": "product:1", "product_name": "Test Product", "unit_price": 4.99}]
    )
    client.get_orders = AsyncMock(
        return_value=[{"order_id": "order:FM-123", "status": "CREATED"}]
    )
    client.create_customer = AsyncMock(return_value={"success": True})
    client.create_order = AsyncMock(return_value={"success": True})
    client.update_order_status = AsyncMock(return_value={"success": True})
    client.update_inventory = AsyncMock(return_value={"success": True})
    return client


@pytest.fixture
def data_generator():
    """Create a data generator with fixed seed."""
    return DataGenerator(seed=42)


@pytest.mark.asyncio
async def test_order_creation_scenario_initialize(mock_api_client, data_generator):
    """Test order creation scenario initialization."""
    scenario = OrderCreationScenario(mock_api_client, data_generator)

    await scenario.initialize()

    # Verify API calls were made
    mock_api_client.get_stores.assert_called_once()
    mock_api_client.get_customers.assert_called_once()
    mock_api_client.get_products.assert_called_once()

    # Verify data was cached
    assert len(scenario.stores) > 0
    assert len(scenario.customers) > 0
    assert len(scenario.products) > 0


@pytest.mark.asyncio
async def test_order_creation_scenario_execute(mock_api_client, data_generator):
    """Test order creation scenario execution."""
    scenario = OrderCreationScenario(mock_api_client, data_generator)
    await scenario.initialize()

    result = await scenario.execute()

    # Verify result structure
    assert "success" in result
    assert result["success"] is True
    assert "order_id" in result

    # Verify API call was made
    mock_api_client.create_order.assert_called_once()


@pytest.mark.asyncio
async def test_order_lifecycle_scenario_noop_without_cancellation(mock_api_client, data_generator):
    """Test order lifecycle scenario returns noop when not cancelling.

    With courier dispatch enabled, status transitions are handled automatically.
    """
    scenario = OrderLifecycleScenario(mock_api_client, data_generator)

    result = await scenario.execute(force_cancellation=False)

    # Should return success with noop action
    assert result["success"] is True
    assert result["action"] == "noop"


@pytest.mark.asyncio
async def test_order_lifecycle_scenario_cancellation(mock_api_client, data_generator):
    """Test order lifecycle scenario forced cancellation.

    Cancellations only apply to orders in CREATED status (before courier pickup).
    """
    scenario = OrderLifecycleScenario(mock_api_client, data_generator)

    result = await scenario.execute(force_cancellation=True)

    # Result should indicate either success or no orders found
    assert "success" in result
    if result["success"] and result.get("action") == "cancelled":
        assert result["old_status"] == "CREATED"
        assert result["new_status"] == "CANCELLED"
        mock_api_client.update_order_status.assert_called_once()


@pytest.mark.asyncio
async def test_customer_scenario_initialize(mock_api_client, data_generator):
    """Test customer scenario initialization."""
    scenario = CustomerScenario(mock_api_client, data_generator)

    await scenario.initialize()

    # Verify API call was made
    mock_api_client.get_stores.assert_called_once()

    # Verify data was cached
    assert len(scenario.stores) > 0


@pytest.mark.asyncio
async def test_customer_scenario_execute(mock_api_client, data_generator):
    """Test customer scenario execution."""
    scenario = CustomerScenario(mock_api_client, data_generator)
    await scenario.initialize()

    result = await scenario.execute()

    # Verify result structure
    assert "success" in result
    assert result["success"] is True
    assert "customer_id" in result

    # Verify API call was made
    mock_api_client.create_customer.assert_called_once()


@pytest.mark.asyncio
async def test_inventory_scenario_initialize(mock_api_client, data_generator):
    """Test inventory scenario initialization."""
    scenario = InventoryScenario(mock_api_client, data_generator)

    await scenario.initialize()

    # Verify API calls were made
    mock_api_client.get_stores.assert_called_once()
    mock_api_client.get_products.assert_called_once()

    # Verify data was cached
    assert len(scenario.stores) > 0
    assert len(scenario.products) > 0


@pytest.mark.asyncio
async def test_inventory_scenario_execute(mock_api_client, data_generator):
    """Test inventory scenario execution."""
    scenario = InventoryScenario(mock_api_client, data_generator)
    await scenario.initialize()

    result = await scenario.execute()

    # Verify result structure
    assert "success" in result
    assert result["success"] is True
    assert "store_name" in result
    assert "product_name" in result
    assert "new_quantity" in result

    # Verify API call was made
    mock_api_client.update_inventory.assert_called_once()


@pytest.mark.asyncio
async def test_order_lifecycle_scenario_no_orders_to_cancel(mock_api_client, data_generator):
    """Test order lifecycle scenario with no orders to cancel.

    When force_cancellation=True but no CREATED orders exist.
    """
    # Mock empty order list for CREATED status
    mock_api_client.get_orders = AsyncMock(return_value=[])

    scenario = OrderLifecycleScenario(mock_api_client, data_generator)

    result = await scenario.execute(force_cancellation=True)

    # Should return failure when no orders found to cancel
    assert result["success"] is False
    assert "error" in result
    assert "CREATED" in result["error"]
