"""Dedicated full-screen help page listing keybindings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

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
  V                bump / set the project version (uv version)
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

Press ? , q , or Escape to close."""


class HelpScreen(Screen[None]):
    """A full-screen help page (not a cramped dialog) — the keybinding list gets the
    whole viewport, scrolls when taller than the terminal, and closes on ?/q/Esc."""

    BINDINGS = [
        Binding("escape", "dismiss", "close"),
        Binding("question_mark", "dismiss", "close", key_display="?"),
        Binding("q", "dismiss", "close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-body"):
            yield Static(_HELP)
        yield Footer()

    def on_mount(self) -> None:
        # Focus the scroller so arrow / page keys scroll the page immediately.
        self.query_one("#help-body").focus()

    def action_dismiss(self) -> None:
        self.dismiss(None)
