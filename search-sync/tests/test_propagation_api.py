"""Tests for the propagation API."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src.propagation_api import create_app
from src.propagation_events import PropagationEvent, get_propagation_store


@pytest.fixture
async def client(aiohttp_client):
    """Create a test client for the propagation API."""
    app = create_app()
    return await aiohttp_client(app)


@pytest.fixture(autouse=True)
def clear_propagation_store():
    """Clear the propagation store before each test."""
    store = get_propagation_store()
    store.clear()
    yield
    store.clear()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health check endpoint."""
    response = await client.get("/health")

    assert response.status == 200
    data = await response.json()
    assert data["status"] == "healthy"
    assert "event_count" in data


@pytest.mark.asyncio
async def test_get_events_empty_store(client):
    """Test getting events from an empty store."""
    response = await client.get("/propagation/events")

    assert response.status == 200
    data = await response.json()
    assert "events" in data
    assert len(data["events"]) == 0


@pytest.mark.asyncio
async def test_get_events_returns_events(client):
    """Test getting events returns events in the store."""
    store = get_propagation_store()

    # Add some test events
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="orders",
            doc_id="order:FM-1002",
            operation="INSERT",
        ),
    ]
    store.add_events(events)

    response = await client.get("/propagation/events")

    assert response.status == 200
    data = await response.json()
    assert "events" in data
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_get_events_with_since_mz_ts_filter(client):
    """Test filtering events by mz_ts."""
    store = get_propagation_store()

    # Add events with different mz_ts values
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="orders",
            doc_id="order:FM-1002",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67894",
            index_name="orders",
            doc_id="order:FM-1003",
            operation="INSERT",
        ),
    ]
    store.add_events(events)

    # Filter by mz_ts
    response = await client.get("/propagation/events?since_mz_ts=12345-67891")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 2
    # Should only return events with mz_ts > 12345-67891
    assert all(e["mz_ts"] > "12345-67891" for e in data["events"])


@pytest.mark.asyncio
async def test_get_events_with_subject_ids_filter(client):
    """Test filtering events by subject IDs."""
    store = get_propagation_store()

    # Add events with different doc_ids
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="orders",
            doc_id="order:FM-1002",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="products",
            doc_id="product:ABC-123",
            operation="INSERT",
        ),
    ]
    store.add_events(events)

    # Filter by subject IDs
    response = await client.get("/propagation/events?subject_ids=order:FM-1001,order:FM-1002")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 2
    assert all(e["doc_id"].startswith("order:") for e in data["events"])


@pytest.mark.asyncio
async def test_get_events_with_limit(client):
    """Test limiting the number of returned events."""
    store = get_propagation_store()

    # Add 20 events
    events = [
        PropagationEvent(
            mz_ts=f"12345-{i:05d}",
            index_name="orders",
            doc_id=f"order:FM-{i:04d}",
            operation="INSERT",
        )
        for i in range(20)
    ]
    store.add_events(events)

    # Request with limit
    response = await client.get("/propagation/events?limit=5")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 5


@pytest.mark.asyncio
async def test_get_all_events(client):
    """Test the /propagation/events/all endpoint."""
    store = get_propagation_store()

    # Add events from different indexes
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="products",
            doc_id="product:ABC-123",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="customers",
            doc_id="customer:456",
            operation="INSERT",
        ),
    ]
    store.add_events(events)

    response = await client.get("/propagation/events/all")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 3


@pytest.mark.asyncio
async def test_get_all_events_with_since_mz_ts(client):
    """Test the /propagation/events/all endpoint with since_mz_ts filter."""
    store = get_propagation_store()

    # Add events with different mz_ts values
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="products",
            doc_id="product:ABC-123",
            operation="INSERT",
        ),
    ]
    store.add_events(events)

    response = await client.get("/propagation/events/all?since_mz_ts=12345-67891")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["doc_id"] == "product:ABC-123"


@pytest.mark.asyncio
async def test_get_all_events_with_limit(client):
    """Test the /propagation/events/all endpoint with limit."""
    store = get_propagation_store()

    # Add 10 events
    events = [
        PropagationEvent(
            mz_ts=f"12345-{i:05d}",
            index_name="orders",
            doc_id=f"order:FM-{i:04d}",
            operation="INSERT",
        )
        for i in range(10)
    ]
    store.add_events(events)

    response = await client.get("/propagation/events/all?limit=3")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 3


@pytest.mark.asyncio
async def test_events_include_all_fields(client):
    """Test that all event fields are included in the response."""
    store = get_propagation_store()

    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="UPDATE",
        field_changes={
            "status": {"old": "CREATED", "new": "CONFIRMED"},
        },
        display_name="Order FM-1001",
    )
    store.add_event(event)

    response = await client.get("/propagation/events")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 1

    returned_event = data["events"][0]
    assert returned_event["mz_ts"] == "12345-67890"
    assert returned_event["index_name"] == "orders"
    assert returned_event["doc_id"] == "order:FM-1001"
    assert returned_event["operation"] == "UPDATE"
    assert returned_event["field_changes"] == {"status": {"old": "CREATED", "new": "CONFIRMED"}}
    assert returned_event["display_name"] == "Order FM-1001"
    assert "timestamp" in returned_event


@pytest.mark.asyncio
async def test_events_returns_most_recent_first(client):
    """Test that events are returned in reverse chronological order."""
    store = get_propagation_store()

    # Add events with different timestamps
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="orders",
            doc_id="order:FM-1001",
            operation="INSERT",
            timestamp=100.0,
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="orders",
            doc_id="order:FM-1002",
            operation="INSERT",
            timestamp=200.0,
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="orders",
            doc_id="order:FM-1003",
            operation="INSERT",
            timestamp=300.0,
        ),
    ]
    store.add_events(events)

    response = await client.get("/propagation/events")

    assert response.status == 200
    data = await response.json()
    assert len(data["events"]) == 3
    # Should be in descending order
    assert data["events"][0]["timestamp"] == 300.0
    assert data["events"][1]["timestamp"] == 200.0
    assert data["events"][2]["timestamp"] == 100.0


@pytest.mark.asyncio
async def test_cors_headers_allowed_origin(client):
    """Test CORS headers for allowed origins."""
    response = await client.get(
        "/propagation/events",
        headers={"Origin": "http://localhost:5173"}
    )

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Methods" in response.headers


@pytest.mark.asyncio
async def test_cors_headers_disallowed_origin(client):
    """Test CORS headers for disallowed origins."""
    response = await client.get(
        "/propagation/events",
        headers={"Origin": "http://evil.com"}
    )

    assert response.status == 200
    # Should not set CORS header for disallowed origins
    assert "Access-Control-Allow-Origin" not in response.headers or \
           response.headers.get("Access-Control-Allow-Origin") != "http://evil.com"


@pytest.mark.asyncio
async def test_cors_preflight_request(client):
    """Test CORS preflight OPTIONS request."""
    response = await client.options(
        "/propagation/events",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        }
    )

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


@pytest.mark.asyncio
async def test_health_endpoint_event_count(client):
    """Test that health endpoint reports correct event count."""
    store = get_propagation_store()

    # Initially should be 0
    response = await client.get("/health")
    data = await response.json()
    assert data["event_count"] == 0

    # Add some events
    events = [
        PropagationEvent(
            mz_ts=f"12345-{i:05d}",
            index_name="orders",
            doc_id=f"order:FM-{i:04d}",
            operation="INSERT",
        )
        for i in range(5)
    ]
    store.add_events(events)

    # Should now report 5
    response = await client.get("/health")
    data = await response.json()
    assert data["event_count"] == 5


# =============================================================================
# Focus Context API Tests
# =============================================================================


@pytest.mark.asyncio
async def test_set_focus_endpoint(client):
    """Test POST /propagation/focus endpoint."""
    response = await client.post(
        "/propagation/focus",
        json={
            "order_id": "order:FM-1001",
            "store_id": "store:BK-01",
            "product_ids": ["product:prod001", "product:prod002"],
        },
    )

    assert response.status == 200
    data = await response.json()
    assert data["status"] == "ok"
    assert data["focus"]["order_id"] == "order:FM-1001"
    assert data["focus"]["store_id"] == "store:BK-01"
    assert data["focus"]["product_count"] == 2


@pytest.mark.asyncio
async def test_set_focus_endpoint_partial_data(client):
    """Test POST /propagation/focus with partial data."""
    # Only store_id, no order_id or product_ids
    response = await client.post(
        "/propagation/focus",
        json={
            "store_id": "store:BK-01",
        },
    )

    assert response.status == 200
    data = await response.json()
    assert data["status"] == "ok"
    assert data["focus"]["order_id"] is None
    assert data["focus"]["store_id"] == "store:BK-01"
    assert data["focus"]["product_count"] == 0


@pytest.mark.asyncio
async def test_set_focus_endpoint_empty_product_ids(client):
    """Test POST /propagation/focus with empty product_ids list."""
    response = await client.post(
        "/propagation/focus",
        json={
            "order_id": "order:FM-1001",
            "store_id": "store:BK-01",
            "product_ids": [],
        },
    )

    assert response.status == 200
    data = await response.json()
    assert data["focus"]["product_count"] == 0


@pytest.mark.asyncio
async def test_set_focus_endpoint_invalid_json(client):
    """Test POST /propagation/focus with invalid JSON."""
    response = await client.post(
        "/propagation/focus",
        data="not valid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status == 400
    data = await response.json()
    assert "error" in data
    assert "Invalid JSON" in data["error"]


@pytest.mark.asyncio
async def test_set_focus_endpoint_invalid_product_ids_type(client):
    """Test POST /propagation/focus with non-list product_ids."""
    response = await client.post(
        "/propagation/focus",
        json={
            "order_id": "order:FM-1001",
            "store_id": "store:BK-01",
            "product_ids": "not a list",
        },
    )

    assert response.status == 400
    data = await response.json()
    assert "error" in data
    assert "product_ids must be a list" in data["error"]


@pytest.mark.asyncio
async def test_clear_focus_endpoint(client):
    """Test DELETE /propagation/focus endpoint."""
    store = get_propagation_store()

    # First set a focus context
    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001"],
    )
    assert store.get_focus_context() is not None

    # Clear it via API
    response = await client.delete("/propagation/focus")

    assert response.status == 200
    data = await response.json()
    assert data["status"] == "ok"

    # Verify it's cleared
    assert store.get_focus_context() is None


@pytest.mark.asyncio
async def test_clear_focus_endpoint_when_not_set(client):
    """Test DELETE /propagation/focus when no focus is set."""
    store = get_propagation_store()
    assert store.get_focus_context() is None

    # Should still succeed
    response = await client.delete("/propagation/focus")

    assert response.status == 200
    data = await response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_focus_affects_event_priority(client):
    """Test that setting focus affects event priority in responses."""
    store = get_propagation_store()

    # Add events with store_id and product_id
    import time
    now = time.time()
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="inventory",
            doc_id="inventory:001",
            operation="UPDATE",
            timestamp=now,
            store_id="store:MAN-01",
            product_id="product:prod999",
            priority=1.0,  # Low priority - cascade
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="inventory",
            doc_id="inventory:002",
            operation="UPDATE",
            timestamp=now,
            store_id="store:BK-01",
            product_id="product:prod001",
            priority=1000.0,  # High priority - direct match
        ),
    ]
    store.add_events(events)

    # Set focus for store:BK-01 and product:prod001
    await client.post(
        "/propagation/focus",
        json={
            "order_id": "order:FM-1001",
            "store_id": "store:BK-01",
            "product_ids": ["product:prod001"],
        },
    )

    # Get events - high priority should come first
    response = await client.get("/propagation/events")
    data = await response.json()

    assert len(data["events"]) == 2
    # Direct match (high priority) should be first
    assert data["events"][0]["doc_id"] == "inventory:002"
    assert data["events"][0]["priority"] == 1000.0


@pytest.mark.asyncio
async def test_cors_for_post_focus(client):
    """Test CORS headers for POST /propagation/focus."""
    response = await client.post(
        "/propagation/focus",
        json={"store_id": "store:BK-01"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.asyncio
async def test_cors_for_delete_focus(client):
    """Test CORS headers for DELETE /propagation/focus."""
    response = await client.delete(
        "/propagation/focus",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
