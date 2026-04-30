"""Middle column: agent reasoning + tool calls."""

from __future__ import annotations

import json
from datetime import datetime

from textual.binding import Binding
from textual.widgets import RichLog

from ..feeds.types import AgentClimax, AgentEvent


class AgentPanel(RichLog):
    DEFAULT_CSS = """
    AgentPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
    }
    AgentPanel:focus {
        border: heavy $success;
    }
    """

    can_focus = True
    BINDINGS = [
        Binding("left", "scroll_left", "scroll left", show=False),
        Binding("right", "scroll_right", "scroll right", show=False),
        Binding("ctrl+pageup", "page_left", "page left", show=False),
        Binding("ctrl+pagedown", "page_right", "page right", show=False),
    ]
    BORDER_TITLE = "(2) AGENT REASONS"
    BORDER_SUBTITLE = "observe -> think -> act -> re-observe"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, markup=True, wrap=True, highlight=False, max_lines=400, **kwargs)
        self._connected = False
        self._plain: list[str] = []

    def to_plaintext(self) -> str:
        return "\n".join(self._plain[-400:])

    def _log(self, line: str, plain: str | None = None) -> None:
        self._plain.append(plain if plain is not None else line)
        self.write(line)

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self._refresh_subtitle()
        self._log("[dim](waiting for input)[/dim]", plain="(waiting for input)")

    def show_submitted(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        preview = text if len(text) < 280 else text[:277] + "..."
        preview = preview.replace("\n", " | ")
        self._log(f"[bold cyan]{ts}  >[/bold cyan] {preview}", plain=f"{ts}  > {preview}")

    def on_agent_event(self, evt: AgentEvent, climax: AgentClimax | None = None) -> None:
        ts = datetime.fromtimestamp(evt.t_wall).strftime("%H:%M:%S.%f")[:-3]
        if evt.type == "connect":
            self._connected = True
            self._refresh_subtitle()
            return
        if evt.type == "disconnect":
            self._connected = False
            self._refresh_subtitle()
            return
        if evt.type == "tool_call":
            name = (evt.data or {}).get("name", "?")
            args = (evt.data or {}).get("args", {})
            args_str = _compact_args(args)
            self._log(
                f"[cyan]{ts}  *[/cyan] [bold]{name}[/bold]({args_str})",
                plain=f"{ts}  * {name}({args_str})",
            )
            return
        if evt.type == "tool_result":
            content = (evt.data or {}).get("content", "")
            body = _truncate(content, 220)
            if climax is not None:
                wt = climax.deltas.get("write_to_reobs")
                wt_str = f"{wt:.2f}s" if wt is not None else "?"
                line = f"{ts}    -> {body}    <- AGENT SAW ITS OWN WRITE ({climax.pk}, {wt_str})"
                rich = (
                    f"[dim]{ts}    ->[/dim] {body}    "
                    f"[bold green on black]<- AGENT SAW ITS OWN WRITE "
                    f"({climax.pk}, {wt_str})[/bold green on black]"
                )
            else:
                line = f"{ts}    -> {body}"
                rich = f"[dim]{line}[/dim]"
            self._log(rich, plain=line)
            return
        if evt.type == "thinking":
            content = (evt.data or {}).get("content", "")
            if not content:
                return
            line = f"{ts}    .. {_truncate(content, 220)}"
            self._log(f"[italic dim]{line}[/italic dim]", plain=line)
            return
        if evt.type == "response":
            text = evt.data if isinstance(evt.data, str) else str(evt.data)
            line = f"{ts}  <- {_truncate(text, 600)}"
            self._log(f"[bold green]{ts}  <-[/bold green] {_truncate(text, 600)}", plain=line)
            return
        if evt.type == "error":
            msg = (evt.data or {}).get("message", str(evt.data))
            line = f"{ts}  ! {msg}"
            self._log(f"[bold red]{ts}  ![/bold red] {msg}", plain=line)
            return
        if evt.type == "done":
            line = f"{ts}    (done)"
            self._log(f"[dim]{line}[/dim]", plain=line)
            return

    def _refresh_subtitle(self) -> None:
        dot = "[green]o[/green]" if self._connected else "[dim]o[/dim]"
        self.border_subtitle = f"{dot} observe -> think -> act -> re-observe"


def _compact_args(args: object) -> str:
    if not isinstance(args, dict):
        return _truncate(str(args), 80)
    parts = []
    for k, v in args.items():
        v_str = json.dumps(v, default=str) if not isinstance(v, str) else v
        v_str = _truncate(v_str, 60)
        parts.append(f"{k}={v_str}")
    return _truncate(", ".join(parts), 160)


def _truncate(text, limit: int) -> str:
    s = text if isinstance(text, str) else str(text)
    s = s.replace("\n", " ")
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."
