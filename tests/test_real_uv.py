"""A few checks against the REAL `uv` binary.

The rest of the suite mocks the subprocess seams and asserts "argv is
well-formed" — necessary, but it can't catch a flag uv doesn't actually accept or
a block shape we misread. These tests run real `uv` in a tmp dir to confirm the M5
inline-script builders do what we intend end-to-end, then read the result back with
our own parser. They skip cleanly when `uv` is missing or resolution fails (e.g. no
network in CI), so they never turn into flaky failures.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lazyuv.commands import (
    build_add_script,
    build_init,
    build_remove_script,
    build_run,
    build_run_script,
    build_tree,
    build_version_bump,
    build_version_set,
    uv_available,
)
from lazyuv.data import (
    load_project,
    load_script,
    parse_outdated,
    parse_pep723_block,
    parse_tree,
)
from lazyuv.models import LoadStatus

pytestmark = pytest.mark.skipif(not uv_available(), reason="uv not on PATH")

# A leaf package (no dependencies) keeps resolution fast and offline-friendlier.
_PKG = "iniconfig"


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=120, check=False
    )


# Substrings uv emits for network/resolution failures. Only these are treated as
# "offline" and skipped; ANY OTHER nonzero exit (an unsupported/misspelled flag, a
# changed CLI) must FAIL — that is the whole point of exercising real uv here.
_NETWORK_MARKERS = (
    "network",
    "failed to fetch",
    "error sending request",
    "could not connect",
    "connection",
    "timed out",
    "timeout",
    "offline",
    "temporary failure in name resolution",
    "dns error",
    "no such host",
    "failed to resolve",
    "tls",
)


def _skip_only_if_offline(result: subprocess.CompletedProcess) -> None:
    if result.returncode == 0:
        return
    stderr = result.stderr.lower()
    if any(marker in stderr for marker in _NETWORK_MARKERS):
        pytest.skip(f"uv could not reach the network: {result.stderr.strip()}")
    # Not a network problem → a real, test-worthy failure (bad flag, changed CLI).
    raise AssertionError(f"uv exited {result.returncode}: {result.stderr.strip()}")


def test_real_add_script_creates_readable_block(tmp_path):
    script = tmp_path / "demo.py"
    script.write_text('print("hi")\n')

    result = _run(build_add_script("demo.py", [_PKG]), tmp_path)
    _skip_only_if_offline(result)

    # uv wrote a PEP 723 block our parser reads back, with the package we asked for.
    meta = parse_pep723_block(script.read_text())
    assert meta is not None
    assert any(dep.split(">=")[0].split("==")[0].strip() == _PKG
               for dep in meta["dependencies"])
    loaded = load_script(script)
    assert loaded is not None and loaded.has_block
    assert _PKG in {d.name for d in loaded.dependencies}


def test_real_remove_script_drops_entry(tmp_path):
    script = tmp_path / "demo.py"
    script.write_text('print("hi")\n')

    add = _run(build_add_script("demo.py", [_PKG]), tmp_path)
    _skip_only_if_offline(add)
    assert _PKG in {d.name for d in load_script(script).dependencies}

    remove = _run(build_remove_script("demo.py", _PKG), tmp_path)
    assert remove.returncode == 0, remove.stderr
    # The block survives (per uv), but the entry is gone.
    assert _PKG not in {d.name for d in load_script(script).dependencies}


def test_real_run_script_executes(tmp_path):
    script = tmp_path / "demo.py"
    script.write_text('print("lazyuv-marker")\n')  # no deps -> no resolution needed

    result = _run(build_run_script("demo.py"), tmp_path)
    assert result.returncode == 0, result.stderr
    assert "lazyuv-marker" in result.stdout


# --- Milestone 6: tree / outdated / run-with-args --------------------------


def _init_project(tmp_path: Path, *pkgs: str) -> subprocess.CompletedProcess:
    _run(["uv", "init", "--quiet", "."], tmp_path)
    return _run(["uv", "add", *pkgs], tmp_path)


def test_real_tree_json_parses(tmp_path):
    _skip_only_if_offline(_init_project(tmp_path, "rich"))
    result = _run(build_tree(), tmp_path)
    _skip_only_if_offline(result)
    forest = parse_tree(result.stdout)
    assert len(forest) >= 1
    # rich pulls transitive deps, so the root must have children
    assert any(node.children for node in forest)


def test_real_tree_outdated_surfaces_latest(tmp_path):
    # Pin an old rich so a newer release is guaranteed to exist.
    _skip_only_if_offline(_init_project(tmp_path, "rich==13.0.0"))
    result = _run(build_tree(outdated=True), tmp_path)
    _skip_only_if_offline(result)
    outdated = parse_outdated(result.stdout)
    assert "rich" in outdated
    assert outdated["rich"] != "13.0.0"


def test_real_run_passes_args_without_separator(tmp_path):
    # No deps -> no resolution/network needed for the run itself.
    (tmp_path / "main.py").write_text("import sys\nprint('GOT', sys.argv[1:])\n")
    result = _run(build_run("main.py", ["--verbose", "pos"]), tmp_path)
    assert result.returncode == 0, result.stderr
    # args reach the program verbatim, and NO literal "--" was injected
    assert "GOT ['--verbose', 'pos']" in result.stdout
    assert "'--'" not in result.stdout


def test_real_version_bump_rewrites_pyproject(tmp_path):
    _init = _run(["uv", "init", "--quiet", "."], tmp_path)
    _skip_only_if_offline(_init)
    # dep-less project -> re-lock is offline; bump 0.1.0 -> 0.1.1
    result = _run(build_version_bump("patch"), tmp_path)
    _skip_only_if_offline(result)
    proj = load_project(tmp_path).project
    assert proj is not None and proj.version == "0.1.1"


def test_real_version_set_exact(tmp_path):
    _init = _run(["uv", "init", "--quiet", "."], tmp_path)
    _skip_only_if_offline(_init)
    result = _run(build_version_set("9.9.9"), tmp_path)
    _skip_only_if_offline(result)
    proj = load_project(tmp_path).project
    assert proj is not None and proj.version == "9.9.9"


def test_real_init_app_creates_loadable_project(tmp_path):
    result = _run(build_init("app"), tmp_path)  # offline
    assert result.returncode == 0, result.stderr
    loaded = load_project(tmp_path)
    assert loaded.status is LoadStatus.OK
    # uv derives (and PEP 503-normalizes) the name from the directory
    assert loaded.project.name  # a real, non-empty project name


def test_real_init_bare_only_pyproject(tmp_path):
    result = _run(build_init("bare"), tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "pyproject.toml").is_file()
    assert not (tmp_path / "main.py").exists()
