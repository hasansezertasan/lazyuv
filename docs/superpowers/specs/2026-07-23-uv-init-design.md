# Milestone 8 — Initialize a project (`uv init`) — Design Spec

**Date:** 2026-07-23
**Status:** Implemented
**Follows:** v1 → M2 … M7 (`2026-07-23-uv-version-design.md`). Implements the ROADMAP
idea "`uv init` from the not-a-project screen".

## Problem

When lazyuv is opened in a directory with no `pyproject.toml`, the Details panel shows
a dead end: *"No pyproject.toml here. Run `uv init` to start a project."* The user has
to leave lazyuv, run `uv init` in the shell, and relaunch. This turns that dead end into
an action: bootstrap a project in place, then load it.

## Verified uv behavior (uv 0.11.31)

Probed before writing:

- `uv init` (default) creates an **application**: `pyproject.toml` + `main.py` +
  `README.md` + `.python-version` + `.gitignore`, and `git init`s. The project name
  defaults to the directory name.
- `uv init --lib --name X` creates a **library** (`src/X/` with `__init__.py` +
  `py.typed`), named `X`.
- `uv init --bare` creates **only** `pyproject.toml`.
- `--name <NAME>` overrides the derived name; a `PATH` positional targets a directory
  (we instead run with `cwd=active_dir`, so none is needed).
- It works in a **non-empty** directory (adds files alongside) and is **offline**.
- It **refuses** when a `pyproject.toml` already exists (`error: Project is already
  initialized …`), so init is only meaningful on the not-a-project screen.

## Decision & scope

A single **init action** (`n`, "new"), available **only when the current directory is
not a project** (project mode + `self.project is None`). It opens a small modal to pick
the project kind and an optional name, then streams `uv init` and loads the result.

- **Kinds:** `app` (default), `lib`, `bare` — a `Select`. These map to `--app` / `--lib`
  / `--bare` and cover the common cases; `--package`, `--script`, `--build-backend`,
  `--vcs`, etc. are out of scope (power-user; `$EDITOR`/shell).
- **Name:** an `Input`; blank → uv's default (the directory name).

The not-a-project Details message is updated to advertise the key.

**Non-goals:** `--package`/`--script`/`--build-backend`/`--vcs`/`--python` selection,
initializing into a *different* directory than the CWD/active member, and any
post-init scaffolding beyond what uv creates.

## Read path

None added. After `uv init` streams, the existing `refresh_project` re-reads the newly
created `pyproject.toml` (+ any `uv.lock`) and populates every panel — no init-specific
rendering.

## Commands (`commands.py`)

Pure argv builder; reuse `run_streaming` (mutation) — no new seam. Runs with
`cwd=active_dir`, so no `PATH` positional.

```python
def build_init(kind: str = "app", name: str = "") -> list[str]:
    argv = ["uv", "init"]
    argv.append({"lib": "--lib", "bare": "--bare"}.get(kind, "--app"))
    if name:
        argv += ["--name", name]
    return argv
```

`--app` is passed explicitly for the default kind (it equals bare `uv init`) so the argv
is deterministic and self-documenting.

## UI (`app.py`, `screens/init.py`)

- **`InitScreen(default_name)`** (`screens/init.py`) — a `ModalScreen` with a `Select`
  of kinds (`app`/`lib`/`bare`, default `app`) and an `Input` for the name (placeholder
  shows the default directory name). Dismisses with `(kind, name)` or `None`.
- **`action_init`** (`n`) — gated to *not-a-project* (`self.mode == "project" and
  self.project is None`) and `_busy`. Opens the modal; on close runs
  `build_init(kind, name)` via `_run_uv` (`cwd=active_dir`). `refresh_project` then
  loads the created project into the panels.
- **`check_action`** — new case: `init` is `True` only when `self.mode == "project" and
  self.project is None`, else `None` (inert once a project exists — where `uv init`
  would refuse anyway).
- The not-a-project Details message becomes: *"No pyproject.toml here. Press `n` to run
  `uv init` and start a project."*
- Help overlay gains an `n` line; `styles.tcss` gets `#init-dialog`. Name is a
  free-text field; it is `escape()`d wherever shown.

## Testing (TDD; `run_streaming`/`run_capture` remain the only mock points)

- **Commands (unit):** `build_init` for each kind (app/lib/bare) and with/without a name.
- **Integration (Pilot):** on a `tmp_path` with no pyproject, `n` opens the modal;
  selecting `lib` + a name builds `["uv","init","--lib","--name",<name>]` with
  `cwd == tmp_path`; default is `--app`; `init` is inert once a project exists
  (`check_action` returns `None` on the sample fixture) and in global/script mode; the
  not-a-project message mentions `n`. A mocked `run_streaming` that writes a minimal
  `pyproject.toml` shows `refresh_project` then loads the project (subtitle populated).
- **Real-uv check (skip-on-offline, though init is offline):** `build_init("app")` in a
  fresh tmp dir actually creates a `pyproject.toml` that `load_project` reads as OK with
  the directory name; `build_init("bare")` creates only `pyproject.toml`.

## Open questions

- Should the modal expose `--package` / `--vcs none` / a build-backend? Draft keeps it
  to kind + name; revisit if users ask.
- After init, should lazyuv offer to open `main.py` or run an initial `uv sync`? Draft
  just loads the project (sync is a keystroke away via `s`).
