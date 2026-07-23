"""Help overlay listing keybindings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
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
  R                run selected script with arguments
  t                dependency tree (uv tree)
  O                toggle outdated overlay (deps with a newer release)
  u                upgrade selected package (uv lock --upgrade-package)
  p                manage Python versions
  v                create / recreate the venv
  w                switch workspace member
  e                export requirements (uv export)
  /                filter dependencies
  o                open / switch an inline script (PEP 723)
  g                toggle project / global mode
  ?                toggle this help
  q                quit

[b]script mode[/b] (a `.py` file's inline deps)

  a                add script dependencies (uv add --script)
  d                remove selected dependency (uv remove --script)
  r                run the script (uv run --script)
  R                run the script with arguments
  o                switch to another script
  Escape           back to project mode

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
        # VerticalScroll (focusable) so the keybinding list is scrollable by keyboard
        # when it's taller than the terminal; escape/? still close via the bindings.
        with VerticalScroll(id="help-dialog"):
            yield Static(_HELP)

    def on_mount(self) -> None:
        # Focus the scroller so arrow / page keys scroll immediately.
        self.query_one("#help-dialog").focus()

    def action_dismiss(self) -> None:
        self.dismiss(None)
