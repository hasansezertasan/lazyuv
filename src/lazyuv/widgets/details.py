"""Details panel: shows the selected dependency or script."""

from __future__ import annotations

from textual.widgets import Static

from lazyuv.models import Dependency, Script


class DetailsPanel(Static):
    BORDER_TITLE = "Details"

    def show_dependency(self, dep: Dependency) -> None:
        spec = dep.spec or "(any)"
        if dep.fork_versions:
            version = " / ".join(dep.fork_versions)
            fork_line = f"\nforks:  {len(dep.fork_versions)} (marker-specific)"
        else:
            version = dep.resolved_version or "(unlocked)"
            fork_line = ""
        self.update(
            f"[b]{dep.name}[/b]  {version}\n"
            f"spec:   {spec}\n"
            f"group:  {dep.group}\n"
            f"source: {dep.source}"
            f"{fork_line}"
        )

    def show_script(self, script: Script) -> None:
        self.update(f"[b]{script.name}[/b]\ntarget: {script.target}")
