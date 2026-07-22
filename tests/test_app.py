from pathlib import Path

import pytest

from lazyuv.app import LazyUvApp
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
