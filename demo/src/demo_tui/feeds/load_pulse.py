"""Roll up order activity into a 60-second sparkline.

Counts +1 diffs from the orders SUBSCRIBE feed; emits a snapshot every second.
"""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from typing import Awaitable, Callable

from .types import LoadTick, MzRow, now_mono

EmitFn = Callable[[LoadTick], Awaitable[None]] | Callable[[LoadTick], None]

WINDOW_SEC = 60
BUCKET_SEC = 2  # 30 buckets across the window


class LoadPulse:
    """Tracks recent inserts on the orders view and exposes a sparkline."""

    def __init__(self) -> None:
        self._events: deque[tuple[float, str | None]] = deque()  # (t_mono, store_zone)

    def ingest(self, row: MzRow) -> None:
        if row.is_heartbeat or row.diff != 1:
            return
        if row.view != "orders_with_lines_mv":
            return
        zone = _zone_for_store(row.columns.get("store_id"))
        self._events.append((row.t_mono, zone))
        self._evict()

    def snapshot(self) -> LoadTick:
        self._evict()
        now = now_mono()
        bucket_count = WINDOW_SEC // BUCKET_SEC
        buckets = [0] * bucket_count
        zone_counts: Counter[str] = Counter()
        for t_mono, zone in self._events:
            age = now - t_mono
            idx = bucket_count - 1 - int(age // BUCKET_SEC)
            if 0 <= idx < bucket_count:
                buckets[idx] += 1
            if zone:
                zone_counts[zone] += 1
        return LoadTick(
            orders_last_60s=len(self._events),
            sparkline_buckets=buckets,
            by_zone=dict(zone_counts),
        )

    def _evict(self) -> None:
        cutoff = now_mono() - WINDOW_SEC
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()


_STORE_ZONE_PREFIX = {
    "MAN": "MAN",
    "BRK": "BK",
    "QNS": "QNS",
    "BX": "BX",
    "SI": "SI",
    "BK": "BK",
}


def _zone_for_store(store_id) -> str | None:
    if not store_id or not isinstance(store_id, str):
        return None
    head = store_id.split("-", 1)[0].upper()
    return _STORE_ZONE_PREFIX.get(head)


async def emit_ticks(pulse: LoadPulse, emit: EmitFn, *, interval_sec: float = 1.0,
                    stop_event: asyncio.Event | None = None) -> None:
    """Periodically emit a LoadTick snapshot."""
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        tick = pulse.snapshot()
        result = emit(tick)
        if asyncio.iscoroutine(result):
            await result
        try:
            await asyncio.sleep(interval_sec)
        except asyncio.CancelledError:
            raise
