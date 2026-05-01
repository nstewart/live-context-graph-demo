"""Stream rows from a Materialize SUBSCRIBE.

Uses the production-tested DECLARE CURSOR + FETCH pattern from
search-sync/src/mz_client_subscribe.py -- this is the same SUBSCRIBE
plumbing that drives OpenSearch sync, validated against this exact
Materialize deployment.

Key choices that match production:
- BEGIN + DECLARE CURSOR FOR SUBSCRIBE (...) WITH (PROGRESS)
- FETCH 100 in a loop, brief sleep when empty
- Take the snapshot, then discard pending on first post-snapshot
  timestamp boundary (no `SNAPSHOT = false`)
- Emit downstream rows in timestamp-batches (flush on timestamp advance)

SUBSCRIBE wire format with WITH (PROGRESS):
    (mz_timestamp, mz_progressed, mz_diff, *projected_columns)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

import psycopg

from .types import MzRow, now_mono

logger = logging.getLogger(__name__)

EmitFn = Callable[[MzRow], Awaitable[None]] | Callable[[MzRow], None]

FETCH_BATCH = 100
EMPTY_FETCH_SLEEP = 0.05  # mirrors production cadence (0.01 there; we're a UI)

_ALLOWED_CLUSTERS: frozenset[str] = frozenset({"serving", "default", "quickstart"})


@dataclass(frozen=True)
class ViewSpec:
    """Which view to subscribe to and how to project it."""

    view: str
    columns: tuple[str, ...]

    def projection_sql(self) -> str:
        cols = ", ".join(self.columns)
        return f"SELECT {cols} FROM {self.view}"


INVENTORY_PRICING_VIEW = ViewSpec(
    view="inventory_items_with_dynamic_pricing_mv",
    columns=(
        "inventory_id",
        "store_id",
        "store_zone",
        "product_id",
        "available_quantity",
        "live_price",
        "price_change",
        "demand_multiplier",
        # `effective_updated_at` powers reaction-time freshness measurement
        # (NOW() - effective_updated_at), matching api/src/routes/query_stats.py.
        "effective_updated_at",
    ),
)

ORDERS_VIEW = ViewSpec(
    view="orders_with_lines_mv",
    columns=(
        "order_id",
        "order_number",
        "order_status",
        "store_id",
        "customer_name",
        "order_total_amount",
    ),
)

DEFAULT_VIEWS: tuple[ViewSpec, ...] = (INVENTORY_PRICING_VIEW, ORDERS_VIEW)


async def subscribe_view(
    dsn: str,
    spec: ViewSpec,
    emit: EmitFn,
    *,
    cluster: str = "serving",
    reconnect_backoff: float = 2.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run forever (until stop_event), reconnecting on failure."""
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            await _run_one_subscription(dsn, spec, emit, cluster=cluster, stop_event=stop_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SUBSCRIBE %s failed: %s; reconnecting in %.1fs",
                spec.view,
                exc,
                reconnect_backoff,
            )
            await _maybe_await(
                emit(
                    MzRow(
                        view=spec.view,
                        mz_timestamp=0,
                        progressed=False,
                        diff=0,
                        columns={"_error": str(exc)},
                    )
                )
            )
            try:
                await asyncio.sleep(reconnect_backoff)
            except asyncio.CancelledError:
                raise


async def _run_one_subscription(
    dsn: str,
    spec: ViewSpec,
    emit: EmitFn,
    *,
    cluster: str,
    stop_event: asyncio.Event | None,
) -> None:
    """One connect-DECLARE-FETCH loop, modeled on search-sync's proven path."""
    logger.info("connecting to mz for %s", spec.view)
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        if cluster not in _ALLOWED_CLUSTERS:
            raise ValueError(f"unknown cluster: {cluster!r}")
        logger.info("connected; SET CLUSTER = %s for %s", cluster, spec.view)
        await conn.execute(f"SET CLUSTER = {cluster}")
        async with conn.cursor() as cur:
            await cur.execute("BEGIN")
            sql = (
                f"DECLARE c CURSOR FOR SUBSCRIBE ({spec.projection_sql()}) "
                f"WITH (PROGRESS)"
            )
            logger.info("declaring cursor: %s", sql)
            await cur.execute(sql)
            await _maybe_await(
                emit(
                    MzRow(
                        view=spec.view,
                        mz_timestamp=0,
                        progressed=False,
                        diff=0,
                        columns={"_status": "subscribed"},
                    )
                )
            )

            last_timestamp: object | None = None
            is_snapshot = True
            pending: list[MzRow] = []
            row_count = 0

            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                # Materialize doesn't accept parameterized FETCH counts; inline.
                await cur.execute(f"FETCH {FETCH_BATCH} c")
                rows = await cur.fetchall()
                if not rows:
                    try:
                        await asyncio.sleep(EMPTY_FETCH_SLEEP)
                    except asyncio.CancelledError:
                        raise
                    continue

                for raw in rows:
                    row_count += 1
                    if row_count <= 3:
                        logger.info("%s raw row #%d: %r", spec.view, row_count, raw)
                    parsed = _classify(spec, raw)
                    if parsed is None:
                        continue
                    kind, mz_ts, diff, cols = parsed

                    # Timestamp boundary: flush prior batch (or discard snapshot)
                    if last_timestamp is not None and mz_ts != last_timestamp:
                        if is_snapshot:
                            logger.info(
                                "snapshot complete for %s: discarding %d buffered rows",
                                spec.view,
                                len(pending),
                            )
                            is_snapshot = False
                            pending = []
                        else:
                            for ev in pending:
                                await _maybe_await(emit(ev))
                            pending = []
                    last_timestamp = mz_ts

                    if kind == "progress":
                        # Forward heartbeat so the panel can update its frontier.
                        await _maybe_await(
                            emit(
                                MzRow(
                                    view=spec.view,
                                    mz_timestamp=int(mz_ts),
                                    progressed=True,
                                    diff=0,
                                    columns={},
                                )
                            )
                        )
                        continue

                    # Data row -> buffer until next timestamp.
                    pending.append(
                        MzRow(
                            view=spec.view,
                            mz_timestamp=int(mz_ts),
                            progressed=False,
                            diff=diff,
                            columns=cols,
                        )
                    )


def _classify(spec: ViewSpec, raw: tuple):
    """Return (kind, mz_ts, diff, cols) or None if the row shape is wrong.

    Wire format: (mz_timestamp, mz_progressed, mz_diff, *projected_cols)
    """
    if len(raw) < 3:
        logger.warning("unexpected SUBSCRIBE row shape for %s: %r", spec.view, raw)
        return None
    mz_ts = raw[0]
    progressed = bool(raw[1]) if isinstance(raw[1], bool) else False
    if progressed:
        return "progress", mz_ts, 0, {}
    try:
        diff = int(raw[2] or 0)
    except (TypeError, ValueError):
        diff = 0
    cols = dict(zip(spec.columns, raw[3:]))
    return "data", mz_ts, diff, cols


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        await value
