import asyncio
import sys

import pytest

from lazyuv.commands import (
    build_add,
    build_add_script,
    build_lock,
    build_tree,
    build_python_install,
    build_python_list,
    build_python_pin,
    build_python_uninstall,
    build_remove,
    build_remove_script,
    build_run,
    build_run_script,
    build_sync,
    build_venv,
    run_capture,
    run_streaming,
    uv_available,
)


def test_build_add_main():
    assert build_add(["httpx"], group="main") == ["uv", "add", "httpx"]


def test_build_add_multiple_main():
    assert build_add(["httpx", "rich"], group="main") == [
        "uv", "add", "httpx", "rich",
    ]


def test_build_add_dev():
    assert build_add(["pytest"], group="dev", kind="dev") == [
        "uv", "add", "--dev", "pytest",
    ]


def test_build_add_script_single():
    assert build_add_script("demo.py", ["requests"]) == [
        "uv", "add", "--script", "demo.py", "requests",
    ]


def test_build_add_script_multiple_preserves_spec():
    assert build_add_script("scripts/x.py", ["rich>=13", "idna"]) == [
        "uv", "add", "--script", "scripts/x.py", "rich>=13", "idna",
    ]


def test_build_remove_script():
    assert build_remove_script("demo.py", "rich") == [
        "uv", "remove", "--script", "demo.py", "rich",
    ]


def test_build_run_script():
    assert build_run_script("demo.py") == ["uv", "run", "--script", "demo.py"]


def test_build_run_with_args_no_separator():
    # Args appended directly, NO `--` (verified: uv passes them through as-is).
    assert build_run("serve", ["--verbose", "pos"]) == [
        "uv", "run", "serve", "--verbose", "pos",
    ]


def test_build_run_script_with_args():
    assert build_run_script("demo.py", ["--name", "two words"]) == [
        "uv", "run", "--script", "demo.py", "--name", "two words",
    ]


def test_build_run_defaults_to_no_args():
    assert build_run("serve") == ["uv", "run", "serve"]


def test_build_tree_bare():
    assert build_tree() == ["uv", "tree", "--format", "json", "--frozen"]


def test_build_tree_outdated():
    assert build_tree(outdated=True) == [
        "uv", "tree", "--format", "json", "--frozen", "--outdated",
    ]


def test_build_tree_not_frozen():
    assert build_tree(frozen=False) == ["uv", "tree", "--format", "json"]


def test_build_tree_scoped_to_package():
    # uv tree is workspace-global (not cwd-scoped), so a focused member needs --package.
    assert build_tree(package="alpha") == [
        "uv", "tree", "--format", "json", "--frozen", "--package", "alpha",
    ]
    assert build_tree(outdated=True, package="alpha") == [
        "uv", "tree", "--format", "json", "--frozen", "--outdated",
        "--package", "alpha",
    ]


def test_build_add_optional_group():
    assert build_add(["typer"], group="cli", kind="extra") == [
        "uv", "add", "--optional", "cli", "typer",
    ]


def test_build_remove():
    assert build_remove("httpx", group="main", kind="main") == ["uv", "remove", "httpx"]


def test_build_remove_dev():
    assert build_remove("pytest", group="dev", kind="dev") == [
        "uv", "remove", "--dev", "pytest",
    ]


def test_build_remove_optional():
    assert build_remove("typer", group="cli", kind="extra") == [
        "uv", "remove", "--optional", "cli", "typer",
    ]


def test_reserved_name_extra_routes_by_kind():
    # An optional extra literally named "dev" must use --optional, not --dev.
    assert build_add(["x"], group="dev", kind="extra") == [
        "uv", "add", "--optional", "dev", "x",
    ]
    assert build_remove("x", group="main", kind="extra") == [
        "uv", "remove", "--optional", "main", "x",
    ]
    # A dependency group named "dev" is genuinely the dev group -> --dev.
    assert build_add(["x"], group="dev", kind="dev") == ["uv", "add", "--dev", "x"]


def test_build_add_dependency_group():
    assert build_add(["mkdocs"], group="docs", kind="group") == [
        "uv", "add", "--group", "docs", "mkdocs",
    ]


def test_build_remove_dependency_group():
    assert build_remove("mkdocs", group="docs", kind="group") == [
        "uv", "remove", "--group", "docs", "mkdocs",
    ]


def test_build_add_optional_extra_kind():
    assert build_add(["typer"], group="cli", kind="extra") == [
        "uv", "add", "--optional", "cli", "typer",
    ]


def test_build_sync_lock_run():
    assert build_sync() == ["uv", "sync"]
    assert build_lock() == ["uv", "lock"]
    assert build_run("serve") == ["uv", "run", "serve"]


def test_build_sync_scoped():
    assert build_sync(extras=["cli"], groups=["docs"], no_dev=True, frozen=True) == [
        "uv", "sync",
        "--extra", "cli",
        "--group", "docs",
        "--no-dev",
        "--frozen",
    ]


def test_build_sync_partial_options():
    assert build_sync(frozen=True) == ["uv", "sync", "--frozen"]
    assert build_sync(extras=["a", "b"]) == [
        "uv", "sync", "--extra", "a", "--extra", "b",
    ]


def test_build_python_commands():
    assert build_python_list() == [
        "uv", "python", "list", "--output-format", "json",
    ]
    assert build_python_install("3.14") == ["uv", "python", "install", "3.14"]
    assert build_python_pin("3.14") == ["uv", "python", "pin", "3.14"]
    assert build_python_uninstall("3.12") == ["uv", "python", "uninstall", "3.12"]


def test_build_venv():
    assert build_venv() == ["uv", "venv"]
    assert build_venv("3.14") == ["uv", "venv", "--python", "3.14"]


def test_build_venv_clear():
    # Recreating over an existing venv needs --clear (uv errors otherwise).
    assert build_venv(clear=True) == ["uv", "venv", "--clear"]
    assert build_venv("3.14", clear=True) == [
        "uv", "venv", "--clear", "--python", "3.14",
    ]


@pytest.mark.asyncio
async def test_run_capture_returns_exit_code_and_output():
    argv = [sys.executable, "-c", "print('hello'); print('world')"]
    exit_code, output = await run_capture(argv)
    assert exit_code == 0
    assert output.splitlines() == ["hello", "world"]


@pytest.mark.asyncio
async def test_run_capture_nonzero_exit():
    argv = [sys.executable, "-c", "import sys; sys.stdout.write('x'); sys.exit(2)"]
    exit_code, output = await run_capture(argv)
    assert exit_code == 2
    assert "x" in output


@pytest.mark.asyncio
async def test_run_capture_excludes_stderr():
    # stderr must not be folded into the returned output (it would corrupt JSON).
    argv = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('WARN'); sys.stdout.write('DATA')",
    ]
    _exit_code, output = await run_capture(argv)
    assert output == "DATA"
    assert "WARN" not in output


@pytest.mark.asyncio
async def test_run_capture_reaps_on_cancel():
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    task = asyncio.create_task(run_capture(argv))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_run_streaming_captures_lines_and_exit_code():
    lines: list[str] = []
    # Use the current Python to emulate a command that prints two lines.
    argv = [sys.executable, "-c", "print('one'); print('two')"]
    exit_code = await run_streaming(argv, on_line=lines.append)
    assert exit_code == 0
    assert lines == ["one", "two"]


@pytest.mark.asyncio
async def test_run_streaming_nonzero_exit():
    argv = [sys.executable, "-c", "import sys; sys.exit(3)"]
    exit_code = await run_streaming(argv, on_line=lambda _l: None)
    assert exit_code == 3


@pytest.mark.asyncio
async def test_run_streaming_reaps_on_cancel():
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    task = asyncio.create_task(run_streaming(argv, on_line=lambda _l: None))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_uv_available_true(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")
    assert uv_available() is True


def test_uv_available_false(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert uv_available() is False


def test_build_tool_commands():
    from lazyuv.commands import (
        build_tool_install,
        build_tool_list,
        build_tool_uninstall,
        build_tool_upgrade,
        build_tool_upgrade_all,
    )

    assert build_tool_list() == ["uv", "tool", "list"]
    assert build_tool_install("ruff") == ["uv", "tool", "install", "ruff"]
    assert build_tool_upgrade("ruff") == ["uv", "tool", "upgrade", "ruff"]
    assert build_tool_upgrade_all() == ["uv", "tool", "upgrade", "--all"]
    assert build_tool_uninstall("ruff") == ["uv", "tool", "uninstall", "ruff"]


def test_build_cache_and_self_commands():
    from lazyuv.commands import (
        build_cache_clean,
        build_cache_dir,
        build_cache_prune,
        build_self_update,
        build_uv_version,
    )

    assert build_cache_dir() == ["uv", "cache", "dir"]
    assert build_cache_clean() == ["uv", "cache", "clean"]
    assert build_cache_prune() == ["uv", "cache", "prune"]
    assert build_uv_version() == ["uv", "--version"]
    assert build_self_update() == ["uv", "self", "update"]


def test_build_lock_upgrade_package():
    from lazyuv.commands import build_lock_upgrade_package

    assert build_lock_upgrade_package("httpx") == [
        "uv", "lock", "--upgrade-package", "httpx",
    ]


def test_build_export_default_and_options():
    from lazyuv.commands import build_export

    assert build_export() == ["uv", "export", "--format", "requirements.txt"]
    assert build_export(
        fmt="requirements.txt",
        no_hashes=True,
        no_dev=True,
        extras=["cli"],
        groups=["docs"],
        output_file="reqs.txt",
    ) == [
        "uv", "export", "--format", "requirements.txt",
        "--extra", "cli",
        "--group", "docs",
        "--no-hashes",
        "--no-dev",
        "-o", "reqs.txt",
    ]
