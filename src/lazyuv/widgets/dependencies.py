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
        self._dependencies: list[Dependency] = []
        # {canonical_name: latest_version} from `O`. `_outdated_active` is separate
        # from the map's contents so an *active* overlay that found nothing still
        # shows "outdated: 0" rather than looking identical to the off state.
        self._outdated: dict[str, str] = {}
        self._outdated_active = False

    def set_filter(self, text: str, dependencies: list[Dependency]) -> None:
        """Apply a name-substring filter and re-populate."""
        self._filter = text.strip().lower()
        self._dependencies = dependencies
        self._repopulate()

    def set_outdated(self, outdated: dict[str, str]) -> None:
        """Turn the overlay on and annotate leaves with their latest version."""
        self._outdated = outdated
        self._outdated_active = True
        self._repopulate()

    def clear_outdated(self) -> None:
        """Turn the overlay off (no annotations, no count in the title)."""
        self._outdated = {}
        self._outdated_active = False
        self._repopulate()

    def _latest_for(self, dep: Dependency) -> str | None:
        """The newer version to show for `dep`, or None when it's not outdated.

        Single source of truth for both the title count and the leaf annotation, so
        they can never disagree (e.g. after an upgrade makes resolved == latest).
        """
        latest = self._outdated.get(dep.name)
        if latest and latest != dep.resolved_version:
            return latest
        return None

    def _repopulate(self) -> None:
        title = "Dependencies"
        if self._filter:
            title += f" — filter: {self._filter}"
        if self._outdated_active:
            n = sum(1 for d in self._dependencies if self._latest_for(d) is not None)
            title += f" — outdated: {n}"
        self.border_title = title
        self.clear()
        self._populate(self._dependencies)

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
                # When the outdated overlay is on and this dep has a newer release,
                # show `cur → latest` so the eye lands on what `u` would upgrade.
                latest = self._latest_for(dep)
                if latest is not None:
                    version = f"{version} → {latest}"
                branch.add_leaf(f"{dep.name}  {version}", data=dep)

    @property
    def selected_dependency(self) -> Dependency | None:
        node = self.cursor_node
        if node is not None and isinstance(node.data, Dependency):
            return node.data
        return None
