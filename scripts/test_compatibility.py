"""Resolve and test dependency endpoints in an isolated venv, without changing uv.lock.

Minimum pins every declared runtime dependency to its lower bound. Latest resolves
fresh within the published ranges. Test/build tools remain independently resolvable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runtime_requirements(project, legacy=False):
    """Flatten quite-admin's extras so endpoint constraints cannot be merely transitive."""
    extras = project["optional-dependencies"]
    result = list(project["dependencies"])
    visited = set()

    def include(extra):
        if extra in visited:
            return
        visited.add(extra)
        for requirement in extras[extra]:
            self_reference = re.fullmatch(r"quite-admin\[([^]]+)\]", requirement)
            if self_reference:
                for child in self_reference[1].split(","):
                    include(child)
            else:
                result.append(requirement)

    include("gino-legacy" if legacy else "all")
    return list(dict.fromkeys(result))


def lower_bound(requirement):
    match = re.fullmatch(r"([\w.-]+(?:\[[^]]+\])?)>=([\d.]+),(<[^;]+)", requirement)
    if match is None:
        raise ValueError(f"Declare an explicit supported lower/upper bound: {requirement}")
    return f"{match[1]}=={match[2]},{match[3]}"


def run(command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=ROOT, check=True, **kwargs)


def check(args, environment):
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())
    runtime = runtime_requirements(configuration["project"], args.legacy)
    if args.profile == "minimum":
        runtime = [lower_bound(requirement) for requirement in runtime]
    elif args.profile == "starlette-0":
        runtime.append("starlette<1")
    tools = configuration["dependency-groups"]["gino-check" if args.legacy else "dev"]
    tools = [requirement for requirement in tools if not requirement.startswith("quite-admin[")]
    # In legacy profiles these frameworks also need real declared endpoint checks.
    if args.legacy and args.profile == "minimum":
        tools = [
            lower_bound(requirement)
            if requirement.startswith(("fastapi>=", "litestar>="))
            else requirement
            for requirement in tools
        ]
    extra = "gino-legacy" if args.legacy else "all"
    run([args.uv, "venv", "--python", args.python, environment])
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(
        [args.uv, "pip", "install", "--python", python, "--upgrade", "-e", f"{ROOT}[{extra}]"]
        + runtime
        + tools
    )
    run([args.uv, "pip", "check", "--python", python])
    installed = json.loads(
        subprocess.check_output(
            [args.uv, "pip", "list", "--python", str(python), "--format", "json"], text=True
        )
    )
    versions = {item["name"]: item["version"] for item in installed}
    python_version = subprocess.check_output(
        [python, "-c", "import sys; print(sys.version)"], text=True
    ).strip()
    report = {
        "profile": args.profile,
        "legacy": args.legacy,
        "python": python_version,
        "checked_at": datetime.now(UTC).isoformat(),
        "runtime_requirements": runtime,
        "installed": versions,
        "tests_passed": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    names = {re.match(r"[\w.-]+", requirement)[0].lower() for requirement in runtime}
    print("Resolved runtime:", json.dumps({k: versions.get(k) for k in sorted(names)}, indent=2))
    if args.legacy and not os.environ.get("QUITE_ADMIN_GINO_TEST_DATABASE_URL"):
        raise ValueError("Legacy contracts require a disposable PostgreSQL database, not skips.")
    tests = ["--confcutdir=tests/gino", "tests/gino"] if args.legacy else ["tests"]
    run(
        [
            python,
            "-m",
            "pytest",
            *tests,
            "-q",
            "--tb=short",
            "--maxfail=10",
            f"--junitxml={args.report.with_suffix('.xml')}",
        ]
    )
    report["tests_passed"] = True
    args.report.write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("minimum", "latest", "starlette-0"), required=True)
    parser.add_argument("--python", required=True, help="Python version or executable for uv venv")
    parser.add_argument("--legacy", action="store_true", help="GINO / SQLAlchemy 1.3 + PostgreSQL")
    parser.add_argument("--uv", default=shutil.which("uv") or "uv")
    parser.add_argument(
        "--environment", type=Path, help="Keep the isolated environment at this path"
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report = args.report.resolve()
    if args.legacy and args.profile == "starlette-0":
        parser.error("starlette-0 is a modern-stack profile")
    if args.environment:
        check(args, args.environment.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="quite-admin-compat-") as directory:
            check(args, Path(directory) / "venv")


if __name__ == "__main__":
    main()
