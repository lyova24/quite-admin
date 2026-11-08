"""Asset reuse must preserve CSP hashes and refresh them when built-in files change."""

import base64
import hashlib
import os
import shutil
from collections import Counter
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin._admin import rendering
from quite_admin._admin.assets import BUILTIN_SCRIPTS, script_names

from .helpers import login


def test_script_dependencies_keep_order_and_reject_unknown_assets():
    assert script_names(("forms.js", "history.js", "datetime.js", "forms.js")) == (
        "datetime.js",
        "forms.js",
        "history.js",
    )
    with pytest.raises(ValueError, match="Unknown built-in script"):
        script_names(("../custom.js",))


async def test_repeated_pages_reuse_hashes_and_refresh_after_an_equal_size_asset_edit(
    web_admin, monkeypatch, tmp_path
):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in BUILTIN_SCRIPTS:
        shutil.copyfile(rendering.STATIC_DIR / name, assets / name)
    monkeypatch.setattr(rendering, "STATIC_DIR", assets)
    reads = Counter()
    read_bytes = Path.read_bytes

    def counted_read(path):
        if path.parent == assets:
            reads[path.name] += 1
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read)
    host = FastAPI()
    web_admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        first = await client.get("/admin/")
        second = await client.get("/admin/")
        assert first.status_code == second.status_code == 200
        assert first.headers["content-security-policy"] == second.headers["content-security-policy"]
        assert reads == {"table-navigation.js": 1, "navigation.js": 1, "dashboard.js": 1}

        script = assets / "navigation.js"
        original = script.stat()
        body = read_bytes(script)
        # Equal length and the same mtime must still invalidate the content hash.
        edited = b" " + body[1:]
        assert edited != body
        script.write_bytes(edited)
        os.utime(script, ns=(original.st_atime_ns, original.st_mtime_ns))
        changed = await client.get("/admin/")
        expected = "sha256-" + base64.b64encode(hashlib.sha256(edited).digest()).decode()
        assert expected in changed.headers["content-security-policy"]
        assert f'integrity="{expected}"' in changed.text
        assert reads == {"table-navigation.js": 1, "navigation.js": 2, "dashboard.js": 1}
        assert (
            changed.headers["content-security-policy"] != first.headers["content-security-policy"]
        )
