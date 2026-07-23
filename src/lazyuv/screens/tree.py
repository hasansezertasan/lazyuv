"""Read-only modal: the transitive dependency graph from `uv tree`."""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Tree
from textual.widgets.tree import TreeNode

from lazyuv.models import DepTreeNode


class DependencyTreeScreen(ModalScreen[None]):
    """Shows a collapsible, scrollable dependency tree. Esc closes."""

    BINDINGS = [("escape", "dismiss", "Close"), ("q", "dismiss", "Close")]

    def __init__(self, forest: list[DepTreeNode]) -> None:
        super().__init__()
        self._forest = forest

    def compose(self) -> ComposeResult:
        with Vertical(id="tree-dialog"):
            yield Label("Dependency tree (Esc to close)")
            if not self._forest:
                yield Label("No tree available.")
            else:
                tree: Tree[None] = Tree("dependencies", id="dep-tree")
                tree.show_root = False
                for root in self._forest:
                    self._add(tree.root, root)
                tree.root.expand_all()
                yield tree

    def _add(self, parent: TreeNode, node: DepTreeNode) -> None:
        label = f"{escape(node.name)} {escape(node.version)}"
        if node.latest_version and node.latest_version != node.version:
            label += f" → {escape(node.latest_version)}"
        if node.deduped:
            label += " (*)"
        if node.children:
            branch = parent.add(label, expand=True)
            for child in node.children:
                self._add(branch, child)
        else:
            parent.add_leaf(label)

    def action_dismiss(self) -> None:
        self.dismiss(None)
