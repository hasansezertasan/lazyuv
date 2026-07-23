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
  u                upgrade selected package (uv lock --upgrade-package)
  p                manage Python versions
  v                create / recreate the venv
  w                switch workspace member
  e                export requirements (uv export)
  /                filter dependencies
  g                toggle project / global mode
  ?                toggle this help
  q                quit

[b]global mode[/b]

  i                install a tool
  u                upgrade selected tool
  U                upgrade all tools
  x                uninstall selected tool
  c                clean the cache
  P                prune the cache
  z                compute cache size
  X                uv self update

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
