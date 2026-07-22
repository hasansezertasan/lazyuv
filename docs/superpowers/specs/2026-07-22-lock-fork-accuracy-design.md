# Multiple Locked Versions (Fork/Conflict Accuracy) — Design Spec

**Date:** 2026-07-22
**Status:** Approved for implementation
**Follows:** v1 (`2026-07-21-lazyuv-design.md`). Addresses the ROADMAP backlog item
"Universal-lock fork accuracy" (raised in PR #1 review).

## Problem

A `uv.lock` can contain multiple `[[package]]` entries for the same package:

- **Resolution forks** — universal locks keyed by `resolution-markers` (different
  versions for different Python versions / platforms).
- **Conflict variants** — `[tool.uv].conflicts` selecting different versions from
  mutually exclusive extras/groups (no `resolution-markers`).

v1's `_read_lock` built a `{name: (version, source)}` map with last-write-wins, so a
package with several entries displayed whichever appeared last — arbitrary and
potentially wrong.

## Decision

**Surface every distinct locked version; don't claim to know which applies.** lazyuv
does not evaluate environment markers or resolve `[tool.uv].conflicts` (that would
require marker/conflict evaluation and likely the `packaging` dependency, breaking
the single-runtime-dependency constraint). So it uses neutral wording — it reports
the versions present in the lock without labeling *why* there are several or scoping
them to a particular extra:

- One locked version → unchanged (`httpx  0.28.1`).
- Several distinct versions → list them in lock-file order with a neutral count
  (`httpx  0.27.0 / 0.28.1  (2 versions)`).

Lock-file order is the deterministic display order — no version comparison, so no
naive-sort bugs.

## Changes

### Model (`models.py`)
Add to `Dependency`:
- `locked_versions: tuple[str, ...] = ()` — all distinct versions when the lock has
  more than one for the package (length ≥ 2); empty when there are 0 or 1 distinct
  versions (repeated entries of the same version do not count).
- `resolved_version` keeps its meaning: the sole version when there's one entry,
  `None` when unlocked. When there are several, it holds the first (a stable
  primary); `locked_versions` is the authoritative multi-value view.

### Data (`data.py`)
- `_read_lock` returns `dict[str, list[tuple[str, str]]]` — every `(version, source)`
  entry per canonical name, in lock order (nameless entries still skipped).
- `_resolve_entries` reduces a name's entries to
  `(primary_version, source, locked_versions)`: 0 entries →
  `(None, "registry", ())`; 1 distinct version → `(v, source, ())`; ≥2 distinct →
  `(first, source, all-distinct)`. `source` uses the first entry's label.

### UI
- `widgets/dependencies.py`: leaf label shows
  `" / ".join(locked_versions) + " (N versions)"` when several, else the single
  version (or `—`).
- `widgets/details.py`: when several, the version line lists all versions and adds a
  `locked: N versions in lock` line; otherwise unchanged.

## Testing
- `_read_lock` keeps all entries for a repeated name; nameless still skipped.
- `_resolve_entries` via `load_project`: several distinct versions →
  `locked_versions` in lock order with `resolved_version` = first; a single distinct
  version (even across duplicate entries) → `locked_versions == ()`.
- End-to-end tree label shows `0.27.0 / 0.28.1  (2 versions)`.

## Non-goals
- Evaluating `resolution-markers` to pick the environment-applicable fork, or
  resolving `[tool.uv].conflicts` to scope a version to its extra/group. Both need
  marker/conflict evaluation (i.e. `packaging`). Consequently, for conflict variants
  a declaration may list versions belonging to other extras — an accepted best-effort
  limitation, tracked in `ROADMAP.md`.
- Version sorting (display follows lock order).
