"""Modal to add dependencies to an inline script's PEP 723 block.

Scripts have no dependency groups, so this is a trimmed AddDependencyScreen: just
package names. Dismisses with the package list, or None if cancelled/blank.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class AddScriptDependencyScreen(ModalScreen[list[str] | None]):
    """Dismisses with a list of package names, or None if cancelled/blank."""

    def compose(self) -> ComposeResult:
        with Vertical(id="add-dialog"):
            yield Label("Add script dependencies")
            yield Input(placeholder="package names, space-separated", id="packages")
            yield Button("Add", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def _submit(self) -> None:
        packages = self.query_one("#packages", Input).value.split()
        self.dismiss(packages or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def key_escape(self) -> None:
        self.dismiss(None)
