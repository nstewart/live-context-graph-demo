"""In-memory event store for tracking write propagation to search indexes."""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PropagationEvent:
    """A single propagation event representing an index update."""

    mz_ts: str  # Materialize timestamp
    index_name: str  # OpenSearch index name
    doc_id: str  # Document ID (e.g., "order:FM-1001")
    operation: str  # INSERT, UPDATE, or DELETE
    field_changes: dict[str, dict[str, str]] = field(default_factory=dict)  # {field: {old, new}}
    timestamp: float = field(default_factory=time.time)  # Unix timestamp when event was recorded
    display_name: Optional[str] = None  # Human-readable name (e.g., product name, order number)
    priority: float = 0.0  # Higher = more interesting (used for sorting)
    store_id: Optional[str] = None  # Store ID for relationship-based prioritization
    product_id: Optional[str] = None  # Product ID for relationship-based prioritization

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

    When an order status changes, this tracks:
    - The order that changed
    - The store the order belongs to
    - The product IDs in the order's line items

    Events related to these entities get higher priority in the propagation list.
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
    """Thread-safe in-memory store for propagation events with TTL-based expiration."""

    MAX_EVENTS = 10000  # Maximum number of events to keep in memory
    FOCUS_TTL_SECONDS = 60.0  # Focus context expires after 60 seconds

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize the store.

        Args:
            ttl_seconds: Time-to-live for events in seconds (default: 5 minutes)
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
