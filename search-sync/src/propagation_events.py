"""In-memory event store for tracking write propagation to search indexes.

Propagation Event System
========================

This module provides the core data structures and storage for tracking how changes
propagate from the PostgreSQL triples table through Materialize to OpenSearch indexes.

Architecture Overview
---------------------

The propagation tracking system enables real-time visibility into data flow:

    PostgreSQL (triples) -> Materialize (CDC) -> OpenSearch (search indexes)
                                    |
                                    v
                           PropagationEventStore
                                    |
                                    v
                           Web UI (real-time updates)

Key Components
--------------

1. **PropagationEvent**: Represents a single index update with:
   - Materialize timestamp (mz_ts) for ordering
   - Document ID and index name
   - Field-level change tracking (old/new values)
   - Priority for UI sorting based on focus context

2. **FocusContext**: Tracks which order/store/products are currently "in focus"
   for the UI, allowing related events to be prioritized higher in the display.

3. **PropagationEventStore**: Thread-safe in-memory store with:
   - TTL-based expiration (default: 5 minutes)
   - Maximum event limit (10,000 events)
   - Priority-based sorting for queries
   - Focus context management

Usage Example
-------------

    from propagation_events import get_propagation_store, PropagationEvent

    # Get the global singleton store
    store = get_propagation_store()

    # Record an event when a document is updated in OpenSearch
    event = PropagationEvent(
        mz_ts="12345-67890",
        index_name="orders",
        doc_id="order:FM-1001",
        operation="UPDATE",
        field_changes={"status": {"old": "CREATED", "new": "PICKING"}},
        display_name="Order FM-1001",
    )
    store.add_event(event)

    # Set focus context when user interacts with an order
    store.set_focus_context(
        order_id="order:FM-1001",
        store_id="store:BK-01",
        product_ids=["product:prod001", "product:prod002"],
    )

    # Query events (returns priority-sorted list)
    events = store.get_events(limit=50)
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PropagationEvent:
    """A single propagation event representing an index update.

    When a document is created, updated, or deleted in OpenSearch as a result
    of changes flowing through Materialize, a PropagationEvent is recorded to
    track this change for real-time UI display.

    Attributes:
        mz_ts: Materialize timestamp string for ordering events chronologically.
            Format is typically "epoch-sequence" (e.g., "1704067200000-12345").
        index_name: The OpenSearch index that was updated (e.g., "orders", "products").
        doc_id: The document ID in the format "type:id" (e.g., "order:FM-1001").
        operation: The type of change - "INSERT", "UPDATE", or "DELETE".
        field_changes: Dictionary mapping field names to {"old": value, "new": value}.
            Only populated for UPDATE operations.
        timestamp: Unix timestamp (seconds since epoch) when the event was recorded.
            Defaults to current time.
        display_name: Human-readable name for the entity (e.g., "Fresh Groceries Order").
            Used in the UI for better readability.
        priority: Numeric priority score for sorting in the UI. Higher values appear first.
            Set based on FocusContext relationship (see FocusContext.compute_priority).
        store_id: The store this event relates to, if applicable. Used for priority
            computation based on focus context.
        product_id: The product this event relates to, if applicable. Used for priority
            computation based on focus context.
    """

    mz_ts: str
    index_name: str
    doc_id: str
    operation: str
    field_changes: dict[str, dict[str, str]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    display_name: Optional[str] = None
    priority: float = 0.0
    store_id: Optional[str] = None
    product_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "mz_ts": self.mz_ts,
            "index_name": self.index_name,
            "doc_id": self.doc_id,
            "operation": self.operation,
            "field_changes": self.field_changes,
            "timestamp": self.timestamp,
            "display_name": self.display_name,
            "priority": self.priority,
            "store_id": self.store_id,
            "product_id": self.product_id,
        }


@dataclass
class FocusContext:
    """Context about what triggered updates - used for prioritizing related events.

    When a user interacts with an order in the UI (e.g., updating its status),
    the FocusContext tracks:
    - The order that was changed
    - The store the order belongs to
    - The product IDs in the order's line items

    Events related to these entities get higher priority in the propagation list,
    making it easier for users to see the immediate effects of their changes.

    Priority Tiers
    --------------
    Events are assigned priority scores based on their relationship to the focus:

    - **TIER_DIRECT (1000)**: Same store AND product in order - direct impact
      Example: Updating stock level for a product that's in the focused order
      at the same store.

    - **TIER_SAME_PRODUCT (500)**: Product in order at a different store
      Example: Stock update for the same product at a different location.

    - **TIER_SAME_STORE (100)**: Same store but different product
      Example: Another product's inventory at the same store was updated.

    - **TIER_CASCADE (1)**: Different store and different product
      Example: Unrelated inventory changes that happened at the same time.

    Attributes:
        order_id: The order ID that triggered the focus (e.g., "order:FM-1001").
        store_id: The store ID the order belongs to (e.g., "store:BK-01").
        product_ids: List of product IDs in the order's line items.
        timestamp: When the focus was set (for TTL expiration).
    """
    order_id: Optional[str] = None
    store_id: Optional[str] = None
    product_ids: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    # Priority tiers (higher = more interesting)
    TIER_DIRECT = 1000.0    # Same store + product in order (direct impact)
    TIER_SAME_PRODUCT = 500.0  # Product in order at different store
    TIER_SAME_STORE = 100.0    # Same store, different product
    TIER_CASCADE = 1.0         # Everything else (cascade effects)

    def compute_priority(self, store_id: Optional[str], product_id: Optional[str]) -> float:
        """Compute priority score for an event based on relationship to focus.

        Args:
            store_id: The store ID of the event's entity
            product_id: The product ID of the event's entity

        Returns:
            Priority score (higher = more interesting)
        """
        if not self.store_id and not self.product_ids:
            return 0.0

        is_same_store = store_id and store_id == self.store_id
        is_focus_product = product_id and product_id in self.product_ids

        if is_same_store and is_focus_product:
            # Tier 1: Direct impact - same store AND product in order
            return self.TIER_DIRECT
        elif is_focus_product:
            # Tier 2: Same product at different store
            return self.TIER_SAME_PRODUCT
        elif is_same_store:
            # Tier 3: Same store, different product
            return self.TIER_SAME_STORE
        else:
            # Tier 4: Cascade effect (different store, different product)
            return self.TIER_CASCADE


class PropagationEventStore:
    """Thread-safe in-memory store for propagation events with TTL-based expiration.

    The PropagationEventStore is the central component for tracking and querying
    propagation events. It provides:

    - **Thread-safe access**: All operations are protected by a lock for safe
      concurrent access from multiple sync workers.

    - **Automatic TTL expiration**: Events older than `ttl_seconds` are automatically
      removed during query operations to prevent unbounded memory growth.

    - **Event count limiting**: A maximum of MAX_EVENTS (10,000) are kept in memory.
      When exceeded, oldest events are evicted.

    - **Priority-based sorting**: Events are returned sorted by priority (highest first),
      then by timestamp (most recent first within same priority).

    - **Focus context management**: Tracks which order/store/products are currently
      in focus for the UI, enabling priority-based event sorting.

    Configuration Constants
    -----------------------
    - MAX_EVENTS: Maximum events to keep in memory (10,000)
    - FOCUS_TTL_SECONDS: Focus context expires after 60 seconds of inactivity

    Example
    -------
        store = PropagationEventStore(ttl_seconds=300)  # 5 minute TTL

        # Add events
        store.add_event(event)
        store.add_events([event1, event2, event3])

        # Query events with filtering
        events = store.get_events(
            since_mz_ts="12345-67890",  # Only newer events
            subject_ids=["order:FM-1001"],  # Filter by document ID
            limit=50,
        )

        # Manage focus context
        store.set_focus_context(order_id="order:FM-1001", store_id="store:BK-01")
        store.clear_focus_context()
    """

    MAX_EVENTS = 10000  # Maximum number of events to keep in memory
    FOCUS_TTL_SECONDS = 60.0  # Focus context expires after 60 seconds

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize the store.

        Args:
            ttl_seconds: Time-to-live for events in seconds (default: 5 minutes).
                Events older than this are automatically removed during queries.
        """
        self._events: list[PropagationEvent] = []
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        self._focus_context: Optional[FocusContext] = None

    def add_event(self, event: PropagationEvent) -> None:
        """Add an event to the store."""
        with self._lock:
            self._events.append(event)
            self._cleanup_expired()

    def add_events(self, events: list[PropagationEvent]) -> None:
        """Add multiple events to the store."""
        with self._lock:
            self._events.extend(events)
            self._cleanup_expired()

    def set_focus_context(
        self,
        order_id: Optional[str] = None,
        store_id: Optional[str] = None,
        product_ids: Optional[list[str]] = None,
    ) -> None:
        """Set the focus context for prioritizing related events.

        Args:
            order_id: The order that triggered the change
            store_id: The store the order belongs to
            product_ids: Product IDs in the order's line items
        """
        with self._lock:
            self._focus_context = FocusContext(
                order_id=order_id,
                store_id=store_id,
                product_ids=product_ids or [],
                timestamp=time.time(),
            )

    def get_focus_context(self) -> Optional[FocusContext]:
        """Get the current focus context (if not expired).

        Returns:
            FocusContext if set and not expired, None otherwise
        """
        with self._lock:
            if self._focus_context is None:
                return None
            # Check if expired
            if time.time() - self._focus_context.timestamp > self.FOCUS_TTL_SECONDS:
                self._focus_context = None
                return None
            return self._focus_context

    def clear_focus_context(self) -> None:
        """Clear the focus context."""
        with self._lock:
            self._focus_context = None

    def get_events(
        self,
        since_mz_ts: Optional[str] = None,
        subject_ids: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query events from the store, sorted by priority (highest first).

        Args:
            since_mz_ts: Only return events with mz_ts greater than this value
            subject_ids: Filter to events where doc_id starts with any of these prefixes
            limit: Maximum number of events to return

        Returns:
            List of events as dicts, sorted by priority (highest first), then by recency
        """
        with self._lock:
            self._cleanup_expired()

            candidates = []
            for event in self._events:
                # Filter by mz_ts if specified
                if since_mz_ts is not None and event.mz_ts <= since_mz_ts:
                    continue

                # Filter by subject_ids if specified
                if subject_ids is not None:
                    # Check if doc_id matches any subject_id prefix
                    # e.g., doc_id="order:FM-1001" matches subject_id="order:FM-1001"
                    # Also handle case where doc_id might be in a different format
                    matches = False
                    for subject_id in subject_ids:
                        if event.doc_id == subject_id or event.doc_id.startswith(subject_id):
                            matches = True
                            break
                    if not matches:
                        continue

                candidates.append(event)

            # Sort by priority (descending), then by timestamp (descending for recency)
            candidates.sort(key=lambda e: (e.priority, e.timestamp), reverse=True)

            # Return top N as dicts
            return [e.to_dict() for e in candidates[:limit]]

    def get_all_events(self, limit: int = 100) -> list[dict]:
        """Get all recent events without filtering.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of events as dicts, most recent first
        """
        return self.get_events(limit=limit)

    def clear(self) -> None:
        """Clear all events from the store."""
        with self._lock:
            self._events.clear()

    def _cleanup_expired(self) -> None:
        """Remove events older than TTL. Must be called with lock held."""
        cutoff = time.time() - self._ttl_seconds
        self._events = [e for e in self._events if e.timestamp > cutoff]
        # Evict oldest if over limit
        if len(self._events) > self.MAX_EVENTS:
            self._events = self._events[-self.MAX_EVENTS:]

    def __len__(self) -> int:
        """Return the number of events in the store."""
        with self._lock:
            return len(self._events)


# Global singleton instance for use across workers
_store: Optional[PropagationEventStore] = None


def get_propagation_store() -> PropagationEventStore:
    """Get the global propagation event store singleton."""
    global _store
    if _store is None:
        _store = PropagationEventStore()
    return _store
