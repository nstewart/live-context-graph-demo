"""Two pollers that mirror the React PropagationContext exactly.

References:
- web/src/contexts/PropagationContext.tsx -- the polling logic we're cloning
- api/src/routes/audit.py -- /api/audit/writes (PG writes)
- search-sync/src/propagation_api.py -- /propagation/events/all (index updates)

Cadence + dedup match the React widget:
- 1s interval (production uses 2s; user requested 1s for the demo)
- limit=100 per poll
- audit dedup key: timestamp + subject_id + predicate
- propagation dedup key: mz_ts + index_name + doc_id + operation
- since_ts cursor on audit (incremental); propagation refetches & dedupes

Each poller is its own coroutine, started as a Textual worker. Errors are
logged + retried with backoff; failures don't bring down the worker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import httpx

from .types import FieldChange, PropagationEvent, SourceWriteEvent

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 1.0
ERROR_BACKOFF_SEC = 3.0
MAX_DEDUP_KEYS = 5000  # bound memory; oldest keys evicted

SourceWriteEmit = Callable[[SourceWriteEvent], Awaitable[None]] | Callable[[SourceWriteEvent], None]
PropagationEmit = Callable[[PropagationEvent], Awaitable[None]] | Callable[[PropagationEvent], None]


async def poll_audit_writes(
    api_url: str,
    emit: SourceWriteEmit,
    *,
    interval_sec: float = POLL_INTERVAL_SEC,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Poll /api/audit/writes; emit each new SourceWriteEvent exactly once."""
    url = f"{api_url.rstrip('/')}/api/audit/writes"
    seen: set[str] = set()
    last_ts: float | None = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
        logger.info("audit/writes poller starting -> %s", url)
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                params: dict = {"limit": 100}
                if last_ts is not None:
                    params["since_ts"] = last_ts
                resp = await client.get(url, params=params)
                if resp.status_code >= 400:
                    logger.warning("audit/writes HTTP %d: %s", resp.status_code, resp.text[:200])
                    await _backoff(stop_event)
                    continue
                events = (resp.json() or {}).get("events", [])
                for raw in events:
                    ev = SourceWriteEvent(
                        subject_id=raw["subject_id"],
                        predicate=raw["predicate"],
                        old_value=raw.get("old_value"),
                        new_value=raw.get("new_value"),
                        operation=raw["operation"],
                        timestamp=float(raw["timestamp"]),
                        batch_id=raw.get("batch_id"),
                    )
                    if ev.dedup_key in seen:
                        continue
                    seen.add(ev.dedup_key)
                    if last_ts is None or ev.timestamp > last_ts:
                        last_ts = ev.timestamp
                    await _maybe_await(emit(ev))
                _evict_seen(seen)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit/writes poll error: %s", exc)
                await _backoff(stop_event)
                continue

            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise


async def poll_propagation_events(
    search_sync_url: str,
    emit: PropagationEmit,
    *,
    interval_sec: float = POLL_INTERVAL_SEC,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Poll /propagation/events/all; emit each new PropagationEvent exactly once."""
    url = f"{search_sync_url.rstrip('/')}/propagation/events/all"
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
        logger.info("propagation/events poller starting -> %s", url)
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                resp = await client.get(url, params={"limit": 100})
                if resp.status_code >= 400:
                    logger.warning(
                        "propagation/events HTTP %d: %s", resp.status_code, resp.text[:200]
                    )
                    await _backoff(stop_event)
                    continue
                events = (resp.json() or {}).get("events", [])
                for raw in events:
                    fc = {
                        k: FieldChange(old=v.get("old"), new=v.get("new"))
                        for k, v in (raw.get("field_changes") or {}).items()
                    }
                    ev = PropagationEvent(
                        mz_ts=str(raw["mz_ts"]),
                        index_name=raw["index_name"],
                        doc_id=raw["doc_id"],
                        operation=raw["operation"],
                        field_changes=fc,
                        timestamp=float(raw["timestamp"]),
                        display_name=raw.get("display_name"),
                        store_id=raw.get("store_id"),
                        product_id=raw.get("product_id"),
                    )
                    if ev.dedup_key in seen:
                        continue
                    seen.add(ev.dedup_key)
                    await _maybe_await(emit(ev))
                _evict_seen(seen)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("propagation/events poll error: %s", exc)
                await _backoff(stop_event)
                continue

            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise


async def _backoff(stop_event: asyncio.Event | None) -> None:
    try:
        if stop_event is not None:
            await asyncio.wait_for(stop_event.wait(), timeout=ERROR_BACKOFF_SEC)
        else:
            await asyncio.sleep(ERROR_BACKOFF_SEC)
    except asyncio.TimeoutError:
        pass
    except asyncio.CancelledError:
        raise


def _evict_seen(seen: set[str]) -> None:
    """Cap dedup memory. Drops a chunk of arbitrary keys when over cap.

    With dedup, we tolerate occasional re-renders if a key returns post-eviction.
    The 5k cap is well above what 1Hz polling produces in any realistic session.
    """
    if len(seen) > MAX_DEDUP_KEYS:
        # Drop ~20% of keys; deterministic order doesn't matter here.
        for _ in range(MAX_DEDUP_KEYS // 5):
            seen.pop()


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        await value
