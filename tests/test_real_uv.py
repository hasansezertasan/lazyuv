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
    build_remove_script,
    build_run_script,
    uv_available,
)
from lazyuv.data import load_script, parse_pep723_block

pytestmark = pytest.mark.skipif(not uv_available(), reason="uv not on PATH")

# A leaf package (no dependencies) keeps resolution fast and offline-friendlier.
_PKG = "iniconfig"


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=120, check=False
    )


def _skip_if_no_network(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        pytest.skip(f"uv could not resolve (likely offline): {result.stderr.strip()}")


def test_real_add_script_creates_readable_block(tmp_path):
    script = tmp_path / "demo.py"
    script.write_text('print("hi")\n')

    result = _run(build_add_script("demo.py", [_PKG]), tmp_path)
    _skip_if_no_network(result)

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
    _skip_if_no_network(add)
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
