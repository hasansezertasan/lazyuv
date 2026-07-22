"""Modal to manage Python versions: install / pin / uninstall."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from lazyuv.models import PythonVersion


class PythonPickerScreen(ModalScreen[tuple[str, str] | None]):
    """Lists Python versions; dismisses with (action, request) or None.

    `action` is "install", "pin", or "uninstall"; `request` is the selected row's
    uv `key` (unambiguous across implementation/variant). `versions` is what the app
    read from `uv python list` — the screen runs no subprocess, mirroring how
    AddDependencyScreen receives its group options. The app turns the intent into a
    `uv` command.

    Actions are gated to what's valid for the selection: Install only for a row that
    isn't installed, Uninstall only for a uv-managed row (`uv python uninstall` can't
    remove system interpreters). An invalid press just bells and keeps the modal open.
    """

    def __init__(self, versions: list[PythonVersion]) -> None:
        super().__init__()
        self._versions = versions

    def compose(self) -> ComposeResult:
        with Vertical(id="python-dialog"):
            yield Label("Python versions")
            items = [ListItem(Label(self._row_label(v))) for v in self._versions]
            yield ListView(*items, id="python-list")
            with Horizontal(id="python-buttons"):
                yield Button("Install", variant="primary", id="install")
                yield Button("Pin", id="pin")
                yield Button("Uninstall", variant="error", id="uninstall")
                yield Button("Cancel", id="cancel")

    @staticmethod
    def _row_label(v: PythonVersion) -> str:
        if v.managed:
            status = "[green]managed[/green]"
        elif v.installed:
            status = "installed"
        else:
            status = "available"
        # Show implementation only when it isn't the common CPython, so PyPy etc.
        # (which can share a version number) are visually distinct too.
        impl = "" if v.implementation == "cpython" else f" {v.implementation}"
        return f"{v.version}{impl}  {status}"

    def _selected(self) -> PythonVersion | None:
        index = self.query_one("#python-list", ListView).index
        if index is None or index >= len(self._versions):
            return None
        return self._versions[index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        selected = self._selected()
        if selected is None:
            self.dismiss(None)
            return
        action = event.button.id
        if action == "install" and selected.installed:
            self.app.bell()  # already installed — nothing to do
            return
        if action == "uninstall" and not selected.managed:
            self.app.bell()  # uv can't uninstall a system/non-managed interpreter
            return
        self.dismiss((action, selected.key))

    def key_escape(self) -> None:
        self.dismiss(None)
