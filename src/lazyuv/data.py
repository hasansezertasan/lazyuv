"""Load a uv project from pyproject.toml + uv.lock into domain models.

This module never runs subprocesses; it only reads files.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from lazyuv.models import (
    Dependency,
    LoadResult,
    LoadStatus,
    Project,
    Script,
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


def load_project(root: Path) -> LoadResult:
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return LoadResult(status=LoadStatus.NOT_A_PROJECT)

    try:
        with pyproject_path.open("rb") as fh:
            pyproject = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return LoadResult(status=LoadStatus.MALFORMED, error=str(exc))

    resolved = _read_lock(root / "uv.lock")

    project_table = pyproject.get("project", {})
    dependencies = _collect_dependencies(pyproject, resolved)
    scripts = [
        Script(name=name, target=target)
        for name, target in sorted(project_table.get("scripts", {}).items())
    ]

    project = Project(
        name=project_table.get("name", root.name),
        version=project_table.get("version", "0.0.0"),
        requires_python=project_table.get("requires-python", ""),
        dependencies=dependencies,
        scripts=scripts,
        groups=_collect_groups(pyproject),
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
    pyproject: dict, resolved: dict[str, list[tuple[str, str]]]
) -> list[Dependency]:
    project_table = pyproject.get("project", {})
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
