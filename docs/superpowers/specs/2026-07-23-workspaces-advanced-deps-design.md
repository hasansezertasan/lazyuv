# Milestone 4 — Workspaces & Advanced Dependencies — Design Spec

**Date:** 2026-07-23
**Status:** Implemented
**Follows:** v1 → M2 → M3 (`2026-07-22-global-tools-cache-design.md`). Implements
ROADMAP "Milestone 4 — Workspaces & advanced dependencies".

## Problem

lazyuv handles a single project and machine-wide state, but not two real-world
shapes: **uv workspaces** (a monorepo of member packages under
`[tool.uv.workspace]`) and the **advanced dependency** operations power users reach
for — a targeted single-package upgrade, exporting a `requirements.txt`, and seeing
where a dependency actually comes from (`[tool.uv.sources]`). Today all of these
send the user back to the shell.

## Decision & scope

Deliver a coherent, reviewable slice that satisfies the milestone's core intent,
and **explicitly defer** the one piece the ROADMAP itself flagged as uncertain
(TUI editing of sources/indexes). In scope:

1. **Workspaces** — detect `[tool.uv.workspace]`, list members, and *switch focus*
   to a member, which re-scopes the existing project panels to that member (it is
   the "constrained project switcher" the backlog anticipated). Member-targeted
   commands run in the focused member's directory.
2. **Targeted upgrade** — `uv lock --upgrade-package <name>` on the selected
   dependency.
3. **Export** — a modal → `uv export` (`--format`, `--no-hashes`, `--no-dev`,
   `--extra`/`--group` selection, `-o <file>`).
4. **Sources (display)** — parse `[tool.uv.sources]` and show *where each dependency
   comes from* (workspace / git / path / url / editable) in the Details panel.

**Deferred (documented resolution of the ROADMAP open question):** *editing* sources
and managing `[[tool.uv.index]]` entries from the TUI. Rationale: source/index
declarations are config that is safer to edit in `$EDITOR` (multi-field, easy to get
subtly wrong via a modal), and the read path already surfaces them for inspection.
`uv add --git/--path/--index` mutation and an outdated view (backlog) are left for a
follow-up. This trims the milestone's "change a dependency's source" to *see* a
dependency's source; noted here and in the ROADMAP so it isn't a silent drop.

## Read path (files, no subprocess)

Workspace and source state live in `pyproject.toml`, so this stays on v1's
"read files for display" path.

- **Workspace members** — from the project-root `[tool.uv.workspace]`: `members`
  (list of glob patterns, relative to root) minus `exclude`. Each glob is expanded
  against the root dir; a directory is a member iff it has a `pyproject.toml` with a
  `[project].name`. The root project itself is always the first "member" (focus =
  root). Result: an ordered list of `(name, relative_dir)`.
- **Sources** — from `[tool.uv.sources]`: a `{canonical_name: source_detail}` map,
  where `source_detail` is a short human string derived from the entry's keys
  (`{workspace=true}` → "workspace", `{git=…}` → "git (<url>)", `{path=…}` →
  "path (<path>)", `{url=…}` → "url (<url>)", `editable` noted). Attached to each
  `Dependency` so the Details panel can show it.

Both parsers live in `data.py` (files only). Switching focus to a member is just
`load_project(root / member_dir)` — the entire existing pipeline (deps, scripts,
environment, sources) is reused for the member, so no member-specific rendering code
is needed.

## Model (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    name: str            # [project].name of the member (or root)
    directory: str       # relative to the workspace root; "" for the root itself
    is_root: bool = False
```

`Project` gains:
- `source_detail: str = ""` on `Dependency` — "" when the dep has no
  `[tool.uv.sources]` entry (the common case); otherwise the short string above.
- `workspace_members: list[WorkspaceMember] = []` on `Project` — empty when the
  project is not a workspace root. Additive/default, like `environment`.

## Commands (`commands.py`)

Pure argv builders; reuse `run_streaming` (mutations/export stream) — no new seam.

```python
def build_lock_upgrade_package(name)   # ["uv", "lock", "--upgrade-package", name]
def build_export(*, fmt="requirements.txt", no_hashes=False, no_dev=False,
                 extras=(), groups=(), output_file=None) -> list[str]
    # ["uv","export","--format",fmt, *(--extra X..), *(--group G..),
    #   *(["--no-hashes"] if..), *(["--no-dev"] if..), *(["-o",file] if file)]
```

Member scoping reuses existing builders with `cwd=<member dir>` (the app passes the
focused member's absolute directory as `cwd` to `run_streaming`), matching how uv
resolves the active project — no `--package` needed because we run *in* the member
dir. (`build_run`/`build_sync`/`build_add`/`build_remove` are unchanged.)

## UI

- **Workspace panel** (`widgets/workspace.py`) — shown in the left column *only when
  a workspace is detected* (members non-empty); lists members with the focused one
  marked. Selecting/activating a member (Enter, or the `w` switcher modal) sets the
  app's `focused_member` and reloads via `load_project(member_dir)`; the subtitle
  shows `root · member`. A uv workspace keeps a single lockfile at the workspace
  root, so a focused member reads that root `uv.lock` (via `lock_root`) to resolve
  its deps. Creating a venv is a root-scope operation (the venv is shared at the
  workspace root), so `v` is disabled while a non-root member is focused.
- **Targeted upgrade** — `u` in project mode: `uv lock --upgrade-package <dep>` on the
  selected dependency (streamed like any mutation). (`u` upgrades the selected package
  in project mode and the selected tool in global mode — the universal upgrade key.)
- **Export** — `e` opens `screens/export.py` (a modal): output filename (default
  `requirements.txt`), `--no-hashes` / `--no-dev` checkboxes, and extras/groups
  multi-selects (reusing the sync-options widget shape). Returns the selections;
  the app runs `build_export(...)`. Output streams to the Output panel; `-o` writes
  the file.
- **Sources** — `DetailsPanel.show_dependency` appends a `via: <detail>` line when
  `dep.source_detail` is set (escaped, like the other panels).
- **Keybindings** — `w` (workspace switcher) and `e` (export) added to project mode;
  `u` (targeted upgrade) is project-mode via `check_action`. All gated off in global
  mode. Help overlay updated.

## Testing

Pilot-based; `run_streaming`/`run_capture` remain the only mock points.

- **Read path (unit):** workspace member resolution (globs, `exclude`, a dir without
  `pyproject`, the root-as-member, a non-workspace project → empty); source_detail
  for each entry kind; `load_project(member_dir)` yields the member's own deps.
- **Commands (unit):** `build_lock_upgrade_package` argv; `build_export` with every
  option combination and the bare default.
- **Integration (Pilot):** workspace panel appears only for a workspace; switching a
  member re-scopes the deps tree and subtitle; `u` builds the upgrade-package argv on
  the selected dep; export modal produces the expected `uv export` argv and streams;
  Details shows a source line; `w`/`e` no-op in global mode.

## Non-goals

- **Editing** `[tool.uv.sources]` / `[[tool.uv.index]]` from the TUI (deferred; see
  scope). Index entries are not shown in M4.
- **Nested/remote workspaces**, `--package` targeting across arbitrary members
  without switching focus (we re-scope by cwd instead).
- **Outdated view** (backlog; pairs with targeted upgrade later).
- **`uv export` to non-requirements formats** beyond passing `--format` through.

## Open questions

- Should the workspace panel replace the Environment panel in the left column when a
  workspace is focused, or stack above it? Draft stacks it at the top when present.
- Export default filename / overwrite behavior — draft defaults to `requirements.txt`
  in the (member) project dir and lets `uv export -o` overwrite.
