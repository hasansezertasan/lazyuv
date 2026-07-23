# Milestone 6 — Dependency Tree, Outdated View & Run Arguments — Design Spec

**Date:** 2026-07-23
**Status:** Implemented
**Follows:** v1 → M2 → M3 → M4 → M5 (`2026-07-24-inline-scripts-design.md`).
Implements three ROADMAP backlog items promoted into a milestone: **dependency tree
view** (`uv tree`), **outdated / upgrade view**, and **run scripts with arguments**.
The fourth candidate (diff view) is explicitly deferred.

## Problem

Three gaps send users back to the shell:

1. **No transitive view.** The dependency panel shows *declared* deps with resolved
   versions, but not the transitive graph — you can't see *why* a package is present.
2. **No outdated signal.** M4 added a targeted upgrade (`u` →
   `uv lock --upgrade-package <name>`), but nothing tells you *which* packages have a
   newer release, so the upgrade key fires blind.
3. **Run takes no arguments.** `r` runs a project script or an inline script with no
   way to pass CLI args (v1/M5 limitation), so any script needing flags can't be run.

## Verified uv behavior (uv 0.11.31)

Probed against the installed `uv 0.11.31` before writing (the M2–M5 lesson):

- **`uv tree --format json`** emits a JSON graph on **stdout**; the "experimental …
  schema may change" notice goes to **stderr** (so `run_capture`, which drops stderr,
  returns clean JSON). Shape:
  ```jsonc
  {
    "schema": {"version": "preview"},   // preview → parse defensively
    "roots": [{"id": "<pkgid>"}],
    "inverted": false,
    "members": [...],
    "resolution": {
      "<pkgid>": {
        "name": "rich", "version": "13.0.0", "kind": "package",
        "dependencies": [{"id": "<childid>"}, ...],   // edges into `resolution`
        "latest_version": "15.0.0",   // present only with --outdated
        "source": {...}, "wheels": [...]
      }
    }
  }
  ```
  The tree is a DAG built by resolving each `roots[].id` in `resolution` and following
  `dependencies[].id` edges. `uv tree`'s text output **de-duplicates** repeated
  subtrees; we mirror that (a node id already expanded shows once, not re-expanded) so
  the tree stays finite even with shared/cyclic deps.
- **`uv tree --outdated --format json`** adds `latest_version` to every node. A package
  is **outdated** iff `latest_version` is present and `!= version`. `--outdated` hits
  the network to look up latest releases (can be slow / fail offline).
- **`uv tree --frozen`** works and does not modify the lock — so both reads run
  `--frozen` to stay read-only (the ROADMAP "reads don't mutate" principle). `--frozen`
  still allows `--outdated` to query latest.
- **Run with arguments:** `uv run <target> <args…>` passes args straight to the program
  — including leading-dash args (`--verbose`) and even uv-looking flags (`--python`),
  because uv stops consuming its own options once the target is seen. Injecting a `--`
  separator is **wrong**: `uv run f.py -- --verbose` delivers a literal `--` to the
  program. So we append args directly, with **no** `--`. Verified for both `uv run
  <file>`/named target and `uv run --script <file>`.

## Decision & scope

Deliver a coherent "inspect & run" slice, reusing existing seams and the M4 upgrade key.

1. **Tree view** — `t` (project mode) opens a **read-only modal** rendering
   `uv tree --frozen --format json` as a collapsible Textual `Tree`. Pure inspection;
   no mutation, so a modal (not a mode) keeps it simple.
2. **Outdated view** — `O` (project mode) fetches `uv tree --frozen --outdated
   --format json`, and **annotates the existing dependency panel**: outdated leaves
   render `name  cur → latest` with a marker, and the panel title shows the count.
   This is the tightest possible integration with `u` — the user highlights a flagged
   dep and presses `u` (existing `uv lock --upgrade-package`). `O` again clears it.
3. **Run with arguments** — `R` (project *and* script mode) opens a one-field prompt;
   the string is `shlex.split` into argv and appended to the run command. `r` keeps its
   quick no-arg behavior.

**Deferred:** the diff view (preview a pending `uv lock`/`uv sync`) — a separate slice.
Also non-goals: `uv tree --invert`/`--package`/`--prune`/`--depth` controls (the modal
shows the full deduped tree; add filters later if needed), an editable tree, and
outdated for inline scripts (`uv tree` is project-scoped; scripts have no tree).

## Read path (`data.py`, subprocess *queries* via `run_capture`)

`uv tree` can't be reconstructed from files (it's the resolver's transitive graph), so
it uses the read-only `run_capture` query seam (like `uv python list`), not file reads.

- `parse_tree(output: str) -> list[DepTreeNode]` — parse the JSON, resolve each
  `roots[].id`, and recurse over `dependencies` edges into `resolution`. A node id
  already expanded anywhere is emitted as a childless `deduped=True` node (mirrors uv's
  text dedupe and bounds cycles); a hard depth cap is a further backstop. Malformed
  JSON, missing `resolution`, or a dangling edge id → best-effort (empty list / skip
  the edge), never a raise.
- `parse_outdated(output: str) -> dict[str, str]` — from the same JSON, return
  `{canonical_name: latest_version}` for every node whose `latest_version` is set and
  `!= version`. Keyed by `canonical_name` so it matches the declared deps the panel
  renders. Malformed → `{}`.

Both are pure functions over captured stdout (no file reads, no new seam).

## Model (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class DepTreeNode:
    name: str
    version: str
    latest_version: str | None = None   # set only from --outdated
    children: tuple[DepTreeNode, ...] = ()
    deduped: bool = False                # repeated node, not re-expanded
```

Outdated is a plain `dict[str, str]` (name → latest) held on the app; no new model.

## Commands (`commands.py`)

Pure argv builders. Tree/outdated use `run_capture` (queries); run-with-args uses
`run_streaming` (unchanged seam).

```python
def build_tree(*, outdated: bool = False, frozen: bool = True) -> list[str]:
    argv = ["uv", "tree", "--format", "json"]
    if frozen:   argv.append("--frozen")
    if outdated: argv.append("--outdated")
    return argv

# args appended directly — NO `--` separator (verified: uv passes them through).
def build_run(script: str, args: Sequence[str] = ()) -> list[str]:
    return ["uv", "run", script, *args]

def build_run_script(path: str, args: Sequence[str] = ()) -> list[str]:
    return ["uv", "run", "--script", path, *args]
```

`build_run`/`build_run_script` gain an optional `args` (default `()`), so existing
no-arg callers are unchanged.

## UI (`app.py`, `widgets/`, `screens/`)

- **Tree modal** (`screens/tree.py`, `DependencyTreeScreen`): a `ModalScreen` wrapping a
  scrollable Textual `Tree` built from `list[DepTreeNode]`; nodes collapsible; outdated
  nodes (if latest known) annotated. `t` in project mode marks `_busy`, fetches via a
  worker (`run_capture(build_tree())`), then pushes the modal — the fetch never blocks
  the event loop (Python-picker pattern). Read-only; Esc closes. Gated off in
  global/script mode and when there is no project.
- **Outdated annotation**: `O` in project mode marks `_busy`, shows a transient
  "checking…" on the panel title, fetches `run_capture(build_tree(outdated=True))` in a
  worker, parses to a `{name: latest}` map stored as `self._outdated`, and calls
  `DependenciesPanel.set_outdated(map)`. Pressing `O` again clears it. Network failure /
  non-zero exit surfaces on the Output panel (like the Python-list read); it never
  crashes or fakes data. Selecting an annotated dep + `u` runs the existing
  `uv lock --upgrade-package`.
- **Run with args** (`screens/run_args.py`, `RunArgsScreen`): a single `Input`
  returning the raw string (or `None`). `R` (project *and* script mode): resolves the
  target (selected `[project.scripts]` entry in project mode, focused inline script in
  script mode), opens the modal, `shlex.split`s the result, and runs
  `build_run(name, args)` / `build_run_script(path, args)`. An empty string runs with no
  args (== `r`). A `shlex` parse error (unbalanced quotes) surfaces on Output, no run.
- **`DependenciesPanel`**: add `self._outdated: dict[str, str] = {}` and remember the
  current `self._dependencies`; `set_filter` stores both. New `set_outdated(mapping)`
  stores the map and re-populates. In `_populate`, an outdated leaf renders
  `name  cur → latest` (a marker/style) and the border title gains `— outdated: N`.
  External callers of `set_filter` are unchanged.
- **Keybindings / `check_action`**: `t` and `O` are **project-only**; `R` is
  **project + script** (like `run`). Added to `BINDINGS`, gated in `check_action`, and
  documented in the help overlay. New dialog ids added to `styles.tcss`.

## Testing (TDD; `run_streaming`/`run_capture` remain the only mock points)

- **Read path (unit):** `parse_tree` — roots + edges into a nested structure, dedupe of
  a repeated node, a cycle bounded, a dangling edge skipped, malformed JSON → `[]`.
  `parse_outdated` — picks nodes with `latest_version != version`, ignores equal/absent,
  canonical-name keys, malformed → `{}`.
- **Commands (unit):** `build_tree` (bare, `outdated=True`, `frozen=False`);
  `build_run`/`build_run_script` with and without args (arg order, no `--`, leading-dash
  arg preserved).
- **Integration (Pilot):** `t` opens the tree modal populated from mocked `run_capture`
  JSON; `O` annotates the panel (outdated leaf shows `cur → latest`, title count) and a
  second `O` clears it; selecting an outdated dep + `u` builds the upgrade argv; `R`
  prompts, and project/script mode each build the expected `uv run …args` argv (with a
  quoted/space arg preserved and no `--`); `t`/`O` inert in global/script mode, `R` inert
  in global mode.
- **Real-uv checks (a few, guarded/skip-on-offline):** `build_tree()` output parses via
  `parse_tree` into ≥1 root with children; `build_tree(outdated=True)` yields a
  `latest_version` that `parse_outdated` surfaces for a deliberately old pin; a
  `uv run … <args>` actually delivers the args to the program (asserting the no-`--`
  contract end-to-end). Skips only on recognized network errors — any other nonzero
  exit fails (the M5 lesson).

## Open questions

- Should the tree modal fetch with `--outdated` too (one view for items 1+2), or keep
  the fast offline tree separate from the networked outdated annotation? Draft keeps
  them separate: `t` is instant/offline, `O` is the networked overlay on the panel that
  feeds `u`. Revisit if users want latest-versions inside the tree.
- Outdated highlighting for transitive (indirect) packages: the panel only shows
  declared deps, so only those are annotated; a transitively-outdated package surfaces
  only in the tree. Acceptable for a first cut.
