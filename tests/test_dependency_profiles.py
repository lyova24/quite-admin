import tomllib
from pathlib import Path

import pytest

from scripts.test_compatibility import lower_bound, runtime_requirements

ROOT = Path(__file__).resolve().parents[1]


def test_minimum_profiles_cover_declared_runtime_dependencies_and_preserve_extras():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    modern = runtime_requirements(project)
    legacy = runtime_requirements(project, legacy=True)
    assert all(
        requirement in modern and requirement in legacy for requirement in project["dependencies"]
    )
    assert any(requirement.startswith("sqlmodel>=") for requirement in modern)
    assert any(requirement.startswith("sqlalchemy[asyncio]>=") for requirement in modern)
    assert not any(requirement.startswith("gino>=") for requirement in modern)
    assert not any(requirement.startswith("sqlmodel>=") for requirement in legacy)
    assert any(requirement.startswith("gino>=") for requirement in legacy)
    for requirement in modern + legacy:
        pin = lower_bound(requirement)
        assert ">=" not in pin and "==" in pin and ",<" in pin
    assert lower_bound("sqlalchemy[asyncio]>=2.0.14,<2.1") == "sqlalchemy[asyncio]==2.0.14,<2.1"


@pytest.mark.parametrize(
    "requirement", ["package", "package>=1", "package~=1.2", "package>=1; os_name=='nt'"]
)
def test_unbounded_or_conditional_floors_require_explicit_profile_support(requirement):
    with pytest.raises(ValueError, match="explicit supported lower/upper bound"):
        lower_bound(requirement)
