"""Build uv command argv and run uv as a streaming subprocess.

Argv builders are pure functions. `run_streaming` is the ONLY code in lazyuv
that executes the real `uv` binary, which makes it a clean seam to mock in tests.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path


def _group_flags(group: str, kind: str) -> list[str]:
    """Map a dependency's (group, kind) to uv's target flags.

    Routing is by `kind`, never by name — an optional extra named "dev" must still
    use `--optional dev`, not `--dev`. `--group` targets PEP 735 dependency groups,
    `--optional` targets optional-dependency extras.
    """
    if kind == "main":
        return []
    if kind == "dev":
        return ["--dev"]
    if kind == "group":
        return ["--group", group]
    return ["--optional", group]


def build_add(packages: list[str], group: str = "main", kind: str = "main") -> list[str]:
    return ["uv", "add", *_group_flags(group, kind), *packages]


def build_remove(package: str, group: str = "main", kind: str = "main") -> list[str]:
    return ["uv", "remove", *_group_flags(group, kind), package]


def build_sync(
    *,
    extras: Sequence[str] = (),
    groups: Sequence[str] = (),
    no_dev: bool = False,
    frozen: bool = False,
) -> list[str]:
    """Build `uv sync`, optionally scoped.

    All arguments are keyword-only with empty/false defaults, so `build_sync()`
    is exactly `["uv", "sync"]` (v1 behavior) and the scoping is purely additive.
    """
    argv = ["uv", "sync"]
    for extra in extras:
        argv += ["--extra", extra]
    for group in groups:
        argv += ["--group", group]
    if no_dev:
        argv.append("--no-dev")
    if frozen:
        argv.append("--frozen")
    return argv


def build_lock() -> list[str]:
    return ["uv", "lock"]


def build_lock_upgrade_package(name: str) -> list[str]:
    return ["uv", "lock", "--upgrade-package", name]


def build_export(
    *,
    fmt: str = "requirements.txt",
    no_hashes: bool = False,
    no_dev: bool = False,
    extras: Sequence[str] = (),
    groups: Sequence[str] = (),
    output_file: str | None = None,
) -> list[str]:
    """Build `uv export`. Defaults to a requirements.txt export to stdout."""
    argv = ["uv", "export", "--format", fmt]
    for extra in extras:
        argv += ["--extra", extra]
    for group in groups:
        argv += ["--group", group]
    if no_hashes:
        argv.append("--no-hashes")
    if no_dev:
        argv.append("--no-dev")
    if output_file:
        argv += ["-o", output_file]
    return argv


def build_run(script: str) -> list[str]:
    return ["uv", "run", script]


# --- inline scripts (PEP 723) (Milestone 5) --------------------------------

# `--script <file>` is the explicit, unambiguous form for all three: it targets a
# standalone script's inline metadata rather than the CWD project. Verified against
# uv 0.11.31 (`uv add/remove/run --script <file>`). The path is passed as-is; the app
# runs these with cwd=active_dir so a relative path resolves.


def build_add_script(path: str, packages: list[str]) -> list[str]:
    return ["uv", "add", "--script", path, *packages]


def build_remove_script(path: str, package: str) -> list[str]:
    return ["uv", "remove", "--script", path, package]


def build_run_script(path: str) -> list[str]:
    return ["uv", "run", "--script", path]


def build_python_list() -> list[str]:
    return ["uv", "python", "list", "--output-format", "json"]


# `request` is a uv Python request — pass the row's fully-qualified `key`
# (e.g. "cpython-3.14.6-macos-aarch64-none") so the action targets the exact
# interpreter the user selected, not an ambiguous bare version.
def build_python_install(request: str) -> list[str]:
    return ["uv", "python", "install", request]


def build_python_pin(request: str) -> list[str]:
    return ["uv", "python", "pin", request]


def build_python_uninstall(request: str) -> list[str]:
    return ["uv", "python", "uninstall", request]


def build_venv(python: str | None = None, clear: bool = False) -> list[str]:
    """Build `uv venv`. `clear` adds `--clear` to replace an existing venv (uv
    refuses to recreate over an existing `.venv` without it)."""
    argv = ["uv", "venv"]
    if clear:
        argv.append("--clear")
    if python:
        argv += ["--python", python]
    return argv


# --- global: tools / cache / self (Milestone 3) ----------------------------


def build_tool_list() -> list[str]:
    return ["uv", "tool", "list"]


def build_tool_install(package: str) -> list[str]:
    return ["uv", "tool", "install", package]


def build_tool_upgrade(name: str) -> list[str]:
    return ["uv", "tool", "upgrade", name]


def build_tool_upgrade_all() -> list[str]:
    return ["uv", "tool", "upgrade", "--all"]


def build_tool_uninstall(name: str) -> list[str]:
    return ["uv", "tool", "uninstall", name]


def build_cache_dir() -> list[str]:
    return ["uv", "cache", "dir"]


def build_cache_clean() -> list[str]:
    return ["uv", "cache", "clean"]


def build_cache_prune() -> list[str]:
    return ["uv", "cache", "prune"]


def build_uv_version() -> list[str]:
    return ["uv", "--version"]


def build_self_update() -> list[str]:
    return ["uv", "self", "update"]


def uv_available() -> bool:
    """True if the `uv` binary is on PATH."""
    return shutil.which("uv") is not None


async def run_streaming(
    argv: list[str],
    on_line: Callable[[str], None],
    cwd: Path | None = None,
) -> int:
    """Run `argv`, invoking `on_line` for each combined stdout/stderr line.

    Returns the process exit code. Lines are yielded without trailing newlines.
    On cancellation (or any error mid-run) the child process is terminated and
    awaited so it is never orphaned.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    try:
        async for raw in process.stdout:
            on_line(raw.decode(errors="replace").rstrip("\r\n"))
        return await process.wait()
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            await process.wait()


async def run_capture(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run `argv` to completion and return (exit_code, stdout).

    The read-only counterpart to `run_streaming`: for queries like `uv python list`
    whose whole stdout we parse at once (as JSON). Unlike `run_streaming`, stderr is
    kept OUT of the returned output — a uv warning/progress line on stderr must not
    corrupt the JSON. Like `run_streaming`, the child is terminated and awaited if
    cancelled, so it is never orphaned.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await process.communicate()
        return process.returncode or 0, stdout.decode(errors="replace")
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            await process.wait()
