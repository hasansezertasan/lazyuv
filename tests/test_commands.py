import asyncio
import sys

import pytest

from lazyuv.commands import (
    build_add,
    build_lock,
    build_remove,
    build_run,
    build_sync,
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
    assert build_add(["pytest"], group="dev") == [
        "uv", "add", "--dev", "pytest",
    ]


def test_build_add_optional_group():
    assert build_add(["typer"], group="cli") == [
        "uv", "add", "--optional", "cli", "typer",
    ]


def test_build_remove():
    assert build_remove("httpx", group="main") == ["uv", "remove", "httpx"]


def test_build_remove_dev():
    assert build_remove("pytest", group="dev") == [
        "uv", "remove", "--dev", "pytest",
    ]


def test_build_remove_optional():
    assert build_remove("typer", group="cli") == [
        "uv", "remove", "--optional", "cli", "typer",
    ]


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
