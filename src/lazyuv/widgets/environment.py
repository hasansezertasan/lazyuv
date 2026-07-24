"""Environment panel: the project's Python/venv state, with drift surfaced."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from textual.widgets import Static

if TYPE_CHECKING:
    from lazyuv.models import Environment


class EnvironmentPanel(Static):
    BORDER_TITLE = "Environment"

    def __init__(self) -> None:
        # Explicit id so styles.tcss's #environment rule (min-height) applies, as
        # every other panel does (DependenciesPanel, ScriptsPanel, OutputPanel).
        super().__init__(id="environment")

    def show(self, env: Environment | None) -> None:
        """Render the project's Python/venv state, or a hint when there is none."""
        if env is None or (
            env.venv_python is None
            and env.venv_path is None
            and env.pinned_python is None
        ):
            self.update(
                "No venv or pin.\nPress v to create a venv, p to manage Python."
            )
            return
        # Values come from disk (paths, versions) — escape so a stray "[" can't be
        # reinterpreted as Rich markup.
        python = escape(env.venv_python) if env.venv_python else "(no venv)"
        lines = [
            f"[b]Python[/b]  {python}",
            f"venv:   {escape(env.venv_path) if env.venv_path else '—'}",
            f"pin:    {escape(env.pinned_python) if env.pinned_python else '—'}",
        ]
        if env.drift:
            lines.append(f"[red]drift:  {escape(env.drift)}[/red]")
        self.update("\n".join(lines))
