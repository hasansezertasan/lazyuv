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

    def set_filter(self, text: str, dependencies: list[Dependency]) -> None:
        """Apply a name-substring filter and re-populate."""
        self._filter = text.strip().lower()
        self.border_title = (
            f"Dependencies — filter: {self._filter}" if self._filter else "Dependencies"
        )
        self.clear()
        self._populate(dependencies)

    def restore_selection(self, group: str, name: str) -> None:
        """Move the cursor back to the dep matching (group, name), if present.

        Used after a refresh so add/remove/sync don't reset the highlight to the
        top of the tree.
        """
        for group_node in self.root.children:
            for leaf in group_node.children:
                data = leaf.data
                if (
                    isinstance(data, Dependency)
                    and data.group == group
                    and data.name == name
                ):
                    self.move_cursor(leaf)
                    return

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
                if dep.locked_versions:
                    joined = " / ".join(dep.locked_versions)
                    version = f"{joined}  ({len(dep.locked_versions)} versions)"
                else:
                    version = dep.resolved_version or "—"
                branch.add_leaf(f"{dep.name}  {version}", data=dep)

    @property
    def selected_dependency(self) -> Dependency | None:
        node = self.cursor_node
        if node is not None and isinstance(node.data, Dependency):
            return node.data
        return None
