import pytest

from lazyuv.parsing import canonical_name, split_requirement


@pytest.mark.parametrize(
    ("requirement", "name", "spec"),
    [
        ("httpx", "httpx", ""),
        ("httpx>=0.28.1", "httpx", ">=0.28.1"),
        ("httpx[socks]>=0.28.1", "httpx", ">=0.28.1"),
        ("httpx >= 0.28.1", "httpx", ">= 0.28.1"),
        ("ruff==0.4.8 ; python_version > '3.10'", "ruff", "==0.4.8"),
        ("Flask", "flask", ""),
        ("typing_extensions", "typing-extensions", ""),
    ],
)
def test_split_requirement(requirement, name, spec) -> None:
    got_name, got_spec = split_requirement(requirement)
    assert got_name == name
    assert got_spec == spec


def test_canonical_name() -> None:
    assert canonical_name("Typing_Extensions") == "typing-extensions"
    assert canonical_name("ruamel.yaml") == "ruamel-yaml"
