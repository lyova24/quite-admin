import asyncio
import hashlib

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, CheckedAdapter, WriteGuard
from quite_admin.concurrency import StaleRecord, canonical

from .helpers import csrf, login, revision


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def test_checked_write_contract(backend):
    adapter, model = backend
    assert isinstance(adapter, CheckedAdapter)
    record = await adapter.create(model, {"name": "Initial"})
    schema = adapter.describe(model)
    key = {f.name: record[f.name] for f in schema.primary_keys}
    fields = tuple(f.name for f in schema.fields if f.kind != "unsupported")
    guard = WriteGuard(
        fingerprint({name: record[name] for name in fields}), {}, fields, fingerprint
    )
    saved = await adapter.save_checked(model, key, {"name": "First save"}, {}, guard=guard)
    assert saved["name"] == "First save"
    with pytest.raises(StaleRecord):
        await adapter.save_checked(model, key, {"name": "Stale save"}, {}, guard=guard)
    assert (await adapter.get(model, key))["name"] == "First save"


@pytest.fixture(params=["fastapi", "litestar"])
async def edit_client(request, backend, auth):
    adapter, model = backend
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    host = FastAPI() if request.param == "fastapi" else Litestar()
    if request.param == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        record = await adapter.create(model, {"name": "Original"})
        path = "/admin/models/items/" + adapter.describe(model).record_key(record)
        yield client, path, adapter, model, record


async def test_stale_form_preserves_input_and_requires_reload(edit_client):
    client, path, adapter, model, record = edit_client
    first, second = await asyncio.gather(client.get(path), client.get(path))
    assert revision(first) and "Original" not in revision(first)
    saved = await client.post(
        path, data={"__csrf": csrf(first), "__revision": revision(first), "name": "First editor"}
    )
    assert saved.status_code == 303
    data = {"__csrf": csrf(second), "__revision": revision(second), "name": "My unsaved change"}
    stale = await client.post(path, data=data)
    assert stale.status_code == 409
    assert 'value="My unsaved change"' in stale.text
    assert "Reload record" in stale.text
    assert revision(stale) == revision(second)
    assert (await client.post(path, data=data)).status_code == 409
    latest = await client.get(path)
    accepted = await client.post(path, data={**data, "__revision": revision(latest)})
    assert accepted.status_code == 303


async def test_simultaneous_edits_do_not_silently_overwrite(edit_client):
    client, path, adapter, model, record = edit_client
    form = await client.get(path)
    data = {"__csrf": csrf(form), "__revision": revision(form)}
    results = await asyncio.gather(
        *[client.post(path, data={**data, "name": name}) for name in ("Editor one", "Editor two")]
    )
    assert sorted(response.status_code for response in results) == [303, 409]
    current = await adapter.get(model, {"id": record["id"]})
    assert current["name"] in {"Editor one", "Editor two"}


async def test_missing_and_tampered_revisions_cannot_bypass_protection(edit_client):
    client, path, adapter, model, record = edit_client
    form = await client.get(path)
    other = await adapter.create(model, {"name": "Other record"})
    other_path = path.rsplit("/", 1)[0] + "/" + adapter.describe(model).record_key(other)
    other_form = await client.get(other_path)
    for token in ("", revision(form) + "tampered", revision(other_form)):
        response = await client.post(
            path, data={"__csrf": csrf(form), "__revision": token, "name": "Must not save"}
        )
        assert response.status_code == 409
    assert (await adapter.get(model, {"id": record["id"]}))["name"] == "Original"
