"""Install both artifacts into isolated environments and exercise packaged assets and HTTP."""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

SMOKE = r"""
import asyncio
import html
import re
import sys
from importlib import metadata, resources
from pathlib import Path

import quite_admin
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from quite_admin import Admin, PasswordAuth
from quite_admin.adapters.sql import SQLAdapter

assert quite_admin.__version__ == sys.argv[1] == metadata.version("quite-admin")
assert Path(quite_admin.__file__).is_relative_to(Path(sys.prefix))
root = resources.files("quite_admin")
for name in ("py.typed", "templates/quite_admin/list.html", "templates/quite_admin/_icons.html",
             "static/admin.css", "static/filters.js", "static/forms.js", "static/inline.js"):
    assert root.joinpath(name).is_file(), name
engine = create_engine("sqlite:///smoke.db")
schema = MetaData()
table = Table("items", schema, Column("id", Integer, primary_key=True), Column("name", String(80)))
schema.create_all(engine)
with engine.begin() as connection:
    connection.execute(table.insert(), {"name": "Packaged record"})

async def check():
    for host, mount in ((FastAPI(), "mount_fastapi"), (Litestar(), "mount_litestar")):
        admin = Admin(auth=PasswordAuth.single_user("smoke", "artifact-smoke-password"),
                      secret_key="artifact-fixture-only-" * 3, secure_cookies=False,
                      adapters=[SQLAdapter(engine)])
        getattr(admin, mount)(host)
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            login = await client.get("/admin/login")
            token = html.unescape(re.search(r'name="__csrf" value="([^"]+)"', login.text)[1])
            response = await client.post("/admin/login", data={"__csrf":token, "username":"smoke",
                                                              "password":"artifact-smoke-password"})
            assert response.status_code == 303, response.text
            page = await client.get("/admin/models/items/", params={"f.name.icontains":"packaged"})
            assert page.status_code == 200 and "Packaged record" in page.text
            assert "unsafe-inline" not in page.headers["content-security-policy"]
            for asset in ("admin.css", "filters.js", "forms.js"):
                assert (await client.get("/admin/assets/" + asset)).status_code == 200
            result = await client.get(
                "/admin/models/items/", params={"export":"csv", "columns":"name"}
            )
            assert result.status_code == 200 and "Packaged record" in result.text

asyncio.run(check())
engine.dispose()
"""


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    artifacts = [
        root / "dist" / f"quite_admin-{version}{suffix}"
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    ]
    if any(not path.is_file() for path in artifacts):
        raise SystemExit("Build the current wheel and sdist before running the installation check.")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv must be installed to create clean artifact environments.")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    for artifact in artifacts:
        with TemporaryDirectory(prefix="quite-admin-artifact-") as temporary:
            workspace = Path(temporary)
            virtualenv = workspace / "venv"
            subprocess.run(
                [uv, "venv", "--python", sys.executable, str(virtualenv)],
                check=True,
                env=environment,
            )
            python = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    f"{artifact}[fastapi,litestar,sqlalchemy]",
                    "httpx>=0.27,<1",
                ],
                cwd=workspace,
                check=True,
                env=environment,
            )
            subprocess.run(
                [str(python), "-I", "-c", SMOKE, version],
                cwd=workspace,
                check=True,
                env=environment,
            )
            print(f"Installed and verified {artifact.name}", flush=True)


if __name__ == "__main__":
    main()
