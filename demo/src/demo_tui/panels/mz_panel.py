"""Right column: live Materialize SUBSCRIBE feed."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.widgets import RichLog

from ..feeds.types import MzAnnotation, MzRow

# Short labels per view so the line stays narrow.
VIEW_LABEL = {
    "inventory_items_with_dynamic_pricing_mv": "pricing",
    "orders_with_lines_mv": "orders ",
}


class MzPanel(RichLog):
    DEFAULT_CSS = """
    MzPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
    }
    MzPanel:focus {
        border: heavy $success;
    }
    """

    can_focus = True
    BORDER_TITLE = "(3) MATERIALIZE -- live read side"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, markup=True, wrap=False, highlight=False, max_lines=400, **kwargs)
        self._views_seen: set[str] = set()
        self._heartbeat_ts: dict[str, int] = {}
        self._subscribed: set[str] = set()
        self._plain: list[str] = []

    def to_plaintext(self) -> str:
        return "\n".join(self._plain[-400:])

    def _log(self, line: str, plain: str) -> None:
        self._plain.append(plain)
        self.write(line)

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self._refresh_subtitle()
        self._log(
            "[dim](waiting for changes -- snapshot discarded; only post-launch deltas show here)[/dim]",
            "(waiting for changes -- snapshot discarded; only post-launch deltas show here)",
        )

    def on_mz_row(self, row: MzRow, annotation: MzAnnotation | None = None) -> None:
        if "_status" in row.columns:
            status = row.columns["_status"]
            if status == "subscribed":
                self._subscribed.add(row.view)
                line = f". subscribed: {row.view}"
                self._log(f"[dim cyan]{line}[/dim cyan]", line)
                self._refresh_subtitle()
            return
        if row.is_heartbeat:
            self._heartbeat_ts[row.view] = row.mz_timestamp
            self._refresh_subtitle()
            return
        if "_error" in row.columns:
            line = f"! {row.view}: {row.columns['_error']}"
            self._log(f"[red]{line}[/red]", line)
            return

        sign_plain = "+" if row.diff > 0 else "-" if row.diff < 0 else "?"
        sign = f"[green]{sign_plain}[/green]" if row.diff > 0 else f"[red]{sign_plain}[/red]" if row.diff < 0 else f"[dim]{sign_plain}[/dim]"
        ts = _fmt_mz_ts(row.mz_timestamp)
        label = VIEW_LABEL.get(row.view, row.view[:8])
        body = _format_columns(row.view, row.columns)

        if annotation is not None:
            # Row matched an agent write -- this is the "agent's write just appeared
            # in Materialize" beat. Star and bold-green it.
            plain = f"* {sign_plain} {ts}  {label}  {body}   <- agent wrote {annotation.pk}"
            line = (
                f"[bold yellow]*[/bold yellow] {sign} {ts}  [bold green]{label}[/bold green]  "
                f"{body}   [bold green]<- agent wrote {annotation.pk}[/bold green]"
            )
        else:
            plain = f"{sign_plain} {ts}  {label}  {body}"
            line = f"{sign} {ts}  [bold]{label}[/bold]  {body}"
        self._log(line, plain)
        self._views_seen.add(row.view)

    def _refresh_subtitle(self) -> None:
        n_sub = len(self._subscribed)
        if not self._heartbeat_ts:
            if n_sub:
                self.border_subtitle = f"subscribed ({n_sub} views) -- waiting for first heartbeat"
            else:
                self.border_subtitle = "connecting..."
            return
        latest = max(self._heartbeat_ts.values())
        self.border_subtitle = (
            f"frontier {_fmt_mz_ts(latest)}  ({n_sub} views, snapshot discarded)"
        )


def _fmt_mz_ts(mz_ts) -> str:
    """mz timestamps are ms-since-epoch."""
    try:
        ms = int(mz_ts)
    except (TypeError, ValueError):
        return str(mz_ts)
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone()
    return dt.strftime("%H:%M:%S.") + f"{ms % 1000:03d}"


def _format_columns(view: str, cols: dict) -> str:
    if view == "inventory_items_with_dynamic_pricing_mv":
        return _fmt_pricing(cols)
    if view == "orders_with_lines_mv":
        return _fmt_order(cols)
    return " ".join(f"{k}={v}" for k, v in cols.items())


def _fmt_pricing(c: dict) -> str:
    store = c.get("store_id", "?")
    zone = c.get("store_zone", "?")
    product = c.get("product_id", "?")
    qty = c.get("available_quantity", "?")
    price = c.get("live_price")
    change = c.get("price_change")
    demand = c.get("demand_multiplier")
    # `effective_updated_at` is consumed by the ReactionMonitor; not displayed here.
    price_str = f"${price}" if price is not None else "$ ?"
    change_str = ""
    if change is not None:
        try:
            cv = float(change)
            if cv > 0:
                change_str = f" [yellow]+{cv:.2f}[/yellow]"
            elif cv < 0:
                change_str = f" [cyan]{cv:.2f}[/cyan]"
        except (TypeError, ValueError):
            pass
    demand_str = f"x{demand}" if demand is not None else "x?"
    return f"{store}({zone})  {product}  qty={qty}  {price_str}{change_str}  {demand_str}"


def _fmt_order(c: dict) -> str:
    num = c.get("order_number", "?")
    status = c.get("order_status", "?")
    store = c.get("store_id", "?")
    customer = c.get("customer_name", "?")
    total = c.get("order_total_amount")
    total_str = f"${total}" if total is not None else "$?"
    return f"{num}  {status:<16}  {store}  {customer}  {total_str}"
