"""Modal to run `uv sync` with extras / groups / flags."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, SelectionList

# Dismiss payload: (extras, groups, no_dev, frozen).
SyncOptions = tuple[list[str], list[str], bool, bool]


class SyncOptionsScreen(ModalScreen["SyncOptions | None"]):
    """Choose sync scope; dismisses with (extras, groups, no_dev, frozen) or None.

    `groups` is the project's (name, kind) pairs (as in AddDependencyScreen): extras
    (kind "extra") and dependency groups (kind "group"/"dev") are offered as
    separate multi-selects. The app turns the result into `build_sync(...)`.
    """

    def __init__(self, groups: list[tuple[str, str]]) -> None:
        super().__init__()
        self._extras = [name for name, kind in groups if kind == "extra"]
        # The `dev` group is excluded here: uv includes it by default and the
        # `--no-dev` checkbox controls it. Offering it in the multi-select too would
        # let a user pick `--group dev` AND `--no-dev`, which uv silently resolves to
        # "no dev" — a confusing contradiction.
        self._groups = [name for name, kind in groups if kind == "group"]

    def compose(self) -> ComposeResult:
        with Vertical(id="sync-dialog"):
            yield Label("Sync options")
            if self._extras:
                yield Label("extras")
                yield SelectionList(
                    *[(name, name) for name in self._extras], id="extras"
                )
            if self._groups:
                yield Label("groups")
                yield SelectionList(
                    *[(name, name) for name in self._groups], id="groups"
                )
            yield Checkbox("--no-dev", id="no-dev")
            yield Checkbox("--frozen", id="frozen")
            yield Button("Sync", variant="primary", id="ok")
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
        self.dismiss(
            (
                self._selected("extras"),
                self._selected("groups"),
                self.query_one("#no-dev", Checkbox).value,
                self.query_one("#frozen", Checkbox).value,
            )
        )

    def key_escape(self) -> None:
        self.dismiss(None)
