"""Tests for the WriteEventStore."""

import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.audit.write_store import WriteEvent, WriteEventStore, generate_batch_id


def test_generate_batch_id():
    """Test batch ID generation produces unique 8-character IDs."""
    batch_id1 = generate_batch_id()
    batch_id2 = generate_batch_id()

    assert len(batch_id1) == 8
    assert len(batch_id2) == 8
    assert batch_id1 != batch_id2


def test_write_event_to_dict():
    """Test WriteEvent serialization to dict."""
    event = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value="CREATED",
        new_value="CONFIRMED",
        operation="UPDATE",
        timestamp=1234567890.0,
        batch_id="abc123",
    )

    result = event.to_dict()

    assert result == {
        "subject_id": "order:FM-1001",
        "predicate": "order_status",
        "old_value": "CREATED",
        "new_value": "CONFIRMED",
        "operation": "UPDATE",
        "timestamp": 1234567890.0,
        "batch_id": "abc123",
    }


def test_write_event_defaults():
    """Test WriteEvent default values."""
    event = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
    )

    assert event.batch_id is None
    assert event.timestamp > 0  # Should have a default timestamp


def test_store_initialization():
    """Test WriteEventStore initialization."""
    store = WriteEventStore(ttl_seconds=600)

    assert len(store) == 0
    assert store._ttl_seconds == 600


def test_add_single_event():
    """Test adding a single event to the store."""
    store = WriteEventStore()
    event = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
    )

    store.add_event(event)

    assert len(store) == 1


def test_add_multiple_events():
    """Test adding multiple events at once."""
    store = WriteEventStore()
    events = [
        WriteEvent(
            subject_id="order:FM-1001",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        ),
        WriteEvent(
            subject_id="order:FM-1002",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        ),
    ]

    store.add_events(events)

    assert len(store) == 2


def test_get_events_returns_most_recent_first():
    """Test that get_events returns events in reverse chronological order."""
    store = WriteEventStore()

    # Add events with different timestamps
    event1 = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=100.0,
    )
    event2 = WriteEvent(
        subject_id="order:FM-1002",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=200.0,
    )
    event3 = WriteEvent(
        subject_id="order:FM-1003",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=300.0,
    )

    store.add_events([event1, event2, event3])

    results = store.get_events()

    assert len(results) == 3
    assert results[0]["timestamp"] == 300.0
    assert results[1]["timestamp"] == 200.0
    assert results[2]["timestamp"] == 100.0


def test_get_events_with_since_ts_filter():
    """Test filtering events by timestamp."""
    store = WriteEventStore()

    event1 = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=100.0,
    )
    event2 = WriteEvent(
        subject_id="order:FM-1002",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=200.0,
    )

    store.add_events([event1, event2])

    # Get events after timestamp 150
    results = store.get_events(since_ts=150.0)

    assert len(results) == 1
    assert results[0]["subject_id"] == "order:FM-1002"


def test_get_events_with_subject_ids_filter():
    """Test filtering events by subject IDs."""
    store = WriteEventStore()

    event1 = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
    )
    event2 = WriteEvent(
        subject_id="order:FM-1002",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
    )
    event3 = WriteEvent(
        subject_id="customer:123",
        predicate="customer_name",
        old_value=None,
        new_value="John Doe",
        operation="INSERT",
    )

    store.add_events([event1, event2, event3])

    # Filter by specific subject IDs
    results = store.get_events(subject_ids=["order:FM-1001", "order:FM-1002"])

    assert len(results) == 2
    assert all(r["subject_id"].startswith("order:") for r in results)


def test_get_events_with_limit():
    """Test limiting the number of returned events."""
    store = WriteEventStore()

    # Add 10 events
    events = [
        WriteEvent(
            subject_id=f"order:FM-{i:04d}",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        )
        for i in range(10)
    ]

    store.add_events(events)

    results = store.get_events(limit=5)

    assert len(results) == 5


def test_ttl_expiration():
    """Test that old events are expired based on TTL."""
    store = WriteEventStore(ttl_seconds=1.0)  # 1 second TTL

    # Add an old event
    old_event = WriteEvent(
        subject_id="order:FM-1001",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
        timestamp=time.time() - 2.0,  # 2 seconds ago
    )

    # Add a recent event
    recent_event = WriteEvent(
        subject_id="order:FM-1002",
        predicate="order_status",
        old_value=None,
        new_value="CREATED",
        operation="INSERT",
    )

    store.add_events([old_event, recent_event])

    # Get events (should trigger cleanup)
    results = store.get_events()

    assert len(results) == 1
    assert results[0]["subject_id"] == "order:FM-1002"


def test_max_events_limit():
    """Test that the store enforces MAX_EVENTS limit."""
    store = WriteEventStore()

    # Add more than MAX_EVENTS
    events = [
        WriteEvent(
            subject_id=f"order:FM-{i:05d}",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
            timestamp=float(i),
        )
        for i in range(store.MAX_EVENTS + 100)
    ]

    store.add_events(events)

    assert len(store) <= store.MAX_EVENTS

    # Verify newest events are kept
    results = store.get_events(limit=1)
    assert results[0]["subject_id"] == f"order:FM-{store.MAX_EVENTS + 99:05d}"


def test_clear():
    """Test clearing all events from the store."""
    store = WriteEventStore()

    events = [
        WriteEvent(
            subject_id=f"order:FM-{i:04d}",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        )
        for i in range(10)
    ]

    store.add_events(events)
    assert len(store) == 10

    store.clear()
    assert len(store) == 0


def test_thread_safety_concurrent_adds():
    """Test thread-safe concurrent event additions."""
    store = WriteEventStore()

    def add_events_thread(thread_id: int, count: int):
        """Add events from a thread."""
        for i in range(count):
            event = WriteEvent(
                subject_id=f"order:thread-{thread_id}-{i:04d}",
                predicate="order_status",
                old_value=None,
                new_value="CREATED",
                operation="INSERT",
            )
            store.add_event(event)

    # Run 5 threads adding 20 events each
    num_threads = 5
    events_per_thread = 20

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(add_events_thread, thread_id, events_per_thread)
            for thread_id in range(num_threads)
        ]
        for future in futures:
            future.result()

    # Should have all events
    assert len(store) == num_threads * events_per_thread


def test_thread_safety_concurrent_reads():
    """Test thread-safe concurrent event reads."""
    store = WriteEventStore()

    # Add some initial events
    events = [
        WriteEvent(
            subject_id=f"order:FM-{i:04d}",
            predicate="order_status",
            old_value=None,
            new_value="CREATED",
            operation="INSERT",
        )
        for i in range(100)
    ]
    store.add_events(events)

    results = []

    def read_events_thread():
        """Read events from a thread."""
        return store.get_events(limit=50)

    # Run 10 threads reading events concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_events_thread) for _ in range(10)]
        results = [future.result() for future in futures]

    # All reads should succeed and return consistent results
    assert all(len(r) == 50 for r in results)


def test_thread_safety_concurrent_reads_and_writes():
    """Test thread-safe concurrent reads and writes."""
    store = WriteEventStore()

    def writer_thread(thread_id: int):
        """Write events from a thread."""
        for i in range(10):
            event = WriteEvent(
                subject_id=f"order:writer-{thread_id}-{i:04d}",
                predicate="order_status",
                old_value=None,
                new_value="CREATED",
                operation="INSERT",
            )
            store.add_event(event)

    def reader_thread():
        """Read events from a thread."""
        return len(store.get_events())

    # Run 5 writers and 5 readers concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        writer_futures = [executor.submit(writer_thread, i) for i in range(5)]
        reader_futures = [executor.submit(reader_thread) for _ in range(5)]

        # Wait for all to complete
        for future in writer_futures + reader_futures:
            future.result()

    # Should have 50 events (5 writers * 10 events each)
    assert len(store) == 50


def test_batch_id_grouping():
    """Test that batch_id correctly groups related writes."""
    store = WriteEventStore()
    batch_id = generate_batch_id()

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

    results = store.get_events()

    # All events should have the same batch_id
    assert all(r["batch_id"] == batch_id for r in results)
