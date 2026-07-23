"""Modal to run a script with arguments."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class RunArgsScreen(ModalScreen[str | None]):
    """Prompts for a raw argument string, or None if cancelled.

    Returns the string verbatim (the caller `shlex.split`s it); an empty string is a
    valid "run with no args". `target` is shown so the user knows what they're running.
    """

    def __init__(self, target: str) -> None:
        super().__init__()
        self._target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="run-args-dialog"):
            yield Label(f"Run {escape(self._target)} with arguments (Enter to run):")
            yield Input(placeholder="e.g. --verbose input.txt", id="run-args")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def key_escape(self) -> None:
        self.dismiss(None)
