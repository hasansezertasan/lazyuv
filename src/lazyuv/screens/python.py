"""Modal to manage Python versions: install / pin / uninstall."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from lazyuv.models import PythonVersion


class PythonPickerScreen(ModalScreen[tuple[str, str] | None]):
    """Lists Python versions; dismisses with (action, version) or None.

    `action` is "install", "pin", or "uninstall". `versions` is what the app read
    from `uv python list` — the screen itself runs no subprocess, mirroring how
    AddDependencyScreen receives its group options. The app turns the returned
    intent into a `uv` command.
    """

    def __init__(self, versions: list[PythonVersion]) -> None:
        super().__init__()
        self._versions = versions

    def compose(self) -> ComposeResult:
        with Vertical(id="python-dialog"):
            yield Label("Python versions")
            items = [
                ListItem(
                    Label(
                        f"{v.version}  "
                        + ("[green]installed[/green]" if v.installed else "available")
                    )
                )
                for v in self._versions
            ]
            yield ListView(*items, id="python-list")
            with Horizontal(id="python-buttons"):
                yield Button("Install", variant="primary", id="install")
                yield Button("Pin", id="pin")
                yield Button("Uninstall", variant="error", id="uninstall")
                yield Button("Cancel", id="cancel")

    def _selected_version(self) -> str | None:
        index = self.query_one("#python-list", ListView).index
        if index is None or index >= len(self._versions):
            return None
        return self._versions[index].version

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        version = self._selected_version()
        if version is None:
            self.dismiss(None)
            return
        self.dismiss((event.button.id, version))

    def key_escape(self) -> None:
        self.dismiss(None)
