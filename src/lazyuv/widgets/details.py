"""Details panel: shows the selected dependency or script."""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import Static

from lazyuv.models import Dependency, Script, Tool


class DetailsPanel(Static):
    BORDER_TITLE = "Details"

    def show_dependency(self, dep: Dependency) -> None:
        spec = dep.spec or "(any)"
        if dep.locked_versions:
            version = " / ".join(dep.locked_versions)
            extra_line = f"\nlocked: {len(dep.locked_versions)} versions in lock"
        else:
            version = dep.resolved_version or "(unlocked)"
            extra_line = ""
        # `via` shows the [tool.uv.sources] entry (workspace/git/path/...) when set.
        via_line = f"\nvia:    {escape(dep.source_detail)}" if dep.source_detail else ""
        self.update(
            f"[b]{dep.name}[/b]  {version}\n"
            f"spec:   {spec}\n"
            f"group:  {dep.group}\n"
            f"source: {dep.source}"
            f"{via_line}"
            f"{extra_line}"
        )

    def show_script(self, script: Script) -> None:
        self.update(f"[b]{script.name}[/b]\ntarget: {script.target}")

    def show_tool(self, tool: Tool) -> None:
        # Escape uv-sourced strings so bracketed names don't render as markup.
        executables = escape(", ".join(tool.executables)) or "—"
        self.update(
            f"[b]{escape(tool.name)}[/b]  {escape(tool.version)}\n"
            f"executables: {executables}"
        )
