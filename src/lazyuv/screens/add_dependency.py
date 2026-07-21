"""Modal to add dependencies: package names + target group."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select


class AddDependencyScreen(ModalScreen[tuple[list[str], str] | None]):
    """Dismisses with (packages, group) or None if cancelled."""

    def __init__(self, groups: list[str]) -> None:
        super().__init__()
        # main + dev always available, plus any existing optional groups.
        options = ["main", "dev", *[g for g in groups if g not in ("main", "dev")]]
        self._group_options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="add-dialog"):
            yield Label("Add dependencies")
            yield Input(placeholder="package names, space-separated", id="packages")
            yield Select(
                [(g, g) for g in self._group_options],
                value="main",
                id="group",
                allow_blank=False,
            )
            yield Button("Add", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        packages = self.query_one("#packages", Input).value.split()
        if not packages:
            self.dismiss(None)
            return
        group = self.query_one("#group", Select).value
        self.dismiss((packages, str(group)))

    def key_escape(self) -> None:
        self.dismiss(None)
