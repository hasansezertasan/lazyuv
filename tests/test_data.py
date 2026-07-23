import json
from pathlib import Path

from lazyuv.data import (
    _compute_drift,
    _read_environment,
    _read_pin,
    _read_venv,
    load_project,
    parse_python_list,
)
from lazyuv.models import Dependency, LoadStatus, Project, PythonVersion, Script

FIXTURE = Path(__file__).parent / "fixtures" / "project"


def _write_venv(root: Path, version: str, home: str = "/usr/bin") -> None:
    venv = root / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text(f"home = {home}\nversion_info = {version}\n")


def test_dependency_defaults():
    dep = Dependency(name="httpx", spec=">=0.28", group="main")
    assert dep.resolved_version is None
    assert dep.source == "registry"


def test_project_holds_deps():
    proj = Project(name="x", version="0.1.0", requires_python=">=3.14")
    assert proj.dependencies == []
    assert LoadStatus.OK.value == "ok"


def test_load_ok_status():
    result = load_project(FIXTURE)
    assert result.status is LoadStatus.OK
    assert result.project is not None
    assert result.project.name == "sample"
    assert result.project.version == "0.2.0"
    assert result.project.requires_python == ">=3.14"


def test_load_groups_and_resolved_versions():
    proj = load_project(FIXTURE).project
    by_name = {d.name: d for d in proj.dependencies}

    assert by_name["httpx"].group == "main"
    assert by_name["httpx"].spec == ">=0.28.1"
    assert by_name["httpx"].resolved_version == "0.28.1"

    assert by_name["typer"].group == "cli"
    assert by_name["typer"].resolved_version == "0.12.5"

    assert by_name["pytest"].group == "dev"
    assert by_name["pytest"].resolved_version == "8.3.2"


def test_load_scripts():
    proj = load_project(FIXTURE).project
    assert proj.scripts == [Script("serve", "sample.cli:serve")]


def test_load_sets_kind():
    proj = load_project(FIXTURE).project
    by_name = {d.name: d for d in proj.dependencies}
    assert by_name["httpx"].kind == "main"
    assert by_name["typer"].kind == "extra"   # from [project.optional-dependencies]
    assert by_name["pytest"].kind == "dev"    # from [dependency-groups].dev


def test_load_skips_include_group(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        "dependencies = []\n\n"
        "[dependency-groups]\n"
        'lint = ["ruff>=0.4"]\n'
        'dev = [{include-group = "lint"}, "pytest>=8"]\n'
    )
    result = load_project(tmp_path)
    assert result.status is LoadStatus.OK
    pairs = {(d.group, d.name) for d in result.project.dependencies}
    assert ("lint", "ruff") in pairs
    assert ("dev", "pytest") in pairs
    # the {include-group = "lint"} reference must NOT appear as a dependency
    assert all(d.name for d in result.project.dependencies)
    lint_kind = {d.name: d.kind for d in result.project.dependencies if d.group == "lint"}
    assert lint_kind["ruff"] == "group"


def test_load_not_a_project(tmp_path):
    result = load_project(tmp_path)
    assert result.status is LoadStatus.NOT_A_PROJECT
    assert result.project is None


def test_load_malformed(tmp_path):
    (tmp_path / "pyproject.toml").write_text("this is = = not toml")
    result = load_project(tmp_path)
    assert result.status is LoadStatus.MALFORMED
    assert result.error


def test_load_collects_groups_including_empty(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        "dependencies = []\n\n"
        "[project.optional-dependencies]\n"
        "cli = []\n\n"
        "[dependency-groups]\n"
        "docs = []\n"
    )
    proj = load_project(tmp_path).project
    # Empty groups must still be discoverable as add targets.
    assert ("cli", "extra") in proj.groups
    assert ("docs", "group") in proj.groups


def test_forked_package_lists_all_versions(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["httpx", "rich"]\n'
    )
    # httpx is forked (two entries, different versions); rich is single.
    (tmp_path / "uv.lock").write_text(
        "version = 1\n"
        'requires-python = ">=3.14"\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.27.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.28.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        "[[package]]\n"
        'name = "rich"\n'
        'version = "13.7.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
    )
    proj = load_project(tmp_path).project
    by_name = {d.name: d for d in proj.dependencies}

    # forked: all distinct versions, in lock order; primary is the first
    assert by_name["httpx"].locked_versions == ("0.27.0", "0.28.1")
    assert by_name["httpx"].resolved_version == "0.27.0"

    # non-forked: unchanged, no locked_versions
    assert by_name["rich"].locked_versions == ()
    assert by_name["rich"].resolved_version == "13.7.1"


def test_duplicate_version_across_entries_is_not_a_fork(tmp_path):
    # Two entries, same version -> one distinct version -> not treated as forked.
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["httpx"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        "version = 1\n"
        'requires-python = ">=3.14"\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.28.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.28.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
    )
    proj = load_project(tmp_path).project
    httpx = next(d for d in proj.dependencies if d.name == "httpx")
    assert httpx.locked_versions == ()
    assert httpx.resolved_version == "0.28.1"


def test_read_lock_skips_nameless_package(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["httpx>=0.1"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        "version = 1\n"
        'requires-python = ">=3.14"\n\n'
        "[[package]]\n"  # malformed: no name — must be skipped, not keyed on ""
        'version = "9.9.9"\n\n'
        "[[package]]\n"
        'name = "httpx"\n'
        'version = "0.28.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
    )
    proj = load_project(tmp_path).project
    by_name = {d.name: d for d in proj.dependencies}
    assert by_name["httpx"].resolved_version == "0.28.1"
    assert all(d.name for d in proj.dependencies)


# --- environment (Python / venv) read path ---------------------------------


def test_read_pin_first_nonempty_line(tmp_path):
    (tmp_path / ".python-version").write_text("\n3.14\n3.12\n")
    assert _read_pin(tmp_path) == "3.14"


def test_read_pin_absent(tmp_path):
    assert _read_pin(tmp_path) is None


def test_read_venv_version_info_and_home(tmp_path):
    _write_venv(tmp_path, "3.14.0", home="/opt/py/bin")
    version, home = _read_venv(tmp_path / ".venv" / "pyvenv.cfg")
    assert version == "3.14.0"
    assert home == "/opt/py/bin"


def test_read_venv_falls_back_to_version_key(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /x\nversion = 3.13.1\n")
    version, _home = _read_venv(venv / "pyvenv.cfg")
    assert version == "3.13.1"


def test_read_venv_absent(tmp_path):
    assert _read_venv(tmp_path / ".venv" / "pyvenv.cfg") == (None, None)


def test_compute_drift_none_without_venv():
    assert _compute_drift(None, "3.14", ">=3.14") is None


def test_compute_drift_pin_mismatch():
    note = _compute_drift("3.12.0", "3.14", ">=3.10")
    assert note is not None and "3.12.0" in note and "3.14" in note


def test_compute_drift_pin_matches_by_component():
    # pin 3.14 matches venv 3.14.0 (component prefix), and pin drives the check
    assert _compute_drift("3.14.0", "3.14", "==3.10") is None
    # pin 3.1 must NOT match venv 3.14.0 (component-wise, not string startswith)
    assert _compute_drift("3.14.0", "3.1", "") is not None


def test_compute_drift_requires_python_floor_below():
    note = _compute_drift("3.12.0", None, ">=3.14")
    assert note is not None and "below" in note


def test_compute_drift_requires_python_floor_satisfied():
    assert _compute_drift("3.14.0", None, ">=3.14") is None


def test_compute_drift_requires_python_exact_and_compatible():
    # No-pin `==` and `~=` branches (venv major.minor from uv is "3.14").
    assert _compute_drift("3.14", None, "==3.12") is not None  # exact mismatch -> drift
    assert _compute_drift("3.14", None, "==3.14") is None      # exact match -> no drift
    assert _compute_drift("3.10", None, "~=3.14") is not None  # below compat floor


def test_compute_drift_complex_requires_python_is_unknown():
    # A compound specifier must be treated as unknown, never compared on its first
    # clause (">=3.9,<3.11" with a 3.14 venv would else wrongly read as satisfied).
    assert _compute_drift("3.12.0", None, ">=3.11,<4.0") is None
    assert _compute_drift("3.14.0", None, ">=3.9,<3.11") is None


def test_compute_drift_patch_pin_no_false_alarm():
    # uv writes major.minor only into pyvenv.cfg ("3.14"); a patch-level pin must
    # NOT be reported as drift just because the patch can't be confirmed.
    assert _compute_drift("3.14", "3.14.2", "") is None
    # but a real major.minor mismatch against a patch pin still drifts
    assert _compute_drift("3.12", "3.14.2", "") is not None


def test_compute_drift_non_version_pin_is_unknown():
    # Implementation-qualified pins / full uv keys can't be compared to a bare
    # venv version -> unknown, not a bogus "≠ pinned" message.
    assert _compute_drift("3.14.0", "pypy@3.10", "") is None
    assert _compute_drift("3.14.0", "cpython-3.14.6-macos-aarch64-none", "") is None


def test_read_environment_composes(tmp_path):
    (tmp_path / ".python-version").write_text("3.14\n")
    _write_venv(tmp_path, "3.12.0")
    env = _read_environment(tmp_path, ">=3.10")
    assert env.pinned_python == "3.14"
    assert env.venv_python == "3.12.0"
    assert env.venv_path == ".venv"
    assert env.drift is not None  # venv 3.12 != pin 3.14


def test_load_project_attaches_environment():
    proj = load_project(FIXTURE).project
    assert proj.environment is not None


def test_parse_python_list_managed_system_and_available():
    output = json.dumps(
        [
            {
                "key": "cpython-3.14.6-macos-aarch64-none",
                "version": "3.14.6",
                "implementation": "cpython",
                "path": "/Users/x/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14",
            },
            {
                "key": "cpython-3.12.13-macos-aarch64-none",
                "version": "3.12.13",
                "implementation": "cpython",
                "path": "/opt/homebrew/bin/python3.12",
            },
            {
                "key": "pypy-3.10.14-macos-aarch64-none",
                "version": "3.10.14",
                "implementation": "pypy",
                "path": None,
            },
        ]
    )
    versions = parse_python_list(output)
    # uv-managed install: installed + managed (uninstallable)
    assert versions[0] == PythonVersion(
        key="cpython-3.14.6-macos-aarch64-none",
        version="3.14.6",
        implementation="cpython",
        installed=True,
        managed=True,
        path="/Users/x/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14",
    )
    # homebrew system interpreter: installed but NOT managed (not uninstallable)
    assert versions[1].installed is True
    assert versions[1].managed is False
    # downloadable: not installed, and preserves implementation to disambiguate
    assert versions[2].installed is False
    assert versions[2].implementation == "pypy"


def test_parse_python_list_skips_entries_without_key():
    # A row missing uv's `key` can't be acted on unambiguously -> skip it.
    output = json.dumps([{"version": "3.14.0", "path": None}])
    assert parse_python_list(output) == []


def test_parse_python_list_malformed_is_empty():
    assert parse_python_list("not json") == []
    assert parse_python_list("") == []


# --- global state: tools / cache / version ---------------------------------


def test_parse_tool_list_multiple_tools_and_executables():
    from lazyuv.data import parse_tool_list
    from lazyuv.models import Tool

    output = (
        "ruff v0.11.31\n"
        "- ruff\n"
        "homebrew-pypi-poet v0.10.0\n"
        "- poet\n"
        "hatch v1.16.5\n"
        "- hatch\n"
        "- hatchling\n"
    )
    tools = parse_tool_list(output)
    assert tools == [
        Tool("ruff", "0.11.31", ("ruff",)),
        Tool("homebrew-pypi-poet", "0.10.0", ("poet",)),
        Tool("hatch", "1.16.5", ("hatch", "hatchling")),
    ]


def test_parse_tool_list_tool_without_executables():
    from lazyuv.data import parse_tool_list

    tools = parse_tool_list("mytool v1.2.3\n")
    assert tools == [__import__("lazyuv.models", fromlist=["Tool"]).Tool("mytool", "1.2.3", ())]


def test_parse_tool_list_empty_and_no_tools_message():
    from lazyuv.data import parse_tool_list

    assert parse_tool_list("") == []
    assert parse_tool_list("No tools installed.\n") == []


def test_parse_uv_version_extracts_and_falls_back():
    from lazyuv.data import parse_uv_version

    assert parse_uv_version("uv 0.11.31 (Homebrew 2026-07-22 aarch64-apple-darwin)") == "0.11.31"
    assert parse_uv_version("weird output") == "weird output"


def test_directory_size_sums_files(tmp_path):
    from lazyuv.data import directory_size

    (tmp_path / "a").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b").write_bytes(b"y" * 50)
    assert directory_size(tmp_path) == 150


def test_directory_size_missing_dir_is_zero(tmp_path):
    from lazyuv.data import directory_size

    assert directory_size(tmp_path / "nope") == 0


def test_format_size_units():
    from lazyuv.data import format_size

    assert format_size(0) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(1536) == "1.5 KiB"
    assert format_size(5 * 1024 * 1024) == "5.0 MiB"
    assert format_size(2 * 1024**3) == "2.0 GiB"


def test_format_size_boundaries_and_tib():
    from lazyuv.data import format_size

    # just under 1 MiB must promote to MiB, not show "1024.0 KiB"
    assert format_size(1024**2 - 1) == "1.0 MiB"
    assert format_size(1024**3 - 1) == "1.0 GiB"
    # TiB is supported (no unbounded "GiB" for huge caches)
    assert format_size(1024**4) == "1.0 TiB"
    assert format_size(3 * 1024**4) == "3.0 TiB"


def test_parse_tool_list_tolerates_extra_spacing():
    from lazyuv.data import parse_tool_list

    # a future padding change (two spaces) must not silently drop the tool
    tools = parse_tool_list("ruff  v0.11.31\n- ruff\n")
    assert len(tools) == 1
    assert tools[0].name == "ruff" and tools[0].version == "0.11.31"


def test_directory_size_on_a_file_is_zero(tmp_path):
    from lazyuv.data import directory_size

    f = tmp_path / "afile"
    f.write_bytes(b"x" * 100)
    # a non-directory path yields 0 (documented "0 if missing/unreadable")
    assert directory_size(f) == 0


# --- M4: sources & workspaces ----------------------------------------------


def test_source_detail_for_each_kind():
    from lazyuv.data import _source_detail

    assert _source_detail({"workspace": True}) == "workspace"
    assert _source_detail({"git": "https://x/y.git"}) == "git (https://x/y.git)"
    assert _source_detail({"path": "../lib"}) == "path (../lib)"
    assert _source_detail({"path": "../lib", "editable": True}) == "path (../lib) editable"
    assert _source_detail({"editable": True}) == "editable"
    assert _source_detail("nonsense") == ""


def test_load_attaches_source_detail(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "x"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["mylib", "httpx"]\n\n'
        "[tool.uv.sources]\n"
        "mylib = { workspace = true }\n"
    )
    proj = load_project(tmp_path).project
    by_name = {d.name: d for d in proj.dependencies}
    assert by_name["mylib"].source_detail == "workspace"
    assert by_name["httpx"].source_detail == ""  # no sources entry


def _write_workspace(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "wsroot"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        "dependencies = []\n\n"
        "[tool.uv.workspace]\n"
        'members = ["packages/*"]\n'
        'exclude = ["packages/skip"]\n'
    )
    for name in ("alpha", "beta", "skip"):
        d = root / "packages" / name
        d.mkdir(parents=True)
        (d / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\n'
            'version = "0.1.0"\n'
            'requires-python = ">=3.14"\n'
            "dependencies = []\n"
        )
    # a directory that matches the glob but has no pyproject -> not a member
    (root / "packages" / "notapkg").mkdir()


def test_workspace_members_resolved(tmp_path):
    _write_workspace(tmp_path)
    proj = load_project(tmp_path).project
    members = proj.workspace_members
    names = [m.name for m in members]
    assert names[0] == "wsroot" and members[0].is_root  # root first
    assert "alpha" in names and "beta" in names
    assert "skip" not in names  # excluded
    assert all(m.name != "notapkg" for m in members)  # no pyproject -> skipped
    alpha = next(m for m in members if m.name == "alpha")
    assert alpha.directory == "packages/alpha"


def test_non_workspace_has_no_members():
    proj = load_project(FIXTURE).project
    assert proj.workspace_members == []


def test_load_member_directory_scopes_to_member(tmp_path):
    _write_workspace(tmp_path)
    (tmp_path / "packages" / "alpha" / "pyproject.toml").write_text(
        "[project]\n"
        'name = "alpha"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["rich"]\n'
    )
    member = load_project(tmp_path / "packages" / "alpha").project
    assert member.name == "alpha"
    assert [d.name for d in member.dependencies] == ["rich"]
