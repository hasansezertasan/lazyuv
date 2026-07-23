import json
from pathlib import Path

import pytest

from lazyuv.app import LazyUvApp
from lazyuv.screens.python import PythonPickerScreen
from lazyuv.widgets.dependencies import DependenciesPanel

FIXTURE = Path(__file__).parent / "fixtures" / "project"


@pytest.mark.asyncio
async def test_app_loads_project_and_shows_deps():
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.project is not None
        # subtitle may gain a " · uv <version>" suffix from the version worker
        assert app.sub_title.startswith("sample 0.2.0")
        tree = app.query_one(DependenciesPanel)
        # root has one child branch per group: main, cli, dev
        labels = {str(node.label) for node in tree.root.children}
        assert any("main" in label for label in labels)
        assert any("cli" in label for label in labels)
        assert any("dev" in label for label in labels)


@pytest.mark.asyncio
async def test_sync_key_runs_mocked_uv(monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        on_line("Resolved 4 packages")
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "sync"]


@pytest.mark.asyncio
async def test_not_a_project_shows_hint(tmp_path):
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.project is None


@pytest.mark.asyncio
async def test_lock_key_runs_mocked_uv(monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("l")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "lock"]


@pytest.mark.asyncio
async def test_malformed_pyproject_no_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("this is = = not toml")
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.project is None


@pytest.mark.asyncio
async def test_add_flow_runs_mocked_uv(monkeypatch):
    from textual.widgets import Input

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")  # open AddDependencyScreen (a separate screen)
        await pilot.pause()
        # The modal is pushed on top, so query its screen, not the default one.
        app.screen.query_one("#packages", Input).value = "cowsay"
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "add", "cowsay"]


@pytest.mark.asyncio
async def test_add_to_optional_extra_routes_optional(monkeypatch):
    from textual.widgets import Input, Select

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        screen = app.screen
        # 'cli' is an optional-dependency extra in the fixture -> must use --optional
        index = next(i for i, (n, _k) in enumerate(screen._options) if n == "cli")
        screen.query_one("#group", Select).value = index
        screen.query_one("#packages", Input).value = "httpx"
        await pilot.pause()
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "add", "--optional", "cli", "httpx"]


@pytest.mark.asyncio
async def test_filter_updates_border_title():
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        assert panel.border_title == "Dependencies"
        panel.set_filter("typ", app.project.dependencies)
        assert "typ" in panel.border_title


@pytest.mark.asyncio
async def test_selection_preserved_across_refresh():
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        leaf = next(
            node
            for group_node in panel.root.children
            for node in group_node.children
            if node.data is not None and node.data.name == "pytest"
        )
        panel.move_cursor(leaf)
        await pilot.pause()
        app.refresh_project()
        await pilot.pause()
        await pilot.pause()
        selected = app.query_one(DependenciesPanel).selected_dependency
        assert selected is not None and selected.name == "pytest"


@pytest.mark.asyncio
async def test_forked_dependency_shows_all_versions(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["httpx"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        "version = 1\n"
        'requires-python = ">=3.14"\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.27.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.28.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
    )
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one(DependenciesPanel)
        labels = [
            str(node.label)
            for group_node in tree.root.children
            for node in group_node.children
        ]
        assert any("0.27.0 / 0.28.1" in lb and "2 versions" in lb for lb in labels)


def test_add_dialog_keeps_reserved_name_extras():
    from lazyuv.screens.add_dependency import AddDependencyScreen

    screen = AddDependencyScreen([("dev", "extra"), ("docs", "group")])
    # The dev/main defaults stay, AND an optional extra named "dev" is selectable.
    assert ("dev", "dev") in screen._options
    assert ("dev", "extra") in screen._options
    assert ("docs", "group") in screen._options
    # No duplicate default pairs.
    assert screen._options.count(("main", "main")) == 1


@pytest.mark.asyncio
async def test_error_state_clears_stale_panels(tmp_path):
    from lazyuv.widgets.scripts import ScriptsPanel

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.project is not None
        assert len(app.query_one(DependenciesPanel).root.children) > 0
        # Project disappears (e.g. pyproject deleted) — panels must not go stale.
        app.root = tmp_path
        app.refresh_project()
        await pilot.pause()
        assert app.project is None
        # project name no longer in the subtitle (a " · uv <version>" suffix may remain)
        assert "sample" not in app.sub_title
        assert len(app.query_one(DependenciesPanel).root.children) == 0
        assert len(app.query_one(ScriptsPanel).children) == 0


# --- Milestone 2: environments & Python versions ---------------------------


def _write_project(root: Path, requires_python: str = ">=3.14") -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        f'requires-python = "{requires_python}"\n'
        "dependencies = []\n\n"
        "[project.optional-dependencies]\n"
        'cli = ["typer"]\n\n'
        "[dependency-groups]\n"
        'docs = ["mkdocs"]\n'
    )


def _write_venv(root: Path, version: str) -> None:
    venv = root / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text(f"home = /x\nversion_info = {version}\n")


@pytest.mark.asyncio
async def test_environment_panel_shows_drift(tmp_path):
    from lazyuv.widgets.environment import EnvironmentPanel

    _write_project(tmp_path)
    (tmp_path / ".python-version").write_text("3.14\n")
    _write_venv(tmp_path, "3.12.0")  # venv 3.12 != pin 3.14 -> drift

    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(EnvironmentPanel)
        rendered = str(panel.render())
        assert "3.12.0" in rendered
        assert "drift" in rendered
        assert "3.14" in rendered


@pytest.mark.asyncio
async def test_sync_options_frozen_builds_argv(monkeypatch):
    from textual.widgets import Checkbox

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("S")
        await pilot.pause()
        app.screen.query_one("#frozen", Checkbox).value = True
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "sync", "--frozen"]


_PYTHON_LIST_JSON = json.dumps(
    [
        {
            "key": "cpython-3.14.6-macos-aarch64-none",
            "version": "3.14.6",
            "implementation": "cpython",
            "path": "/home/x/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14",
        },
        {
            "key": "cpython-3.12.5-macos-aarch64-none",
            "version": "3.12.5",
            "implementation": "cpython",
            "path": None,
        },
        {
            "key": "cpython-3.11.14-macos-aarch64-none",
            "version": "3.11.14",
            "implementation": "cpython",
            "path": "/opt/homebrew/bin/python3.11",
        },
    ]
)


def _fake_capture(_output):
    async def fake_run_capture(argv, cwd=None, timeout=None):
        return 0, _output

    return fake_run_capture


@pytest.mark.asyncio
async def test_python_picker_install_uses_key(monkeypatch):
    from textual.widgets import ListView

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_capture", _fake_capture(_PYTHON_LIST_JSON))
    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # second row is the available (not-installed) 3.12.5 -> install by its key
        app.screen.query_one("#python-list", ListView).index = 1
        await pilot.pause()
        await pilot.click("#install")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == [
            "uv", "python", "install", "cpython-3.12.5-macos-aarch64-none",
        ]


@pytest.mark.asyncio
async def test_python_picker_uninstall_gated_to_managed(monkeypatch):
    """Uninstall on a non-managed (system) interpreter must not dispatch a command."""
    from textual.widgets import ListView

    captured = {"called": False}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["called"] = True
        return 0

    monkeypatch.setattr("lazyuv.commands.run_capture", _fake_capture(_PYTHON_LIST_JSON))
    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # third row is the homebrew (system, non-managed) interpreter
        app.screen.query_one("#python-list", ListView).index = 2
        await pilot.pause()
        await pilot.click("#uninstall")
        await pilot.pause()
        # bell + modal stays open; no uv command dispatched
        assert captured["called"] is False
        assert isinstance(app.screen, PythonPickerScreen)


@pytest.mark.asyncio
async def test_python_picker_empty_list_cancels_cleanly(monkeypatch):
    monkeypatch.setattr("lazyuv.commands.run_capture", _fake_capture("[]"))
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, PythonPickerScreen)
        await pilot.click("#install")  # nothing selected -> dismiss(None)
        await pilot.pause()
        assert not isinstance(app.screen, PythonPickerScreen)
        assert app._busy is False  # busy released even on empty/cancel


@pytest.mark.asyncio
async def test_python_picker_list_failure_no_crash(monkeypatch):
    """A nonzero `uv python list` must not open a picker or crash the app."""

    async def fake_run_capture(argv, cwd=None, timeout=None):
        return 1, ""

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not isinstance(app.screen, PythonPickerScreen)
        assert app._busy is False  # not wedged busy


@pytest.mark.asyncio
async def test_python_picker_capture_exception_no_crash(monkeypatch):
    """An exception from run_capture (e.g. uv missing) is contained, not fatal."""

    async def boom(argv, cwd=None):
        raise OSError("uv not found")

    monkeypatch.setattr("lazyuv.commands.run_capture", boom)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.project is not None  # app still alive
        assert app._busy is False


@pytest.mark.asyncio
async def test_recreate_existing_venv_uses_clear(monkeypatch, tmp_path):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_project(tmp_path)
    (tmp_path / ".python-version").write_text("3.14\n")
    _write_venv(tmp_path, "3.14")

    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        await pilot.click("#yes")  # confirm recreate
        await app.workers.wait_for_complete()
        await pilot.pause()
        # existing venv -> must pass --clear (uv errors otherwise)
        assert captured["argv"] == ["uv", "venv", "--clear", "--python", "3.14"]


@pytest.mark.asyncio
async def test_create_venv_when_absent_no_confirm_no_clear(monkeypatch, tmp_path):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_project(tmp_path)  # no .venv, no pin

    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")  # no venv -> creates directly, no confirm screen
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "venv"]


@pytest.mark.asyncio
async def test_sync_options_selects_extra(monkeypatch):
    from textual.widgets import SelectionList

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    # fixture has extra "cli" and dev group (dev is excluded from the group list)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("S")
        await pilot.pause()
        app.screen.query_one("#extras", SelectionList).select_all()
        await pilot.pause()
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "sync", "--extra", "cli"]


@pytest.mark.asyncio
async def test_environment_panel_empty_state(tmp_path):
    from lazyuv.widgets.environment import EnvironmentPanel

    _write_project(tmp_path)  # no .venv, no .python-version

    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        rendered = str(app.query_one(EnvironmentPanel).render())
        assert "No venv or pin" in rendered


def test_help_overlay_lists_new_bindings():
    from lazyuv.screens.help import _HELP

    assert "p" in _HELP and "python" in _HELP.lower()
    assert "S" in _HELP
    assert "v" in _HELP and "venv" in _HELP.lower()


# --- Milestone 3: global tools & cache -------------------------------------

_TOOL_LIST = "ruff v0.11.31\n- ruff\nhatch v1.16.5\n- hatch\n- hatchling\n"


def _global_capture(cache_dir="/home/x/.cache/uv", tool_list=_TOOL_LIST):
    async def fake_run_capture(argv, cwd=None, timeout=None):
        if argv[:3] == ["uv", "tool", "list"]:
            return 0, tool_list
        if argv[:3] == ["uv", "cache", "dir"]:
            return 0, cache_dir + "\n"
        if argv == ["uv", "--version"]:
            return 0, "uv 0.11.31 (Homebrew)"
        return 0, ""

    return fake_run_capture


def _capture_streaming(captured):
    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    return fake_run_streaming


@pytest.mark.asyncio
async def test_toggle_to_global_loads_tools(monkeypatch):
    from lazyuv.widgets.tools import ToolsPanel

    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.global_mode is True
        assert app.query_one("#global-panels").display is True
        assert app.query_one("#project-panels").display is False
        assert [t.name for t in app.tools] == ["ruff", "hatch"]
        assert isinstance(app.query_one(ToolsPanel), ToolsPanel)
        # toggling back restores project mode
        await pilot.press("g")
        await pilot.pause()
        assert app.global_mode is False
        assert app.query_one("#project-panels").display is True


@pytest.mark.asyncio
async def test_tool_install_flow(monkeypatch):
    from textual.widgets import Input

    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        app.screen.query_one("#tool-package", Input).value = "cowsay"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "tool", "install", "cowsay"]


@pytest.mark.asyncio
async def test_tool_upgrade_all_flow(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("U")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "tool", "upgrade", "--all"]


@pytest.mark.asyncio
async def test_tool_uninstall_confirm_flow(monkeypatch):
    from lazyuv.widgets.tools import ToolsPanel

    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.query_one(ToolsPanel).index = 0  # "ruff"
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "tool", "uninstall", "ruff"]


@pytest.mark.asyncio
async def test_cache_prune_flow(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("P")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "cache", "prune"]


@pytest.mark.asyncio
async def test_cache_clean_confirm_flow(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "cache", "clean"]


@pytest.mark.asyncio
async def test_cache_size_computed_on_demand(monkeypatch, tmp_path):
    from lazyuv.widgets.cache import CachePanel

    (tmp_path / "blob").write_bytes(b"x" * 2048)
    monkeypatch.setattr(
        "lazyuv.commands.run_capture", _global_capture(cache_dir=str(tmp_path))
    )

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("z")
        await app.workers.wait_for_complete()
        await pilot.pause()
        rendered = str(app.query_one(CachePanel).render())
        assert "KiB" in rendered  # 2048 bytes -> 2.0 KiB


@pytest.mark.asyncio
async def test_self_update_confirm_flow(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("X")
        await pilot.pause()
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "self", "update"]


@pytest.mark.asyncio
async def test_global_keys_noop_in_project_mode(monkeypatch):
    from lazyuv.screens.tool_install import ToolInstallScreen

    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        # 'i' (install tool) must do nothing in project mode
        await pilot.press("i")
        await pilot.pause()
        assert not isinstance(app.screen, ToolInstallScreen)
        # 'U' (upgrade all) must not dispatch a command in project mode
        await pilot.press("U")
        await pilot.pause()
        assert "argv" not in captured


@pytest.mark.asyncio
async def test_project_keys_noop_in_global_mode(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # 's' (sync) is a project action -> no-op in global mode
        await pilot.press("s")
        await pilot.pause()
        assert "argv" not in captured


# --- M3 review fixes -------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_focuses_tools_then_dependencies(monkeypatch):
    from lazyuv.widgets.tools import ToolsPanel

    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # focus must move into the visible global column, not stay on a hidden panel
        assert isinstance(app.focused, ToolsPanel)
        await pilot.press("g")
        await pilot.pause()
        assert isinstance(app.focused, DependenciesPanel)


@pytest.mark.asyncio
async def test_tool_upgrade_single_flow(monkeypatch):
    from lazyuv.widgets.tools import ToolsPanel

    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.query_one(ToolsPanel).index = 1  # "hatch"
        await pilot.pause()
        await pilot.press("u")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "tool", "upgrade", "hatch"]


@pytest.mark.asyncio
async def test_cache_size_busy_guard_blocks_second_scan(monkeypatch, tmp_path):
    (tmp_path / "blob").write_bytes(b"x" * 4096)
    monkeypatch.setattr(
        "lazyuv.commands.run_capture", _global_capture(cache_dir=str(tmp_path))
    )
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # while _busy is set (simulating an in-flight op), z must not start a scan
        app._busy = True
        await pilot.press("z")
        await pilot.pause()
        # panel should not have been switched to "calculating…" — guard fired
        from lazyuv.widgets.cache import CachePanel

        assert "calculating" not in str(app.query_one(CachePanel).render())


@pytest.mark.asyncio
async def test_self_update_failure_surfaced(monkeypatch):
    """A failing `uv self update` must surface its exit in the Output panel."""
    from lazyuv.widgets.output import OutputPanel

    async def failing_streaming(argv, on_line, cwd=None):
        on_line("error: uv was installed through an external package manager")
        return 2

    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", failing_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("X")
        await pilot.pause()
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        log = str(app.query_one(OutputPanel).lines)
        assert "external package manager" in log or "exited with 2" in log


@pytest.mark.asyncio
async def test_self_update_refreshes_version(monkeypatch):
    """After self-update, the shown uv version is re-read (not left stale)."""
    versions = iter(["uv 0.11.31 (Homebrew)", "uv 0.99.0 (Homebrew)"])

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if argv == ["uv", "--version"]:
            return 0, next(versions, "uv 0.99.0 (Homebrew)")
        if argv[:3] == ["uv", "tool", "list"]:
            return 0, _TOOL_LIST
        if argv[:3] == ["uv", "cache", "dir"]:
            return 0, "/tmp/cache\n"
        return 0, ""

    async def fake_run_streaming(argv, on_line, cwd=None):
        return 0

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()  # mount version load -> 0.11.31
        await pilot.press("g")
        await app.workers.wait_for_complete()  # global refresh re-reads -> 0.99.0
        await pilot.pause()
        assert app.uv_version == "0.99.0"
        assert "uv 0.99.0" in app.sub_title


@pytest.mark.asyncio
async def test_refresh_global_surfaces_tool_list_failure(monkeypatch):
    from lazyuv.widgets.output import OutputPanel

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if argv[:3] == ["uv", "tool", "list"]:
            return 1, ""
        if argv == ["uv", "--version"]:
            return 0, "uv 0.11.31"
        return 0, "/tmp/cache\n"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.tools == []
        assert "uv tool list" in str(app.query_one(OutputPanel).lines)


@pytest.mark.asyncio
async def test_tools_panel_escapes_markup(monkeypatch):
    """A tool name with bracket markup must not be interpreted as Rich markup."""
    from lazyuv.widgets.tools import ToolsPanel

    tool_list = "ev[il] v1.0.0\n- evil\n"
    monkeypatch.setattr(
        "lazyuv.commands.run_capture", _global_capture(tool_list=tool_list)
    )
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = app.query_one(ToolsPanel)
        assert len(panel) == 1  # panel populated (rendered the markup-y name) without raising
        # the parsed tool keeps its literal name; rendering doesn't raise
        assert app.tools and app.tools[0].name == "ev[il]"


@pytest.mark.asyncio
async def test_more_mode_gated_keys(monkeypatch):
    captured = {}
    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    monkeypatch.setattr("lazyuv.commands.run_streaming", _capture_streaming(captured))
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        # project mode: global mutation keys must not dispatch
        for key in ("c", "P", "x"):
            await pilot.press(key)
            await pilot.pause()
        assert "argv" not in captured
        # global mode: project mutation keys must not dispatch
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        for key in ("l", "d"):
            await pilot.press(key)
            await pilot.pause()
        assert "argv" not in captured


# --- Milestone 4: workspaces & advanced deps -------------------------------


def _write_ws(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "wsroot"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["httpx"]\n\n'
        "[tool.uv.workspace]\n"
        'members = ["packages/*"]\n\n'
        "[tool.uv.sources]\n"
        "alpha = { workspace = true }\n"
    )
    for name, dep in (("alpha", "rich"), ("beta", "click")):
        d = root / "packages" / name
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\n'
            'version = "0.1.0"\n'
            'requires-python = ">=3.14"\n'
            f'dependencies = ["{dep}"]\n'
        )


@pytest.mark.asyncio
async def test_workspace_panel_shows_and_switches(tmp_path, monkeypatch):
    from lazyuv.widgets.workspace import WorkspacePanel

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        wp = app.query_one(WorkspacePanel)
        assert wp.display is True
        assert next(m.name for m in app.workspace_members) == "wsroot"
        assert {m.name for m in app.workspace_members} >= {"wsroot", "alpha", "beta"}
        # switch to member "alpha"
        await pilot.press("w")
        await pilot.pause()
        from textual.widgets import ListView

        members = app.workspace_members
        idx = next(i for i, m in enumerate(members) if m.name == "alpha")
        app.screen.query_one("#workspace-list", ListView).index = idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        assert app.focused_member is not None and app.focused_member.name == "alpha"
        # deps tree is now scoped to alpha's own dependency ("rich")
        labels = [
            str(node.label)
            for group_node in app.query_one(DependenciesPanel).root.children
            for node in group_node.children
        ]
        assert any("rich" in lb for lb in labels)
        assert "wsroot" in app.sub_title and "alpha" in app.sub_title
        # a mutation now runs in the focused member's dir, not the workspace root
        await pilot.press("s")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["cwd"] == tmp_path / "packages" / "alpha"


@pytest.mark.asyncio
async def test_workspace_switch_back_to_root_rescopes(tmp_path):
    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import ListView

        # focus member "alpha"
        await pilot.press("w")
        await pilot.pause()
        members = app.workspace_members
        alpha_idx = next(i for i, m in enumerate(members) if m.name == "alpha")
        app.screen.query_one("#workspace-list", ListView).index = alpha_idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        assert app.focused_member is not None
        # switch back to the root member
        await pilot.press("w")
        await pilot.pause()
        root_idx = next(i for i, m in enumerate(app.workspace_members) if m.is_root)
        app.screen.query_one("#workspace-list", ListView).index = root_idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        assert app.focused_member is None
        # deps re-scope to the root project's own dep ("httpx"), not alpha's "rich"
        labels = [
            str(node.label)
            for group_node in app.query_one(DependenciesPanel).root.children
            for node in group_node.children
        ]
        assert any("httpx" in lb for lb in labels)
        assert not any("rich" in lb for lb in labels)


@pytest.mark.asyncio
async def test_no_workspace_panel_hidden():
    from lazyuv.widgets.workspace import WorkspacePanel

    app = LazyUvApp(root=FIXTURE)  # sample project is not a workspace
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(WorkspacePanel).display is False
        assert app.workspace_members == []


@pytest.mark.asyncio
async def test_targeted_upgrade_builds_argv(monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        leaf = next(
            node
            for group_node in panel.root.children
            for node in group_node.children
            if node.data is not None and node.data.name == "httpx"
        )
        panel.move_cursor(leaf)
        await pilot.pause()
        await pilot.press("u")  # upgrade selected package
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "lock", "--upgrade-package", "httpx"]


@pytest.mark.asyncio
async def test_export_flow_builds_argv(monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        from textual.widgets import Checkbox

        app.screen.query_one("#export-no-hashes", Checkbox).value = True
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == [
            "uv", "export", "--format", "requirements.txt",
            "--no-hashes", "-o", "requirements.txt",
        ]


@pytest.mark.asyncio
async def test_details_shows_source_via_line(tmp_path):
    from lazyuv.widgets.details import DetailsPanel

    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # switch to member alpha whose own dep "rich" has no source; instead check
        # the root project where "alpha" dep has a workspace source
        dep = next(d for d in app.project.dependencies if d.name == "httpx")
        app.query_one(DetailsPanel).show_dependency(dep)
        # httpx has no source entry -> no via line; now render a sourced dep
        from lazyuv.models import Dependency

        sourced = Dependency(name="alpha", spec="", group="main", source_detail="workspace")
        app.query_one(DetailsPanel).show_dependency(sourced)
        assert "via:" in str(app.query_one(DetailsPanel).render())
        assert "workspace" in str(app.query_one(DetailsPanel).render())


@pytest.mark.asyncio
async def test_workspace_export_gated_in_global(monkeypatch):
    from lazyuv.screens.export import ExportScreen
    from lazyuv.screens.workspace import WorkspaceSwitchScreen

    monkeypatch.setattr("lazyuv.commands.run_capture", _global_capture())
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert not isinstance(app.screen, WorkspaceSwitchScreen)
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, ExportScreen)


# --- Milestone 5: inline scripts (PEP 723) ---------------------------------

_SCRIPT_BLOCK = (
    "# /// script\n"
    '# requires-python = ">=3.14"\n'
    "# dependencies = [\n"
    '#     "requests>=2.34.2",\n'
    '#     "rich>=13",\n'
    "# ]\n"
    "# ///\n"
    'print("hello")\n'
)


def _write_script_project(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "host"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        "dependencies = []\n"
    )
    (root / "demo.py").write_text(_SCRIPT_BLOCK)


async def _enter_script_mode(pilot, app, tmp_path):
    # demo.py is the only .py under the host project, so it's the sole (highlighted)
    # entry in the picker — just confirm the default selection.
    await pilot.press("o")
    await pilot.pause()
    await pilot.click("#ok")
    await pilot.pause()


@pytest.mark.asyncio
async def test_open_script_enters_script_mode(tmp_path):
    from lazyuv.widgets.environment import EnvironmentPanel
    from lazyuv.widgets.scripts import ScriptsPanel

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        assert app.mode == "script"
        assert str(app.script_path) == "demo.py"
        assert "script · demo.py" in app.sub_title
        # deps tree shows the block's deps under the "script" group
        labels = [
            str(node.label)
            for group_node in app.query_one(DependenciesPanel).root.children
            for node in group_node.children
        ]
        assert any("requests" in lb for lb in labels)
        assert any("rich" in lb for lb in labels)
        # project-only sub-panels are hidden in script mode
        assert app.query_one(EnvironmentPanel).display is False
        assert app.query_one(ScriptsPanel).display is False


@pytest.mark.asyncio
async def test_script_add_builds_script_argv(tmp_path, monkeypatch):
    from textual.widgets import Input

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        await pilot.press("a")
        await pilot.pause()
        app.screen.query_one("#packages", Input).value = "cowsay httpx"
        await pilot.click("#ok")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == [
            "uv", "add", "--script", "demo.py", "cowsay", "httpx",
        ]
        assert captured["cwd"] == tmp_path


@pytest.mark.asyncio
async def test_script_remove_builds_script_argv(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        app.query_one(DependenciesPanel).restore_selection("script", "rich")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "remove", "--script", "demo.py", "rich"]


@pytest.mark.asyncio
async def test_script_run_builds_script_argv(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "run", "--script", "demo.py"]
        assert captured["cwd"] == tmp_path


@pytest.mark.asyncio
async def test_escape_exits_script_mode(tmp_path):
    from lazyuv.widgets.environment import EnvironmentPanel

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        assert app.mode == "script"
        await pilot.press("escape")
        await pilot.pause()
        assert app.mode == "project"
        assert app.script_path is None
        # project panels are restored
        assert app.query_one(EnvironmentPanel).display is True
        # subtitle back to the host project
        assert "host 0.1.0" in app.sub_title


@pytest.mark.asyncio
async def test_mode_gating_check_action(tmp_path):
    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # project mode: script-only exit is inert, open_script is live
        assert app.check_action("exit_script", ()) is None
        assert app.check_action("open_script", ()) is True
        # enter script mode: project-only keys inert, script keys live
        await _enter_script_mode(pilot, app, tmp_path)
        assert app.check_action("sync", ()) is None
        assert app.check_action("workspace", ()) is None
        assert app.check_action("upgrade", ()) is None
        assert app.check_action("exit_script", ()) is True
        assert app.check_action("add", ()) is True
        assert app.check_action("run", ()) is True
        # global mode: script keys inert
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        assert app.check_action("open_script", ()) is None
        assert app.check_action("exit_script", ()) is None


@pytest.mark.asyncio
async def test_toggle_global_clears_script_focus(tmp_path):
    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        assert app.mode == "script"
        await pilot.press("g")
        await pilot.pause()
        assert app.mode == "global"
        assert app.script_path is None


@pytest.mark.asyncio
async def test_script_picker_manual_path_opens_omitted_script(tmp_path, monkeypatch):
    from textual.widgets import Input

    # Simulate a truncated scan that omitted the target script entirely.
    monkeypatch.setattr("lazyuv.data.find_scripts", lambda root: (["other.py"], True))

    _write_script_project(tmp_path)  # writes demo.py (the "omitted" target)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        app.screen.query_one("#script-path", Input).value = "demo.py"
        await pilot.click("#ok")
        await pilot.pause()
        assert app.mode == "script"
        assert str(app.script_path) == "demo.py"
        labels = [
            str(node.label)
            for group_node in app.query_one(DependenciesPanel).root.children
            for node in group_node.children
        ]
        assert any("requests" in lb for lb in labels)


# --- Milestone 6: tree / outdated / run-with-args --------------------------

_APP_TREE_JSON = json.dumps({
    "schema": {"version": "preview"},
    "roots": [{"id": "root"}],
    "resolution": {
        "root": {"name": "sample", "version": "0.2.0",
                 "dependencies": [{"id": "httpx"}]},
        "httpx": {"name": "httpx", "version": "0.28.1",
                  "latest_version": "0.29.0", "dependencies": []},
    },
})


@pytest.mark.asyncio
async def test_tree_key_opens_modal(monkeypatch):
    from lazyuv.screens.tree import DependencyTreeScreen

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, DependencyTreeScreen)
        from textual.widgets import Tree
        labels = [str(n.label) for n in app.screen.query_one(Tree).root.children]
        assert any("sample" in lb for lb in labels)


@pytest.mark.asyncio
async def test_outdated_toggle_annotates_and_clears(monkeypatch):
    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        assert app._outdated_on is True
        assert "outdated: 1" in panel.border_title
        labels = [
            str(node.label)
            for group_node in panel.root.children
            for node in group_node.children
        ]
        assert any("httpx" in lb and "→ 0.29.0" in lb for lb in labels)
        # toggle off
        await pilot.press("O")
        await pilot.pause()
        assert app._outdated_on is False
        assert panel.border_title == "Dependencies"


@pytest.mark.asyncio
async def test_outdated_dep_upgrades_with_u(monkeypatch):
    captured = {}

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        leaf = next(
            node
            for group_node in panel.root.children
            for node in group_node.children
            if node.data is not None and node.data.name == "httpx"
        )
        panel.move_cursor(leaf)
        await pilot.pause()
        await pilot.press("u")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "lock", "--upgrade-package", "httpx"]


@pytest.mark.asyncio
async def test_run_args_project_mode_builds_argv(monkeypatch):
    from textual.widgets import Input

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    from lazyuv.widgets.scripts import ScriptsPanel

    app = LazyUvApp(root=FIXTURE)  # fixture has a [project.scripts] entry "serve"
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(ScriptsPanel).index = 0  # select the "serve" script
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        app.screen.query_one("#run-args", Input).value = "--verbose input.txt"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == [
            "uv", "run", "serve", "--verbose", "input.txt",
        ]


@pytest.mark.asyncio
async def test_run_args_script_mode_preserves_quoted_arg(tmp_path, monkeypatch):
    from textual.widgets import Input

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)

    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _enter_script_mode(pilot, app, tmp_path)
        await pilot.press("R")
        await pilot.pause()
        app.screen.query_one("#run-args", Input).value = '--name "two words"'
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # shlex keeps the quoted arg as one token; no `--` injected
        assert captured["argv"] == [
            "uv", "run", "--script", "demo.py", "--name", "two words",
        ]


@pytest.mark.asyncio
async def test_m6_mode_gating(tmp_path):
    _write_script_project(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # project mode: all three live
        assert app.check_action("tree", ()) is True
        assert app.check_action("outdated", ()) is True
        assert app.check_action("run_args", ()) is True
        # script mode: tree/outdated inert, run_args live
        await _enter_script_mode(pilot, app, tmp_path)
        assert app.check_action("tree", ()) is None
        assert app.check_action("outdated", ()) is None
        assert app.check_action("run_args", ()) is True
        # global mode: all three inert
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        assert app.check_action("tree", ()) is None
        assert app.check_action("outdated", ()) is None
        assert app.check_action("run_args", ()) is None


@pytest.mark.asyncio
async def test_outdated_count_matches_annotations_after_upgrade(monkeypatch):
    # Regression: once resolved == latest (post-upgrade), the dep is no longer shown
    # as outdated AND must not be counted in the title — the two use one predicate.
    from lazyuv.models import Dependency

    panel_deps = [
        Dependency(name="httpx", spec="", group="main", resolved_version="0.29.0"),
    ]
    from lazyuv.widgets.dependencies import DependenciesPanel

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        panel.set_filter("", panel_deps)
        # latest == resolved -> not outdated: no annotation, count 0 (not 1)
        panel.set_outdated({"httpx": "0.29.0"})
        assert "outdated: 0" in panel.border_title
        labels = [
            str(node.label)
            for group_node in panel.root.children
            for node in group_node.children
        ]
        assert not any("→" in lb for lb in labels)


@pytest.mark.asyncio
async def test_tree_scopes_to_focused_member(tmp_path, monkeypatch):
    # uv tree is workspace-global; a focused member must be targeted with --package.
    from textual.widgets import ListView

    captured = {}

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            captured["argv"] = argv
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)

    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # focus member "alpha"
        await pilot.press("w")
        await pilot.pause()
        members = app.workspace_members
        idx = next(i for i, m in enumerate(members) if m.name == "alpha")
        app.screen.query_one("#workspace-list", ListView).index = idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        # now request the tree; the query must scope to --package alpha
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == [
            "uv", "tree", "--format", "json", "--frozen", "--package", "alpha",
        ]


@pytest.mark.asyncio
async def test_tree_no_package_at_workspace_root(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            captured["argv"] = argv
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)

    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")  # root focused -> no --package
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "--package" not in captured["argv"]


# --- Milestone 6: review-hardening (error paths, overlay lifecycle) ---------


@pytest.mark.asyncio
async def test_outdated_active_empty_shows_zero(monkeypatch):
    # An active overlay that found nothing must still read "outdated: 0", not look off.
    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, json.dumps({"schema": {"version": "preview"}, "roots": [],
                                  "resolution": {}})
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        assert app._outdated_on is True
        assert "outdated: 0" in panel.border_title


@pytest.mark.asyncio
async def test_outdated_unparseable_does_not_claim_zero(monkeypatch):
    # exit 0 but unreadable JSON must surface an error and NOT report "0 outdated".
    from lazyuv.widgets.output import OutputPanel

    lines = []

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, "not json at all"
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app.query_one(OutputPanel), "line", lines.append)
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app._outdated_on is False
        assert app.query_one(DependenciesPanel).border_title == "Dependencies"
        assert any("could not read" in ln for ln in lines)
        assert not any("with a newer release" in ln for ln in lines)


@pytest.mark.asyncio
async def test_outdated_query_failure_clears_and_resets_busy(monkeypatch):
    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 2, ""
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app._outdated_on is False
        assert app._busy is False  # released so the next action works
        assert app.query_one(DependenciesPanel).border_title == "Dependencies"


@pytest.mark.asyncio
async def test_tree_unparseable_opens_no_modal(monkeypatch):
    from lazyuv.screens.tree import DependencyTreeScreen

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, "garbage"
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not isinstance(app.screen, DependencyTreeScreen)
        assert app._busy is False


@pytest.mark.asyncio
async def test_run_args_invalid_shlex_surfaced_no_run(monkeypatch):
    from textual.widgets import Input
    from lazyuv.widgets.scripts import ScriptsPanel

    ran = []
    from lazyuv.widgets.output import OutputPanel

    async def fake_run_streaming(argv, on_line, cwd=None):
        ran.append(argv)
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(ScriptsPanel).index = 0
        await pilot.pause()
        lines = []
        monkeypatch.setattr(app.query_one(OutputPanel), "line", lines.append)
        await pilot.press("R")
        await pilot.pause()
        app.screen.query_one("#run-args", Input).value = 'foo "unbalanced'
        await pilot.press("enter")
        await pilot.pause()
        assert ran == []  # no run dispatched
        assert any("invalid arguments" in ln for ln in lines)


@pytest.mark.asyncio
async def test_run_args_empty_runs_with_no_args(monkeypatch):
    from textual.widgets import Input
    from lazyuv.widgets.scripts import ScriptsPanel

    captured = {}

    async def fake_run_streaming(argv, on_line, cwd=None):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("lazyuv.commands.run_streaming", fake_run_streaming)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(ScriptsPanel).index = 0
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        app.screen.query_one("#run-args", Input).value = "   "  # whitespace only
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert captured["argv"] == ["uv", "run", "serve"]


@pytest.mark.asyncio
async def test_outdated_cleared_when_entering_script_mode(tmp_path, monkeypatch):
    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            return 0, _APP_TREE_JSON  # marks httpx outdated
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    _write_script_project(tmp_path)  # host project + demo.py
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app._outdated_on is True
        # entering script mode must clear the project overlay
        await _enter_script_mode(pilot, app, tmp_path)
        assert app._outdated_on is False
        assert app.query_one(DependenciesPanel).border_title == "Dependencies"


@pytest.mark.asyncio
async def test_outdated_cleared_on_workspace_switch(tmp_path, monkeypatch):
    from textual.widgets import ListView

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            # rich (alpha's dep) is outdated
            return 0, json.dumps({
                "schema": {"version": "preview"}, "roots": [{"id": "r"}],
                "resolution": {"r": {"name": "alpha", "version": "0.1.0",
                                     "dependencies": [{"id": "rich"}]},
                               "rich": {"name": "rich", "version": "13.0.0",
                                        "latest_version": "15.0.0",
                                        "dependencies": []}},
            })
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # focus alpha, turn overlay on
        await pilot.press("w")
        await pilot.pause()
        idx = next(i for i, m in enumerate(app.workspace_members) if m.name == "alpha")
        app.screen.query_one("#workspace-list", ListView).index = idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app._outdated_on is True
        # switching to beta must clear alpha's overlay (no bleed)
        await pilot.press("w")
        await pilot.pause()
        bidx = next(i for i, m in enumerate(app.workspace_members) if m.name == "beta")
        app.screen.query_one("#workspace-list", ListView).index = bidx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        assert app._outdated_on is False
        assert app.query_one(DependenciesPanel).border_title == "Dependencies"


@pytest.mark.asyncio
async def test_outdated_scopes_to_focused_member(tmp_path, monkeypatch):
    from textual.widgets import ListView

    captured = {}

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            captured["argv"] = argv
            return 0, _APP_TREE_JSON
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    _write_ws(tmp_path)
    app = LazyUvApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        idx = next(i for i, m in enumerate(app.workspace_members) if m.name == "alpha")
        app.screen.query_one("#workspace-list", ListView).index = idx
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()
        await pilot.press("O")  # outdated must also scope with --package
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "--package" in captured["argv"]
        assert captured["argv"][-1] == "alpha"
        assert "--outdated" in captured["argv"]


@pytest.mark.asyncio
async def test_outdated_query_timeout_recovers(monkeypatch):
    # A network stall must not wedge the UI: _busy resets, overlay clears, error shown.
    from lazyuv.widgets.output import OutputPanel

    async def fake_run_capture(argv, cwd=None, timeout=None):
        if "tree" in argv:
            raise TimeoutError("`uv tree --outdated` timed out after 60s")
        return 0, "uv 0.11.31"

    monkeypatch.setattr("lazyuv.commands.run_capture", fake_run_capture)
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        lines = []
        monkeypatch.setattr(app.query_one(OutputPanel), "line", lines.append)
        await pilot.press("O")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app._busy is False
        assert app._outdated_on is False
        assert app.query_one(DependenciesPanel).border_title == "Dependencies"
        assert any("timed out" in ln for ln in lines)


@pytest.mark.asyncio
async def test_outdated_count_respects_filter():
    # Title count must match the filtered leaves, not the whole dependency set.
    from lazyuv.models import Dependency
    from lazyuv.widgets.dependencies import DependenciesPanel

    deps = [
        Dependency(name="httpx", spec="", group="main", resolved_version="0.28.1"),
        Dependency(name="rich", spec="", group="main", resolved_version="13.0.0"),
    ]
    app = LazyUvApp(root=FIXTURE)
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(DependenciesPanel)
        panel.set_filter("", deps)
        panel.set_outdated({"httpx": "0.29.0", "rich": "15.0.0"})  # both outdated
        assert "outdated: 2" in panel.border_title
        # filter to just httpx -> count and visible annotations both drop to 1
        panel.set_filter("httpx", deps)
        assert "outdated: 1" in panel.border_title
        labels = [
            str(node.label)
            for group_node in panel.root.children
            for node in group_node.children
        ]
        assert len(labels) == 1 and "httpx" in labels[0]


# --- help page -------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_is_fullscreen_page_without_wrapping():
    from lazyuv.screens.help import HelpScreen, _HELP
    from textual.widgets import Static

    longest = max(len(line) for line in _HELP.splitlines())
    assert longest > 60  # wider than the old shared dialog width

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        body = app.screen.query_one("#help-body")
        # a full-screen page: the body spans (nearly) the whole width, and its text
        # region is far wider than the longest line -> no wrap on any normal terminal
        assert body.region.width >= 100
        assert app.screen.query_one(Static).region.width >= longest


@pytest.mark.asyncio
async def test_help_page_scrollable_when_taller_than_terminal():
    # On a short terminal the list overflows; the page must be keyboard-scrollable
    # (focused scroller) so the bottom is reachable, and close on escape and q.
    from lazyuv.screens.help import HelpScreen

    app = LazyUvApp(root=FIXTURE)
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        body = app.screen.query_one("#help-body")
        assert body.show_vertical_scrollbar  # content taller than the viewport
        before = body.scroll_offset.y
        await pilot.press("pagedown")
        await pilot.pause()
        assert body.scroll_offset.y > before  # keys actually scroll it
        await pilot.press("q")  # q closes the page (screen binding wins over app quit)
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
