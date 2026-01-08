"""Tests for the PropagationEventStore."""

import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.propagation_events import FocusContext, PropagationEvent, PropagationEventStore


def test_propagation_event_to_dict():
    """Test PropagationEvent serialization to dict."""
    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="UPDATE",
        field_changes={
            "status": {"old": "CREATED", "new": "CONFIRMED"},
            "price": {"old": "100.00", "new": "120.00"},
        },
        timestamp=1234567890.0,
        display_name="Order FM-1001",
        priority=100.0,
        store_id="store:BK-01",
        product_id="product:prod001",
    )

    result = event.to_dict()

    assert result == {
        "mz_ts": "12345-67890",
        "index_name": "orders",
        "doc_id": "order:FM-1001",
        "operation": "UPDATE",
        "field_changes": {
            "status": {"old": "CREATED", "new": "CONFIRMED"},
            "price": {"old": "100.00", "new": "120.00"},
        },
        "timestamp": 1234567890.0,
        "display_name": "Order FM-1001",
        "priority": 100.0,
        "store_id": "store:BK-01",
        "product_id": "product:prod001",
    }


def test_propagation_event_defaults():
    """Test PropagationEvent default values."""
    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
    )

    assert event.field_changes == {}
    assert event.display_name is None
    assert event.timestamp > 0  # Should have a default timestamp


def test_store_initialization():
    """Test PropagationEventStore initialization."""
    store = PropagationEventStore(ttl_seconds=600)

    assert len(store) == 0
    assert store._ttl_seconds == 600


def test_add_single_event():
    """Test adding a single event to the store."""
    store = PropagationEventStore()
    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
    )

    store.add_event(event)

    assert len(store) == 1


def test_add_multiple_events():
    """Test adding multiple events at once."""
    store = PropagationEventStore()
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

    assert len(store) == 2


def test_get_events_returns_most_recent_first():
    """Test that get_events returns events in reverse chronological order."""
    store = PropagationEventStore()

    # Add events with different timestamps (using recent times to avoid TTL expiration)
    now = time.time()
    event1 = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
        timestamp=now - 2,
    )
    event2 = PropagationEvent(
        mz_ts="12345-67891",
        index_name="orders",
        doc_id="order:FM-1002",
        operation="INSERT",
        timestamp=now - 1,
    )
    event3 = PropagationEvent(
        mz_ts="12345-67892",
        index_name="orders",
        doc_id="order:FM-1003",
        operation="INSERT",
        timestamp=now,
    )

    store.add_events([event1, event2, event3])

    results = store.get_events()

    assert len(results) == 3
    # Results are sorted by priority (all 0) then by timestamp (most recent first)
    assert results[0]["doc_id"] == "order:FM-1003"
    assert results[1]["doc_id"] == "order:FM-1002"
    assert results[2]["doc_id"] == "order:FM-1001"


def test_get_events_with_since_mz_ts_filter():
    """Test filtering events by mz_ts."""
    store = PropagationEventStore()

    event1 = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
    )
    event2 = PropagationEvent(
        mz_ts="12345-67892",
        index_name="orders",
        doc_id="order:FM-1002",
        operation="INSERT",
    )
    event3 = PropagationEvent(
        mz_ts="12345-67894",
        index_name="orders",
        doc_id="order:FM-1003",
        operation="INSERT",
    )

    store.add_events([event1, event2, event3])

    # Get events after mz_ts 12345-67891
    results = store.get_events(since_mz_ts="12345-67891")

    assert len(results) == 2
    assert results[0]["mz_ts"] == "12345-67894"
    assert results[1]["mz_ts"] == "12345-67892"


def test_get_events_with_subject_ids_filter():
    """Test filtering events by subject IDs (doc_id)."""
    store = PropagationEventStore()

    event1 = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
    )
    event2 = PropagationEvent(
        mz_ts="12345-67891",
        index_name="orders",
        doc_id="order:FM-1002",
        operation="INSERT",
    )
    event3 = PropagationEvent(
        mz_ts="12345-67892",
        index_name="products",
        doc_id="product:ABC-123",
        operation="INSERT",
    )

    store.add_events([event1, event2, event3])

    # Filter by specific subject IDs
    results = store.get_events(subject_ids=["order:FM-1001", "order:FM-1002"])

    assert len(results) == 2
    assert all(r["doc_id"].startswith("order:") for r in results)


def test_get_events_with_subject_id_prefix_matching():
    """Test that subject_id filtering supports prefix matching."""
    store = PropagationEventStore()

    event1 = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
    )
    event2 = PropagationEvent(
        mz_ts="12345-67891",
        index_name="orders",
        doc_id="order:FM-1001-line:1",
        operation="INSERT",
    )

    store.add_events([event1, event2])

    # Filter by prefix (should match both)
    results = store.get_events(subject_ids=["order:FM-1001"])

    assert len(results) == 2


def test_get_events_with_limit():
    """Test limiting the number of returned events."""
    store = PropagationEventStore()

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

    results = store.get_events(limit=5)

    assert len(results) == 5


def test_get_all_events():
    """Test get_all_events method."""
    store = PropagationEventStore()

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

    results = store.get_all_events()

    assert len(results) == 5


def test_ttl_expiration():
    """Test that old events are expired based on TTL."""
    store = PropagationEventStore(ttl_seconds=1.0)  # 1 second TTL

    # Add an old event
    old_event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
        timestamp=time.time() - 2.0,  # 2 seconds ago
    )

    # Add a recent event
    recent_event = PropagationEvent(
        mz_ts="12345-67891",
        index_name="orders",
        doc_id="order:FM-1002",
        operation="INSERT",
    )

    store.add_events([old_event, recent_event])

    # Get events (should trigger cleanup)
    results = store.get_events()

    assert len(results) == 1
    assert results[0]["doc_id"] == "order:FM-1002"


def test_max_events_limit():
    """Test that the store enforces MAX_EVENTS limit."""
    store = PropagationEventStore()

    # Add more than MAX_EVENTS (use recent timestamps to avoid TTL expiration)
    now = time.time()
    events = [
        PropagationEvent(
            mz_ts=f"12345-{i:05d}",
            index_name="orders",
            doc_id=f"order:FM-{i:05d}",
            operation="INSERT",
            timestamp=now + i * 0.001,  # Slight increment to maintain order
        )
        for i in range(store.MAX_EVENTS + 100)
    ]

    store.add_events(events)

    assert len(store) <= store.MAX_EVENTS

    # Verify newest events are kept
    results = store.get_events(limit=1)
    assert results[0]["doc_id"] == f"order:FM-{store.MAX_EVENTS + 99:05d}"


def test_clear():
    """Test clearing all events from the store."""
    store = PropagationEventStore()

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
    assert len(store) == 10

    store.clear()
    assert len(store) == 0


def test_thread_safety_concurrent_adds():
    """Test thread-safe concurrent event additions."""
    store = PropagationEventStore()

    def add_events_thread(thread_id: int, count: int):
        """Add events from a thread."""
        for i in range(count):
            event = PropagationEvent(
                mz_ts=f"{thread_id:05d}-{i:05d}",
                index_name="orders",
                doc_id=f"order:thread-{thread_id}-{i:04d}",
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
    store = PropagationEventStore()

    # Add some initial events
    events = [
        PropagationEvent(
            mz_ts=f"12345-{i:05d}",
            index_name="orders",
            doc_id=f"order:FM-{i:04d}",
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
    store = PropagationEventStore()

    def writer_thread(thread_id: int):
        """Write events from a thread."""
        for i in range(10):
            event = PropagationEvent(
                mz_ts=f"{thread_id:05d}-{i:05d}",
                index_name="orders",
                doc_id=f"order:writer-{thread_id}-{i:04d}",
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


def test_field_changes_tracking():
    """Test that field changes are properly tracked."""
    store = PropagationEventStore()

    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="UPDATE",
        field_changes={
            "status": {"old": "CREATED", "new": "CONFIRMED"},
            "updated_at": {"old": "2024-01-01", "new": "2024-01-02"},
        },
    )

    store.add_event(event)

    results = store.get_events()

    assert len(results) == 1
    assert results[0]["field_changes"] == {
        "status": {"old": "CREATED", "new": "CONFIRMED"},
        "updated_at": {"old": "2024-01-01", "new": "2024-01-02"},
    }


def test_display_name_tracking():
    """Test that display_name is properly tracked."""
    store = PropagationEventStore()

    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="INSERT",
        display_name="Fresh Groceries Order",
    )

    store.add_event(event)

    results = store.get_events()

    assert len(results) == 1
    assert results[0]["display_name"] == "Fresh Groceries Order"


def test_multiple_index_types():
    """Test events from different index types."""
    store = PropagationEventStore()

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

    results = store.get_events()

    assert len(results) == 3
    index_names = {r["index_name"] for r in results}
    assert index_names == {"orders", "products", "customers"}


# =============================================================================
# FocusContext Tests
# =============================================================================


def test_focus_context_defaults():
    """Test FocusContext default values."""
    ctx = FocusContext()

    assert ctx.order_id is None
    assert ctx.store_id is None
    assert ctx.product_ids == []
    assert ctx.timestamp > 0


def test_focus_context_compute_priority_direct_match():
    """Test priority computation for direct match (same store + product in order)."""
    ctx = FocusContext(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    # Direct match: same store AND product in order
    priority = ctx.compute_priority(store_id="store:BK-01", product_id="product:prod001")
    assert priority == FocusContext.TIER_DIRECT


def test_focus_context_compute_priority_same_product_different_store():
    """Test priority computation for same product at different store."""
    ctx = FocusContext(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    # Same product, different store
    priority = ctx.compute_priority(store_id="store:MAN-01", product_id="product:prod001")
    assert priority == FocusContext.TIER_SAME_PRODUCT


def test_focus_context_compute_priority_same_store_different_product():
    """Test priority computation for same store but different product."""
    ctx = FocusContext(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    # Same store, different product
    priority = ctx.compute_priority(store_id="store:BK-01", product_id="product:prod999")
    assert priority == FocusContext.TIER_SAME_STORE


def test_focus_context_compute_priority_cascade():
    """Test priority computation for cascade (different store and product)."""
    ctx = FocusContext(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    # Different store AND different product
    priority = ctx.compute_priority(store_id="store:MAN-01", product_id="product:prod999")
    assert priority == FocusContext.TIER_CASCADE


def test_focus_context_compute_priority_no_context():
    """Test priority computation when focus context has no store/products."""
    ctx = FocusContext()

    # No store_id or product_ids set
    priority = ctx.compute_priority(store_id="store:BK-01", product_id="product:prod001")
    assert priority == 0.0


def test_focus_context_compute_priority_none_values():
    """Test priority computation with None store_id or product_id."""
    ctx = FocusContext(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001"],
    )

    # None store_id
    priority = ctx.compute_priority(store_id=None, product_id="product:prod001")
    assert priority == FocusContext.TIER_SAME_PRODUCT

    # None product_id
    priority = ctx.compute_priority(store_id="store:BK-01", product_id=None)
    assert priority == FocusContext.TIER_SAME_STORE

    # Both None
    priority = ctx.compute_priority(store_id=None, product_id=None)
    assert priority == FocusContext.TIER_CASCADE


# =============================================================================
# PropagationEventStore Focus Context Tests
# =============================================================================


def test_set_focus_context():
    """Test setting focus context in the store."""
    store = PropagationEventStore()

    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    ctx = store.get_focus_context()
    assert ctx is not None
    assert ctx.order_id == "order:FM-1001"
    assert ctx.store_id == "store:BK-01"
    assert ctx.product_ids == ["product:prod001", "product:prod002"]


def test_get_focus_context_returns_none_when_not_set():
    """Test that get_focus_context returns None when not set."""
    store = PropagationEventStore()

    ctx = store.get_focus_context()
    assert ctx is None


def test_clear_focus_context():
    """Test clearing focus context."""
    store = PropagationEventStore()

    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001"],
    )
    assert store.get_focus_context() is not None

    store.clear_focus_context()
    assert store.get_focus_context() is None


def test_focus_context_ttl_expiration():
    """Test that focus context expires after TTL."""
    store = PropagationEventStore()

    # Set focus context with timestamp in the past
    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001"],
    )

    # Manually set the timestamp to be expired
    store._focus_context.timestamp = time.time() - store.FOCUS_TTL_SECONDS - 1

    # Should return None because it's expired
    ctx = store.get_focus_context()
    assert ctx is None


def test_events_sorted_by_priority():
    """Test that events are sorted by priority (highest first)."""
    store = PropagationEventStore()

    # Set focus context
    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001"],
    )

    # Add events with different priorities
    now = time.time()
    events = [
        PropagationEvent(
            mz_ts="12345-67890",
            index_name="inventory",
            doc_id="inventory:001",
            operation="UPDATE",
            timestamp=now,
            store_id="store:MAN-01",  # Different store, different product = cascade
            product_id="product:prod999",
            priority=FocusContext.TIER_CASCADE,
        ),
        PropagationEvent(
            mz_ts="12345-67891",
            index_name="inventory",
            doc_id="inventory:002",
            operation="UPDATE",
            timestamp=now,
            store_id="store:BK-01",  # Same store, different product
            product_id="product:prod999",
            priority=FocusContext.TIER_SAME_STORE,
        ),
        PropagationEvent(
            mz_ts="12345-67892",
            index_name="inventory",
            doc_id="inventory:003",
            operation="UPDATE",
            timestamp=now,
            store_id="store:BK-01",  # Same store AND same product = direct
            product_id="product:prod001",
            priority=FocusContext.TIER_DIRECT,
        ),
    ]

    store.add_events(events)

    results = store.get_events()

    # Should be sorted by priority (highest first)
    assert results[0]["priority"] == FocusContext.TIER_DIRECT
    assert results[1]["priority"] == FocusContext.TIER_SAME_STORE
    assert results[2]["priority"] == FocusContext.TIER_CASCADE


def test_propagation_event_with_store_and_product_ids():
    """Test PropagationEvent with store_id and product_id fields."""
    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="inventory",
        doc_id="inventory:001",
        operation="UPDATE",
        store_id="store:BK-01",
        product_id="product:prod001",
        priority=100.0,
    )

    result = event.to_dict()

    assert result["store_id"] == "store:BK-01"
    assert result["product_id"] == "product:prod001"
    assert result["priority"] == 100.0
