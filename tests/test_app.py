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
        assert app.sub_title == "sample 0.2.0"
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
        assert app.sub_title == ""
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
    async def fake_run_capture(argv, cwd=None):
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

    async def fake_run_capture(argv, cwd=None):
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
