"""Pytest fixtures for search-sync tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_mz_client():
    """Create a mock Materialize client."""
    client = AsyncMock()
    client.refresh_views = AsyncMock()
    client.get_cursor = AsyncMock(return_value=None)
    client.update_cursor = AsyncMock()
    client.query_orders_search_source = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_os_client():
    """Create a mock OpenSearch client."""
    client = AsyncMock()
    client.setup_indices = AsyncMock()
    client.bulk_upsert = AsyncMock(return_value=(0, 0))
    client.bulk_patch = AsyncMock(return_value=(0, 0))
    client.bulk_delete = AsyncMock(return_value=(0, 0))
    client.search_orders = AsyncMock(return_value=[])
    client.health_check = AsyncMock(return_value=True)
    client.ensure_index = AsyncMock()
    client.close = AsyncMock()
    client.orders_index = "orders"
    return client


@pytest.fixture
def mock_embedder():
    """Create a mock Embedder that returns deterministic 384-dim vectors."""
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1] * 384]
    return embedder


@pytest.fixture
def sample_order_document():
    """Sample order document from Materialize."""
    from datetime import datetime, timezone

    return {
        "order_id": "order:FM-1001",
        "order_number": "FM-1001",
        "order_status": "OUT_FOR_DELIVERY",
        "store_id": "store:BK-01",
        "customer_id": "customer:101",
        "delivery_window_start": "2024-01-15T14:00:00",
        "delivery_window_end": "2024-01-15T16:00:00",
        "order_total_amount": 45.99,
        "customer_name": "Alex Thompson",
        "customer_email": "alex.thompson@example.com",
        "customer_address": "123 Main St, Brooklyn, NY",
        "store_name": "FreshMart Brooklyn Heights",
        "store_zone": "Brooklyn",
        "store_address": "100 Court St, Brooklyn, NY",
        "assigned_courier_id": "courier:C-101",
        "delivery_task_status": "IN_PROGRESS",
        "delivery_eta": "2024-01-15T15:30:00",
        "effective_updated_at": datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def sample_order_documents(sample_order_document):
    """List of sample order documents."""
    from datetime import datetime, timezone, timedelta

    docs = [sample_order_document]
    doc2 = {**sample_order_document}
    doc2["order_id"] = "order:FM-1002"
    doc2["order_number"] = "FM-1002"
    doc2["customer_name"] = "Jordan Lee"
    doc2["effective_updated_at"] = datetime(2024, 1, 15, 14, 35, 0, tzinfo=timezone.utc)
    docs.append(doc2)
    return docs
