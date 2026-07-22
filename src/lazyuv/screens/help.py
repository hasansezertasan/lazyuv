"""Help overlay listing keybindings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

_HELP = """[b]lazyuv keybindings[/b]

  j / k , arrows   navigate within a panel
  Tab              cycle panel focus
  a                add dependencies
  d                remove selected dependency
  s                sync
  S                sync with options (extras / groups / flags)
  l                lock
  r                run selected script
  p                manage Python versions
  v                create / recreate the venv
  /                filter dependencies
  ?                toggle this help
  q                quit

Press ? or Escape to close."""


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(_HELP)

    def action_dismiss(self) -> None:
        self.dismiss(None)
