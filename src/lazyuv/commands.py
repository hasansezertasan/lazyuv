"""Build uv command argv and run uv as a streaming subprocess.

Argv builders are pure functions. `run_streaming` is the ONLY code in lazyuv
that executes the real `uv` binary, which makes it a clean seam to mock in tests.
"""

from __future__ import annotations


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
