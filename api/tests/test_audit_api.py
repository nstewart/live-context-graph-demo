"""Tests for the audit API routes."""

import time

import pytest
from httpx import AsyncClient

from src.audit.write_store import WriteEvent, get_write_store


@pytest.fixture(autouse=True)
def clear_write_store():
    """Clear the write store before each test."""
    store = get_write_store()
    store.clear()
    yield
    store.clear()


@pytest.mark.asyncio
async def test_get_writes_empty_store(async_client: AsyncClient):
    """Test getting writes from an empty store."""
    response = await async_client.get("/api/audit/writes")

    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) == 0


@pytest.mark.asyncio
async def test_get_writes_returns_events(async_client: AsyncClient):
    """Test getting writes returns events in the store."""
    store = get_write_store()

    # Add some test events
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            batch_id="batch123",
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            batch_id="batch124",
        ),
    ]
    store.add_events(events)

    response = await async_client.get("/api/audit/writes")

    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_get_writes_with_since_ts_filter(async_client: AsyncClient):
    """Test filtering writes by timestamp."""
    store = get_write_store()

    # Add events with recent timestamps to avoid TTL expiration
    base_time = time.time()
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 30,  # 30 seconds ago
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 20,  # 20 seconds ago
        ),
        WriteEvent(
            subject_id="order:FM-1003",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 10,  # 10 seconds ago
        ),
    ]
    store.add_events(events)

    # Filter by timestamp - should get events from last 25 seconds
    since_ts = base_time - 25
    response = await async_client.get(f"/api/audit/writes?since_ts={since_ts}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 2
    # Should only return events with timestamp > since_ts
    assert all(e["timestamp"] > since_ts for e in data["events"])


@pytest.mark.asyncio
async def test_get_writes_with_subject_ids_filter(async_client: AsyncClient):
    """Test filtering writes by subject IDs."""
    store = get_write_store()

    # Add events with different subject IDs (use recent timestamps)
    base_time = time.time()
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 10,
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 5,
        ),
        WriteEvent(
            subject_id="customer:123",
            predicate="customer_name",
            old_value=None,
            new_value="John Doe",
            operation="INSERT",
            timestamp=base_time,
        ),
    ]
    store.add_events(events)

    # Filter by subject IDs
    response = await async_client.get("/api/audit/writes?subject_ids=order:FM-1001,order:FM-1002")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 2
    assert all(e["subject_id"].startswith("order:") for e in data["events"])


@pytest.mark.asyncio
async def test_get_writes_with_limit(async_client: AsyncClient):
    """Test limiting the number of returned writes."""
    store = get_write_store()

    # Add 20 events
    events = [
        WriteEvent(
            subject_id=f"order:FM-{i:04d}",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        )
        for i in range(20)
    ]
    store.add_events(events)

    # Request with limit
    response = await async_client.get("/api/audit/writes?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 5


@pytest.mark.asyncio
async def test_get_writes_limit_validation_too_low(async_client: AsyncClient):
    """Test that limit validation rejects values < 1."""
    response = await async_client.get("/api/audit/writes?limit=0")

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_writes_limit_validation_too_high(async_client: AsyncClient):
    """Test that limit validation rejects values > 500."""
    response = await async_client.get("/api/audit/writes?limit=1000")

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_get_writes_combined_filters(async_client: AsyncClient):
    """Test using multiple filters together."""
    store = get_write_store()

    # Add events with recent timestamps to avoid TTL expiration
    base_time = time.time()
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 30,  # 30 seconds ago
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=base_time - 20,  # 20 seconds ago
        ),
        WriteEvent(
            subject_id="customer:123",
            predicate="customer_name",
            old_value=None,
            new_value="John Doe",
            operation="INSERT",
            timestamp=base_time - 10,  # 10 seconds ago
        ),
    ]
    store.add_events(events)

    # Filter by timestamp AND subject_ids AND limit
    since_ts = base_time - 60  # Everything within last minute
    response = await async_client.get(
        f"/api/audit/writes?since_ts={since_ts}&subject_ids=order:FM-1001,order:FM-1002&limit=1"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["subject_id"].startswith("order:")


@pytest.mark.asyncio
async def test_get_writes_returns_most_recent_first(async_client: AsyncClient):
    """Test that events are returned in reverse chronological order."""
    store = get_write_store()

    # Add events with recent timestamps to avoid TTL expiration
    base_time = time.time()
    ts1 = base_time - 30  # 30 seconds ago
    ts2 = base_time - 20  # 20 seconds ago
    ts3 = base_time - 10  # 10 seconds ago
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=ts1,
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=ts2,
        ),
        WriteEvent(
            subject_id="order:FM-1003",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=ts3,
        ),
    ]
    store.add_events(events)

    response = await async_client.get("/api/audit/writes")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 3
    # Should be in descending order (most recent first)
    assert data["events"][0]["timestamp"] == ts3
    assert data["events"][1]["timestamp"] == ts2
    assert data["events"][2]["timestamp"] == ts1


@pytest.mark.asyncio
async def test_get_writes_includes_all_fields(async_client: AsyncClient):
    """Test that all event fields are included in the response."""
    store = get_write_store()

    event = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value="CREATED",
        new_value="CONFIRMED",
        operation="UPDATE",
        batch_id="batch123",
    )
    store.add_event(event)

    response = await async_client.get("/api/audit/writes")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1

    returned_event = data["events"][0]
    assert returned_event["subject_id"] == "order:FM-1001"
    assert returned_event["predicate"] == "order_status"
    assert returned_event["old_value"] == "CREATED"
    assert returned_event["new_value"] == "CONFIRMED"
    assert returned_event["operation"] == "UPDATE"
    assert returned_event["batch_id"] == "batch123"
    assert "timestamp" in returned_event


@pytest.mark.asyncio
async def test_get_writes_batch_grouping(async_client: AsyncClient):
    """Test that events with the same batch_id are returned together."""
    store = get_write_store()

    batch_id = "batch789"

    # Add multiple events with the same batch_id
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            batch_id=batch_id,
        ),
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="customer_id",
            old_value=None,
            new_value="customer:123",
            operation="INSERT",
            batch_id=batch_id,
        ),
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="store_id",
            old_value=None,
            new_value="store:456",
            operation="INSERT",
            batch_id=batch_id,
        ),
    ]
    store.add_events(events)

    response = await async_client.get("/api/audit/writes")

    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 3
    # All should have the same batch_id
    assert all(e["batch_id"] == batch_id for e in data["events"])
