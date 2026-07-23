"""Scripts panel: runnable project scripts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from lazyuv.models import Script


class ScriptsPanel(ListView):
    BORDER_TITLE = "Scripts"

    def __init__(self) -> None:
        super().__init__(id="scripts")
        self._scripts: list[Script] = []

    def load(self, scripts: list[Script]) -> None:
        self._scripts = scripts
        self.clear()
        for script in scripts:
            self.append(ListItem(Label(script.name)))

    @property
    def selected_script(self) -> Script | None:
        index = self.index
        if index is None or index >= len(self._scripts):
            return None
        return self._scripts[index]
