"""Freshness Under Load: PG view vs batch cache vs Materialize.

Mirrors web/src/pages/QueryStatisticsPage.tsx:
- POST /api/query-stats/start/{order_id} on launch
- GET  /api/query-stats/metrics every 1s
- POST /api/query-stats/stop on quit
- LoadPanel on the left for orders/min driving the load axis
- ComparisonPanel on the right with the three-source table
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer

from .config import Config
from .feeds.load_pulse import LoadPulse, emit_ticks
from .feeds.mz_subscribe import ORDERS_VIEW, subscribe_view
from .feeds.query_stats_client import (
    OrderChoice,
    list_orders,
    poll_metrics,
    start_polling,
    stop_polling,
)
from .feeds.types import LoadTick, MzRow
from .panels.comparison_panel import ComparisonPanel
from .panels.load_panel import LoadPanel


def _configure_logging() -> str:
    path = os.environ.get("DEMO_TUI_LOG", "/tmp/demo-tui.log")
    handler = logging.FileHandler(path, mode="a")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger("demo_tui")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    root.info("---- demo_tui (freshness) log opened ----")
    return path


logger = logging.getLogger(__name__)


class FreshnessApp(App):
    CSS_PATH = "freshness.tcss"
    TITLE = "FreshMart -- Freshness Under Load"
    SUB_TITLE = "PostgreSQL view  vs  batch cache  vs  Materialize"

    BINDINGS = [
        Binding("f1", "focus_load", "load", show=True, priority=True),
        Binding("f2", "focus_compare", "comparison", show=True, priority=True),
        Binding("ctrl+shift+c", "yank", "copy panels", show=True),
        Binding("ctrl+c", "quit", "quit", show=True, priority=True),
    ]

    def __init__(
        self, config: Config | None = None, order_id: str | None = None
    ) -> None:
        super().__init__()
        self.config = config or Config.from_env()
        self.requested_order_id = order_id  # None -> auto-pick
        self.pulse = LoadPulse()
        self.log_path = _configure_logging()
        self._chosen_order: OrderChoice | None = None
        self._latest_metrics: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="row"):
            yield LoadPanel(id="load_panel")
            yield ComparisonPanel(id="compare_panel")
        yield Footer()

    def on_mount(self) -> None:
        # Workers:
        #   * orders SUBSCRIBE -> LoadPulse for the orders/min sparkline
        #   * pulse aggregator -> 1Hz LoadTick
        #   * orchestrator -> picks order, starts server polling, polls /metrics,
        #     stops on shutdown.
        self.run_worker(
            self._orders_subscribe_worker,
            name="mz:orders",
            exclusive=False,
            exit_on_error=False,
        )
        self.run_worker(
            self._pulse_worker, name="pulse", exclusive=False, exit_on_error=False
        )
        self.run_worker(
            self._orchestrator, name="orchestrator", exclusive=False, exit_on_error=False
        )

    # ----- workers -----

    async def _orders_subscribe_worker(self) -> None:
        await subscribe_view(self.config.mz_dsn, ORDERS_VIEW, self._on_mz_row)

    async def _pulse_worker(self) -> None:
        await emit_ticks(self.pulse, self._on_load_tick, interval_sec=1.0)

    async def _orchestrator(self) -> None:
        """Pick an order, start server polling, poll /metrics until shutdown."""
        try:
            await self._select_and_start_order()
        except Exception as exc:  # noqa: BLE001
            logger.error("orchestrator failed to start polling: %s", exc, exc_info=True)
            self.notify(f"failed to start query-stats: {exc}", severity="error")
            return

        try:
            await poll_metrics(
                self.config.api_base_url,
                self._on_metrics,
                interval_sec=1.0,
            )
        finally:
            # Best-effort cleanup; runs whether worker is cancelled or returns.
            await stop_polling(self.config.api_base_url)
            logger.info("orchestrator stopped server polling")

    async def _select_and_start_order(self) -> None:
        target = self.requested_order_id
        if target:
            logger.info("using user-supplied order: %s", target)
            self._chosen_order = OrderChoice(
                order_id=target,
                order_number=target.split(":", 1)[-1],
                order_status="UNKNOWN",
                store_id=None,
                store_name=None,
                customer_name=None,
            )
        else:
            orders = await list_orders(self.config.api_base_url)
            if not orders:
                raise RuntimeError("no orders returned from /api/query-stats/orders")
            self._chosen_order = orders[0]
            logger.info(
                "auto-selected order %s (status=%s, store=%s)",
                self._chosen_order.order_id,
                self._chosen_order.order_status,
                self._chosen_order.store_id,
            )

        order_id = self._chosen_order.order_id
        cp = self.query_one(ComparisonPanel)
        cp.set_session(order_id, is_polling=False)
        await start_polling(self.config.api_base_url, order_id)
        cp.set_session(order_id, is_polling=True)
        self.notify(f"polling started for {self._chosen_order.order_number}", timeout=3)

    # ----- emit callbacks -----

    def _on_mz_row(self, row: MzRow) -> None:
        self.pulse.ingest(row)

    def _on_load_tick(self, tick: LoadTick) -> None:
        try:
            self.query_one(LoadPanel).on_load_tick(tick)
        except Exception:
            pass

    def _on_metrics(self, payload: dict[str, Any]) -> None:
        self._latest_metrics = payload
        try:
            self.query_one(ComparisonPanel).set_metrics(payload)
        except Exception:
            pass

    # ----- actions -----

    def action_focus_load(self) -> None:
        try:
            self.query_one(LoadPanel).focus()
        except Exception:
            pass

    def action_focus_compare(self) -> None:
        try:
            self.query_one(ComparisonPanel).focus()
        except Exception:
            pass

    def action_yank(self) -> None:
        # Best-effort plaintext export of the latest metrics for paste-debug.
        m = self._latest_metrics or {}
        order = m.get("order_id") or (
            self._chosen_order.order_id if self._chosen_order else "?"
        )
        lines = [
            f"order: {order}",
            f"is_polling: {m.get('is_polling')}",
        ]
        for key in ("postgresql_view", "batch_cache", "materialize"):
            stats = m.get(key, {}) or {}
            rt = stats.get("response_time", {}) or {}
            ft = stats.get("reaction_time", {}) or {}
            lines.append(
                f"{key:18}  response p50={rt.get('median')} p99={rt.get('p99')} max={rt.get('max')}  "
                f"reaction p50={ft.get('median')} p99={ft.get('p99')} max={ft.get('max')}  "
                f"qps={stats.get('qps')}  samples={stats.get('sample_count')}"
            )
        text = "\n".join(lines)
        self.copy_to_clipboard(text)
        self.notify("copied freshness metrics to clipboard", timeout=2)


def run(order_id: str | None = None) -> None:
    FreshnessApp(order_id=order_id).run(mouse=False)


if __name__ == "__main__":
    run()
