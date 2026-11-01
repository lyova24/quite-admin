import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import ModelOptions, OperationHooks

from .helpers import login


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_inline_edit_policies_csrf_validation_hooks_and_stale_guard(
    admin, backend, framework
):
    adapter, model = backend
    record = await adapter.create(model, {"name": "Original", "active": True})
    resource = (await admin.resources())["items"]
    token = resource.schema.record_key(record)
    events = []

    async def before(operation):
        events.append((operation.action, dict(operation.values)))

    admin.hooks = OperationHooks(before_write=before)
    app = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        path = f"/admin/models/items/{token}/inline/"
        listing = await client.get("/admin/models/items/")
        assert path + "name" in listing.text
        assert path + "count" not in listing.text
        for field in ("count", "internal", "id", "missing"):
            assert (await client.get(path + field)).status_code == 403
        response = await client.get(path + "name")
        assert response.status_code == 200
        state = response.json()
        data = {"__csrf": state["csrf"], "__revision": state["revision"], "name": "Changed"}
        assert (await client.post(path + "name", data={**data, "count": "99"})).status_code == 422
        assert (await client.post(path + "name", data={**data, "__csrf": "bad"})).status_code == 403
        invalid = await client.post(path + "name", data={**data, "name": "x" * 121})
        assert invalid.status_code == 422 and "name" in invalid.json()["errors"]
        assert (await adapter.get(model, {"id": record["id"]}))["name"] == "Original"
        response = await client.post(path + "name", data=data)
        assert response.status_code == 200, response.text
        assert response.json()["cells"]["name"]["text"] == "Changed"
        assert "internal" not in response.json()["cells"]
        assert events == [("edit", {"name": "Changed"})]
        saved = await adapter.get(model, {"id": record["id"]})
        assert saved["name"] == "Changed" and saved["active"] is True
        stale = await client.post(path + "name", data={**data, "name": "Overwrite"})
        assert stale.status_code == 409
        assert (await adapter.get(model, {"id": record["id"]}))["name"] == "Changed"
        # Configuration is rechecked on the endpoint, including already-open editors.
        admin.configure("items", options=ModelOptions(list_editable=()))
        assert (await client.post(path + "name", data=data)).status_code == 403
        assert "data-inline-endpoint" not in (await client.get("/admin/models/items/")).text
        admin.configure("items", options=ModelOptions(list_fields=("id",), list_editable=("name",)))
        assert (await client.get(path + "name")).status_code == 403
        admin.configure("items", options=ModelOptions(permission=lambda r, i, a: a != "list"))
        assert (await client.get(path + "name")).status_code == 403


async def test_inline_boolean_is_parsed_and_only_selected_columns_are_editable(admin, backend):
    adapter, model = backend
    record = await adapter.create(model, {"name": "Entry", "active": True})
    schema = adapter.describe(model)
    admin.configure("items", options=ModelOptions(list_editable=("active",), exclude=("internal",)))
    app = FastAPI()
    admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        path = f"/admin/models/items/{schema.record_key(record)}/inline/"
        assert (await client.get(path + "name")).status_code == 403
        state = (await client.get(path + "active")).json()
        data = {"__csrf": state["csrf"], "__revision": state["revision"], "active": "false"}
        response = await client.post(path + "active", data=data)
        assert response.status_code == 200, response.text
        assert (await adapter.get(model, {"id": record["id"]}))["active"] is False
