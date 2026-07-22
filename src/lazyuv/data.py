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
    )
    return LoadResult(status=LoadStatus.OK, project=project)


def _read_lock(lock_path: Path) -> dict[str, tuple[str, str]]:
    """Return {canonical_name: (version, source_label)} from uv.lock.

    Returns an empty mapping if the lock is missing or unreadable — the UI
    still shows declared deps, just without resolved versions.
    """
    if not lock_path.is_file():
        return {}
    try:
        with lock_path.open("rb") as fh:
            lock = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return {}

    resolved: dict[str, tuple[str, str]] = {}
    for package in lock.get("package", []):
        name = canonical_name(package.get("name", ""))
        version = package.get("version", "")
        source_dict = package.get("source", {})
        label = "other"
        for key in source_dict:
            if key in _SOURCE_LABELS:
                label = _SOURCE_LABELS[key]
                break
        resolved[name] = (version, label)
    return resolved


def _collect_dependencies(
    pyproject: dict, resolved: dict[str, tuple[str, str]]
) -> list[Dependency]:
    project_table = pyproject.get("project", {})
    deps: list[Dependency] = []

    def add(requirement: str, group: str, kind: str) -> None:
        name, spec = split_requirement(requirement)
        version, source = resolved.get(name, (None, "registry"))
        deps.append(
            Dependency(
                name=name,
                spec=spec,
                group=group,
                resolved_version=version,
                source=source,
                kind=kind,
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
