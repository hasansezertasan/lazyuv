"""Modal to install a uv tool by package name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ToolInstallScreen(ModalScreen[str | None]):
    """Dismisses with the package name to install, or None if cancelled/blank."""

    def compose(self) -> ComposeResult:
        with Vertical(id="tool-install-dialog"):
            yield Label("Install tool (Enter to install, Esc to cancel)")
            yield Input(placeholder="package name, e.g. ruff", id="tool-package")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        package = event.value.strip()
        self.dismiss(package or None)

    def key_escape(self) -> None:
        self.dismiss(None)
