# Universal-lock Fork Accuracy — Design Spec

**Date:** 2026-07-22
**Status:** Approved for implementation
**Follows:** v1 (`2026-07-21-lazyuv-design.md`). Addresses the ROADMAP backlog item
"Universal-lock fork accuracy" (raised in PR #1 review).

## Problem

A universal `uv.lock` can contain multiple `[[package]]` entries for the same
package — resolution *forks* keyed by `resolution-markers` (e.g. different versions
for different Python versions or platforms). v1's `_read_lock` builds a
`{name: (version, source)}` map with last-write-wins, so a forked package displays
whichever fork appeared last in the lock — arbitrary and potentially wrong.

## Decision

**Show all distinct fork versions** rather than picking one. lazyuv does not evaluate
environment markers (that would require `packaging` or a hand-rolled marker
evaluator, breaking the single-runtime-dependency constraint). Instead it surfaces
the ambiguity honestly:

- Single resolved version → unchanged (`httpx  0.28.1`).
- Multiple distinct versions → list them in lock-file order with a count
  (`httpx  0.27.0 / 0.28.1  (2 forks)`).

Lock-file order is the deterministic display order — no version comparison, so no
naive-sort bugs.

## Changes

### Model (`models.py`)
Add to `Dependency`:
- `fork_versions: tuple[str, ...] = ()` — all distinct resolved versions when the
  package is forked (length ≥ 2); empty when there is 0 or 1 lock entry.
- `resolved_version` keeps its meaning: the sole version when not forked, `None`
  when unlocked. When forked, it holds the first fork version (a stable primary);
  `fork_versions` is the authoritative multi-value view.

### Data (`data.py`)
- `_read_lock` returns `dict[str, list[tuple[str, str]]]` — every `(version, source)`
  entry per canonical name, in lock order (nameless entries still skipped).
- `_collect_dependencies` builds `fork_versions` from the distinct versions
  (order-preserving dedupe). 0 entries → `resolved_version=None, fork_versions=()`.
  1 distinct version → `resolved_version=v, fork_versions=()`. ≥2 →
  `resolved_version=first, fork_versions=(all distinct)`. `source` uses the first
  entry's label.

### UI
- `widgets/dependencies.py`: leaf label shows `" / ".join(fork_versions) + " (N forks)"`
  when forked, else the single version (or `—`).
- `widgets/details.py`: when forked, the version line lists all versions and adds a
  `forks:` line; otherwise unchanged.

## Testing
- `_read_lock` returns all entries for a forked name; nameless still skipped.
- `_collect_dependencies`: forked package → `fork_versions` has the distinct
  versions in order, `resolved_version` is the first; non-forked unchanged
  (`fork_versions == ()`).
- Details/label rendering for a forked dependency (via the panel or a direct call).

## Non-goals
- Marker evaluation / picking the environment-applicable fork (would need
  `packaging`). Tracked separately if ever wanted.
- Version sorting (display follows lock order).
