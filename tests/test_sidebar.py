import base64
import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin import Admin, Page

from .helpers import login


@pytest.mark.parametrize(
    ("language", "home", "profile"),
    [
        ("en", "Home", "Profile"),
        ("ru", "Главная", "Профиль"),
    ],
)
async def test_fixed_rail_is_localized_mount_scoped_and_hash_trusted(
    auth, tmp_path, language, home, profile
):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "report.html").write_text(
        '{% extends "quite_admin/base.html" %}{% block content %}Report{% endblock %}'
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 48,
        secure_cookies=False,
        language=language,
        templates_dir=templates,
    )
    admin.add_page(Page("report", "Report", "report.html"))
    app = FastAPI()
    admin.mount_fastapi(app, "/tools/admin")
    asset = Path(__file__).parents[1] / "src/quite_admin/static/navigation.js"
    digest = "sha256-" + base64.b64encode(hashlib.sha256(asset.read_bytes()).digest()).decode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        signed_out = await client.get("/tools/admin/login")
        assert "data-sidebar-toggle" not in signed_out.text
        assert "navigation.js" not in signed_out.text
        await login(client, "/tools/admin")
        for path in ("/", "/schema", "/history", "/pages/report"):
            response = await client.get("/tools/admin" + path)
            assert response.status_code == 200
            assert 'data-admin-shell data-storage-key="/tools/admin/"' in response.text
            assert '<aside class="sidebar" id="admin-sidebar">' in response.text
            aside = response.text.split('<aside class="sidebar" id="admin-sidebar">')[1].split(
                "</aside>"
            )[0]
            assert f'aria-label="{home}"' in aside
            assert f'aria-label="{profile}"' in aside
            assert 'href="/tools/admin/"' in aside
            assert 'action="/tools/admin/logout"' in aside
            assert 'name="__csrf"' in aside
            assert "data-table-directory" not in aside
            assert "data-table-search" not in aside
            for removed in (
                "data-sidebar-toggle",
                "data-sidebar-resizer",
                "data-sidebar-dismiss",
            ):
                assert removed not in response.text
            assert response.text.index("data-table-directory") > response.text.index("</aside>")
            assert f'integrity="{digest}"' in response.text
            policy = response.headers["content-security-policy"]
            assert f"'{digest}'" in policy
            assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
            assert "'self'" not in policy.split("script-src ")[1].split(";")[0]
