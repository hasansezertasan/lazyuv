# Milestone 2 — Environments & Python Versions — Design Spec

**Date:** 2026-07-22
**Status:** Implemented
**Follows:** v1 (`2026-07-21-lazyuv-design.md`) and the fork-accuracy follow-up
(`2026-07-22-lock-fork-accuracy-design.md`). Implements ROADMAP "Milestone 2 —
Environments & Python versions".

## Problem

v1 manages a project's *dependencies* but says nothing about the *environment* those
dependencies run in. A user cannot see which Python the project resolves against,
whether a `.venv` exists or matches the project's `requires-python` / pin, or run a
scoped sync — they must drop back to the shell for `uv python …`, `uv venv`, and
`uv sync --extra/--group/--no-dev/--frozen`. Environment is the natural next concern
after dependencies, and it is the last piece needed before lazyuv is a complete
*project* tool (global/machine state is Milestone 3).

## Decision

Add a project-scoped **Environment** view and the commands to act on it, staying
inside v1's constraints (single runtime dependency `textual`, CWD project only,
Python 3.14+). Three decisions frame the milestone (confirmed in review):

1. **A second subprocess seam for read-only queries.** v1's only subprocess is
   `run_streaming` (line-by-line, for *actions* with live output). The Python
   picker needs the list of installed/available interpreters, which lives in no
   project file — only `uv python list` knows it. So we add `run_capture` alongside
   `run_streaming`: it runs a uv command and returns its captured output for
   parsing. Both remain the single mockable subprocess family, so tests still never
   invoke real `uv`. Current-environment *display* still reads files (see below);
   `run_capture` is only for machine state that files cannot provide.
2. **Project `.venv` only.** M2 manages the current project's virtualenv and Python
   pin. Listing/switching arbitrary uv-managed Pythons is deferred to Milestone 3's
   global mode (it is machine-wide, not CWD-scoped).
3. **Drift is a passive colored indicator,** not a modal or blocking prompt —
   consistent with v1's calm, panel-based style. The Environment panel shows drift;
   it never interrupts.

## Read path (files, no subprocess)

Current-environment display follows v1's "read files for display" split. No
subprocess is used to render the Environment panel:

- **Pin** — read `.python-version` at the project root (uv's `uv python pin` target).
  A single line like `3.14`; absent → no pin.
- **Venv** — read `.venv/pyvenv.cfg` (INI-style `key = value`). Extract the venv's
  Python version (`version` / `version_info` key) and interpreter `home`. Absent
  `.venv/` → no venv.
- **requires-python** — already parsed into `Project.requires_python` from
  `pyproject.toml` in v1.

`pyvenv.cfg` is parsed with a tiny local `key = value` reader (stdlib only; no new
dependency). Parsing lives in `data.py`, mirroring `_read_lock`: file-missing and
malformed cases return "unknown/absent" rather than raising, so a project with no
venv still renders.

### Drift

Drift is computed, not stored: the venv Python version vs. the pin (if any) and vs.
`requires-python`. M2 uses **conservative string/prefix comparison only** — no
version-range evaluation (that would need `packaging`, breaking the single-dependency
constraint, exactly as the fork spec established). Concretely:

- Pin present: compare the venv version and the pin over their **shared leading
  components** (`min(len)`), so a major.minor venv (uv writes only
  `version_info = 3.14`) does not falsely mismatch a patch-level pin like `3.14.2`,
  while `3.1` still mismatches `3.14.x`. A pin that isn't a plain version (e.g.
  `pypy@3.10` or a full uv key) is uncomparable → "unknown". The pin drives the check.
- No pin: only a **single** bare `>=`/`==`/`~=` `major.minor` in `requires-python` is
  compared against the venv's leading `major.minor` — below a `>=`/`~=` floor, or
  unequal to an `==`, is drift. A compound specifier (`>=3.9,<3.11`) or anything
  unparsable is "unknown", never "drift" (no false alarm). Non-goal: full specifier
  satisfaction.

## Model (`models.py`)

Add a plain dataclass (no behavior, like the rest of `models.py`):

```
@dataclass(frozen=True, slots=True)
class Environment:
    venv_path: str | None          # ".venv" if present, else None
    venv_python: str | None        # version from pyvenv.cfg (uv writes major.minor, e.g. "3.14")
    pinned_python: str | None      # from .python-version, e.g. "3.14"
    drift: str | None              # human-readable drift note, None if aligned/unknown
```

`Project` gains `environment: Environment | None = None` (None only when not a
project). Additive and default-valued, so nothing in v1 breaks (same approach as
`locked_versions`).

## Data (`data.py`)

- `_read_pin(root) -> str | None` — read/strip `.python-version`; missing/blank/OSError → None.
- `_read_venv(venv_cfg_path) -> tuple[str | None, str | None]` — `(python_version, home)`
  from `pyvenv.cfg`; missing/malformed → `(None, None)`.
- `_compute_drift(venv_python, pinned, requires_python) -> str | None` — the
  conservative comparison above.
- `_read_environment(root, requires_python) -> Environment` — composes the three
  (`requires_python` is needed for drift); `load_project` attaches it to `Project`.
  `NOT_A_PROJECT` / `MALFORMED` paths are unchanged.

## Commands (`commands.py`)

Pure argv builders (unchanged style), plus the new capture seam:

```
def build_python_list() -> list[str]:          # ["uv", "python", "list", "--output-format", "json"]
def build_python_install(request: str)         # ["uv", "python", "install", request]
def build_python_pin(request: str)             # ["uv", "python", "pin", request]
def build_python_uninstall(request: str)       # ["uv", "python", "uninstall", request]
def build_venv(python=None, clear=False)       # ["uv", "venv", ("--clear"?), ("--python", python)?]
def build_sync(*, extras=(), groups=(), no_dev=False, frozen=False) -> list[str]
    # ["uv", "sync", *(--extra X ...), *(--group G ...), *(["--no-dev"] if no_dev), *(["--frozen"] if frozen)]
```

`build_python_*` take a uv *request* string — the picker passes each row's fully
qualified `key`, not a bare version, so the action targets the exact interpreter
(implementations/variants can share a version number). `build_venv(clear=True)` is
required to recreate over an existing `.venv` (uv refuses otherwise). `build_sync()`
stays backward-compatible: no args → `["uv", "sync"]` exactly as v1.

```
async def run_capture(argv, cwd=None) -> tuple[int, str]:
    """Run argv to completion, return (exit_code, stdout). Read-only queries.
    stderr is captured separately (kept out of stdout) so a uv warning can't corrupt
    the JSON. Terminates/awaits the child on cancellation, like run_streaming."""
```

Parsing of `uv python list --output-format json` lives next to the read path
(`parse_python_list`), preserving each entry's `key` (unambiguous request id),
`implementation`, `installed` (has a path), and `managed` (path under uv's
`…/uv/python/…` dir — only managed installs are uninstallable). It stays out of
`commands.py` (which is pure argv + the two subprocess seams). Actions
(install/pin/uninstall/venv/scoped-sync) route through `run_streaming` and the
`_busy`/worker flow in `app.py`; the picker's own `run_capture` query is guarded by
`_busy` too, so it can't be cancelled by — or race with — a mutation.

## UI

- **Environment panel** — a new panel in the left column (`widgets/environment.py`,
  `BORDER_TITLE = "Environment"`), composed above `DependenciesPanel`. Renders:
  active Python (venv version, or "no venv"), venv path, pinned version, and the
  drift line in red when present (passive; no prompt). Reads from
  `Project.environment` in `refresh_project`, alongside the existing panel loads.
- **Python picker modal** (`screens/python.py`, a `ModalScreen`) — opened by `p`. The
  app reads `run_capture(build_python_list())` in a worker (wrapped so a `uv` failure
  surfaces on the OutputPanel rather than crashing the app), parses the JSON, and
  hands the list to the modal. Rows show version + implementation + status
  (managed/installed/available). Actions dismiss with `(action, key)`; the app turns
  that into a `run_streaming` command (matching `AddDependencyScreen`'s intent-tuple
  pattern). Actions are gated: Install only when not installed, Uninstall only for a
  uv-managed row.
- **Scoped sync** — new binding (proposed `S`, "sync options") opens a small modal
  to choose extras/groups (from `Project.groups`, reusing the add-modal's kind-aware
  option list) and toggle `--no-dev` / `--frozen`; it returns the selections and the
  app calls `build_sync(...)`. Plain `s` (`build_sync()`) is unchanged.
- **Recreate venv** — offered from the Environment panel/binding (proposed `v`),
  routed through `ConfirmScreen` (reused) when a venv already exists, then
  `build_venv()` (optionally `--python <pin>`).

New keybindings added to `LazyUvApp.BINDINGS` and surfaced in the footer + help
overlay: `p` python picker, `S` scoped sync, `v` (re)create venv. Existing bindings
unchanged.

## Testing

Extends the Pilot-based suite; the two subprocess seams are the only mock points, so
tests never call real `uv`.

- **Read path (unit):** `_read_pin`, `_read_venv`, `_compute_drift` — present/absent/
  malformed files; drift vs. no-drift vs. unknown; venv version prefix-matching the
  pin. `load_project` attaches a correct `Environment`.
- **Commands (unit):** `build_sync` with each option combination (and the empty
  backward-compatible case); `build_python_*` and `build_venv` argv shapes.
- **Integration (Pilot):** Environment panel renders venv/pin/drift; drift line is
  styled when present. Python picker opens, parses a mocked `uv python list` JSON via
  a stubbed `run_capture`, and dismisses with the right install/pin/uninstall intent.
  Scoped-sync modal produces the expected `build_sync(...)` argv. Recreate-venv goes
  through the confirm screen.

## Non-goals

- **Listing/switching arbitrary uv-managed Pythons** — deferred to Milestone 3
  (global mode); M2 is project-scoped.
- **Version-range / specifier evaluation** — drift and any comparison use
  conservative prefix matching only; full `requires-python` satisfaction would need
  `packaging` and is out of scope (same constraint as the fork spec). Ambiguous cases
  report "unknown", never a false drift warning.
- **Active/blocking drift prompts** — drift is passive display only.
- **Managing venvs outside the project** or non-uv virtualenvs.

## Open questions

- Binding letters (`p` / `S` / `v`) — confirm none clash with future modes; `S` as
  "sync with options" vs. reworking `s` into a single options-aware sync.
- Whether the Environment panel should also show the resolved interpreter `path`
  (from `pyvenv.cfg home`) or keep the panel minimal (version + status + drift).
