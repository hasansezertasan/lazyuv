"""LazyUvApp: composes the panels, loads the project, wires keybindings."""

from __future__ import annotations

import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header

from lazyuv import commands
from lazyuv.data import load_project
from lazyuv.models import Dependency, LoadStatus, Project, Script
from lazyuv.screens.add_dependency import AddDependencyScreen
from lazyuv.screens.confirm import ConfirmScreen
from lazyuv.screens.filter import FilterScreen
from lazyuv.screens.help import HelpScreen
from lazyuv.widgets.dependencies import DependenciesPanel
from lazyuv.widgets.details import DetailsPanel
from lazyuv.widgets.output import OutputPanel
from lazyuv.widgets.scripts import ScriptsPanel

STYLES = Path(__file__).parent / "styles.tcss"


class LazyUvApp(App[None]):
    CSS_PATH = STYLES
    TITLE = "lazyuv"

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("question_mark", "help", "help", key_display="?"),
        Binding("a", "add", "add"),
        Binding("d", "remove", "remove"),
        Binding("s", "sync", "sync"),
        Binding("l", "lock", "lock"),
        Binding("r", "run", "run"),
        Binding("slash", "filter", "filter", key_display="/"),
    ]

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root = root or Path.cwd()
        self.project: Project | None = None
        self._busy = False
        self._filter_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
            with Vertical(id="left"):
                yield DependenciesPanel()
                yield ScriptsPanel()
            with Vertical(id="right"):
                yield DetailsPanel()
                yield OutputPanel()
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_project()

    # --- loading -----------------------------------------------------------

    def refresh_project(self) -> None:
        result = load_project(self.root)
        details = self.query_one(DetailsPanel)
        if result.status is LoadStatus.NOT_A_PROJECT:
            self.project = None
            details.update("No pyproject.toml here.\nRun `uv init` to start a project.")
            return
        if result.status is LoadStatus.MALFORMED:
            self.project = None
            details.update(f"[red]pyproject.toml is malformed:[/red]\n{result.error}")
            return

        self.project = result.project
        self.sub_title = f"{self.project.name} {self.project.version}"
        self.query_one(DependenciesPanel).set_filter(
            self._filter_text, self.project.dependencies
        )
        self.query_one(ScriptsPanel).load(self.project.scripts)

    # --- selection wiring --------------------------------------------------

    def on_tree_node_highlighted(self, event) -> None:
        dep = self.query_one(DependenciesPanel).selected_dependency
        if dep is not None:
            self.query_one(DetailsPanel).show_dependency(dep)

    def on_list_view_highlighted(self, event) -> None:
        script = self.query_one(ScriptsPanel).selected_script
        if script is not None:
            self.query_one(DetailsPanel).show_script(script)

    # --- command execution -------------------------------------------------

    def _run_uv(self, argv: list[str]) -> None:
        if self._busy:
            self.bell()
            return
        self._busy = True
        output = self.query_one(OutputPanel)
        output.start(argv)
        self.run_worker(self._run_uv_worker(argv), exclusive=True)

    async def _run_uv_worker(self, argv: list[str]) -> None:
        output = self.query_one(OutputPanel)
        try:
            exit_code = await commands.run_streaming(
                argv, on_line=output.line, cwd=self.root
            )
            output.finish(exit_code)
        except Exception as exc:  # noqa: BLE001 - surface any launch/stream failure
            output.line(f"error: {exc}")
            output.finish(1)
        finally:
            self._busy = False
            self.refresh_project()

    # --- actions -----------------------------------------------------------

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_sync(self) -> None:
        self._run_uv(commands.build_sync())

    def action_lock(self) -> None:
        self._run_uv(commands.build_lock())

    def action_run(self) -> None:
        script = self.query_one(ScriptsPanel).selected_script
        if script is not None:
            self._run_uv(commands.build_run(script.name))

    def action_add(self) -> None:
        if self.project is None:
            return
        kinds = {d.group: d.kind for d in self.project.dependencies}
        groups = sorted(kinds)

        def on_close(result: tuple[list[str], str] | None) -> None:
            if result is not None:
                packages, group = result
                if group in ("main", "dev"):
                    kind = group
                else:
                    kind = kinds.get(group, "group")
                self._run_uv(commands.build_add(packages, group, kind))

        self.push_screen(AddDependencyScreen(groups), on_close)

    def action_remove(self) -> None:
        dep = self.query_one(DependenciesPanel).selected_dependency
        if dep is None:
            return

        def on_close(confirmed: bool) -> None:
            if confirmed:
                self._run_uv(commands.build_remove(dep.name, dep.group, dep.kind))

        self.push_screen(ConfirmScreen(f"Remove {dep.name}?"), on_close)

    def action_filter(self) -> None:
        if self.project is None:
            return

        def on_close(text: str | None) -> None:
            if text is None:
                return
            self._filter_text = text
            self.query_one(DependenciesPanel).set_filter(text, self.project.dependencies)

        self.push_screen(FilterScreen(self._filter_text), on_close)


def main() -> None:
    if not commands.uv_available():
        print("lazyuv: `uv` was not found on your PATH. Install uv first.", file=sys.stderr)
        raise SystemExit(1)
    LazyUvApp().run()
