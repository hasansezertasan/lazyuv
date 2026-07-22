"""Domain models for lazyuv. Plain data, no behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LoadStatus(Enum):
    OK = "ok"
    NOT_A_PROJECT = "not_a_project"  # no pyproject.toml found
    MALFORMED = "malformed"          # TOML failed to parse


@dataclass(frozen=True, slots=True)
class Dependency:
    name: str                 # canonical package name, e.g. "httpx"
    spec: str                 # declared version specifier, e.g. ">=0.28.1" ("" if none)
    group: str                # "main", "dev", or an optional-group name
    resolved_version: str | None = None  # from uv.lock, None if not locked
    source: str = "registry"  # registry | git | path | url | other
    kind: str = "extra"       # main | dev | extra | group  (how uv targets this dep)
    # All distinct versions when the lock holds more than one for this package
    # (universal-lock resolution forks OR [tool.uv].conflicts variants), in
    # lock-file order; empty when there are 0 or 1 distinct versions (repeated
    # entries of the same version do not count). lazyuv does not evaluate
    # markers/conflicts, so it neither labels nor scopes these — it just surfaces
    # every locked version.
    locked_versions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Script:
    name: str                 # e.g. "serve"
    target: str               # entry point string, e.g. "myproject.cli:main"


@dataclass(slots=True)
class Project:
    name: str
    version: str
    requires_python: str
    dependencies: list[Dependency] = field(default_factory=list)
    scripts: list[Script] = field(default_factory=list)
    # Declared (name, kind) groups from the TOML tables, including empty ones so
    # the UI can offer them as add targets even before they contain a dependency.
    groups: list[tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class LoadResult:
    status: LoadStatus
    project: Project | None = None
    error: str | None = None  # human-readable detail for MALFORMED
