from lazyuv.models import Dependency, LoadStatus, Project


def test_dependency_defaults():
    dep = Dependency(name="httpx", spec=">=0.28", group="main")
    assert dep.resolved_version is None
    assert dep.source == "registry"


def test_project_holds_deps():
    proj = Project(name="x", version="0.1.0", requires_python=">=3.14")
    assert proj.dependencies == []
    assert LoadStatus.OK.value == "ok"
