"""LazyUvApp: composes the panels, loads the project, wires keybindings."""

from __future__ import annotations

import asyncio
import shlex
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, ListView, Tree

from lazyuv import commands
from lazyuv.data import (
    directory_size,
    find_scripts,
    format_size,
    load_project,
    load_script,
    parse_outdated,
    parse_python_list,
    parse_tool_list,
    parse_tree,
    parse_uv_version,
)
from lazyuv.models import InlineScript, LoadStatus, Project, Tool, WorkspaceMember
from lazyuv.screens.add_dependency import AddDependencyScreen
from lazyuv.screens.add_script_dependency import AddScriptDependencyScreen
from lazyuv.screens.confirm import ConfirmScreen
from lazyuv.screens.export import ExportScreen
from lazyuv.screens.filter import FilterScreen
from lazyuv.screens.help import HelpScreen
from lazyuv.screens.init import InitScreen
from lazyuv.screens.python import PythonPickerScreen
from lazyuv.screens.run_args import RunArgsScreen
from lazyuv.screens.script_picker import ScriptPickerScreen
from lazyuv.screens.tree import DependencyTreeScreen
from lazyuv.screens.sync_options import SyncOptionsScreen
from lazyuv.screens.tool_install import ToolInstallScreen
from lazyuv.screens.version import VersionScreen
from lazyuv.screens.workspace import WorkspaceSwitchScreen
from lazyuv.widgets.cache import CachePanel
from lazyuv.widgets.dependencies import DependenciesPanel
from lazyuv.widgets.details import DetailsPanel
from lazyuv.widgets.environment import EnvironmentPanel
from lazyuv.widgets.output import OutputPanel
from lazyuv.widgets.scripts import ScriptsPanel
from lazyuv.widgets.tools import ToolsPanel
from lazyuv.widgets.workspace import WorkspacePanel

STYLES = Path(__file__).parent / "styles.tcss"

# Bounds the network-dependent `uv tree` queries so a stalled connection can't leave
# the UI wedged (`_busy` stuck True, title stuck "checking…"). Generous enough not to
# false-trip a slow-but-working index lookup across many packages.
_TREE_QUERY_TIMEOUT = 60.0


class LazyUvApp(App[None]):
    CSS_PATH = STYLES
    TITLE = "lazyuv"

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("question_mark", "help", "help", key_display="?"),
        Binding("a", "add", "add"),
        Binding("d", "remove", "remove"),
        Binding("s", "sync", "sync"),
        Binding("S", "sync_options", "sync opts", key_display="S"),
        Binding("l", "lock", "lock"),
        Binding("r", "run", "run"),
        Binding("p", "python", "python"),
        Binding("v", "venv", "venv"),
        Binding("w", "workspace", "workspace"),
        Binding("e", "export", "export"),
        Binding("slash", "filter", "filter", key_display="/"),
        Binding("g", "toggle_mode", "global"),
        # inline-script mode: `o` opens/switches a script; escape leaves script mode
        Binding("o", "open_script", "script"),
        Binding("escape", "exit_script", "exit script"),
        # inspect & run-args (Milestone 6)
        Binding("t", "tree", "tree"),
        Binding("O", "outdated", "outdated", key_display="O"),
        Binding("R", "run_args", "run args", key_display="R"),
        Binding("V", "version", "version", key_display="V"),
        # bootstrap a project when the cwd isn't one yet
        Binding("n", "init", "init"),
        # `u` upgrades the selected thing in either mode (tool / package)
        Binding("u", "upgrade", "upgrade"),
        # global-mode actions (no-op in project mode)
        Binding("i", "tool_install", "install tool"),
        Binding("U", "tool_upgrade_all", "upgrade all", key_display="U"),
        Binding("x", "tool_uninstall", "uninstall"),
        Binding("c", "cache_clean", "cache clean"),
        Binding("P", "cache_prune", "prune", key_display="P"),
        Binding("z", "cache_size", "cache size"),
        Binding("X", "self_update", "uv update", key_display="X"),
    ]

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root = root or Path.cwd()
        self.project: Project | None = None
        self._busy = False
        self._filter_text = ""
        self.global_mode = False
        self.tools: list[Tool] = []
        self.cache_dir: str | None = None
        self.uv_version: str = ""
        # Workspace state: members come from the workspace root; focus scopes the
        # loaded project + command cwd to a member. None focus == the root.
        self.workspace_members: list[WorkspaceMember] = []
        self.workspace_root_name: str = ""
        self.focused_member: WorkspaceMember | None = None
        # Inline-script (PEP 723) mode: the focused `.py` file, relative to
        # active_dir. None means not in script mode.
        self.script_path: Path | None = None
        self.inline_script: InlineScript | None = None
        # Outdated overlay toggle (project mode): whether `O` annotations are showing.
        self._outdated_on = False
        # True only when the active dir has no pyproject.toml (LoadStatus.NOT_A_PROJECT)
        # — the sole state where `uv init` (the `n` action) can succeed.
        self._not_a_project = False

    @property
    def active_dir(self) -> Path:
        """The directory the project view is scoped to (root, or a focused member)."""
        if self.focused_member is not None:
            return self.root / self.focused_member.directory
        return self.root

    @property
    def _focused_package(self) -> str | None:
        """The focused workspace member's package name, or None (root / no workspace).

        `uv tree` is workspace-global and not cwd-scoped, so a focused non-root member
        must be targeted with `--package`.
        """
        if self.focused_member is not None and not self.focused_member.is_root:
            return self.focused_member.name
        return None

    @property
    def mode(self) -> str:
        """The active top-level mode: 'global', 'script', or 'project' (default).

        The three are mutually exclusive: entering global clears the script focus and
        vice versa, so at most one of `global_mode` / `script_path` is ever set.
        """
        if self.global_mode:
            return "global"
        if self.script_path is not None:
            return "script"
        return "project"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
            with Vertical(id="left"):
                with Vertical(id="project-panels"):
                    yield WorkspacePanel()
                    yield EnvironmentPanel()
                    yield DependenciesPanel()
                    yield ScriptsPanel()
                with Vertical(id="global-panels"):
                    yield ToolsPanel()
                    yield CachePanel()
            with Vertical(id="right"):
                yield DetailsPanel()
                yield OutputPanel()
        yield Footer()

    # Actions available only in one mode; used by check_action to make the footer
    # context-sensitive (inapplicable keys are hidden rather than shown as live).
    _GLOBAL_ACTIONS = frozenset({
        "tool_install", "tool_upgrade_all", "tool_uninstall",
        "cache_clean", "cache_prune", "cache_size", "self_update",
    })
    # Project-only: inert in both global and script mode.
    _PROJECT_ONLY_ACTIONS = frozenset({
        "sync", "sync_options", "lock", "python", "venv", "filter",
        "workspace", "export", "tree", "outdated", "version",
    })
    # Shared by project and script mode (dispatch branches on `self.mode`).
    _PROJECT_OR_SCRIPT_ACTIONS = frozenset({
        "add", "remove", "run", "run_args", "open_script",
    })
    _SCRIPT_ONLY_ACTIONS = frozenset({"exit_script"})

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        mode = self.mode
        if action in self._GLOBAL_ACTIONS:
            return True if mode == "global" else None
        if action in self._PROJECT_ONLY_ACTIONS:
            return True if mode == "project" else None
        if action in self._SCRIPT_ONLY_ACTIONS:
            return True if mode == "script" else None
        if action in self._PROJECT_OR_SCRIPT_ACTIONS:
            return True if mode in ("project", "script") else None
        # `upgrade` is a tool (global) or package (project) op — not a script op.
        if action == "upgrade":
            return True if mode in ("global", "project") else None
        # `init` only makes sense when there's no pyproject.toml at all; uv refuses
        # otherwise (incl. a MALFORMED pyproject, which also leaves project None).
        if action == "init":
            return True if (mode == "project" and self._not_a_project) else None
        return True

    def on_mount(self) -> None:
        self.query_one("#global-panels").display = False
        self.query_one(WorkspacePanel).display = False
        self.refresh_project()
        self.run_worker(self._load_uv_version())

    async def _load_uv_version(self) -> None:
        try:
            _code, out = await commands.run_capture(commands.build_uv_version())
        except Exception:  # noqa: BLE001 - version indicator is best-effort
            return
        self.uv_version = parse_uv_version(out)
        self._update_subtitle()

    # --- loading -----------------------------------------------------------

    def refresh_project(self) -> None:
        # Project mode owns the full sub-panel set; restore any that script mode hid.
        self.query_one(EnvironmentPanel).display = True
        self.query_one(ScriptsPanel).display = True
        # A workspace keeps one lockfile at the root; a focused member has none, so
        # read the lock from the workspace root to resolve the member's deps.
        result = load_project(self.active_dir, lock_root=self.root)
        # `init` is offered ONLY when there's genuinely no pyproject.toml — a MALFORMED
        # one also leaves project None but `uv init` would refuse it. Track the status
        # (not just project-is-None) and refresh the footer whenever it changes.
        self._not_a_project = result.status is LoadStatus.NOT_A_PROJECT
        self.refresh_bindings()
        details = self.query_one(DetailsPanel)
        if result.status is LoadStatus.NOT_A_PROJECT:
            self._clear_project_panels()
            details.update(
                "No pyproject.toml here.\n"
                "Press `n` to run `uv init` and start a project."
            )
            return
        if result.status is LoadStatus.MALFORMED:
            self._clear_project_panels()
            details.update(f"[red]pyproject.toml is malformed:[/red]\n{result.error}")
            return

        self.project = result.project
        # Workspace membership is a property of the ROOT project; only refresh it
        # when the root is loaded (a focused member's pyproject has no workspace).
        if self.focused_member is None or self.focused_member.is_root:
            self.workspace_members = self.project.workspace_members
            self.workspace_root_name = self.project.name
        self._update_workspace_panel()
        self._update_subtitle()
        panel = self.query_one(DependenciesPanel)
        previous = panel.selected_dependency
        panel.set_filter(self._filter_text, self.project.dependencies)
        if previous is not None:
            # Defer until the rebuilt tree is laid out; move_cursor needs the new
            # nodes to have real line numbers.
            self.call_after_refresh(
                panel.restore_selection, previous.group, previous.name
            )
        self.query_one(ScriptsPanel).load(self.project.scripts)
        self.query_one(EnvironmentPanel).show(self.project.environment)

    def refresh_script(self) -> None:
        """Re-read the focused inline script and show its deps in the deps panel.

        Script mode reuses #project-panels but shows only the Dependencies panel — a
        script has no venv, workspace, or [project.scripts]. A read failure surfaces
        on Output and drops back to project mode (never a stale/blank script view).
        """
        assert self.script_path is not None
        script = load_script(self.active_dir / self.script_path)
        if script is None:
            self.query_one(OutputPanel).line(f"cannot read {self.script_path}")
            self.action_exit_script()
            return
        self.inline_script = script
        self.query_one(WorkspacePanel).display = False
        self.query_one(EnvironmentPanel).display = False
        self.query_one(ScriptsPanel).display = False
        self._update_subtitle()
        panel = self.query_one(DependenciesPanel)
        previous = panel.selected_dependency
        panel.set_filter("", script.dependencies)
        if previous is not None:
            self.call_after_refresh(
                panel.restore_selection, previous.group, previous.name
            )

    def _update_workspace_panel(self) -> None:
        panel = self.query_one(WorkspacePanel)
        has_workspace = bool(self.workspace_members)
        panel.display = has_workspace
        if has_workspace:
            focused_dir = self.focused_member.directory if self.focused_member else ""
            panel.show(self.workspace_members, focused_dir)

    def _clear_project_panels(self) -> None:
        """Reset project-scoped views so a lost/invalid project shows no stale data."""
        self.project = None
        # Fully revert workspace focus: a failed load must not leave active_dir
        # pointing at a member dir that may have been deleted.
        self.focused_member = None
        self.workspace_members = []
        self.query_one(WorkspacePanel).display = False
        self._update_subtitle()
        self.query_one(DependenciesPanel).set_filter(self._filter_text, [])
        self.query_one(ScriptsPanel).load([])
        self.query_one(EnvironmentPanel).show(None)

    def _update_subtitle(self) -> None:
        parts: list[str] = []
        if self.global_mode:
            parts.append("global")
        elif self.script_path is not None:
            parts.append(f"script · {self.script_path}")
        elif self.project is not None:
            name = f"{self.project.name} {self.project.version}"
            # In a focused non-root member, prefix the workspace root: "root · member".
            if (
                self.focused_member is not None
                and not self.focused_member.is_root
                and self.workspace_root_name
            ):
                name = f"{self.workspace_root_name} · {name}"
            parts.append(name)
        if self.uv_version:
            parts.append(f"uv {self.uv_version}")
        self.sub_title = " · ".join(parts)

    async def _refresh_global(self) -> None:
        """Populate the Tools + Cache panels and uv version from `uv`.

        Caller must have set `_busy = True`; this resets it in `finally`. These are
        global (machine) queries, so no `cwd` is passed. Failures are surfaced on the
        Output panel (like the Python-list read), not silently swallowed.
        """
        output = self.query_one(OutputPanel)
        try:
            code, out = await commands.run_capture(commands.build_tool_list())
            if code != 0:
                output.line(f"`uv tool list` failed (exit {code})")
                self.tools = []
            else:
                self.tools = parse_tool_list(out)
            dir_code, dir_out = await commands.run_capture(commands.build_cache_dir())
            self.cache_dir = dir_out.strip() if dir_code == 0 and dir_out.strip() else None
            ver_code, ver_out = await commands.run_capture(commands.build_uv_version())
            if ver_code == 0:
                self.uv_version = parse_uv_version(ver_out)
        except Exception as exc:  # noqa: BLE001 - a query failure must not crash the app
            output.line(f"error: {exc}")
            self.tools = []
            self.cache_dir = None
        finally:
            self._busy = False
        self.query_one(ToolsPanel).load(self.tools)
        self.query_one(CachePanel).show(self.cache_dir, None)
        self._update_subtitle()

    # --- selection wiring --------------------------------------------------

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        # The tree-view modal is also a Tree whose events bubble here; only the main
        # dependency panel drives the Details view.
        panel = self.query_one(DependenciesPanel)
        if event.control is not panel:
            return
        dep = panel.selected_dependency
        if dep is not None:
            self.query_one(DetailsPanel).show_dependency(dep)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        # A modal's ListView (workspace-list, python-list) must not repaint Details
        # from the hidden Scripts panel; only the two real panels are handled here.
        if event.list_view.id not in ("tools", "scripts"):
            return
        # Both ScriptsPanel and ToolsPanel are ListViews; route by widget id.
        if event.list_view.id == "tools":
            tool = self.query_one(ToolsPanel).selected_tool
            if tool is not None:
                self.query_one(DetailsPanel).show_tool(tool)
        else:
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
            # Project mutations run in the focused member's dir; global (tool/cache)
            # mutations must run at the root, never a member cwd.
            exit_code = await commands.run_streaming(
                argv,
                on_line=output.line,
                cwd=self.root if self.global_mode else self.active_dir,
            )
            output.finish(exit_code)
        except Exception as exc:  # noqa: BLE001 - surface any launch/stream failure
            output.line(f"error: {exc}")
            output.finish(1)
        finally:
            # Re-read whichever view is showing so it reflects the mutation.
            # In global mode we keep `_busy` True and hand off directly to
            # `_refresh_global`, which clears it in its own `finally` once the
            # re-read completes — never leaving a window where `_busy` is False
            # mid-transition (which would let a second mutation start concurrently).
            if self.global_mode:
                self.run_worker(self._refresh_global())
            elif self.script_path is not None:
                self._busy = False
                self.refresh_script()
            else:
                self._busy = False
                self.refresh_project()

    # --- actions -----------------------------------------------------------

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_sync(self) -> None:
        if self.global_mode:
            return
        if self.project is None:
            return
        self._run_uv(commands.build_sync())

    def action_lock(self) -> None:
        if self.global_mode:
            return
        if self.project is None:
            return
        self._run_uv(commands.build_lock())

    def action_run(self) -> None:
        # Script mode runs the focused inline script; project mode runs the selected
        # [project.scripts] entry.
        if self.mode == "script":
            self._run_uv(commands.build_run_script(str(self.script_path)))
            return
        if self.global_mode:
            return
        script = self.query_one(ScriptsPanel).selected_script
        if script is not None:
            self._run_uv(commands.build_run(script.name))

    def action_add(self) -> None:
        if self.mode == "script":
            def on_close_script(packages: list[str] | None) -> None:
                if packages:
                    self._run_uv(
                        commands.build_add_script(str(self.script_path), packages)
                    )

            self.push_screen(AddScriptDependencyScreen(), on_close_script)
            return
        if self.global_mode or self.project is None:
            return

        def on_close(result: tuple[list[str], str, str] | None) -> None:
            if result is not None:
                packages, group, kind = result
                self._run_uv(commands.build_add(packages, group, kind))

        self.push_screen(AddDependencyScreen(self.project.groups), on_close)

    def action_remove(self) -> None:
        if self.global_mode:
            return
        dep = self.query_one(DependenciesPanel).selected_dependency
        if dep is None:
            return

        # In script mode, remove targets the script's inline block, not a project.
        script_mode = self.mode == "script"

        def on_close(confirmed: bool) -> None:
            if not confirmed:
                return
            if script_mode:
                self._run_uv(
                    commands.build_remove_script(str(self.script_path), dep.name)
                )
            else:
                self._run_uv(commands.build_remove(dep.name, dep.group, dep.kind))

        self.push_screen(ConfirmScreen(f"Remove {dep.name}?"), on_close)

    def action_sync_options(self) -> None:
        if self.global_mode or self.project is None:
            return
        if self._busy:
            self.bell()
            return

        def on_close(result: tuple[list[str], list[str], bool, bool] | None) -> None:
            if result is None:
                return
            extras, groups, no_dev, frozen = result
            self._run_uv(
                commands.build_sync(
                    extras=extras, groups=groups, no_dev=no_dev, frozen=frozen
                )
            )

        self.push_screen(SyncOptionsScreen(self.project.groups), on_close)

    def action_python(self) -> None:
        """Read `uv python list` (a query, not an action), then open the picker."""
        if self.global_mode:
            return
        if self._busy:
            self.bell()
            return
        # Mark busy for the whole picker lifecycle: this both serializes against
        # mutations (so a concurrent `uv sync` can't cancel this worker or silently
        # swallow the picked action) and prevents a second `p` from stacking modals.
        self._busy = True
        self.run_worker(self._open_python_picker())

    async def _open_python_picker(self) -> None:
        output = self.query_one(OutputPanel)
        try:
            exit_code, out = await commands.run_capture(
                commands.build_python_list(), cwd=self.root
            )
        except Exception as exc:  # noqa: BLE001 - a query failure must not crash the app
            output.line(f"error: {exc}")
            output.finish(1)
            self._busy = False
            return
        if exit_code != 0:
            output.line(f"`uv python list` failed (exit {exit_code})")
            output.finish(exit_code)
            self._busy = False
            return

        versions = parse_python_list(out)

        def on_close(result: tuple[str, str] | None) -> None:
            self._busy = False  # release before dispatching so _run_uv can run
            if result is None:
                return
            action, request = result
            builders = {
                "install": commands.build_python_install,
                "pin": commands.build_python_pin,
                "uninstall": commands.build_python_uninstall,
            }
            builder = builders.get(action)
            if builder is not None:
                self._run_uv(builder(request))

        self.push_screen(PythonPickerScreen(versions), on_close)

    def action_venv(self) -> None:
        if self.global_mode or self.project is None:
            return
        # The venv is shared at the workspace root; running `uv venv` in a focused
        # member would plant a disconnected member/.venv.
        if self.focused_member is not None and not self.focused_member.is_root:
            self.bell()
            return
        if self._busy:
            self.bell()
            return
        env = self.project.environment
        pin = env.pinned_python if env else None
        exists = env is not None and env.venv_path is not None

        def recreate(confirmed: bool) -> None:
            if confirmed:
                # `--clear` when a venv exists: uv refuses to recreate over it otherwise.
                self._run_uv(commands.build_venv(pin, clear=exists))

        if exists:
            self.push_screen(
                ConfirmScreen("Recreate .venv? The existing venv is replaced."),
                recreate,
            )
        else:
            recreate(True)

    def action_filter(self) -> None:
        if self.global_mode or self.project is None:
            return

        def on_close(text: str | None) -> None:
            if text is None:
                return
            self._filter_text = text
            self.query_one(DependenciesPanel).set_filter(text, self.project.dependencies)

        self.push_screen(FilterScreen(self._filter_text), on_close)

    def action_workspace(self) -> None:
        if self.global_mode or not self.workspace_members:
            return
        # Switching members mid-command would make the in-flight worker (which reads
        # cwd=self.active_dir lazily) run in the wrong dir.
        if self._busy:
            self.bell()
            return

        def on_close(directory: str | None) -> None:
            if directory is None:
                return
            member = next(
                (m for m in self.workspace_members if m.directory == directory), None
            )
            if member is None:
                return
            self.focused_member = None if member.is_root else member
            self._filter_text = ""
            # The outdated overlay was computed for the previous member; clear it so
            # its annotations/count don't bleed onto the newly-focused member's deps.
            self._clear_outdated()
            self.refresh_project()

        focused_dir = self.focused_member.directory if self.focused_member else ""
        self.push_screen(
            WorkspaceSwitchScreen(self.workspace_members, focused_dir), on_close
        )

    def action_export(self) -> None:
        if self.global_mode or self.project is None:
            return
        if self._busy:
            self.bell()
            return

        def on_close(
            result: tuple[str, str, bool, bool, list[str], list[str]] | None,
        ) -> None:
            if result is None:
                return
            fmt, output_file, no_hashes, no_dev, extras, groups = result
            self._run_uv(
                commands.build_export(
                    fmt=fmt,
                    no_hashes=no_hashes,
                    no_dev=no_dev,
                    extras=extras,
                    groups=groups,
                    output_file=output_file,
                )
            )

        self.push_screen(ExportScreen(self.project.groups), on_close)

    # --- inspect (tree / outdated) & run-with-args (Milestone 6) -----------

    def action_tree(self) -> None:
        """Show the transitive dependency graph (read-only, `uv tree`)."""
        if self.mode != "project" or self.project is None:
            return
        if self._busy:
            self.bell()
            return
        self._busy = True
        self.run_worker(self._open_tree())

    async def _open_tree(self) -> None:
        output = self.query_one(OutputPanel)
        try:
            code, out = await commands.run_capture(
                commands.build_tree(package=self._focused_package),
                cwd=self.active_dir,
                timeout=_TREE_QUERY_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - a query failure must not crash the app
            output.line(f"error: {exc}")
            self._busy = False
            return
        self._busy = False
        if code != 0:
            output.line(f"`uv tree` failed (exit {code})")
            return
        forest = parse_tree(out)
        if forest is None:
            # exit 0 but unreadable output (e.g. the experimental JSON schema changed)
            # — surface it rather than opening a misleading empty tree.
            output.line("could not parse `uv tree` output (unrecognized format)")
            return
        self.push_screen(DependencyTreeScreen(forest))

    def action_outdated(self) -> None:
        """Toggle the outdated overlay: annotate deps with a newer release available."""
        if self.mode != "project" or self.project is None:
            return
        if self._busy:
            self.bell()
            return
        if self._outdated_on:
            self._clear_outdated()
            return
        self._busy = True
        self.query_one(DependenciesPanel).border_title = "Dependencies — checking…"
        self.run_worker(self._load_outdated())

    async def _load_outdated(self) -> None:
        output = self.query_one(OutputPanel)
        try:
            code, out = await commands.run_capture(
                commands.build_tree(outdated=True, package=self._focused_package),
                cwd=self.active_dir,
                timeout=_TREE_QUERY_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - a query failure must not crash the app
            output.line(f"error: {exc}")
            self._busy = False
            self._clear_outdated()  # restore the plain title
            return
        self._busy = False
        if code != 0:
            output.line(f"`uv tree --outdated` failed (exit {code})")
            self._clear_outdated()
            return
        mapping = parse_outdated(out)
        if mapping is None:
            # exit 0 but unreadable output — don't report a reassuring "0 outdated".
            output.line("could not read `uv tree --outdated` output (unrecognized format)")
            self._clear_outdated()
            return
        self._outdated_on = True
        self.query_one(DependenciesPanel).set_outdated(mapping)
        output.line(f"outdated: {len(mapping)} package(s) with a newer release")

    def _clear_outdated(self) -> None:
        self._outdated_on = False
        self.query_one(DependenciesPanel).clear_outdated()

    def action_run_args(self) -> None:
        """Run the selected/focused script with user-supplied arguments."""
        script_mode = self.mode == "script"
        if script_mode:
            target = str(self.script_path)
        elif self.mode == "project":
            script = self.query_one(ScriptsPanel).selected_script
            if script is None:
                return
            target = script.name
        else:
            return
        if self._busy:
            self.bell()
            return

        def on_close(text: str | None) -> None:
            if text is None:
                return
            try:
                args = shlex.split(text)
            except ValueError as exc:
                self.query_one(OutputPanel).line(f"invalid arguments: {exc}")
                return
            if script_mode:
                self._run_uv(commands.build_run_script(target, args))
            else:
                self._run_uv(commands.build_run(target, args))

        self.push_screen(RunArgsScreen(target), on_close)

    def action_init(self) -> None:
        """Bootstrap a project with `uv init` when the cwd isn't one yet."""
        if self.mode != "project" or not self._not_a_project:
            return
        if self._busy:
            self.bell()
            return

        def on_close(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            kind, name = result
            self._run_uv(commands.build_init(kind, name))

        self.push_screen(InitScreen(self.active_dir.name), on_close)

    def action_version(self) -> None:
        """Bump or set the project version (`uv version`)."""
        if self.mode != "project" or self.project is None:
            return
        if self._busy:
            self.bell()
            return

        def on_close(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            kind, value = result
            if kind == "set":
                self._run_uv(commands.build_version_set(value))
            else:
                self._run_uv(commands.build_version_bump(value))

        self.push_screen(
            VersionScreen(self.project.name, self.project.version), on_close
        )

    # --- inline-script mode (PEP 723) --------------------------------------

    def action_open_script(self) -> None:
        """Open the script picker to enter or switch the focused inline script.

        The file scan runs off the event loop (a large tree could otherwise freeze
        the UI). `_busy` is held for the whole picker lifecycle — like the Python
        picker — so the scan can't race a mutation and a second `o` can't stack modals.
        """
        if self.global_mode:
            return
        if self._busy:
            self.bell()
            return
        self._busy = True
        self.run_worker(self._open_script_picker())

    async def _open_script_picker(self) -> None:
        scripts, truncated = await asyncio.to_thread(find_scripts, self.active_dir)
        focused = str(self.script_path) if self.script_path is not None else None

        def on_close(path: str | None) -> None:
            self._busy = False  # release before dispatching so refresh can run
            if path is None:
                return
            self.script_path = Path(path)
            self._clear_outdated()  # project overlay must not bleed into script deps
            self.set_focus(self.query_one(DependenciesPanel))
            self.refresh_script()
            self.refresh_bindings()  # footer shows script-mode keys

        self.push_screen(ScriptPickerScreen(scripts, focused, truncated), on_close)

    def action_exit_script(self) -> None:
        """Leave script mode, restoring the project view."""
        if self.mode != "script":
            return
        if self._busy:
            self.bell()
            return
        self.script_path = None
        self.inline_script = None
        self.set_focus(self.query_one(DependenciesPanel))
        self.refresh_project()
        self.refresh_bindings()  # footer returns to project-mode keys

    # --- global mode (tools / cache / self) --------------------------------

    def action_toggle_mode(self) -> None:
        if self._busy:
            self.bell()
            return
        # Global and script mode are mutually exclusive: entering/leaving global
        # always clears any script focus so the two never overlap.
        self.script_path = None
        self.inline_script = None
        self._clear_outdated()  # the outdated overlay is a project-mode concept
        self.global_mode = not self.global_mode
        self.query_one("#project-panels").display = not self.global_mode
        self.query_one("#global-panels").display = self.global_mode
        self._update_subtitle()
        self.refresh_bindings()  # footer shows only the active mode's keys
        # Move focus into the newly-visible column; otherwise focus stays on a
        # now-hidden widget and arrow keys reach nothing until the user Tabs/clicks.
        if self.global_mode:
            self.set_focus(self.query_one(ToolsPanel))
            self._busy = True
            self.run_worker(self._refresh_global())
        else:
            self.set_focus(self.query_one(DependenciesPanel))
            self.refresh_project()

    def action_tool_install(self) -> None:
        if not self.global_mode:
            return
        if self._busy:
            self.bell()
            return

        def on_close(package: str | None) -> None:
            if package:
                self._run_uv(commands.build_tool_install(package))

        self.push_screen(ToolInstallScreen(), on_close)

    def action_upgrade(self) -> None:
        """Upgrade the selected thing: a tool (global mode) or a package (project)."""
        if self.global_mode:
            tool = self.query_one(ToolsPanel).selected_tool
            if tool is not None:
                self._run_uv(commands.build_tool_upgrade(tool.name))
        else:
            dep = self.query_one(DependenciesPanel).selected_dependency
            if dep is not None:
                self._run_uv(commands.build_lock_upgrade_package(dep.name))

    def action_tool_upgrade_all(self) -> None:
        if not self.global_mode:
            return
        self._run_uv(commands.build_tool_upgrade_all())

    def action_tool_uninstall(self) -> None:
        if not self.global_mode:
            return
        tool = self.query_one(ToolsPanel).selected_tool
        if tool is None:
            return

        def on_close(confirmed: bool) -> None:
            if confirmed:
                self._run_uv(commands.build_tool_uninstall(tool.name))

        self.push_screen(ConfirmScreen(f"Uninstall {tool.name}?"), on_close)

    def action_cache_clean(self) -> None:
        if not self.global_mode:
            return

        def on_close(confirmed: bool) -> None:
            if confirmed:
                self._run_uv(commands.build_cache_clean())

        self.push_screen(ConfirmScreen("Clean the entire uv cache?"), on_close)

    def action_cache_prune(self) -> None:
        if not self.global_mode:
            return
        self._run_uv(commands.build_cache_prune())

    def action_cache_size(self) -> None:
        if not self.global_mode or self.cache_dir is None:
            return
        if self._busy:
            self.bell()  # a mutation/read is in flight — don't race a walk against it
            return
        self._busy = True
        self.query_one(CachePanel).show(self.cache_dir, "calculating…")
        self.run_worker(self._compute_cache_size())

    async def _compute_cache_size(self) -> None:
        cache_dir = self.cache_dir
        try:
            if cache_dir is None:
                return
            size = await asyncio.to_thread(directory_size, Path(cache_dir))
            self.query_one(CachePanel).show(cache_dir, format_size(size))
        finally:
            self._busy = False

    def action_self_update(self) -> None:
        if not self.global_mode:
            return

        def on_close(confirmed: bool) -> None:
            if confirmed:
                self._run_uv(commands.build_self_update())

        self.push_screen(ConfirmScreen("Run `uv self update`?"), on_close)


def main() -> None:
    if not commands.uv_available():
        print("lazyuv: `uv` was not found on your PATH. Install uv first.", file=sys.stderr)
        raise SystemExit(1)
    LazyUvApp().run()
