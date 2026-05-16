"""CQRS dashboard: input -> agent -> Materialize-side propagation, full height.

Load + reaction-time-comparison live in freshness_app.py (different demo).
"""

from __future__ import annotations

import logging
import os
import uuid

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer


def _configure_logging() -> str:
    """Send feed warnings/info to a file so we can tail-debug a running TUI."""
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
    root.info("---- demo_tui (cqrs) log opened ----")
    return path


logger = logging.getLogger(__name__)

from .config import Config
from .feeds.agent_stream import stream_prompt
from .feeds.mz_subscribe import DEFAULT_VIEWS, subscribe_view
from .feeds.propagation import poll_audit_writes, poll_propagation_events
from .feeds.types import AgentEvent, MzRow, PropagationEvent, SourceWriteEvent, now_mono
from .panels.agent_panel import AgentPanel
from .panels.mz_panel import MzPanel
from .timing import WriteTracker
from .widgets.input_pane import InputPane


class DemoApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "FreshMart Live CQRS Dashboard"
    SUB_TITLE = "you write -> agent reasons -> Materialize reflects"

    BINDINGS = [
        Binding("f1", "focus_input", "input", show=True, priority=True),
        Binding("f2", "focus_agent", "agent", show=True, priority=True),
        Binding("f3", "focus_mz", "materialize", show=True, priority=True),
        Binding("escape", "focus_input", "input", show=False, priority=True),
        Binding("ctrl+shift+c", "yank_panels", "copy panels", show=True),
        Binding("ctrl+c", "quit", "quit", show=True, priority=True),
    ]

    def __init__(self, config: Config | None = None, scenario: str | None = None) -> None:
        super().__init__()
        self.config = config or Config.from_env()
        self.scenario = scenario
        self.tracker = WriteTracker()
        self.log_path = _configure_logging()
        self._chat_thread_id: str = f"tui-{uuid.uuid4().hex[:8]}"

    def compose(self) -> ComposeResult:
        with Horizontal(id="top_row"):
            yield InputPane(id="input_pane")
            yield AgentPanel(id="agent_panel")
            yield MzPanel(id="mz_panel")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(30, self.tracker.expire_old)
        # SUBSCRIBE workers feed the WriteTracker's climax detection only --
        # the right pane is rendered from /api/audit/writes + /propagation/events.
        for spec in DEFAULT_VIEWS:
            self.run_worker(
                _bind(self._mz_worker, spec),
                name=f"mz:{spec.view}",
                exclusive=False,
                exit_on_error=False,
            )
        # HTTP pollers driving the right pane (matches PropagationContext.tsx).
        self.run_worker(
            self._audit_writes_worker,
            name="audit_writes",
            exclusive=False,
            exit_on_error=False,
        )
        self.run_worker(
            self._propagation_events_worker,
            name="propagation_events",
            exclusive=False,
            exit_on_error=False,
        )

    # ----- workers -----

    async def _mz_worker(self, spec) -> None:
        await subscribe_view(self.config.mz_dsn, spec, self._on_mz_row)

    async def _audit_writes_worker(self) -> None:
        await poll_audit_writes(self.config.api_base_url, self._on_source_write)

    async def _propagation_events_worker(self) -> None:
        await poll_propagation_events(
            self.config.search_sync_url, self._on_propagation_event
        )

    async def _agent_worker(self, prompt: str) -> None:
        await stream_prompt(
            self.config.agent_base_url,
            prompt,
            thread_id=self._chat_thread_id,
            emit=self._on_agent_event,
        )

    # ----- emit callbacks -----

    def _on_mz_row(self, row: MzRow) -> None:
        # SUBSCRIBE rows are now invisible plumbing -- only the WriteTracker
        # consumes them, for sub-second climax detection on agent writes.
        self.tracker.on_mz_row(row)

    def _on_source_write(self, event: SourceWriteEvent) -> None:
        try:
            mp = self.query_one(MzPanel)
            mp.set_tracked_pks(self.tracker.tracked_pks())
            mp.on_source_write(event)
        except Exception:
            logger.debug("_on_source_write failed", exc_info=True)

    def _on_propagation_event(self, event: PropagationEvent) -> None:
        try:
            mp = self.query_one(MzPanel)
            mp.set_tracked_pks(self.tracker.tracked_pks())
            mp.on_propagation_event(event)
        except Exception:
            logger.debug("_on_propagation_event failed", exc_info=True)

    def _on_agent_event(self, evt: AgentEvent) -> None:
        climax = self.tracker.on_agent_event(evt)
        try:
            self.query_one(AgentPanel).on_agent_event(evt, climax=climax)
        except Exception:
            logger.debug("_on_agent_event failed", exc_info=True)

    # ----- actions -----

    def action_focus_input(self) -> None:
        from .widgets.input_pane import PromptTextArea

        try:
            self.query_one(PromptTextArea).focus()
        except Exception:
            pass

    def action_focus_agent(self) -> None:
        try:
            self.query_one(AgentPanel).focus()
        except Exception:
            pass

    def action_focus_mz(self) -> None:
        try:
            self.query_one(MzPanel).focus()
        except Exception:
            pass

    def action_yank_panels(self) -> None:
        agent = self.query_one(AgentPanel).to_plaintext()
        mz = self.query_one(MzPanel).to_plaintext()
        bundle = (
            "===== AGENT =====\n" + agent + "\n\n"
            "===== MATERIALIZE =====\n" + mz + "\n"
        )
        self.copy_to_clipboard(bundle)
        self.notify("copied agent + materialize panes to clipboard", timeout=2)

    def on_input_pane_submitted(self, message: InputPane.Submitted) -> None:
        self.tracker.notify_submit(now_mono())
        self.query_one(AgentPanel).show_submitted(message.text)
        self.run_worker(
            _bind(self._agent_worker, message.text),
            name="agent_call",
            exclusive=False,
            exit_on_error=False,
        )


def _bind(coro_fn, *args):
    """Wrap a bound async method so Textual calls it lazily."""

    async def _start():
        return await coro_fn(*args)

    return _start


def run(scenario: str | None = None) -> None:
    # mouse=False disables Textual's mouse capture so the terminal handles
    # selection natively -- click-and-drag works for copy in iTerm/Terminal.app
    # without needing Option as a modifier. This app is keyboard-driven anyway.
    DemoApp(scenario=scenario).run(mouse=False)


if __name__ == "__main__":
    run()
