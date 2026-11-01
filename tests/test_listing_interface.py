import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin import ModelOptions

from .helpers import login


async def test_sidebar_groups_are_permission_filtered_and_current_group_is_marked(admin):
    admin.configure("items", options=ModelOptions(group="Sales <team>"))
    app = FastAPI()
    admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        assert "data-current-group" in page.text and "Sales &lt;team&gt;" in page.text
        assert "navigation.js" in page.text
        admin.configure(
            "items", options=ModelOptions(group="Hidden", permission=lambda r, i, a: False)
        )
        page = await client.get("/admin/")
        assert 'data-group="Hidden"' not in page.text
        assert "navigation.js" not in page.text


def test_blank_sidebar_group_is_rejected():
    from quite_admin import Field, ModelSchema

    with pytest.raises(ValueError, match="group"):
        ModelOptions(group=" ").validate(
            ModelSchema("items", (Field("id", int, primary_key=True),))
        )


async def test_listing_automatic_search_has_no_submit_button_and_has_trusted_script(admin):
    app = FastAPI()
    admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        assert "listing.js" in page.text
        search = page.text.split('role="search"')[1].split("</div>")[0]
        assert "<button" not in search
        assert 'name="q"' in search


async def test_listing_boolean_switches_follow_inline_field_permissions(admin, backend):
    import re

    adapter, model = backend
    await adapter.create(model, {"name": "Switch", "active": True})
    app = FastAPI()
    admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        switch = re.search(r"<button[^>]*data-list-switch[^>]*>", page.text).group()
        assert 'aria-checked="true"' in switch and "disabled" not in switch
        assert "data-toggle-endpoint=" in page.text
        admin.configure("items", options=ModelOptions(list_editable=()))
        page = await client.get("/admin/models/items/")
        switch = re.search(r"<button[^>]*data-list-switch[^>]*>", page.text).group()
        assert "disabled" in switch and 'aria-checked="true"' in switch
        assert "data-toggle-endpoint=" not in page.text
