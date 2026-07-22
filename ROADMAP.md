# lazyuv Roadmap

A living plan for lazyuv beyond v1. lazyuv is a keyboard-driven terminal UI for
[`uv`](https://docs.astral.sh/uv/), in the spirit of `lazygit` — it makes the
everyday `uv` surface fast and discoverable without leaving the terminal.

This document records what shipped, the principles that keep scope disciplined,
and the milestones ahead with enough detail to plan from. Each milestone becomes
its own spec → plan → implementation cycle when it's picked up. Ordering reflects
current priority and may change; nothing below Milestone 2 is committed.

## Guiding principles

These constrain every milestone and are the reason the tool stays small:

- **One project surface at a time.** Each milestone adds a coherent slice of uv's
  surface, not a scattering of flags.
- **uv is authoritative.** Every mutation goes through the `uv` CLI. lazyuv never
  hand-edits `pyproject.toml` or `uv.lock`.
- **Read files for display, shell out for actions.** The read path parses TOML
  directly (fast, offline); the write path streams `uv` subprocesses live and then
  re-reads. New features follow this same split.
- **Keyboard-first, panel-based.** New capabilities are new panels/modes with
  discoverable, context-sensitive keybindings — not nested menus.
- **YAGNI per milestone.** Ship the smallest thing that makes a real workflow
  faster; defer the rest to the backlog.

## Status — v1 (shipped)

The daily project workflow, operating on the uv project in the current working
directory:

- **View dependencies** — `pyproject.toml` + `uv.lock` rendered as a collapsible
  tree grouped by group (main / dev / optional), with resolved versions and source
  (registry / git / path).
- **Add / remove** — `uv add [--dev|--group <group>|--optional <group>] <pkgs>`,
  `uv remove …`, via a modal with group selection (routed by dependency kind) and a
  remove confirmation.
- **Sync / lock** — `uv sync`, `uv lock`, with live-streamed output.
- **Run scripts** — `[project.scripts]` entries via `uv run <name>`.
- **Filter** the dependency list; **help** overlay; context-sensitive keybinding bar.

**Architecture:** three layers — `data.py`/`models.py`/`parsing.py` (read-only TOML →
dataclasses), `commands.py` (pure argv builders + one async `run_streaming` seam),
and the Textual UI (`app.py` + `widgets/` + `screens/`).

**Constraints:** operates on the CWD project only; single runtime dependency
(`textual`); requires Python 3.14+; installed as an isolated tool
(`uv tool install lazyuv`).

---

## Milestone 2 — Environments & Python versions — *shipped*

**Intent:** manage the *environment* a project runs in, the natural next concern
after its dependencies.

*Implemented* (design:
`docs/superpowers/specs/2026-07-22-environments-python-design.md`). An **Environment**
panel shows the project's venv Python, `.venv` presence, and `.python-version` pin,
read from files only (no subprocess), with a passive colored **drift** line when the
venv Python misaligns with the pin / `requires-python`. A **Python picker** (`p`)
lists interpreters from `uv python list` — via a new read-only `run_capture` seam —
and installs / pins / uninstalls a selected version. **Scoped sync** (`S`) attaches
`--extra`/`--group`/`--no-dev`/`--frozen` to `uv sync` (plain `s` unchanged), and `v`
(re)creates the venv. Deferred (still non-goals): listing/switching arbitrary
uv-managed Pythons (→ M3), full `requires-python` specifier evaluation (drift uses
conservative leading `major.minor` comparison only), and active/blocking drift
prompts.

**Features:**
- Python version management: `uv python list`, `uv python install <ver>`,
  `uv python pin <ver>` (writes `.python-version`), `uv python uninstall`.
- Virtualenv management: show the active `.venv` (path, Python version, whether it
  matches `requires-python` / the pin), `uv venv` to (re)create it, and surface
  drift ("venv is Python 3.12 but project pins 3.14").
- Selective sync: `uv sync --extra <x>`, `--group <g>`, `--no-dev`, `--frozen`.

**UI impact:** a new left-column **Environment** panel (active Python, venv status,
pinned version) and a Python-versions picker modal. Selective-sync options attach
to the existing sync action (e.g. `S` for "sync with options").

**Done when:** a user can see their project's Python/venv state at a glance, pin or
install a Python version, recreate the venv, and run a scoped sync — all keyboard-driven.

**Open questions:** how prominent should venv *drift* be (passive indicator vs.
active warning)? Do we manage only the project venv, or also list/switch arbitrary
uv-managed Pythons?

## Milestone 3 — Global tools & cache (the "full dashboard") — *shipped*

**Intent:** step outside a single project to manage machine-wide uv state — the
breadth that turns lazyuv from a project tool into a uv cockpit.

*Implemented* (design:
`docs/superpowers/specs/2026-07-22-global-tools-cache-design.md`). A `g` toggle swaps
the left column into a **global mode** with a **Tools** panel (`uv tool list` — parsed
from plain text, uv emits no JSON here) and a **Cache** panel. Tools: `i` install, `u`
upgrade, `U` upgrade all, `x` uninstall (confirm). Cache: `c` clean (confirm), `P`
prune, `z` size (computed on demand in a background thread — never blocks the view).
`X` runs `uv self update` (confirmed; a package-manager install's refusal is surfaced
verbatim, not faked), with the uv version shown in the subtitle. Queries reuse M2's
`run_capture` seam.

**Features:**
- Global tools / uvx: `uv tool list`, `uv tool install`, `uv tool upgrade [--all]`,
  `uv tool uninstall`, and surface each tool's version + exposed executables.
- Cache: `uv cache dir` (show location + size), `uv cache clean`, `uv cache prune`.
- `uv self update` and a visible uv-version indicator.

**UI impact:** introduces a **global mode** (toggle, e.g. `g`) that swaps the
project panels for a Tools panel + Cache panel, since these aren't tied to the CWD
project. The project mode from v1/M2 remains the default.

**Done when:** a user can install/upgrade/remove global tools and inspect/clean the
cache without leaving lazyuv, and mode-switching between project and global views is
obvious.

**Open questions:** is "mode toggle" the right model, or should global tools be a
peer top-level view (tab bar)? How do we represent cache size without a slow scan?

## Milestone 4 — Workspaces & advanced dependencies

**Intent:** support real-world project shapes and the dependency operations power
users reach for.

**Features:**
- **Workspaces** (`[tool.uv.workspace]`): list members, show which member is
  focused, and run member-scoped commands (`uv run --package <m>`, `uv sync` at the
  workspace root).
- **Dependency sources & indexes**: display and edit git / path / editable sources
  and `[[tool.uv.index]]` entries (add/remove a source via `uv add <pkg> --index …`
  / `--git …` / `--editable …`).
- **Targeted upgrades**: `uv lock --upgrade-package <pkg>`, and an outdated view
  (see backlog) feeding directly into it.
- **Export**: `uv export` to `requirements.txt` (with `--format`, `--no-hashes`,
  group/extra selection).

**UI impact:** a workspace switcher (when a workspace is detected) that re-scopes the
whole UI to a member; the Details panel gains source/index editing; export is a
modal off the dependency list.

**Done when:** lazyuv is usable in a uv workspace monorepo, and a user can change a
dependency's source, upgrade a single package, and export a lockfile.

**Open questions:** does workspace support reopen the "project switcher" backlog
item (members are a constrained switcher)? How much index/source editing belongs in
a TUI vs. deferring to `$EDITOR`?

## Milestone 5 — Inline scripts (PEP 723)

**Intent:** support standalone scripts with inline dependency metadata, a distinct
uv workflow from projects.

**Features:** detect/edit PEP 723 `# /// script` blocks, `uv add --script <file>`,
`uv run <file>`, and manage a script's inline deps the way v1 manages project deps.

**UI impact:** a "script mode" reusing the dependency panel against a single file's
inline metadata instead of `pyproject.toml`.

**Done when:** a user can open a `.py` script, view/add/remove its inline deps, and
run it — all through the same panel vocabulary as project mode.

**Open questions:** is this a mode in the main app, or a separate lightweight entry
point (`lazyuv script foo.py`)?

---

## Backlog (unscheduled)

Lower-priority or design-uncertain items; promoted into a milestone when justified:

- **Project browser/switcher** — open a project other than the CWD (may be
  subsumed by workspace support in M4).
- **Dependency tree view** (`uv tree`) — visualize the transitive graph; collapsible.
- **Outdated / upgrade view** — highlight deps with newer releases, feed targeted
  upgrades (pairs with M4).
- **Build & publish** (`uv build`, `uv publish`) — for library authors; needs care
  around credentials.
- **`uv pip` compatibility layer** — a view over the pip-style interface for users
  who live there.
- **`uv version`** — read/bump the project version from the UI.
- **Diff view** — show what a pending `uv lock`/`uv sync` *would* change before
  applying.
- **Run scripts with arguments** — v1 runs `uv run <script>` with no extra args;
  add an args prompt (`uv run <script> -- <args>`).
- **Multiple locked versions** — *addressed:* a package with several `uv.lock`
  entries (universal-lock resolution forks or `[tool.uv].conflicts` variants) now
  displays all its distinct versions (`httpx  0.27.0 / 0.28.1  (2 versions)`) in
  lock-file order instead of an arbitrary last-write-wins pick. Evaluating
  `resolution-markers` to show only the environment-applicable version, or resolving
  `[tool.uv].conflicts` to scope a version to its extra/group, remains a non-goal
  (would require marker/conflict evaluation / the `packaging` dependency); until
  then a conflict-variant declaration may list versions from other extras.
- **Preserve selection UX** — v1 restores the highlighted dependency across
  refreshes; extend the same to the scripts panel and scroll position.

## Non-functional & cross-cutting

Tracked separately because they span milestones:

- **Configuration** — a config file (e.g. `~/.config/lazyuv/config.toml`) for
  defaults: default dependency group, confirm-on-remove, output verbosity.
- **Theming** — light/dark and custom Textual themes; respect terminal palette.
- **Custom keybindings** — user-remappable keys via config, for `lazygit`/vim
  muscle memory.
- **Error surfacing** — consistent handling of uv failures (non-zero exits, network
  errors, auth prompts) across every command, building on v1's crash-safe worker.
- **Performance** — keep the read path instant on large lockfiles; lazy-render big
  trees; avoid blocking cache-size scans.
- **Testing** — extend the Pilot-based integration suite to each new mode; keep the
  single mockable subprocess seam so tests never invoke real `uv`.

## Distribution

Getting lazyuv into users' hands — currently only `uv tool install` from source:

- Publish to **PyPI** so `uv tool install lazyuv` / `pipx install lazyuv` work from
  the registry (needs the build/publish pipeline and a trusted-publisher setup).
- **Homebrew** formula / tap for macOS + Linux users.
- Tagged releases with changelog; consider prebuilt standalone binaries later.

## Versioning & releases

Semantic versioning. v1 is the current line (project workflow). Milestones 2–3 are
minor feature releases (0.2, 0.3, …); a 1.0 is warranted once the project surface
(M2) and at least the global dashboard (M3) are stable and the tool is on PyPI.
Each release ships a changelog entry and updates this roadmap's "Status" section.
