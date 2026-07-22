"""Details panel: shows the selected dependency or script."""

from __future__ import annotations

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
        self.update(
            f"[b]{dep.name}[/b]  {version}\n"
            f"spec:   {spec}\n"
            f"group:  {dep.group}\n"
            f"source: {dep.source}"
            f"{extra_line}"
        )

    def show_script(self, script: Script) -> None:
        self.update(f"[b]{script.name}[/b]\ntarget: {script.target}")

    def show_tool(self, tool: Tool) -> None:
        executables = ", ".join(tool.executables) or "—"
        self.update(
            f"[b]{tool.name}[/b]  {tool.version}\nexecutables: {executables}"
        )
