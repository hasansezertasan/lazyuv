"""Modal to enter a dependency name filter."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class FilterScreen(ModalScreen[str | None]):
    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog"):
            yield Label("Filter dependencies (Enter to apply, Esc to cancel)")
            yield Input(value=self._current, placeholder="name substring", id="filter")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def key_escape(self) -> None:
        self.dismiss(None)
