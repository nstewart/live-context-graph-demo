"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_stores():
    """Sample store data for testing."""
    return [
        {
            "store_id": "store:1",
            "store_name": "FreshMart Manhattan",
            "store_address": "123 Main St, Manhattan, NY",
            "zone": "Manhattan",
        },
        {
            "store_id": "store:2",
            "store_name": "FreshMart Brooklyn",
            "store_address": "456 Oak Ave, Brooklyn, NY",
            "zone": "Brooklyn",
        },
    ]


@pytest.fixture
def sample_customers():
    """Sample customer data for testing."""
    return [
        {
            "customer_id": "customer:1001",
            "customer_name": "John Doe",
            "customer_email": "john@example.com",
            "customer_address": "789 Elm St, Manhattan, NY",
        },
        {
            "customer_id": "customer:1002",
            "customer_name": "Jane Smith",
            "customer_email": "jane@example.com",
            "customer_address": "321 Pine St, Brooklyn, NY",
        },
    ]


@pytest.fixture
def sample_products():
    """Sample product data for testing."""
    return [
        {
            "product_id": "product:1",
            "product_name": "Organic Milk",
            "unit_price": 4.99,
            "category": "Dairy",
        },
        {
            "product_id": "product:2",
            "product_name": "Fresh Eggs",
            "unit_price": 3.49,
            "category": "Dairy",
        },
        {
            "product_id": "product:3",
            "product_name": "Whole Wheat Bread",
            "unit_price": 2.99,
            "category": "Bakery",
        },
    ]


@pytest.fixture
def sample_orders():
    """Sample order data for testing."""
    return [
        {
            "order_id": "order:FM-10001",
            "order_status": "CREATED",
            "customer_id": "customer:1001",
            "store_id": "store:1",
        },
        {
            "order_id": "order:FM-10002",
            "order_status": "PICKING",
            "customer_id": "customer:1002",
            "store_id": "store:2",
        },
    ]
