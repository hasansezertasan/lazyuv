"""Modal to open/switch the focused inline script (a `.py` file)."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView


class ScriptPickerScreen(ModalScreen[str | None]):
    """Dismisses with the chosen script's relative path, or None.

    `scripts` are relative `.py` paths discovered under the active dir; `focused` is
    the currently-open script's path (highlighted initially) or None.
    """

    def __init__(
        self, scripts: list[str], focused: str | None = None, truncated: bool = False
    ) -> None:
        super().__init__()
        self._scripts = scripts
        self._focused = focused
        self._truncated = truncated

    def compose(self) -> ComposeResult:
        with Vertical(id="script-dialog"):
            yield Label("Open inline script")
            if not self._scripts:
                yield Label("No .py files found here.")
            else:
                if self._truncated:
                    yield Label(f"(showing first {len(self._scripts)})")
                items = []
                initial = 0
                for index, path in enumerate(self._scripts):
                    items.append(ListItem(Label(escape(path))))
                    if path == self._focused:
                        initial = index
                yield ListView(*items, initial_index=initial, id="script-list")
                yield Button("Open", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel" or not self._scripts:
            self.dismiss(None)
            return
        index = self.query_one("#script-list", ListView).index
        if index is None or index >= len(self._scripts):
            self.dismiss(None)
            return
        self.dismiss(self._scripts[index])

    def key_escape(self) -> None:
        self.dismiss(None)
