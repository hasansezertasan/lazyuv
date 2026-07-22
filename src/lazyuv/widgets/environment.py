"""Environment panel: the project's Python/venv state, with drift surfaced."""

from __future__ import annotations

from textual.widgets import Static

from lazyuv.models import Environment


class EnvironmentPanel(Static):
    BORDER_TITLE = "Environment"

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
        python = env.venv_python or "(no venv)"
        lines = [
            f"[b]Python[/b]  {python}",
            f"venv:   {env.venv_path or '—'}",
            f"pin:    {env.pinned_python or '—'}",
        ]
        if env.drift:
            lines.append(f"[red]drift:  {env.drift}[/red]")
        self.update("\n".join(lines))
