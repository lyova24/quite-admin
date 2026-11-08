import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import ModelOptions

from .helpers import login


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_overview_groups_tables_without_field_counts(web_admin, framework):
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(web_admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        for options in (ModelOptions(), ModelOptions(group="Sales <team>")):
            web_admin.configure("items", options=options)
            response = await client.get("/admin/")
            assert response.status_code == 200
            group = re.search(r"<details[^>]*data-dashboard-group[^>]*>", response.text)[0]
            assert "open" not in group
            card = re.search(r'<a class="collection-card".*?</a>', response.text, re.S)[0]
            assert "/models/items/" in card and "Items" in card
            assert "muted" not in card and " fields" not in card
        assert "Sales &lt;team&gt;" in response.text
        web_admin.configure(
            "items", options=ModelOptions(group="Hidden", permission=lambda r, i, a: False)
        )
        response = await client.get("/admin/")
        assert "data-dashboard-group" not in response.text and "Hidden" not in response.text
