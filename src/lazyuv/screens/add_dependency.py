"""Modal to add dependencies: package names + target group."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select


class AddDependencyScreen(ModalScreen[tuple[list[str], str, str] | None]):
    """Dismisses with (packages, group, kind) or None if cancelled.

    `groups` is the list of existing (name, kind) pairs for non-main/dev groups,
    so the modal can carry each group's kind (extra vs. dependency group) back to
    the caller unambiguously — even when an extra and a dependency group share a
    name.
    """

    def __init__(self, groups: list[tuple[str, str]]) -> None:
        super().__init__()
        # main + dev are always available; append existing (name, kind) pairs.
        # Deduplicate exact pairs (not names), so an optional extra literally named
        # "dev" or "main" — distinct from the dev/main defaults — stays selectable.
        options: list[tuple[str, str]] = [("main", "main"), ("dev", "dev")]
        for name, kind in groups:
            if (name, kind) not in options:
                options.append((name, kind))
        self._options = options

    def compose(self) -> ComposeResult:
        names = [name for name, _ in self._options]
        # Select values are indices into self._options; disambiguate the label
        # only when the same name exists as both an extra and a dependency group.
        select_options = [
            (name if names.count(name) == 1 else f"{name} ({kind})", index)
            for index, (name, kind) in enumerate(self._options)
        ]
        with Vertical(id="add-dialog"):
            yield Label("Add dependencies")
            yield Input(placeholder="package names, space-separated", id="packages")
            yield Select(select_options, value=0, id="group", allow_blank=False)
            yield Button("Add", variant="primary", id="ok")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        packages = self.query_one("#packages", Input).value.split()
        if not packages:
            self.dismiss(None)
            return
        group, kind = self._options[int(self.query_one("#group", Select).value)]
        self.dismiss((packages, group, kind))

    def key_escape(self) -> None:
        self.dismiss(None)
