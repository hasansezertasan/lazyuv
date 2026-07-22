# lazyuv — Design Spec (v1)

**Date:** 2026-07-21
**Status:** Approved for planning
**Scope:** v1 — project workflow only. Later milestones are captured in `ROADMAP.md`.

## Summary

`lazyuv` is a keyboard-driven terminal UI for [`uv`](https://docs.astral.sh/uv/),
in the lineage of `lazygit` / `lazydocker`. It opens the uv project in the current
working directory and provides a fast, mutating daily loop: view dependencies,
add/remove them, sync/lock the environment, and run project scripts — all without
leaving the terminal.

v1 deliberately targets a single, narrow surface (the project workflow). Wider
surfaces (Python versions, virtualenvs, global tools/uvx, cache) are roadmapped,
not built.

## Goals

- Make the everyday uv project loop faster and more discoverable than raw CLI.
- Always keep `uv.lock`/`pyproject.toml` authoritative — never hand-edit TOML.
- Stream live command output so the user sees exactly what `uv` is doing.
- Ship as a self-contained CLI installable with `uv tool install lazyuv`.

## Non-Goals (v1)

- Managing Python versions (`uv python install/pin`) — Milestone 2.
- Virtualenv management (`uv venv`) — Milestone 2.
- Global tools / `uvx` (`uv tool ...`) — Milestone 3.
- Cache management (`uv cache ...`) — Milestone 3.
- A project browser/switcher — backlog. v1 operates on the CWD project only.

## Architecture

Three layers with clear boundaries:

### Data layer (`models.py`, `data.py`)

Reads `pyproject.toml` and `uv.lock` with stdlib `tomllib` and maps them into plain
dataclasses. No subprocess is required to display anything — the read path is fast
and works even when `uv` is busy.

Domain models:

- `Dependency` — `name`, `spec` (version specifier from pyproject), `resolved_version`
  (from uv.lock), `group` (`main` | `dev` | optional-extra / dependency-group name),
  `source` (`registry` | `git` | `path` | `url` | `other`), `kind`
  (`main` | `dev` | `extra` | `group` — how uv targets it: `--optional` vs `--group`).
- `Script` — `name`, `target` (the entry-point string).
- `Project` — `name`, `version`, `requires_python`, `dependencies: list[Dependency]`,
  `scripts: list[Script]`, `groups: list[tuple[str, str]]` (declared `(name, kind)`
  groups, including empty ones).

`data.py` exposes a single `load_project(root: Path) -> LoadResult` — a wrapper
carrying a `status` (`OK` / `NOT_A_PROJECT` / `MALFORMED`) and an optional `Project`,
so the "not a uv project" and "malformed TOML" states are signaled without raising
into the UI.

> Note: `Dependency.kind`, `Project.groups`, and the `source`/`Script.target` shapes
> above reflect refinements made during implementation and review; this section was
> updated to match the shipped v1 code.

### Command layer (`commands.py`)

- **Pure argv builders** — functions that take structured input and return the
  `uv` command as `list[str]` (e.g. `build_add(pkgs, group)`,
  `build_remove(pkg)`, `build_sync()`, `build_lock()`, `build_run(script)`).
  These are pure and directly unit-testable.
- **Async streaming runner** — spawns the command via
  `asyncio.create_subprocess_exec`, streams stdout/stderr line-by-line to a callback,
  and reports the exit code. This is the *only* module that touches the real `uv`
  binary, which makes it a clean seam to mock in tests.

All mutations (add/remove/sync/lock/run) go through this layer. After a command
completes, the app re-reads the files via the data layer and refreshes the views.

### UI layer (Textual)

A Textual `App` composing the panels below, with global keybindings and modal
screens. Long-running commands run as Textual workers so the UI stays responsive
and output streams in live.

## Layout

lazygit-style: a left column of navigable panels, a right column of detail + output,
and a context-sensitive keybinding bar at the bottom.

```
┌ lazyuv ─ myproject 0.1.0 ─ Python >=3.14 ─────────────────────────────┐
│┌ Dependencies ────────────┐┌ Details ────────────────────────────────┐│
││ ▾ main (4)               ││ httpx  0.27.0                            ││
││   httpx      0.27.0      ││ spec:   >=0.27                           ││
││   rich       13.7.1      ││ group:  main                            ││
││   typer      0.12.3      ││ source: pypi (registry)                 ││
││   textual    0.60.0      │└──────────────────────────────────────────┘│
││ ▾ dev (2)                │┌ Output ─────────────────────────────────┐│
││   pytest     8.2.0       ││ $ uv sync                               ││
││   ruff       0.4.8       ││ Resolved 24 packages in 12ms            ││
│└──────────────────────────┘│ Installed 2 packages in 30ms            ││
│┌ Scripts ─────────────────┐│  + pytest==8.2.0                        ││
││   serve                  ││  + ruff==0.4.8                          ││
││   test                   ││ ✓ done                                  ││
│└──────────────────────────┘└──────────────────────────────────────────┘│
│ a:add  d:remove  s:sync  l:lock  r:run  /:filter  ?:help  q:quit       │
└────────────────────────────────────────────────────────────────────────┘
```

- **Dependencies** (top-left) — grouped, collapsible (main / dev / optional groups),
  showing resolved versions.
- **Scripts** (bottom-left) — runnable project scripts.
- **Details** (top-right) — details of the currently selected dependency or script.
- **Output** (bottom-right) — live stream of the running/last `uv` command.
- **Keybinding bar** (bottom) — context-sensitive.

## Keybindings & Flows

| Key   | Action | Behavior |
|-------|--------|----------|
| `j`/`k`, arrows | Navigate | Move within the focused panel |
| `Tab` | Cycle focus | Move focus between panels |
| `a`   | Add | Modal: type package name(s), pick group (main/dev/optional) → `uv add [--dev] <pkg…>` |
| `d`   | Remove | Confirm on selected dependency → `uv remove <pkg>` |
| `s`   | Sync | `uv sync`, output streamed |
| `l`   | Lock | `uv lock`, output streamed |
| `r`   | Run | On selected script → `uv run <script>` |
| `/`   | Filter | Filter the dependency list |
| `?`   | Help | Help overlay |
| `q`   | Quit | Exit |

While a command runs, a status indicator shows "running" and conflicting actions are
disabled until it completes.

## Error Handling

- **Not a uv project** (no `pyproject.toml`) → friendly empty state suggesting
  `uv init`. App does not crash.
- **`uv` not on PATH** → detected at startup; clear message + graceful exit.
- **Non-zero command exit** → output stays visible, status line turns red, no crash.
- **Malformed TOML** → per-panel error state; the rest of the app stays usable.

## Project Structure

```
src/lazyuv/
  __init__.py
  __main__.py        # python -m lazyuv entry
  app.py             # Textual App, bindings, main()
  models.py          # dataclasses
  data.py            # TOML -> models, error states
  commands.py        # pure argv builders + async streaming runner
  widgets/
    dependencies.py
    details.py
    output.py
    scripts.py
  screens/
    add_dependency.py  # modal
    help.py            # help overlay
  styles.tcss
```

- **Runtime dependency:** `textual` only (`tomllib` is stdlib).
- **`requires-python >= 3.14`** — lazyuv is a system-wide tool installed in its own
  isolated environment (`uv tool install`), independent of the Python version of the
  projects it manages. Pinning to the latest stable release lets us use current
  stdlib/typing features without compatibility guards. Backwards compatibility is a
  non-goal.
- Ships as a CLI via a console-script entry point (`lazyuv = "lazyuv.app:main"`).

## Testing

- **Unit** — `data.py` parsing against fixture `pyproject.toml` / `uv.lock` files
  covering main/dev/optional groups and different sources; `commands.py` argv builders
  (pure functions).
- **Integration** — Textual's `App.run_test()` Pilot to simulate keypresses (navigate
  panels, trigger `s`/`a`/`d`/`r`) with the command layer's subprocess runner **mocked**
  so tests never invoke real `uv`. Asserts the correct argv is built and the UI
  refreshes on completion.

## Documentation (DDD)

Authored before/alongside implementation:

- **`README.md`** — what it is, install (`uv tool install lazyuv`), usage, full
  keybinding reference.
- **`ROADMAP.md`** — future milestones:
  - *Milestone 2 — Environments:* Python version management (`uv python install/pin`),
    virtualenv management (`uv venv`).
  - *Milestone 3 — Full dashboard:* global tools / `uvx` (`uv tool …`), cache
    management (`uv cache …`).
  - *Backlog:* project browser/switcher, dependency tree view (`uv tree`),
    outdated/upgrade view, build/publish.
- This design spec.

## Open Questions

None outstanding. All scoping decisions resolved during brainstorming.
