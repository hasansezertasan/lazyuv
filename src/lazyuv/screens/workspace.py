"""Modal to switch the focused workspace member."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from lazyuv.models import WorkspaceMember


class WorkspaceSwitchScreen(ModalScreen[str | None]):
    """Dismisses with the chosen member's directory ("" for root), or None."""

    def __init__(self, members: list[WorkspaceMember], focused_dir: str) -> None:
        super().__init__()
        self._members = members
        self._focused = focused_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="workspace-dialog"):
            yield Label("Switch workspace member")
            items = []
            initial = 0
            for index, member in enumerate(self._members):
                label = f"{member.name} (root)" if member.is_root else member.name
                items.append(ListItem(Label(escape(label))))
                if member.directory == self._focused:
                    initial = index
            yield ListView(*items, initial_index=initial, id="workspace-list")
            yield Button("Switch", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        index = self.query_one("#workspace-list", ListView).index
        if index is None or index >= len(self._members):
            self.dismiss(None)
            return
        self.dismiss(self._members[index].directory)

    def key_escape(self) -> None:
        self.dismiss(None)
