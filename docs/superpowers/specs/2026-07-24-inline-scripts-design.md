# Milestone 5 — Inline Scripts (PEP 723) — Design Spec

**Date:** 2026-07-23
**Status:** Implemented
**Follows:** v1 → M2 → M3 → M4 (`2026-07-23-workspaces-advanced-deps-design.md`).
Implements ROADMAP "Milestone 5 — Inline scripts (PEP 723)".

## Problem

uv supports **standalone scripts** whose dependencies live *in the script file* as a
[PEP 723](https://peps.python.org/pep-0723/) inline-metadata block, with no
`pyproject.toml`:

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "requests>=2.34.2",
#     "rich>=13",
# ]
# ///
print("hello")
```

This is a distinct uv workflow from projects: `uv add --script <file> <pkg>`,
`uv remove --script <file> <pkg>`, and `uv run <file>`. lazyuv today only knows about
project (`pyproject.toml`) surfaces, so a user editing a script's inline deps or
running it must drop back to the shell. M5 brings the script workflow into the same
panel vocabulary lazyuv already uses for project dependencies.

## Verified uv behavior (uv 0.11.31)

All of the following were probed against the installed `uv 0.11.31` before writing
this spec (not from docs — version-pinned verification is the M2–M4 lesson):

- `uv add --script demo.py requests` on a file **with no block** *creates* the block
  (inserting `# /// script … # ///` at the top, or **after a shebang** if present),
  seeding `requires-python` from the environment and adding the requirement with a
  resolved lower-bound specifier (`requests>=2.34.2`).
- `uv add --script demo.py "rich>=13"` appends to the existing `dependencies` list,
  preserving the user's specifier verbatim.
- `uv remove --script demo.py rich` drops that entry; removing the **last** dep leaves
  `dependencies = []` (the block and `requires-python` are **not** deleted).
- `uv run demo.py` and `uv run --script demo.py` both run the file; `--script` is the
  explicit, unambiguous form (a plain `uv run <name>` could resolve a project entry
  point). A file with **no** block runs fine too. **We use `--script` explicitly.**
- `uv lock --script demo.py` writes a **companion lockfile** next to the script named
  `demo.py.lock` (the file name with `.lock` appended). Its `[[package]]` entries have
  the **same shape** as `uv.lock` (`name`, `version`, `source = { registry = … }`), so
  the existing `_read_lock` reader is reusable to resolve versions for display. `uv add
  --script` / `uv run --script` also create/update this `.lock` when they resolve.
- The block may carry more than `requires-python`/`dependencies` — e.g.
  `uv add --script f.py idna --index <url>` adds a nested `# [[tool.uv.index]]` table.
  Extracting the block's text (strip the leading `# ` / `#`) and parsing it with
  `tomllib` handles this uniformly; we only read `requires-python` + `dependencies`.

PEP 723 extraction is the reference regex, matching uv's own writer:

```python
_PEP723_RE = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)
```

Only a block whose `type` is `script` is metadata. Per PEP 723, **more than one**
`script` block is an error; to stay crash-safe we treat "0 or >1 blocks" as "no inline
metadata" (empty deps) rather than raising — the file is still openable and `uv add
--script` will create/repair the single canonical block.

## Decision & scope

Resolve the ROADMAP open question — *"a mode in the main app, or a separate entry
point (`lazyuv script foo.py`)?"* — in favor of **a mode inside the existing app**,
peer to project mode and global mode. This reuses the dependency panel, the modal
patterns, the single subprocess seams, and the `check_action` mode-gating already in
place; a separate entry point would fork all of that. In scope:

1. **Script mode** — a third top-level mode (project | global | **script**). Entered by
   picking a `.py` file; the left column shows that file's inline dependencies in the
   **same `DependenciesPanel`** used for project deps.
2. **Read path** — parse the PEP 723 block from the `.py` file into the existing
   `Dependency` shape (all under one synthetic `script` group), resolving versions from
   the companion `<file>.lock` when present. Files only, no subprocess.
3. **Add / remove / run** — `uv add --script`, `uv remove --script`, `uv run --script`,
   dispatched by the same `a` / `d` / `r` keys, which branch on the active mode.
4. **Script picker** — a modal listing `.py` files discovered under the active dir, to
   enter or switch the focused script.

**Out of scope (YAGNI / deferred):** editing `requires-python` or `[tool.uv]` tables in
the block from the TUI (safer in `$EDITOR`, like M4's source/index editing); a separate
`lazyuv script <file>` CLI entry; `uv lock --script` / `uv sync --script` /
`uv export --script` for scripts; running a script with arguments (backlog item
already tracked for project scripts); a filter box in script mode (deps are few).

## Read path (`data.py`, files only)

New, subprocess-free, mirroring the project read path:

- `parse_pep723_block(text: str) -> dict | None` — extract the single `script` block,
  strip the comment prefixes, `tomllib.loads` the reconstructed TOML, and return the
  metadata dict. Returns `None` when there is no block, more than one block, or the
  content fails to parse (crash-safe: an unparseable/duplicated block reads as "no
  inline metadata", not an exception).
- `load_script(path: Path) -> InlineScript | None` — read the file, call
  `parse_pep723_block`, build `Dependency` rows from `metadata["dependencies"]` (via
  the existing `split_requirement`, `group="script"`, `kind="script"`), and resolve
  versions from `path.with_name(path.name + ".lock")` using the **existing** `_read_lock`
  (+ `_resolve_entries`) helpers. Returns `None` only when the file itself can't be
  read (surface an error; stay in project mode). A readable `.py` with **no** block
  yields an `InlineScript` with `has_block=False` and no deps (still runnable; `uv add
  --script` will create the block).
- `find_scripts(root: Path) -> list[str]` — a bounded walk of `root` returning
  relative paths of `*.py` files, skipping any path component starting with `.`
  (so `.venv`, `.git`, … are excluded), sorted, capped (e.g. 500) with the cap
  `log`-noted if hit — never a silent truncation. Feeds the script picker.

## Model (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class InlineScript:
    path: str                              # the .py path as given (for display + argv)
    requires_python: str = ""              # from the block, "" if absent
    dependencies: list[Dependency] = ()    # group/kind == "script"
    has_block: bool = False                # a PEP 723 script block was present
```

`Dependency` is reused unchanged: script deps get `group="script"`, `kind="script"`.
The new `kind` value is inert in `_group_flags` (falls through to the `--optional`
branch) but is **never** routed through project builders — script add/remove use the
dedicated `--script` builders below, so the flag mapping is not exercised for scripts.

## Commands (`commands.py`)

Pure argv builders; reuse `run_streaming` (mutations/run stream live) — **no new
seam**. `path` is passed as-is (the picker yields a path relative to the active dir,
which is also the command `cwd`).

```python
def build_add_script(path: str, packages: list[str]) -> list[str]:
    return ["uv", "add", "--script", path, *packages]

def build_remove_script(path: str, package: str) -> list[str]:
    return ["uv", "remove", "--script", path, package]

def build_run_script(path: str) -> list[str]:
    return ["uv", "run", "--script", path]
```

Script commands run with `cwd=self.active_dir` (the project/workspace dir the picker
walked), exactly like project mutations, so a relative script path resolves correctly.

## UI (`app.py`, `widgets/`, `screens/`)

**Mode model.** Three mutually-exclusive modes derived from two fields:

```python
@property
def mode(self) -> str:
    if self.global_mode: return "global"
    if self.script_path is not None: return "script"
    return "project"
```

Entering global clears `script_path`; entering script clears `global_mode` — they can
never both be set.

**Panels.** Script mode reuses `#project-panels` but shows only `DependenciesPanel`
(the Workspace / Environment / Scripts panels are hidden — a script has no venv,
workspace, or `[project.scripts]`). `refresh_script()` populates the deps tree from
`load_script(...)`; the Details panel shows the selected inline dep via the existing
`show_dependency` (the `script` group renders as its own branch). The subtitle reads
`script · <filename> · uv <version>`.

**Keybindings** (added to `BINDINGS`, gated by `check_action`):

- `o` — **open/switch inline script**: opens `ScriptPickerScreen`. Available in
  project and script mode. Choosing a file enters (or switches within) script mode via
  `load_script`; a read failure is surfaced on the Output panel and leaves the mode
  unchanged.
- `escape` — **exit script mode** back to project. Bound at app level, active only in
  script mode (modals handle their own escape first, so this only fires with no modal
  open). This is the way back out; `g` from script mode switches to global as usual.
- `a` / `d` / `r` — **reused**, branching on mode:
  - `a` (add): project → `AddDependencyScreen` (group select); script →
    `AddScriptDependencyScreen` (package-names input only, no group) →
    `build_add_script`.
  - `d` (remove): project → remove selected dep with group/kind; script → remove the
    selected inline dep by name → `build_remove_script` (behind the existing
    `ConfirmScreen`).
  - `r` (run): project → run the selected `[project.scripts]` entry; script →
    `build_run_script(script_path)`.

`sync`, `sync_options`, `lock`, `python`, `venv`, `filter`, `workspace`, `export`, and
`upgrade` are **project-mode only** (unchanged); they are `None` (hidden/inert) in
script mode. Global-mode keys stay global-only. The help overlay and the
context-sensitive footer update accordingly.

**`check_action`** becomes three-way:

```python
_GLOBAL_ACTIONS        = {tool_install, tool_upgrade_all, tool_uninstall,
                          cache_clean, cache_prune, cache_size, self_update}
_PROJECT_ONLY_ACTIONS  = {sync, sync_options, lock, python, venv, filter,
                          workspace, export}
_PROJECT_OR_SCRIPT     = {add, remove, run, open_script}
_SCRIPT_ONLY_ACTIONS   = {exit_script}
# upgrade: project + global (not script). toggle_mode/help/quit: always.
```

**Modals** (return an intent tuple/value; app dispatches — the established pattern):

- `ScriptPickerScreen(scripts: list[str], focused: str | None)` → dismisses with the
  chosen path `str` or `None`. A `ListView` of discovered `.py` paths (escaped labels),
  like `WorkspaceSwitchScreen`. When the list is empty it shows a hint and only
  Cancels.
- `AddScriptDependencyScreen()` → dismisses with `list[str]` (package names) or `None`,
  like a trimmed `AddDependencyScreen` (no group `Select`).

**Escaping.** Every file-sourced string (script path, requires-python, dep names,
picker labels) is `escape()`d at the render boundary, matching Details/Workspace
panels.

**Busy/serialization.** `o`, `a`, `d`, `r`, and `exit_script` respect the existing
`_busy` guard (bell + no-op while a command runs), so a script switch can't race an
in-flight worker reading `cwd=self.active_dir`. After a script mutation completes,
`_run_uv_worker` re-reads via `refresh_script()` (mirroring how project mode calls
`refresh_project()`), so the deps tree reflects the edit.

## Testing (TDD; `run_streaming`/`run_capture` remain the only mock points)

- **Read path (unit, `test_data.py`):** `parse_pep723_block` on the uv-style block
  (with shebang + nested `[[tool.uv.index]]`), empty `dependencies = []`, no block
  (→ None), and a malformed/duplicated block (→ None). `load_script` builds `script`-
  group `Dependency` rows, resolves versions from a companion `<file>.lock`, and
  returns `has_block=False` for a plain `.py`. `find_scripts` skips dot-dirs, returns
  sorted relative paths, and reports the cap.
- **Commands (unit, `test_commands.py`):** `build_add_script`, `build_remove_script`,
  `build_run_script` argv (single + multiple packages, spec preservation).
- **Integration (Pilot, `test_app.py`):** `o` opens the picker; choosing a file enters
  script mode (subtitle `script · <file>`, deps tree shows the block's deps, project-
  only panels hidden); `a`/`d`/`r` build the `--script` argv on the focused file with
  `cwd=active_dir`; `escape` returns to project mode restoring project panels; script
  keys are inert in global mode and project-only keys are inert in script mode
  (`check_action`).
- **Real-uv checks (a few, not mocked):** the mocked tests assert *argv is
  well-formed*, not that uv does what we intend. Add a small set of tests that invoke
  the **real** `uv 0.11.31` in a `tmp_path` (guarded by `uv_available()` /
  skip-if-missing) to confirm: `build_add_script` argv actually creates/updates a PEP
  723 block that `parse_pep723_block` then reads back; `build_remove_script` removes an
  entry; and a resolved script writes a `<file>.lock` that `load_script` resolves. This
  closes the "argv well-formed ≠ correct" gap the M2–M4 lessons flagged.

## Non-goals

- Editing `requires-python` / `[tool.uv]` tables in the block from the TUI (→ `$EDITOR`).
- A separate `lazyuv script <file>` CLI entry point.
- `uv lock/sync/export --script`, script `--python` pinning, or run-with-args.
- Evaluating markers/extras in the script `.lock` (same conservative stance as project
  deps — surface resolved versions, don't interpret markers).

## Open questions

- Should the script picker walk recursively (chosen: yes, bounded + dot-dir-skipped) or
  only the active dir's top level? Draft walks recursively so `scripts/foo.py` is
  reachable; revisit if it's slow on large trees.
- Should script mode show `requires-python` somewhere (e.g. a one-line header)? Draft
  keeps the panel minimal (deps only); the value is visible via the file itself.
