# Milestone 3 — Global Tools & Cache ("full dashboard") — Design Spec

**Date:** 2026-07-22
**Status:** Implemented
**Follows:** v1, the fork-accuracy follow-up, and M2
(`2026-07-22-environments-python-design.md`). Implements ROADMAP "Milestone 3 —
Global tools & cache".

## Problem

Everything lazyuv does so far is scoped to the CWD project. But a lot of daily `uv`
use is *machine-wide*: the tools installed via `uv tool` (a.k.a. `uvx`), and the
shared cache. Today a user must leave lazyuv to `uv tool list/install/upgrade/
uninstall`, inspect/clean the cache, or check their `uv` version. M3 brings that
global surface in, turning lazyuv from a project tool into a small uv cockpit.

## Decision

Add a **global mode** — a second view over machine state — reachable by a toggle,
without disturbing the project view. Three decisions frame it (confirmed in review):

1. **Mode toggle, not tabs.** A key (`g`) swaps the left column between the project
   panels (Environment / Dependencies / Scripts) and the global panels (Tools /
   Cache). Project mode is the default; the right column (Details / Output) is shared.
   This keeps v1's calm, panel-based, keyboard-first feel and adds no persistent
   navigation chrome.
2. **Cache size: path now, size on demand.** `uv cache dir` (a fast subprocess) gives
   the path immediately; the *size* (a potentially slow directory walk) is computed
   only when the user asks (a keypress), in a background worker — opening the global
   view is never blocked by a scan.
3. **Include `uv self update`,** with a confirm and a visible uv-version indicator.
   Because a package-manager-installed uv (Homebrew, etc.) *cannot* self-update, the
   command's failure is surfaced verbatim in the Output panel — lazyuv never fakes
   success (same honesty principle as M2's drift/uninstall gating).

## Read path (subprocess queries + one filesystem walk)

Global state lives in no project file, so — unlike the project read path — it comes
from `uv` via the M2 `run_capture` seam, plus one filesystem walk for cache size:

- **Tools** — `uv tool list`. **uv emits plain text, not JSON** (verified: no
  `--output-format`). Format is one tool per block:
  ```
  <name> v<version>
  - <executable>
  - <executable>
  ```
  `parse_tool_list(output)` parses this into `Tool` rows (see Model). Lines that
  match neither shape (e.g. "No tools installed.") are ignored → empty list.
- **uv version** — `uv --version` → `"uv 0.11.31 (Homebrew 2026-… )"`;
  `parse_uv_version(output)` extracts `"0.11.31"` (falls back to the raw string).
- **Cache dir / tool dir** — `uv cache dir`, `uv tool dir` → a single path line.
- **Cache size** — `directory_size(path)` walks the dir summing file sizes
  (`os.walk`, `os.stat`), tolerant of unreadable entries; run in a worker, formatted
  by `format_size(n)` (B/KiB/MiB/GiB). This is a *read*, so it lives in `data.py`, not
  `commands.py`.

## Model (`models.py`)

```
@dataclass(frozen=True, slots=True)
class Tool:
    name: str                       # e.g. "ruff"
    version: str                    # e.g. "0.11.31" ("" if unparsable)
    executables: tuple[str, ...]    # exposed commands, e.g. ("ruff",)
```

No change to `Project`; global state is not part of a project. The app holds the
current tool list / cache info in memory (refreshed after a global mutation), the
same way it holds `project`.

## Commands (`commands.py`)

Pure argv builders (unchanged style); all reuse the existing `run_streaming`
(mutations) and `run_capture` (queries) seams — no new seam needed.

```
def build_tool_list()            # ["uv", "tool", "list"]
def build_tool_install(pkg)      # ["uv", "tool", "install", pkg]
def build_tool_upgrade(name)     # ["uv", "tool", "upgrade", name]
def build_tool_upgrade_all()     # ["uv", "tool", "upgrade", "--all"]
def build_tool_uninstall(name)   # ["uv", "tool", "uninstall", name]
def build_cache_dir()            # ["uv", "cache", "dir"]
def build_cache_clean()          # ["uv", "cache", "clean"]
def build_cache_prune()          # ["uv", "cache", "prune"]
def build_uv_version()           # ["uv", "--version"]
def build_self_update()          # ["uv", "self", "update"]
```

Queries (`tool list`, `cache dir`, `--version`) go through `run_capture`; mutations
(`install`/`upgrade`/`uninstall`/`cache clean`/`prune`/`self update`) through
`run_streaming` + the `_busy`/worker flow, exactly like project actions. The global
read (`tool list` + `cache dir` + `--version`) is guarded by `_busy` just as the M2
Python-picker query is, so it can't race or be cancelled by a mutation.

## UI

- **Mode toggle** (`g`) — swaps the left column. Implemented with a `ContentSwitcher`
  (or two containers whose `display` toggles) holding a project group (v1/M2 panels)
  and a global group. `LazyUvApp` gains `global_mode: bool`; `refresh_project`
  populates project panels, a new `refresh_global` populates global panels (only the
  visible group is refreshed). The subtitle shows the mode + uv version
  (e.g. `global · uv 0.11.31`).
- **Tools panel** (`widgets/tools.py`) — a list of installed tools (`name  version`,
  executables as a dim suffix or child rows). Selecting one shows details
  (executables) in the shared Details panel. Actions:
  - `i` install → a modal (`screens/tool_install.py`) prompting for a package name →
    `uv tool install <pkg>` (returns an intent, app executes — the M2 modal pattern).
  - `u` upgrade selected → `uv tool upgrade <name>`; `U` upgrade all →
    `uv tool upgrade --all`.
  - `x` uninstall selected → confirm (reuse `ConfirmScreen`) → `uv tool uninstall <name>`.
- **Cache panel** (`widgets/cache.py`) — shows the cache dir path immediately and
  size as `—` until requested; `z` computes size in a worker (shows `calculating…`
  then the formatted size). Actions: `c` clean (confirm) → `uv cache clean`; `P`
  prune → `uv cache prune` (`P`, since `p` is the project-mode Python picker).
- **Version indicator** — uv version in the subtitle (read once on mount via
  `uv --version`); `uv self update` is action `X` (confirm), streamed like any
  mutation; its output (including "cannot self-update a package-manager install")
  shows in the Output panel.
- **Keybindings** — global-mode actions (`i`/`u`/`U`/`x`/`c`/`P`/`z`/`X`) are gated on
  `global_mode`; project-mode actions (`a`/`d`/`s`/`S`/`l`/`r`/`p`/`v`/`/`) are gated on
  *not* global mode. `g` (toggle), `q`, and `?` are always active. Prune is `P`
  (capital) because `p` is the project-mode Python picker. Help overlay lists both
  sets under "project"/"global" headings.

## Testing

Extends the Pilot suite; `run_capture`/`run_streaming` remain the only mock points.

- **Parsers (unit):** `parse_tool_list` — multi-tool blocks, a tool with no
  executables, the "No tools installed." case, blank output. `parse_uv_version` —
  normal string and a fallback. `directory_size`/`format_size` — a small temp tree,
  unreadable entries, and B/KiB/MiB/GiB boundaries.
- **Commands (unit):** argv shape of every new builder.
- **Integration (Pilot):** `g` toggles the visible panel group; global read parses a
  mocked `uv tool list`; install/upgrade/upgrade-all/uninstall produce the right argv
  (uninstall via confirm); cache clean/prune argv; `z` fills size from a stubbed walk;
  `uv self update` streams and surfaces a non-zero exit; mode-gated keys no-op in the
  wrong mode.

## Non-goals

- **A full package browser / search** of the tool registry — install is by typed
  name only (like the M2 dependency add).
- **Per-tool Python / `--with` management, editable/git tool installs** — deferred;
  M3 covers the common list/install/upgrade/uninstall loop.
- **Live cache-size auto-refresh** — size is on demand only (decision #2).
- **JSON parsing of `uv tool list`** — uv doesn't emit JSON here; plain-text parsing
  is the only option and is treated as best-effort (unrecognized lines ignored).

## Resolved during implementation

- Key set is `i`/`u`/`U`/`x`/`c`/`P`/`z`/`X` (uninstall `x`, prune `P`). Tools and
  Cache stack in the left column (swapped in for the project panels via
  `display` toggling); Details/Output stay shared on the right.
