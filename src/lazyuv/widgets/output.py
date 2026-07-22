"""Output panel: live stream of the running/last uv command."""

from __future__ import annotations

from textual.widgets import RichLog


class OutputPanel(RichLog):
    BORDER_TITLE = "Output"

    def __init__(self) -> None:
        super().__init__(id="output", wrap=True, markup=False, highlight=False)

    def start(self, argv: list[str]) -> None:
        self.write(f"$ {' '.join(argv)}")

    def line(self, text: str) -> None:
        self.write(text)

    def finish(self, exit_code: int) -> None:
        self.write("✓ done" if exit_code == 0 else f"✗ exited with {exit_code}")
