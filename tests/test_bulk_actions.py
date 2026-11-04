import re
from html import unescape

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import ModelOptions, OperationHooks, RecordAction, current_operation
from quite_admin.errors import Conflict

from .helpers import csrf, login


def confirmation(response):
    match = re.search(r'name="__confirmation" value="([^"]+)"', response.text)
    assert match is not None, response.text
    return unescape(match[1])


@pytest.fixture(params=["fastapi", "litestar"])
async def bulk_client(request, web_admin):
    host = FastAPI() if request.param == "fastapi" else Litestar()
    getattr(web_admin, "mount_" + request.param)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        yield client


async def selection(client, adapter, model, records, action="delete"):
    page = await client.get("/admin/models/items/")
    return await client.post(
        "/admin/models/items/actions/bulk",
        data={
            "__csrf": csrf(page),
            "keys": [adapter.describe(model).record_key(row) for row in records],
            "action": action,
        },
    )


@pytest.mark.parametrize(
    "web_backend",
    ["sqlalchemy", "sqlalchemy_async", "sql", "sql_async", "peewee", "tortoise"],
    indirect=True,
)
async def test_bulk_delete_confirms_then_records_each_write(bulk_client, web_admin, web_backend):
    adapter, model = web_backend
    rows = [await adapter.create(model, {"name": name}) for name in ("first", "second", "kept")]
    preview = await selection(bulk_client, adapter, model, rows[:2])
    assert preview.status_code == 200
    assert "Confirm bulk action" in preview.text
    assert await adapter.get(model, {"id": rows[0]["id"]})
    result = await bulk_client.post(
        "/admin/models/items/actions/bulk",
        data={"__csrf": csrf(preview), "__confirmation": confirmation(preview)},
    )
    assert result.status_code == 200, result.text
    assert "Succeeded: 2" in result.text and "Failed: 0" in result.text
    for row in rows[:2]:
        assert await adapter.get(model, {"id": row["id"]}) is None
    assert await adapter.get(model, {"id": rows[2]["id"]})
    events = (await web_admin.storage.activities()).events
    assert len(events) == 2
    assert all(item.action == "delete" and item.outcome == "success" for item in events)
    assert all(item.details is not None and not item.details.record_exists for item in events)


async def test_bulk_action_uses_existing_hooks_and_preserves_partial_results(
    bulk_client, web_admin, web_backend
):
    adapter, model = web_backend
    web_admin.history_level = "audit"
    rows = [
        await adapter.create(model, {"name": name, "count": 7})
        for name in ("first", "blocked", "third")
    ]
    calls = []

    async def before(operation):
        assert operation is current_operation()
        if operation.record["name"] == "blocked":
            raise Conflict("This record is blocked.")
        calls.append(operation.key["id"])

    async def reset(operation):
        assert operation.action == "action:reset"
        return await adapter.update(model, operation.key, {"count": 0})

    web_admin.hooks = OperationHooks(before_write=before)
    web_admin.configure(
        "items",
        options=ModelOptions(actions=(RecordAction("reset", "Reset counters", reset, bulk=True),)),
    )
    preview = await selection(bulk_client, adapter, model, rows, "action:reset")
    result = await bulk_client.post(
        "/admin/models/items/actions/bulk",
        data={"__csrf": csrf(preview), "__confirmation": confirmation(preview)},
    )
    assert result.status_code == 200
    assert "Succeeded: 2" in result.text and "Failed: 1" in result.text
    assert "This record is blocked." in result.text
    assert calls == [rows[0]["id"], rows[2]["id"]]
    assert [(await adapter.get(model, {"id": row["id"]}))["count"] for row in rows] == [0, 7, 0]
    events = [
        item
        for item in (await web_admin.storage.activities()).events
        if item.action == "action:reset"
    ]
    assert len(events) == 3
    assert sum(item.outcome == "success" for item in events) == 2
    assert current_operation() is None


async def test_bulk_rechecks_permissions_and_record_changes(bulk_client, web_admin, web_backend):
    adapter, model = web_backend
    rows = [
        await adapter.create(model, {"name": name}) for name in ("changed", "denied", "allowed")
    ]
    denied = set()

    def permission(request, identity, action):
        return action != "delete" or request.path_params.get("key") not in denied

    web_admin.configure("items", options=ModelOptions(permission=permission))
    preview = await selection(bulk_client, adapter, model, rows)
    await adapter.update(model, {"id": rows[0]["id"]}, {"name": "Changed after confirmation"})
    denied.add(adapter.describe(model).record_key(rows[1]))
    result = await bulk_client.post(
        "/admin/models/items/actions/bulk",
        data={"__csrf": csrf(preview), "__confirmation": confirmation(preview)},
    )
    assert "Succeeded: 1" in result.text and "Failed: 2" in result.text
    assert "The record changed." in result.text
    assert await adapter.get(model, {"id": rows[0]["id"]})
    assert await adapter.get(model, {"id": rows[1]["id"]})
    assert await adapter.get(model, {"id": rows[2]["id"]}) is None


async def test_bulk_rejects_csrf_tampering_and_unsupported_actions(
    bulk_client, web_admin, web_backend
):
    adapter, model = web_backend
    row = await adapter.create(model, {"name": "kept"})
    preview = await selection(bulk_client, adapter, model, [row])
    token = confirmation(preview)
    path = "/admin/models/items/actions/bulk"
    assert (await bulk_client.get(path)).status_code == 405
    assert (
        await bulk_client.post(path, data={"__csrf": "bad", "__confirmation": token})
    ).status_code == 403
    assert (
        await bulk_client.post(path, data={"__csrf": csrf(preview), "__confirmation": token + "x"})
    ).status_code == 400
    assert (
        await bulk_client.post(
            path, data={"__csrf": csrf(preview), "__confirmation": token, "action": "delete"}
        )
    ).status_code == 422
    web_admin.configure("items", options=ModelOptions(bulk_delete=False))
    result = await bulk_client.post(path, data={"__csrf": csrf(preview), "__confirmation": token})
    assert "Failed: 1" in result.text
    assert await adapter.get(model, {"id": row["id"]})
    listing = await bulk_client.get("/admin/models/items/")
    assert "data-bulk-form" not in listing.text
    assert (
        await selection(bulk_client, adapter, model, [row], "action:missing")
    ).status_code == 404


async def test_bulk_limit_duplicates_and_session_binding(bulk_client, web_admin, web_backend):
    adapter, model = web_backend
    row = await adapter.create(model, {"name": "kept"})
    assert (await selection(bulk_client, adapter, model, [row, row])).status_code == 422
    assert (await selection(bulk_client, adapter, model, [row] * 101)).status_code == 422
    preview = await selection(bulk_client, adapter, model, [row])
    # A fresh login has a different CSRF/session binding even for the same identity.
    await login(bulk_client)
    page = await bulk_client.get("/admin/models/items/")
    assert (
        await bulk_client.post(
            "/admin/models/items/actions/bulk",
            data={"__csrf": csrf(page), "__confirmation": confirmation(preview)},
        )
    ).status_code == 400
