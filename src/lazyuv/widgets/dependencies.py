"""Dependencies panel: a collapsible tree grouped by dependency group."""

from __future__ import annotations

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from lazyuv.models import Dependency


class DependenciesPanel(Tree):
    """Groups -> dependencies. Leaf node data is the Dependency."""

    BORDER_TITLE = "Dependencies"

    def __init__(self) -> None:
        super().__init__("dependencies", id="dependencies")
        self.show_root = False
        self._filter = ""

    def load(self, dependencies: list[Dependency]) -> None:
        """Reset the filter and populate the tree from scratch."""
        self._filter = ""
        self.clear()
        self._populate(dependencies)

    def set_filter(self, text: str, dependencies: list[Dependency]) -> None:
        """Apply a name-substring filter and re-populate."""
        self._filter = text.strip().lower()
        self.clear()
        self._populate(dependencies)

    def _populate(self, dependencies: list[Dependency]) -> None:
        groups: dict[str, list[Dependency]] = {}
        for dep in dependencies:
            if self._filter and self._filter not in dep.name.lower():
                continue
            groups.setdefault(dep.group, []).append(dep)

        for group in sorted(groups):
            deps = groups[group]
            branch: TreeNode = self.root.add(f"{group} ({len(deps)})", expand=True)
            for dep in sorted(deps, key=lambda d: d.name):
                version = dep.resolved_version or "—"
                branch.add_leaf(f"{dep.name}  {version}", data=dep)

    @property
    def selected_dependency(self) -> Dependency | None:
        node = self.cursor_node
        if node is not None and isinstance(node.data, Dependency):
            return node.data
        return None
