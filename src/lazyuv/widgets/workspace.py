"""Workspace panel: uv workspace members, with the focused one marked."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from textual.widgets import Static

if TYPE_CHECKING:
    from lazyuv.models import WorkspaceMember


class WorkspacePanel(Static):
    BORDER_TITLE = "Workspace"

    def __init__(self) -> None:
        super().__init__(id="workspace")

    def show(self, members: list[WorkspaceMember], focused_dir: str) -> None:
        lines = []
        for member in members:
            marker = "▶ " if member.directory == focused_dir else "  "
            label = f"{member.name} (root)" if member.is_root else member.name
            lines.append(f"{marker}{escape(label)}")
        self.update("\n".join(lines) or "No workspace members.")
