"""Modal to open/switch the focused inline script (a `.py` file)."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView


class ScriptPickerScreen(ModalScreen[str | None]):
    """Dismisses with the chosen script's path, or None.

    `scripts` are relative `.py` paths discovered under the active dir; `focused` is
    the currently-open script's path (highlighted initially) or None. A free-text
    path input is always offered so a script the (bounded/truncated) scan omitted is
    still reachable; a non-empty typed path wins over the list selection.
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
            if self._scripts:
                if self._truncated:
                    yield Label(f"(showing first {len(self._scripts)} — type a path below)")
                items = []
                initial = 0
                for index, path in enumerate(self._scripts):
                    items.append(ListItem(Label(escape(path))))
                    if path == self._focused:
                        initial = index
                yield ListView(*items, initial_index=initial, id="script-list")
            else:
                yield Label("No .py files found — type a path below.")
            yield Input(placeholder="or a path, e.g. scripts/tool.py", id="script-path")
            yield Button("Open", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def _chosen(self) -> str | None:
        typed = self.query_one("#script-path", Input).value.strip()
        if typed:
            return typed
        if not self._scripts:
            return None
        index = self.query_one("#script-list", ListView).index
        if index is None or index >= len(self._scripts):
            return None
        return self._scripts[index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else self._chosen())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(self._chosen())

    def key_escape(self) -> None:
        self.dismiss(None)
