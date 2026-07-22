"""Tools panel: globally-installed uv tools (`uv tool list`)."""

from __future__ import annotations

from textual.widgets import Label, ListItem, ListView

from lazyuv.models import Tool


class ToolsPanel(ListView):
    BORDER_TITLE = "Tools"

    def __init__(self) -> None:
        super().__init__(id="tools")
        self._tools: list[Tool] = []

    def load(self, tools: list[Tool]) -> None:
        self._tools = tools
        self.clear()
        for tool in tools:
            self.append(ListItem(Label(f"{tool.name}  {tool.version}")))

    @property
    def selected_tool(self) -> Tool | None:
        index = self.index
        if index is None or index >= len(self._tools):
            return None
        return self._tools[index]
