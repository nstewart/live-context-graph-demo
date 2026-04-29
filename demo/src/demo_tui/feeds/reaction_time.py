"""Reaction-time + query-latency monitor for the dynamic pricing view.

Mirrors the formula used in the original demo's query_stats API
(api/src/routes/query_stats.py):

    reaction_time = NOW() - effective_updated_at  -- data freshness
    response_time = perf_counter() - start_of_query  -- query latency

Two separate input streams populate two rolling sample sets:

1. Freshness samples come from the ongoing SUBSCRIBE -- every non-progress
   row arriving from inventory_items_with_dynamic_pricing_mv carries an
   `effective_updated_at`. The freshness at observation time is the gap
   between wall-clock now and that timestamp.

2. Query-time samples come from a periodic point query against the same
   view, run on a dedicated psycopg connection at 1Hz.

Stats exposed: median, p99, max -- same shape as SourceMetrics.stats() in
the original demo.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import psycopg

from .types import MzRow

logger = logging.getLogger(__name__)


_DEFAULT_VIEW = "inventory_items_with_dynamic_pricing_mv"
_QUERY_INTERVAL_SEC = 1.0
_RECONNECT_BACKOFF = 2.0
# Rolling window for stats. 300 = 5 min @ 1Hz query cadence; gives stable p99
# without growing memory unbounded. (Production uses 500K for 3 min at high QPS.)
_MAX_SAMPLES = 300


class ReactionMonitor:
    """Owns rolling p50/p99/max stats for freshness + query latency."""

    def __init__(self, dsn: str, view: str = _DEFAULT_VIEW, *, cluster: str = "serving") -> None:
        self.dsn = dsn
        self.view = view
        self.cluster = cluster
        self._freshness_ms: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self._query_ms: deque[float] = deque(maxlen=_MAX_SAMPLES)
        # Lifetime totals -- never bounded, so the audience sees throughput
        # accumulate even after the rolling stats window saturates.
        self._freshness_total = 0
        self._query_total = 0
        self._last_query_ok_t: float | None = None
        self._consecutive_query_errors = 0

    # ----- inputs -----

    def ingest_row(self, row: MzRow) -> None:
        """Feed every SUBSCRIBE data row through here; freshness is derived."""
        if row.view != self.view:
            return
        if row.is_heartbeat or row.diff <= 0:
            return
        ts = row.columns.get("effective_updated_at")
        if ts is None:
            return
        try:
            ts_dt = _to_aware_utc(ts)
        except Exception:  # noqa: BLE001
            return
        freshness_ms = max(0.0, (datetime.now(timezone.utc) - ts_dt).total_seconds() * 1000.0)
        self._freshness_ms.append(freshness_ms)
        self._freshness_total += 1

    async def run_query_loop(self, stop_event: asyncio.Event | None = None) -> None:
        """Issue a tight point query against the view at 1Hz; record latency."""
        sql = (
            f"SELECT live_price, effective_updated_at FROM {self.view} LIMIT 1"
        )
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                async with await psycopg.AsyncConnection.connect(
                    self.dsn, autocommit=True
                ) as conn:
                    await conn.execute(f"SET CLUSTER = {self.cluster}")
                    while True:
                        if stop_event is not None and stop_event.is_set():
                            return
                        start = time.perf_counter()
                        try:
                            cur = await conn.execute(sql)
                            await cur.fetchall()
                        except Exception:
                            raise
                        elapsed_ms = (time.perf_counter() - start) * 1000.0
                        self._query_ms.append(elapsed_ms)
                        self._query_total += 1
                        self._last_query_ok_t = time.monotonic()
                        self._consecutive_query_errors = 0
                        try:
                            await asyncio.sleep(_QUERY_INTERVAL_SEC)
                        except asyncio.CancelledError:
                            raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._consecutive_query_errors += 1
                logger.warning(
                    "reaction-time query failed: %s; reconnecting in %.1fs",
                    exc,
                    _RECONNECT_BACKOFF,
                )
                try:
                    await asyncio.sleep(_RECONNECT_BACKOFF)
                except asyncio.CancelledError:
                    raise

    # ----- output -----

    def stats(self) -> dict[str, Any]:
        return {
            "freshness": _stats(self._freshness_ms),
            "query": _stats(self._query_ms),
            "freshness_window": len(self._freshness_ms),
            "query_window": len(self._query_ms),
            "freshness_total": self._freshness_total,
            "query_total": self._query_total,
            "window_max": _MAX_SAMPLES,
            "view": self.view,
            "query_errors_streak": self._consecutive_query_errors,
        }


def _stats(samples) -> dict[str, float | None]:
    if not samples:
        return {"p50": None, "p99": None, "max": None}
    s = sorted(samples)
    p99_idx = min(int(len(s) * 0.99), len(s) - 1)
    return {
        "p50": round(statistics.median(s), 1),
        "p99": round(s[p99_idx], 1),
        "max": round(s[-1], 1),
    }


def _to_aware_utc(value) -> datetime:
    """Best-effort coerce an effective_updated_at column into aware-UTC datetime."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError(f"unsupported effective_updated_at type: {type(value).__name__}")
