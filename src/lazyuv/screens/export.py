"""Modal to export a requirements file via `uv export`."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, SelectionList

# Dismiss payload: (output_file, no_hashes, no_dev, extras, groups).
ExportOptions = tuple[str, bool, bool, list[str], list[str]]


class ExportScreen(ModalScreen["ExportOptions | None"]):
    """Choose export options; dismisses with ExportOptions or None.

    `groups` is the project's (name, kind) pairs (as in AddDependencyScreen): extras
    and dependency groups are offered as multi-selects. `dev` is excluded — `--no-dev`
    controls it (same reasoning as SyncOptionsScreen).
    """

    def __init__(self, groups: list[tuple[str, str]]) -> None:
        super().__init__()
        self._extras = [name for name, kind in groups if kind == "extra"]
        self._groups = [name for name, kind in groups if kind == "group"]

    def compose(self) -> ComposeResult:
        with Vertical(id="export-dialog"):
            yield Label("Export requirements")
            yield Input(value="requirements.txt", id="export-output")
            if self._extras:
                yield Label("extras")
                yield SelectionList(*[(n, n) for n in self._extras], id="export-extras")
            if self._groups:
                yield Label("groups")
                yield SelectionList(*[(n, n) for n in self._groups], id="export-groups")
            yield Checkbox("--no-hashes", id="export-no-hashes")
            yield Checkbox("--no-dev", id="export-no-dev")
            yield Button("Export", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def _selected(self, list_id: str) -> list[str]:
        matches = self.query(f"#{list_id}")
        if not matches:
            return []
        return list(matches.first(SelectionList).selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        output = self.query_one("#export-output", Input).value.strip() or "requirements.txt"
        self.dismiss(
            (
                output,
                self.query_one("#export-no-hashes", Checkbox).value,
                self.query_one("#export-no-dev", Checkbox).value,
                self._selected("export-extras"),
                self._selected("export-groups"),
            )
        )

    def key_escape(self) -> None:
        self.dismiss(None)
