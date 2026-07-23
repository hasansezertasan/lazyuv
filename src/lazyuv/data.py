"""Load a uv project from pyproject.toml + uv.lock into domain models.

This module never runs subprocesses; it only reads files.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

from lazyuv.models import (
    Dependency,
    Environment,
    LoadResult,
    LoadStatus,
    Project,
    PythonVersion,
    Script,
    Tool,
    WorkspaceMember,
)
from lazyuv.parsing import canonical_name, split_requirement

# uv.lock source keys mapped to our simple source labels.
_SOURCE_LABELS = {
    "registry": "registry",
    "git": "git",
    "url": "url",
    "path": "path",
    "directory": "path",
    "editable": "path",
}


def load_project(root: Path, lock_root: Path | None = None) -> LoadResult:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return LoadResult(status=LoadStatus.NOT_A_PROJECT)

    try:
        with pyproject_path.open("rb") as fh:
            pyproject = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return LoadResult(status=LoadStatus.MALFORMED, error=str(exc))

    # A uv workspace keeps a single lockfile at its root, so a focused member reads
    # the root's uv.lock (its own dir has none) to show resolved versions.
    resolved = _read_lock((lock_root or root) / "uv.lock")

    project_table = pyproject.get("project", {})
    sources = _read_sources(pyproject)
    dependencies = _collect_dependencies(pyproject, resolved, sources)
    scripts = [
        Script(name=name, target=target)
        for name, target in sorted(project_table.get("scripts", {}).items())
    ]

    requires_python = project_table.get("requires-python", "")
    project = Project(
        name=project_table.get("name", root.name),
        version=project_table.get("version", "0.0.0"),
        requires_python=requires_python,
        dependencies=dependencies,
        scripts=scripts,
        groups=_collect_groups(pyproject),
        environment=_read_environment(root, requires_python),
        workspace_members=_read_workspace_members(root, pyproject),
    )
    return LoadResult(status=LoadStatus.OK, project=project)


def _read_lock(lock_path: Path) -> dict[str, list[tuple[str, str]]]:
    """Return {canonical_name: [(version, source_label), ...]} from uv.lock.

    Every `[[package]]` entry is kept, in lock-file order, so multiple entries for
    one name (universal-lock resolution forks or [tool.uv].conflicts variants) are
    preserved rather than collapsed. Returns an empty mapping if the lock is missing
    or unreadable — the UI still shows declared deps, just without resolved versions.
    """
    if not lock_path.is_file():
        return {}
    try:
        with lock_path.open("rb") as fh:
            lock = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return {}

    resolved: dict[str, list[tuple[str, str]]] = {}
    for package in lock.get("package", []):
        raw_name = package.get("name", "")
        if not raw_name:
            continue  # malformed lock entry — skip rather than key on ""
        name = canonical_name(raw_name)
        version = package.get("version", "")
        source_dict = package.get("source", {})
        label = "other"
        for key in source_dict:
            if key in _SOURCE_LABELS:
                label = _SOURCE_LABELS[key]
                break
        resolved.setdefault(name, []).append((version, label))
    return resolved


def _resolve_entries(
    entries: list[tuple[str, str]],
) -> tuple[str | None, str, tuple[str, ...]]:
    """Reduce a name's lock entries to (primary_version, source, locked_versions).

    Distinct versions are kept in lock order. A single distinct version is the
    common case: `locked_versions` is empty. Two or more distinct versions (a
    universal-lock fork or a [tool.uv].conflicts variant) mean `locked_versions`
    lists them all and the primary version is the first.
    """
    if not entries:
        return None, "registry", ()
    distinct = tuple(dict.fromkeys(version for version, _ in entries))
    source = entries[0][1]
    if len(distinct) > 1:
        return distinct[0], source, distinct
    return distinct[0], source, ()


def _collect_dependencies(
    pyproject: dict,
    resolved: dict[str, list[tuple[str, str]]],
    sources: dict[str, str] | None = None,
) -> list[Dependency]:
    project_table = pyproject.get("project", {})
    sources = sources or {}
    deps: list[Dependency] = []

    def add(requirement: str, group: str, kind: str) -> None:
        name, spec = split_requirement(requirement)
        version, source, locked_versions = _resolve_entries(resolved.get(name, []))
        deps.append(
            Dependency(
                name=name,
                spec=spec,
                group=group,
                resolved_version=version,
                source=source,
                kind=kind,
                locked_versions=locked_versions,
                source_detail=sources.get(name, ""),
            )
        )

    for requirement in project_table.get("dependencies", []):
        add(requirement, "main", "main")

    for group_name, reqs in project_table.get("optional-dependencies", {}).items():
        for requirement in reqs:
            add(requirement, group_name, "extra")

    for group_name, reqs in pyproject.get("dependency-groups", {}).items():
        kind = "dev" if group_name == "dev" else "group"
        for requirement in reqs:
            # PEP 735 allows {include-group = "..."} references. The referenced
            # group is rendered under its own heading, so skip the reference
            # here rather than treating the dict as a requirement string.
            if isinstance(requirement, dict):
                continue
            add(requirement, group_name, kind)

    return deps


def _source_detail(entry: object) -> str:
    """Summarize one [tool.uv.sources] entry as a short human string.

    uv allows a dict or a list of dicts (index-specific). Unknown shapes → "custom".
    """
    if isinstance(entry, list):
        parts = [_source_detail(item) for item in entry]
        return " / ".join(p for p in parts if p)
    if not isinstance(entry, dict):
        return ""
    if entry.get("workspace"):
        return "workspace"
    for key in ("git", "url", "path", "index"):
        value = entry.get(key)
        if value:
            detail = f"{key} ({value})"
            if entry.get("editable"):
                detail += " editable"
            return detail
    if entry.get("editable"):
        return "editable"
    return "custom"


def _tool_uv(pyproject: dict) -> dict:
    """Return the [tool.uv] table, or {} when tool / tool.uv isn't a dict.

    A malformed pyproject can make `tool` or `tool.uv` a non-dict (e.g. a string);
    chaining `.get` on it would raise, so each level is type-checked here.
    """
    tool = pyproject.get("tool")
    if not isinstance(tool, dict):
        return {}
    uv = tool.get("uv")
    return uv if isinstance(uv, dict) else {}


def _read_sources(pyproject: dict) -> dict[str, str]:
    """Return {canonical_name: source_detail} from [tool.uv.sources]."""
    sources = _tool_uv(pyproject).get("sources", {})
    if not isinstance(sources, dict):
        return {}
    result: dict[str, str] = {}
    for raw_name, entry in sources.items():
        detail = _source_detail(entry)
        if detail:
            result[canonical_name(raw_name)] = detail
    return result


def _read_workspace_members(root: Path, pyproject: dict) -> list[WorkspaceMember]:
    """Resolve [tool.uv.workspace] members (root first), or [] if not a workspace.

    `members`/`exclude` are glob patterns relative to the root. A directory is a
    member iff it has a pyproject.toml with a [project].name. Missing/unreadable
    member pyprojects are skipped rather than raising.
    """
    workspace = _tool_uv(pyproject).get("workspace")
    # Only the [tool.uv.workspace] table's ABSENCE means "not a workspace". A table
    # present but with empty/absent members is still a workspace whose sole member
    # is the root (spec: the root is always the first member).
    if not isinstance(workspace, dict):
        return []
    member_globs = workspace.get("members") or []
    if not isinstance(member_globs, list):
        member_globs = []

    excluded: set[Path] = set()
    for pattern in workspace.get("exclude") or []:
        try:
            matches = list(root.glob(pattern))
        except (ValueError, NotImplementedError, OSError):
            continue  # e.g. "." or an absolute path — skip the bad pattern
        excluded.update(p.resolve() for p in matches)

    root_name = pyproject.get("project", {}).get("name", root.name)
    members = [WorkspaceMember(name=root_name, directory="", is_root=True)]
    seen: set[str] = set()
    for pattern in member_globs:
        try:
            matches = sorted(root.glob(pattern))
        except (ValueError, NotImplementedError, OSError):
            continue  # e.g. "." or an absolute path — skip the bad pattern
        for path in matches:
            if not path.is_dir() or path.resolve() in excluded:
                continue
            # A `**` glob can match the root itself (duplicate) or hidden dirs like
            # `.venv`; neither is a real member.
            if path.resolve() == root.resolve():
                continue
            if any(p.startswith(".") for p in path.relative_to(root).parts):
                continue
            member_pyproject = path / "pyproject.toml"
            if not member_pyproject.is_file():
                continue
            try:
                with member_pyproject.open("rb") as fh:
                    member_data = tomllib.load(fh)
            except (tomllib.TOMLDecodeError, OSError):
                continue
            name = member_data.get("project", {}).get("name")
            if not name:
                continue
            rel = str(path.relative_to(root))
            if rel in seen:
                continue
            seen.add(rel)
            members.append(WorkspaceMember(name=name, directory=rel))
    return members


def _collect_groups(pyproject: dict) -> list[tuple[str, str]]:
    """Return every declared (name, kind) group, including empty ones.

    Derived from the TOML tables directly rather than from dependency leaves, so
    a group with no dependencies yet is still offered as an add target.
    """
    project_table = pyproject.get("project", {})
    groups: list[tuple[str, str]] = []
    for name in project_table.get("optional-dependencies", {}):
        groups.append((name, "extra"))
    for name in pyproject.get("dependency-groups", {}):
        groups.append((name, "dev" if name == "dev" else "group"))
    return groups


# --- environment (Python / venv) read path --------------------------------

# Matches a leading operator + bare "major.minor" in a requires-python string,
# e.g. ">=3.14", "==3.12", "~=3.11". Anything more complex is treated as unknown.
_REQUIRES_RE = re.compile(r"^\s*(>=|==|~=)\s*(\d+)\.(\d+)")

# A plain dotted version like "3", "3.14", "3.14.2". Pins that aren't plain
# versions (e.g. "pypy@3.10" or a full uv key) can't be compared to a bare venv
# version, so drift treats them as unknown rather than guessing.
_PLAIN_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def _read_pin(root: Path) -> str | None:
    """Return the pinned Python from `.python-version`, or None.

    uv writes one version per line; the first non-empty line is the active pin.
    Missing/blank/unreadable → None.
    """
    try:
        text = (root / ".python-version").read_text()
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _read_venv(cfg_path: Path) -> tuple[str | None, str | None]:
    """Return (python_version, home) from a `pyvenv.cfg`, or (None, None).

    pyvenv.cfg is a flat `key = value` file. uv writes `version_info = 3.14.0`;
    the stdlib venv writes `version = 3.14.0`. Either is accepted. Missing or
    unreadable file → (None, None).
    """
    try:
        text = cfg_path.read_text()
    except OSError:
        return None, None
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().lower()] = value.strip()
    version = values.get("version_info") or values.get("version")
    return version or None, values.get("home") or None


def _version_matches(version: str, prefix: str) -> bool:
    """True when `version` and `prefix` agree on their shared leading components.

    Component-wise over `min(len)` parts, so a major.minor venv (uv writes only
    `version_info = 3.14`) does NOT falsely mismatch a patch-level pin like "3.14.2":
    we compare "3.14" vs "3.14" and can't confirm the patch, so we don't flag drift.
    Conversely "3.1" still mismatches "3.14.x" (component "1" ≠ "14").
    """
    got = version.split(".")
    want = prefix.split(".")
    n = min(len(got), len(want))
    return n > 0 and got[:n] == want[:n]


def _compute_drift(
    venv_python: str | None, pinned: str | None, requires_python: str
) -> str | None:
    """Describe how the venv Python misaligns with the pin / requires-python.

    Conservative by design — never a false alarm; ambiguous cases return None:
    - A plain-version pin drives a shared-leading-component comparison. A pin that
      isn't a plain version (e.g. "pypy@3.10" or a full uv key) is uncomparable → None.
    - Without a pin, only a single bare `>=`/`==`/`~=` major.minor requires-python is
      compared. Compound specifiers (e.g. ">=3.9,<3.11") are unknown → None.
    """
    if not venv_python:
        return None
    if pinned:
        if not _PLAIN_VERSION_RE.match(pinned):
            return None
        if not _version_matches(venv_python, pinned):
            return f"venv Python {venv_python} ≠ pinned {pinned}"
        return None
    if "," in requires_python:
        return None
    match = _REQUIRES_RE.match(requires_python)
    if not match:
        return None
    op, major, minor = match.group(1), int(match.group(2)), int(match.group(3))
    parts = venv_python.split(".")
    try:
        got = (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return None
    want = (major, minor)
    if op in (">=", "~=") and got < want:
        return f"venv Python {venv_python} below requires-python {requires_python}"
    if op == "==" and got != want:
        return f"venv Python {venv_python} ≠ requires-python {requires_python}"
    return None


def _read_environment(root: Path, requires_python: str) -> Environment:
    """Compose the project's Python/venv state from files only."""
    pinned = _read_pin(root)
    venv_dir = root / ".venv"
    venv_python, _home = _read_venv(venv_dir / "pyvenv.cfg")
    venv_path = ".venv" if venv_dir.is_dir() else None
    drift = _compute_drift(venv_python, pinned, requires_python)
    return Environment(
        venv_path=venv_path,
        venv_python=venv_python,
        pinned_python=pinned,
        drift=drift,
    )


# uv-managed interpreters live under uv's data dir (…/uv/python/…); interpreters
# merely discovered on PATH (homebrew, /usr/bin, …) do not. `uv python uninstall`
# only removes managed ones, so the picker gates uninstall on this.
_MANAGED_PATH_MARKER = "/uv/python/"


def parse_python_list(output: str) -> list[PythonVersion]:
    """Parse `uv python list --output-format json` into PythonVersion rows.

    Preserves uv's `key` (the unambiguous request id) so same-`version` rows across
    implementations/variants stay distinct. A row is "installed" when uv reports a
    `path`, and "managed" when that path is under uv's managed-Python dir. Malformed
    or empty output → empty list.
    """
    try:
        entries = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    versions: list[PythonVersion] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        key = entry.get("key")
        if not version or not key:
            continue
        path = entry.get("path")
        installed = path is not None
        managed = installed and _MANAGED_PATH_MARKER in str(path).replace("\\", "/")
        versions.append(
            PythonVersion(
                key=key,
                version=version,
                implementation=entry.get("implementation") or "cpython",
                installed=installed,
                managed=managed,
                path=path,
            )
        )
    return versions


# --- global state (tools / cache / version) --------------------------------

# A `uv tool list` tool line: "<name> v<version>" (names are single tokens).
# `\s+` (not a literal space) tolerates any future padding change without silently
# dropping the whole tool row.
_TOOL_RE = re.compile(r"^(?P<name>\S+)\s+v(?P<version>\S+)")


def parse_tool_list(output: str) -> list[Tool]:
    """Parse `uv tool list` (plain text; uv emits no JSON here) into Tool rows.

    Each tool is a line `name vX.Y.Z` followed by indented `- executable` lines.
    Lines matching neither shape (e.g. "No tools installed") are ignored, so
    empty/absent output yields an empty list.
    """
    tools: list[Tool] = []
    name: str | None = None
    version = ""
    executables: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            exe = stripped.lstrip("-").strip()
            if name is not None and exe:
                executables.append(exe)
            continue
        match = _TOOL_RE.match(stripped)
        if not match:
            continue
        if name is not None:
            tools.append(Tool(name, version, tuple(executables)))
        name, version, executables = match.group("name"), match.group("version"), []
    if name is not None:
        tools.append(Tool(name, version, tuple(executables)))
    return tools


def parse_uv_version(output: str) -> str:
    """Extract a version like "0.11.31" from `uv --version` output.

    Falls back to the stripped raw string if no version-looking token is found.
    """
    match = re.search(r"\b(\d+\.\d+\.\d+\S*)", output)
    return match.group(1) if match else output.strip()


def directory_size(path: Path) -> int:
    """Total size in bytes of all files under `path` (0 if missing/unreadable).

    Uses `lstat` (does not follow symlinks) so shared link targets aren't double
    counted and dangling links don't raise. Tolerant of unreadable entries — a stat
    failure on one file is skipped rather than aborting the walk.
    """
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _exc: None):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                continue
    return total


def format_size(num_bytes: int) -> str:
    """Human-readable size, e.g. 0 -> "0 B", 1536 -> "1.5 KiB", 1048575 -> "1.0 MiB"."""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        # Promote on the *rounded* value so 1023.99 KiB shows as 1.0 MiB, not
        # "1024.0 KiB". TiB is the terminal unit (no further promotion).
        if unit == "B":
            if size < 1024:
                return f"{int(size)} B"
        elif unit == "TiB" or round(size, 1) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"
