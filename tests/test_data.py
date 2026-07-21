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


def test_load_not_a_project(tmp_path):
    result = load_project(tmp_path)
    assert result.status is LoadStatus.NOT_A_PROJECT
    assert result.project is None


def test_load_malformed(tmp_path):
    (tmp_path / "pyproject.toml").write_text("this is = = not toml")
    result = load_project(tmp_path)
    assert result.status is LoadStatus.MALFORMED
    assert result.error
