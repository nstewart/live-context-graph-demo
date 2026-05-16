"""Left column: multi-line prompt input + scrolling prompt history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static, TextArea


class PromptTextArea(TextArea):
    """TextArea with chat-app key conventions.

    enter        -> submit (post SubmitRequested up to the app)
    shift+enter  -> insert newline (kitty-protocol terminals)
    ctrl+j       -> insert newline (universal fallback; ctrl+j == LF)
    """

    class SubmitRequested(Message):
        pass

    def on_key(self, event: events.Key) -> None:
        if event.key in ("shift+enter", "ctrl+j"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.SubmitRequested())
            return


@dataclass
class HistoryEntry:
    submitted_at: datetime
    text: str


class InputPane(Vertical):
    """The 'write side': user types here, history accrues below."""

    DEFAULT_CSS = """
    InputPane {
        height: 100%;
        border: round $accent;
        padding: 0 1;
    }
    InputPane > #prompt_input {
        height: 60%;
        border: tall $primary;
    }
    InputPane > #history_label {
        height: 1;
        color: $text-muted;
        padding: 1 0 0 0;
    }
    InputPane > #history_log {
        height: 1fr;
        border: tall $primary-darken-2;
        padding: 0 1;
        overflow-y: auto;
    }
    """

    BORDER_TITLE = "(1) YOU TYPE  -- write side"
    BORDER_SUBTITLE = "enter=submit | f2=agent f3=mz to scroll | esc=back to input"

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        editor = PromptTextArea(id="prompt_input", language=None, soft_wrap=True)
        editor.show_line_numbers = False
        yield editor
        yield Static("history", id="history_label")
        yield Static("(no prompts yet)", id="history_log", markup=False)

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self.border_subtitle = self.BORDER_SUBTITLE
        self.query_one("#prompt_input", PromptTextArea).focus()

    def on_prompt_text_area_submit_requested(
        self, _: PromptTextArea.SubmitRequested
    ) -> None:
        self.submit_current()

    def submit_current(self) -> None:
        editor = self.query_one("#prompt_input", PromptTextArea)
        text = editor.text.strip()
        if not text:
            return
        editor.text = ""
        self._record_history(text)
        self.post_message(self.Submitted(text))

    def prefill(self, text: str) -> None:
        editor = self.query_one("#prompt_input", PromptTextArea)
        editor.text = text

    def _record_history(self, text: str) -> None:
        self._history.append(HistoryEntry(datetime.now(), text))
        self._history = self._history[-10:]
        self.query_one("#history_log", Static).update(self._render_history())

    def _render_history(self) -> str:
        if not self._history:
            return "(no prompts yet)"
        lines = []
        for entry in reversed(self._history):
            ts = entry.submitted_at.strftime("%H:%M:%S")
            preview = entry.text.replace("\n", " | ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            lines.append(f"{ts}  {preview}")
        return "\n".join(lines)
