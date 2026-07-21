"""Lightweight PEP 508 / PEP 503 helpers (avoids a `packaging` dependency)."""

from __future__ import annotations

import re

# The name is the leading run of letters/digits/._- ; everything after the name,
# an extras bracket, or a marker/version operator is the specifier.
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_CANON_RE = re.compile(r"[-_.]+")


def canonical_name(name: str) -> str:
    """Normalize a project name per PEP 503."""
    return _CANON_RE.sub("-", name).lower()


def split_requirement(requirement: str) -> tuple[str, str]:
    """Split a PEP 508 requirement into (canonical_name, version_spec).

    Extras and environment markers are dropped from the spec.
    """
    match = _NAME_RE.match(requirement)
    if not match:
        return canonical_name(requirement.strip()), ""
    name = match.group(1)
    rest = requirement[match.end():]

    # Drop an extras bracket: httpx[socks]>=1 -> >=1
    rest = re.sub(r"^\s*\[[^\]]*\]", "", rest)
    # Drop an environment marker: ">=1 ; python_version>'3'" -> ">=1"
    rest = rest.split(";", 1)[0]

    return canonical_name(name), rest.strip()
