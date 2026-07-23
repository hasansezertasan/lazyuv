"""Modal to initialize a new project (`uv init`) on the not-a-project screen."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

_KINDS = ("app", "lib", "bare")


class InitScreen(ModalScreen[tuple[str, str] | None]):
    """Dismisses with (kind, name) or None. `name` is "" to use uv's default."""

    def __init__(self, default_name: str) -> None:
        super().__init__()
        self._default_name = default_name

    def compose(self) -> ComposeResult:
        with Vertical(id="init-dialog"):
            yield Label("Initialize a project (uv init)")
            yield Select(
                [(k, k) for k in _KINDS], value="app", id="kind", allow_blank=False
            )
            yield Input(
                placeholder=f"name (default: {escape(self._default_name)})", id="name"
            )
            yield Button("Create", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def _result(self) -> tuple[str, str]:
        kind = str(self.query_one("#kind", Select).value)
        name = self.query_one("#name", Input).value.strip()
        return (kind, name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else self._result())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(self._result())

    def key_escape(self) -> None:
        self.dismiss(None)
