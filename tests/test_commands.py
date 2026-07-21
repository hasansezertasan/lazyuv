from lazyuv.commands import (
    build_add,
    build_lock,
    build_remove,
    build_run,
    build_sync,
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


def test_build_sync_lock_run():
    assert build_sync() == ["uv", "sync"]
    assert build_lock() == ["uv", "lock"]
    assert build_run("serve") == ["uv", "run", "serve"]
