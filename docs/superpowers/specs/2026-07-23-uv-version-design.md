# Milestone 7 — Project version (read / bump) — Design Spec

**Date:** 2026-07-23
**Status:** Implemented
**Follows:** v1 → M2 → M3 → M4 → M5 → M6 (`2026-07-23-tree-outdated-run-args-design.md`).
Implements the ROADMAP backlog item "**`uv version`** — read/bump the project version
from the UI."

## Problem

lazyuv already *shows* the project version (in the subtitle, `name X.Y.Z`, read from
`pyproject.toml`), but there is no way to **change** it. Bumping a version before a
release means dropping to the shell for `uv version --bump patch`. This milestone adds
in-UI version bumping (and explicit set), keeping uv authoritative for the write.

## Verified uv behavior (uv 0.11.31)

Probed against the installed `uv 0.11.31` before writing:

- **Read:** `uv version` → `name X.Y.Z`; `--short` → `X.Y.Z`; `--output-format json`
  → `{"package_name", "version", "commit_info"}`. lazyuv already reads the version from
  the file, so no subprocess read is added.
- **Set:** `uv version <VALUE>` → prints `name old => new` and writes `pyproject.toml`.
- **Bump:** `uv version --bump <kind>` where kind ∈ {major, minor, patch, stable,
  alpha, beta, rc, post, dev} → prints `name old => new`.
- **`--dry-run`** previews (`old => new`) without writing.
- **`--frozen`** updates the version without re-locking; the default (no flag)
  re-locks + syncs.
- **Workspace scoping:** unlike `uv tree`, `uv version` **is cwd-scoped** — run from a
  member directory it targets that member (verified: `alpha 2.0.0` from
  `packages/alpha`). So the existing M4 cwd mechanism is sufficient; **no `--package`**
  is needed.

## Decision & scope

A single **version action** (`V`, since `v` is venv) opens a small modal to bump or set
the project version; the mutation streams through the existing `run_streaming` seam and
the view re-reads (subtitle updates). In scope:

1. **Bump** via `uv version --bump {major,minor,patch}` — the three common bumps in a
   `Select`.
2. **Set** an explicit value via `uv version <VALUE>` — a free-text `Input` that, when
   non-empty, takes precedence over the bump select. This also covers the pre-release
   kinds (alpha/rc/post/…) without cluttering the UI: the user types `1.0.0rc1`.

The mutation runs with uv's **default** behavior (re-lock + sync, streamed), matching
how `add`/`lock`/`sync` already behave and keeping `uv.lock` consistent — not `--frozen`
(which would leave the lock's project version stale). On a project that needs no
re-resolution this is fast/offline; otherwise it streams like any sync and surfaces
failures on the Output panel.

Runs with `cwd=self.active_dir`, so in a workspace the focused member's version is
bumped (cwd-scoped, verified).

**Out of scope / non-goals:** the pre-release bump kinds as dedicated buttons (covered
by the explicit-value input); a `--dry-run` preview step (the current version is shown
for context and bump semantics are standard — YAGNI); `--package` targeting without
switching focus; editing `commit_info` / dynamic versioning.

## Read path

None added — `Project.version` already comes from `load_project` and is shown in the
subtitle. The modal is seeded with the current `name`/`version` from `self.project`.

## Commands (`commands.py`)

Pure argv builders; reuse `run_streaming` — no new seam.

```python
def build_version_bump(bump: str) -> list[str]:
    return ["uv", "version", "--bump", bump]

def build_version_set(value: str) -> list[str]:
    return ["uv", "version", value]
```

## UI (`app.py`, `screens/version.py`)

- **`VersionScreen(name, current)`** (`screens/version.py`) — a `ModalScreen` that shows
  `Current: <name> <version>`, a `Select` of bump kinds (`major`/`minor`/`patch`), and
  an `Input` for an explicit version. Dismisses with an intent:
  - `("set", value)` when the input is non-empty (takes precedence), else
  - `("bump", kind)` from the select, or
  - `None` on cancel/escape.
- **`action_version`** (`V`) — project-mode only; guarded on `self.project` and `_busy`.
  Opens the modal; on close runs `build_version_set(value)` / `build_version_bump(kind)`
  via `_run_uv` (streamed, `cwd=self.active_dir`). `refresh_project` re-reads the new
  version afterward, updating the subtitle.
- **`check_action`** — `version` added to `_PROJECT_ONLY_ACTIONS` (inert in global and
  script mode).
- Help overlay gains a `V` line; `styles.tcss` gets `#version-dialog`.
- File-sourced strings (`name`, `version`) are `escape()`d in the modal.

## Testing (TDD; `run_streaming`/`run_capture` remain the only mock points)

- **Commands (unit):** `build_version_bump` for each kind; `build_version_set`.
- **Integration (Pilot):** `V` opens the modal seeded with the current version;
  selecting `patch` → `["uv","version","--bump","patch"]`; a non-empty explicit value
  → `["uv","version","<value>"]` and overrides the select; `cwd == active_dir`; empty
  input falls back to the select; `V` inert in global/script mode; busy guard bells.
- **Real-uv check (skip-on-offline):** `build_version_bump("patch")` on a real
  dep-less `uv init` project actually rewrites `pyproject.toml` from `0.1.0` to
  `0.1.1` (read back via `load_project`); `build_version_set("9.9.9")` sets it exactly.
  Skips only on recognized network errors (the M5/M6 lesson) — any other nonzero exit
  fails.

## Open questions

- Should the modal offer a dry-run preview of the resulting version? Draft omits it
  (standard semantics, current version shown). Revisit if users want confirmation for
  the pre-release kinds.
- Should a bump run `--frozen` (fast, pyproject-only) instead of the default re-lock?
  Draft uses the default for lock consistency; revisit if the re-lock proves annoying
  on large projects.
