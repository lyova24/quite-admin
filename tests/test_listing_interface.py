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
