"""Modal to bump or set the project version (`uv version`)."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

# The common bumps; pre-release kinds (alpha/rc/post/…) are reachable via the
# explicit-value input rather than cluttering the select.
_BUMPS = ("major", "minor", "patch")


class VersionScreen(ModalScreen[tuple[str, str] | None]):
    """Dismisses with an intent, or None on cancel:

    - ("set", value) when the explicit input is non-empty (takes precedence), else
    - ("bump", kind) from the select.
    """

    def __init__(self, name: str, current: str) -> None:
        super().__init__()
        self._name = name
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="version-dialog"):
            yield Label(f"Version — {escape(self._name)} {escape(self._current)}")
            yield Select(
                [(b, b) for b in _BUMPS], value="patch", id="bump", allow_blank=False
            )
            yield Input(placeholder="or set an explicit version, e.g. 1.2.3", id="value")
            yield Button("Apply", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def _result(self) -> tuple[str, str] | None:
        value = self.query_one("#value", Input).value.strip()
        if value:
            return ("set", value)
        return ("bump", str(self.query_one("#bump", Select).value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else self._result())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(self._result())

    def key_escape(self) -> None:
        self.dismiss(None)
