"""Build uv command argv and run uv as a streaming subprocess.

Argv builders are pure functions. `run_streaming` is the ONLY code in lazyuv
that executes the real `uv` binary, which makes it a clean seam to mock in tests.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Callable
from pathlib import Path


def _group_flags(group: str) -> list[str]:
    if group == "main":
        return []
    if group == "dev":
        return ["--dev"]
    return ["--optional", group]


def build_add(packages: list[str], group: str = "main") -> list[str]:
    return ["uv", "add", *_group_flags(group), *packages]


def build_remove(package: str, group: str = "main") -> list[str]:
    return ["uv", "remove", *_group_flags(group), package]


def build_sync() -> list[str]:
    return ["uv", "sync"]


def build_lock() -> list[str]:
    return ["uv", "lock"]


def build_run(script: str) -> list[str]:
    return ["uv", "run", script]


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
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    async for raw in process.stdout:
        on_line(raw.decode(errors="replace").rstrip("\n"))
    return await process.wait()
