from pathlib import Path

from lazyuv.data import load_project
from lazyuv.models import Dependency, LoadStatus, Project, Script

FIXTURE = Path(__file__).parent / "fixtures" / "project"


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
