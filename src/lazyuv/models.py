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
    # Where the dep comes from per [tool.uv.sources], as a short human string
    # (e.g. "workspace", "git (<url>)", "path (<path>)"); "" when it has no
    # sources entry (the common registry case).
    source_detail: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """A member of a uv workspace ([tool.uv.workspace])."""

    name: str            # the member's [project].name
    directory: str       # relative to the workspace root; "" for the root itself
    is_root: bool = False


@dataclass(frozen=True, slots=True)
class Script:
    name: str                 # e.g. "serve"
    target: str               # entry point string, e.g. "myproject.cli:main"


@dataclass(frozen=True, slots=True)
class Tool:
    """A globally-installed uv tool (from `uv tool list`)."""

    name: str                     # e.g. "ruff"
    version: str                  # e.g. "0.11.31" ("" if unparsable)
    executables: tuple[str, ...] = ()  # exposed commands, e.g. ("ruff",)


@dataclass(frozen=True, slots=True)
class Environment:
    """The project's Python/venv state, read from files (no subprocess).

    Everything is best-effort: a field is None when the source file is absent or
    unparseable. `drift` is computed on read (venv Python vs. pin / requires-python)
    using conservative comparison only — never a false alarm; ambiguous cases stay
    None. See the M2 design spec.
    """

    venv_path: str | None = None  # ".venv" when present, else None
    venv_python: str | None = None  # version from .venv/pyvenv.cfg, e.g. "3.14.0"
    pinned_python: str | None = None  # from .python-version, e.g. "3.14"
    drift: str | None = None  # human-readable note when misaligned, else None


@dataclass(frozen=True, slots=True)
class PythonVersion:
    """A Python interpreter reported by `uv python list`.

    `key` is uv's fully-qualified request id (e.g. "cpython-3.14.6-macos-aarch64-none")
    — unambiguous across implementation/variant, unlike `version` alone, which can
    repeat across CPython/PyPy/free-threaded builds. Actions use `key`, never `version`.
    """

    key: str                  # uv request id, e.g. "cpython-3.14.6-macos-aarch64-none"
    version: str              # e.g. "3.14.6"
    implementation: str       # "cpython", "pypy", ...
    installed: bool           # True when uv reports a local path for it
    managed: bool             # True when uv manages this install (safe to uninstall)
    path: str | None = None   # interpreter path when installed, else None


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
    # Python/venv state; None only when this is not a loaded project.
    environment: Environment | None = None
    # Workspace members when this project is a [tool.uv.workspace] root (root first);
    # empty when it is not a workspace.
    workspace_members: list[WorkspaceMember] = field(default_factory=list)


@dataclass(slots=True)
class LoadResult:
    status: LoadStatus
    project: Project | None = None
    error: str | None = None  # human-readable detail for MALFORMED
