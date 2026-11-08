import html
import json
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin import ModelOptions

from .helpers import login


async def test_home_catalog_groups_are_permission_filtered_and_table_pages_keep_only_metadata(
    web_admin,
):
    web_admin.configure("items", options=ModelOptions(group="Sales <team>"))
    app = FastAPI()
    web_admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        dashboard = await client.get("/admin/")
        group = re.search(r'<details[^>]*data-group="Sales &lt;team&gt;"[^>]*>', dashboard.text)[0]
        assert " open" not in group
        page = await client.get("/admin/models/items/")
        assert "data-home-catalog" not in page.text
        metadata = re.search(r"data-catalog='([^']*)'", page.text)[1]
        assert json.loads(html.unescape(metadata))[0]["group"] == "Sales <team>"
        assert "navigation.js" in page.text
        web_admin.configure(
            "items", options=ModelOptions(group="Hidden", permission=lambda r, i, a: False)
        )
        page = await client.get("/admin/")
        assert 'data-group="Hidden"' not in page.text
        assert "navigation.js" in page.text


def test_blank_sidebar_group_is_rejected():
    from quite_admin import Field, ModelSchema

    with pytest.raises(ValueError, match="group"):
        ModelOptions(group=" ").validate(
            ModelSchema("items", (Field("id", int, primary_key=True),))
        )


async def test_listing_automatic_search_has_no_submit_button_and_has_trusted_script(web_admin):
    app = FastAPI()
    web_admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        assert "listing.js" in page.text
        search = page.text.split('role="search"')[1].split("</div>")[0]
        assert "<button" not in search
        assert 'name="q"' in search


async def test_listing_boolean_switches_follow_inline_field_permissions(web_admin, web_backend):
    import re

    adapter, model = web_backend
    await adapter.create(model, {"name": "Switch", "active": True})
    app = FastAPI()
    web_admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        switch = re.search(r"<button[^>]*data-list-switch[^>]*>", page.text).group()
        assert 'aria-checked="true"' in switch and "disabled" not in switch
        assert "data-toggle-endpoint=" in page.text
        web_admin.configure("items", options=ModelOptions(list_editable=()))
        page = await client.get("/admin/models/items/")
        switch = re.search(r"<button[^>]*data-list-switch[^>]*>", page.text).group()
        assert "disabled" in switch and 'aria-checked="true"' in switch
        assert "data-toggle-endpoint=" not in page.text


async def test_listing_edit_button_contains_only_the_pencil(web_admin, web_backend):
    import re

    adapter, model = web_backend
    await adapter.create(model, {"name": "Open this record"})
    app = FastAPI()
    web_admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        cell = re.search(r'<td data-list-field="name"[^>]*>(.*?)</td>', page.text, re.S)[1]
        button = re.search(r'<button class="cell-edit".*?</button>', cell, re.S)[0]
        assert "✎" in button and "data-inline-endpoint=" in button
        assert "data-cell-value" not in button and "Open this record" not in button
        assert cell.index("data-cell-value") < cell.index("cell-edit")
        assert 'class="record-row-link"' in page.text
