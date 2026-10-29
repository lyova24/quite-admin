import re
import shutil
import tomllib
from pathlib import Path

import pytest

from scripts.check_release import check


@pytest.fixture
def release_tree(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in (
        "pyproject.toml",
        "README.md",
        "CHANGELOG.md",
        "uv.lock",
        "src/quite_admin/__init__.py",
        "src/quite_admin/templates/quite_admin/base.html",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    version = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]["version"]
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        re.sub(
            rf"^## {re.escape(version)}[^\n]*",
            f"## {version} — Unreleased",
            changelog.read_text(),
            flags=re.MULTILINE,
        )
    )
    return tmp_path


def test_release_requires_matching_versions_tag_and_finalized_changelog(release_tree):
    version, notes = check(release_tree)
    assert notes.strip() and not notes.startswith("# Changelog")
    with pytest.raises(ValueError, match="tag must equal"):
        check(release_tree, "v99.0.0")
    with pytest.raises(ValueError, match="Finalize the changelog"):
        check(release_tree, "v" + version)
    path = release_tree / "CHANGELOG.md"
    path.write_text(path.read_text().replace("Unreleased", "2026-10-29", 1))
    assert check(release_tree, "v" + version)[0] == version
    path = release_tree / "README.md"
    path.write_text(path.read_text().replace(f"Version: {version}", "Version: 99.0.0"))
    with pytest.raises(ValueError, match="README version"):
        check(release_tree, "v" + version)
