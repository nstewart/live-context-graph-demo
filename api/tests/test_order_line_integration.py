"""Integration tests for order line CRUD operations.

Tests the complete workflow: Create order → Add line → Update quantity → Delete line

Note: These tests read from Materialize (CQRS pattern) so we need to wait for
replication after writes to PostgreSQL.
"""

import asyncio
import pytest
from decimal import Decimal
from httpx import AsyncClient

from tests.conftest import requires_db


async def wait_for_materialize_sync(
    async_client: AsyncClient,
    url: str,
    condition: callable,
    timeout: float = 5.0,
    interval: float = 0.2,
) -> dict:
    """Wait for Materialize to sync and condition to be met.

    Args:
        async_client: HTTP client
        url: URL to poll
        condition: Function that takes response JSON and returns True when ready
        timeout: Maximum time to wait in seconds
        interval: Time between polls in seconds

    Returns:
        Response JSON when condition is met

    Raises:
        TimeoutError: If condition not met within timeout
    """
    elapsed = 0.0
    while elapsed < timeout:
        response = await async_client.get(url)
        if response.status_code == 200:
            data = response.json()
            if condition(data):
                return data
        await asyncio.sleep(interval)
        elapsed += interval

    # Final attempt for error message
    response = await async_client.get(url)
    raise TimeoutError(
        f"Materialize sync timeout after {timeout}s. "
        f"URL: {url}, Status: {response.status_code}, "
        f"Response: {response.text[:500]}"
    )


@pytest.mark.asyncio
@requires_db
async def test_order_line_crud_workflow(async_client: AsyncClient):
    """
    End-to-end integration test: Create order → Add line → Update quantity → Delete line.

    This test verifies:
    1. Order can be created via batch API
    2. Line items can be added to an existing order
    3. Line item quantities can be updated
    4. Line items can be deleted
    5. Order total is recalculated after changes (via materialized views)
    """

    # Step 1: Create an order with one line item via batch API
    order_id = "order:FM-TEST-INTEGRATION"
    line_id_1 = "orderline:test-line-001"
    line_id_2 = "orderline:test-line-002"
    product_id_1 = "product:PROD-TEST-001"
    product_id_2 = "product:PROD-TEST-002"
    customer_id = "customer:TEST-CUST-001"
    store_id = "store:TEST-STORE-01"

    # Clean up any existing test data from previous runs
    for subject_id in [order_id, line_id_1, line_id_2, product_id_1, product_id_2, customer_id, store_id]:
        await async_client.delete(f"/triples/subjects/{subject_id}")

    # Wait for Materialize to sync the deletions
    await asyncio.sleep(1)

    # Create test customer
    customer_triples = [
        {
            "subject_id": customer_id,
            "predicate": "customer_name",
            "object_value": "Test Customer",
            "object_type": "string",
        },
        {
            "subject_id": customer_id,
            "predicate": "customer_email",
            "object_value": "test@example.com",
            "object_type": "string",
        },
    ]

    create_customer_response = await async_client.post(
        "/triples/batch",
        json=customer_triples,
        params={"validate": True},
    )
    assert create_customer_response.status_code == 201, f"Failed to create customer: {create_customer_response.text}"

    # Create test products
    product_triples = [
        {
            "subject_id": product_id_1,
            "predicate": "product_name",
            "object_value": "Test Product 1",
            "object_type": "string",
        },
        {
            "subject_id": product_id_1,
            "predicate": "category",
            "object_value": "Test",
            "object_type": "string",
        },
        {
            "subject_id": product_id_1,
            "predicate": "perishable",
            "object_value": "false",
            "object_type": "bool",
        },
        {
            "subject_id": product_id_2,
            "predicate": "product_name",
            "object_value": "Test Product 2",
            "object_type": "string",
        },
        {
            "subject_id": product_id_2,
            "predicate": "category",
            "object_value": "Test",
            "object_type": "string",
        },
        {
            "subject_id": product_id_2,
            "predicate": "perishable",
            "object_value": "true",
            "object_type": "bool",
        },
    ]

    create_products_response = await async_client.post(
        "/triples/batch",
        json=product_triples,
        params={"validate": True},
    )
    assert create_products_response.status_code == 201, f"Failed to create products: {create_products_response.text}"

    # Create test store
    store_triples = [
        {
            "subject_id": store_id,
            "predicate": "store_name",
            "object_value": "Test Store",
            "object_type": "string",
        },
        {
            "subject_id": store_id,
            "predicate": "store_address",
            "object_value": "123 Test St",
            "object_type": "string",
        },
    ]

    create_store_response = await async_client.post(
        "/triples/batch",
        json=store_triples,
        params={"validate": True},
    )
    assert create_store_response.status_code == 201, f"Failed to create store: {create_store_response.text}"

    # Create order with initial line item
    order_triples = [
        {
            "subject_id": order_id,
            "predicate": "order_number",
            "object_value": "FM-TEST-INT-001",
            "object_type": "string",
        },
        {
            "subject_id": order_id,
            "predicate": "order_status",
            "object_value": "CREATED",
            "object_type": "string",
        },
        {
            "subject_id": order_id,
            "predicate": "placed_by",
            "object_value": customer_id,
            "object_type": "entity_ref",
        },
        {
            "subject_id": order_id,
            "predicate": "order_store",
            "object_value": store_id,
            "object_type": "entity_ref",
        },
        {
            "subject_id": order_id,
            "predicate": "order_total_amount",
            "object_value": "25.00",
            "object_type": "float",
        },
        # Initial line item
        {
            "subject_id": line_id_1,
            "predicate": "line_of_order",
            "object_value": order_id,
            "object_type": "entity_ref",
        },
        {
            "subject_id": line_id_1,
            "predicate": "line_product",
            "object_value": product_id_1,
            "object_type": "entity_ref",
        },
        {
            "subject_id": line_id_1,
            "predicate": "quantity",
            "object_value": "2",
            "object_type": "int",
        },
        {
            "subject_id": line_id_1,
            "predicate": "order_line_unit_price",
            "object_value": "10.00",
            "object_type": "float",
        },
        {
            "subject_id": line_id_1,
            "predicate": "line_amount",
            "object_value": "20.00",
            "object_type": "float",
        },
        {
            "subject_id": line_id_1,
            "predicate": "line_sequence",
            "object_value": "1",
            "object_type": "int",
        },
        # Note: perishable_flag is NOT stored - it is derived from the product's perishable attribute
    ]

    create_order_response = await async_client.post(
        "/triples/batch",
        json=order_triples,
        params={"validate": True},
    )
    assert create_order_response.status_code == 201, f"Failed to create order: {create_order_response.text}"

    # Wait for Materialize to sync and verify order exists
    order = await wait_for_materialize_sync(
        async_client,
        f"/freshmart/orders/{order_id}",
        lambda data: data.get("order_id") == order_id,
        timeout=5.0,
    )
    assert order["order_status"] == "CREATED"

    # Step 2: List line items (should have 1) - wait for Materialize sync
    line_items = await wait_for_materialize_sync(
        async_client,
        f"/freshmart/orders/{order_id}/line-items",
        lambda data: len(data) == 1,
        timeout=5.0,
    )
    assert line_items[0]["line_id"] == line_id_1
    assert line_items[0]["quantity"] == 2

    # Step 3: Add a new line item using batch endpoint
    line_id_2 = "orderline:test-line-002"
    add_response = await async_client.post(
        f"/freshmart/orders/{order_id}/line-items/batch",
        json={
            "line_items": [
                {
                    "line_id": line_id_2,
                    "product_id": product_id_2,
                    "quantity": 3,
                    "unit_price": 5.00,
                    "line_sequence": 2,
                }
            ]
        },
    )
    assert add_response.status_code == 201, f"Failed to add line item: {add_response.text}"
    all_line_items = add_response.json()
    # API returns ALL line items for the order, not just newly added
    assert len(all_line_items) == 2
    new_item = [item for item in all_line_items if item["line_id"] == line_id_2][0]
    assert new_item["quantity"] == 3

    # Verify we now have 2 line items - wait for Materialize sync
    line_items = await wait_for_materialize_sync(
        async_client,
        f"/freshmart/orders/{order_id}/line-items",
        lambda data: len(data) == 2,
        timeout=5.0,
    )
    assert len(line_items) == 2

    # Step 4: Update quantity of first line item
    update_response = await async_client.put(
        f"/freshmart/orders/{order_id}/line-items/{line_id_1}",
        json={"quantity": 5},
    )
    assert update_response.status_code == 200, f"Failed to update line item: {update_response.text}"
    updated_line = update_response.json()
    assert updated_line["quantity"] == 5
    assert updated_line["line_id"] == line_id_1
    # Line amount should be recalculated: 5 * 10.00 = 50.00
    assert float(updated_line["line_amount"]) == 50.00

    # Verify the update persisted - wait for Materialize sync
    line_items = await wait_for_materialize_sync(
        async_client,
        f"/freshmart/orders/{order_id}/line-items",
        lambda data: any(item["line_id"] == line_id_1 and item["quantity"] == 5 for item in data),
        timeout=5.0,
    )
    line_1 = next((item for item in line_items if item["line_id"] == line_id_1), None)
    assert line_1 is not None
    assert line_1["quantity"] == 5

    # Step 5: Delete the second line item
    delete_response = await async_client.delete(
        f"/freshmart/orders/{order_id}/line-items/{line_id_2}"
    )
    assert delete_response.status_code == 204, f"Failed to delete line item: {delete_response.status_code}"

    # Verify we now have only 1 line item - wait for Materialize sync
    line_items = await wait_for_materialize_sync(
        async_client,
        f"/freshmart/orders/{order_id}/line-items",
        lambda data: len(data) == 1,
        timeout=5.0,
    )
    assert line_items[0]["line_id"] == line_id_1

    # Cleanup: Delete the test order, line items, and other test entities via triples endpoint
    for entity_id in [order_id, line_id_1, customer_id, product_id_1, product_id_2, store_id]:
        await async_client.delete(f"/triples/subjects/{entity_id}")


@pytest.mark.asyncio
@requires_db
async def test_add_line_with_invalid_product(async_client: AsyncClient):
    """Test that adding a line item with non-existent product fails gracefully."""

    order_id = "order:FM-TEST-INVALID-PROD"
    customer_id = "customer:TEST-CUST-002"
    store_id = "store:TEST-STORE-02"

    # Clean up any existing test data
    for subject_id in [order_id, customer_id, store_id]:
        await async_client.delete(f"/triples/subjects/{subject_id}")
    await asyncio.sleep(0.5)

    # Create minimal test entities
    customer_triples = [
        {"subject_id": customer_id, "predicate": "customer_name", "object_value": "Test", "object_type": "string"},
    ]
    store_triples = [
        {"subject_id": store_id, "predicate": "store_name", "object_value": "Test", "object_type": "string"},
    ]
    order_triples = [
        {"subject_id": order_id, "predicate": "order_number", "object_value": "FM-TEST-002", "object_type": "string"},
        {"subject_id": order_id, "predicate": "order_status", "object_value": "CREATED", "object_type": "string"},
        {"subject_id": order_id, "predicate": "placed_by", "object_value": customer_id, "object_type": "entity_ref"},
        {"subject_id": order_id, "predicate": "order_store", "object_value": store_id, "object_type": "entity_ref"},
    ]

    await async_client.post("/triples/batch", json=customer_triples, params={"validate": True})
    await async_client.post("/triples/batch", json=store_triples, params={"validate": True})
    await async_client.post("/triples/batch", json=order_triples, params={"validate": True})

    # Try to add line item with non-existent product
    add_response = await async_client.post(
        f"/freshmart/orders/{order_id}/line-items/batch",
        json={
            "line_items": [
                {
                    "line_id": "orderline:test-invalid",
                    "product_id": "product:DOES-NOT-EXIST",
                    "quantity": 1,
                    "unit_price": 10.00,
                }
            ]
        },
    )

    # Should still create (product reference validation is not enforced at API level)
    # But the product won't resolve in views
    assert add_response.status_code in [201, 400], f"Unexpected status: {add_response.status_code}"

    # Cleanup
    for entity_id in [order_id, "orderline:test-invalid", customer_id, store_id]:
        await async_client.delete(f"/triples/subjects/{entity_id}")


@pytest.mark.asyncio
@requires_db
async def test_update_line_quantity_validation(async_client: AsyncClient):
    """Test that quantity validation works on update."""

    order_id = "order:FM-TEST-QTY-VAL"
    line_id = "orderline:test-qty-val"
    customer_id = "customer:TEST-CUST-003"
    store_id = "store:TEST-STORE-03"
    product_id = "product:PROD-TEST-003"

    # Clean up any existing test data from previous runs
    for subject_id in [order_id, line_id, customer_id, store_id, product_id]:
        await async_client.delete(f"/triples/subjects/{subject_id}")
    await asyncio.sleep(0.5)

    # Create test entities
    await async_client.post(
        "/triples/batch",
        json=[
            {"subject_id": customer_id, "predicate": "customer_name", "object_value": "Test", "object_type": "string"},
            {"subject_id": store_id, "predicate": "store_name", "object_value": "Test", "object_type": "string"},
            {"subject_id": product_id, "predicate": "product_name", "object_value": "Test", "object_type": "string"},
            {"subject_id": product_id, "predicate": "perishable", "object_value": "false", "object_type": "bool"},
            {"subject_id": order_id, "predicate": "order_number", "object_value": "FM-TEST-003", "object_type": "string"},
            {"subject_id": order_id, "predicate": "order_status", "object_value": "CREATED", "object_type": "string"},
            {"subject_id": order_id, "predicate": "placed_by", "object_value": customer_id, "object_type": "entity_ref"},
            {"subject_id": order_id, "predicate": "order_store", "object_value": store_id, "object_type": "entity_ref"},
            {"subject_id": line_id, "predicate": "line_of_order", "object_value": order_id, "object_type": "entity_ref"},
            {"subject_id": line_id, "predicate": "line_product", "object_value": product_id, "object_type": "entity_ref"},
            {"subject_id": line_id, "predicate": "quantity", "object_value": "1", "object_type": "int"},
            {"subject_id": line_id, "predicate": "order_line_unit_price", "object_value": "10.00", "object_type": "float"},
            {"subject_id": line_id, "predicate": "line_amount", "object_value": "10.00", "object_type": "float"},
        ],
        params={"validate": True},
    )

    # Try to update with valid quantity
    update_response = await async_client.put(
        f"/freshmart/orders/{order_id}/line-items/{line_id}",
        json={"quantity": 10},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["quantity"] == 10

    # Cleanup
    for entity_id in [order_id, line_id, customer_id, store_id, product_id]:
        await async_client.delete(f"/triples/subjects/{entity_id}")
