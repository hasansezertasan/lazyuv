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


def build_run(script: str) -> list[str]:
    return ["uv", "run", script]


def build_python_list() -> list[str]:
    return ["uv", "python", "list", "--output-format", "json"]


def build_python_install(version: str) -> list[str]:
    return ["uv", "python", "install", version]


def build_python_pin(version: str) -> list[str]:
    return ["uv", "python", "pin", version]


def build_python_uninstall(version: str) -> list[str]:
    return ["uv", "python", "uninstall", version]


def build_venv(python: str | None = None) -> list[str]:
    return ["uv", "venv", *(["--python", python] if python else [])]


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
    """Run `argv` to completion and return (exit_code, combined_output).

    The read-only counterpart to `run_streaming`: for queries like
    `uv python list` whose whole output we parse at once rather than stream.
    Like `run_streaming`, the child is terminated and awaited if cancelled, so
    it is never orphaned.
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await process.communicate()
        return process.returncode or 0, stdout.decode(errors="replace")
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            await process.wait()
