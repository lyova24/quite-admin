"""Validate release inputs and extract the exact changelog section, without importing the app."""

import argparse
import ast
import re
import tomllib
from pathlib import Path


def check(root: Path, tag: str | None = None) -> tuple[str, str]:
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assignments = ast.parse((root / "src/quite_admin/__init__.py").read_text()).body
    public = next(
        ast.literal_eval(node.value)
        for node in assignments
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    )
    if public != version:
        raise ValueError("pyproject.toml and __version__ disagree.")
    if tag is not None and tag != f"v{version}":
        raise ValueError("The release tag must equal v<project.version>.")
    if f"**Version: {version}**" not in (root / "README.md").read_text():
        raise ValueError("README version does not match pyproject.toml.")
    lock = tomllib.loads((root / "uv.lock").read_text())
    if (
        next(item["version"] for item in lock["package"] if item["name"] == "quite-admin")
        != version
    ):
        raise ValueError("uv.lock version does not match pyproject.toml.")
    template = (root / "src/quite_admin/templates/quite_admin/base.html").read_text()
    if f">v{version}</span>" not in template:
        raise ValueError("The UI version does not match pyproject.toml.")
    changelog = (root / "CHANGELOG.md").read_text()
    match = re.search(
        rf"^## {re.escape(version)}(?P<heading>[^\n]*)\n(?P<notes>.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if match is None or not match["notes"].strip():
        raise ValueError("The release needs a nonempty versioned changelog section.")
    if tag is not None and "unreleased" in match["heading"].casefold():
        raise ValueError("Finalize the changelog date before creating the release tag.")
    return version, match["notes"].strip() + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    try:
        version, notes = check(Path(__file__).resolve().parents[1], args.tag)
    except (ValueError, StopIteration) as exc:
        parser.exit(1, f"Release validation failed: {exc}\n")
    if args.notes:
        args.notes.write_text(notes)
    print(f"Validated quite-admin {version}")
