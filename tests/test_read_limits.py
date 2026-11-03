import asyncio
from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, DelegatingAdapter, ModelOptions, Query, RecordAction
from quite_admin._reads import ReadLimits
from quite_admin.errors import QueryTimeout
from quite_admin.pagination import WindowAdapter

from .helpers import csrf, login
from .test_relations import related_backend  # noqa: F401


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_admin_limits_queued_reads_and_releases_slots_after_timeouts(
    backend, auth, framework
):
    native, model = backend
    await native.create(model, {"name": "Still available"})
    entered = asyncio.Event()
    started = asyncio.Event()
    release = asyncio.Event()
    active = maximum = 0

    class DelayedReads(DelegatingAdapter):
        async def list(self, model, query):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            started.set()
            if active == 2:
                entered.set()
            try:
                await release.wait()
                return await super().list(model, query)
            finally:
                active -= 1

    adapter = DelayedReads(native)
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        query_timeout=0.1,
        max_concurrent_reads=2,
        history_enabled=False,
    )
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        tasks = [asyncio.create_task(client.get("/admin/models/items/")) for _ in range(6)]
        try:
            await asyncio.wait_for(entered.wait(), timeout=2)
            # Host/business reads use their original adapter and remain independent
            # of the admin's queue. This executes a real database query.
            assert (await native.list(model, Query())).records[0]["name"] == "Still available"
            responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            assert all(response.status_code == 504 for response in responses)
            assert active == 0 and maximum == 2
            release.set()
            assert (await client.get("/admin/models/items/")).status_code == 200
            release.clear()
            started.clear()
            cancelled = asyncio.create_task(client.get("/admin/models/items/"))
            tasks.append(cancelled)
            await asyncio.wait_for(started.wait(), timeout=2)
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled
            assert active == 0
            release.set()
            assert (await client.get("/admin/models/items/")).status_code == 200
        finally:
            release.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_deadline_covers_records_exports_and_post_commit_reads(web_backend, auth, framework):
    adapter, model = web_backend
    record = await adapter.create(model, {"name": "Original"})
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        query_timeout=0.1,
        max_concurrent_reads=1,
    )
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    key = {"id": record["id"]}
    path = "/admin/models/items/" + adapter.describe(model).record_key(record)
    native_get, native_list = adapter.get, adapter.list

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        adapter.get = blocked
        assert (await client.get(path)).status_code == 504
        adapter.get = native_get
        adapter.list = blocked
        assert (
            await client.get("/admin/models/items/", params={"export": "csv", "columns": "name"})
        ).status_code == 504
        adapter.list = native_list
        native_window = adapter.list_window
        adapter.list_window = blocked
        admin.register(model, options=ModelOptions(pagination="cursor"))
        assert (await client.get("/admin/models/items/")).status_code == 504
        adapter.list_window = native_window

        async def slow_create(operation, payload):
            await asyncio.sleep(0.04)
            return await adapter.create(model, payload)

        admin.register(
            model, options=ModelOptions(create_fields=("name",), create_handler=slow_create)
        )
        page = await client.get("/admin/models/items/new")
        created = await client.post(
            "/admin/models/items/new", data={"__csrf": csrf(page), "name": "Write is not cancelled"}
        )
        assert created.status_code == 303

        async def rename(operation):
            await adapter.update(model, key, {"name": "Committed"})
            adapter.get = blocked

        admin.register(
            model, options=ModelOptions(actions=(RecordAction("rename", "Rename", rename),))
        )
        page = await client.get(path)
        response = await client.post(path + "/actions/rename", data={"__csrf": csrf(page)})
        assert response.status_code == 303
        adapter.get = native_get
        assert (await native_get(model, key))["name"] == "Committed"
        assert (await client.get(path)).status_code == 200


async def test_relationship_reads_and_batches_share_the_read_deadline(related_backend, auth):  # noqa: F811
    adapter, models = related_backend
    parent = await adapter.create(models["parents"], {"name": "Parent"})
    relation = next(
        item for item in adapter.relations(models["parents"]) if item.target is models["children"]
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        query_timeout=0.1,
        max_concurrent_reads=1,
    )
    path = "/models/parents/" + adapter.describe(models["parents"]).record_key(parent)

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        await login(client, "")
        native_list = adapter.list
        adapter.list = blocked
        assert (await client.get("/models/parents/new")).status_code == 504
        adapter.list = native_list
        native_related = adapter.related
        adapter.related = blocked
        assert (await client.get(path)).status_code == 504
        adapter.related = native_related
        native_batch = adapter.related_batch
        adapter.related_batch = blocked
        exported = await client.get(
            "/models/parents/",
            params=[("export", "csv"), ("columns", "name"), ("columns", relation.name + ".name")],
        )
        assert exported.status_code == 504
        adapter.related_batch = native_batch
        assert (await client.get(path)).status_code == 200


async def test_async_discovery_obeys_read_deadline(web_backend, auth):
    native, _ = web_backend
    blocked = True

    class Discovery(DelegatingAdapter):
        async def discover(self):
            if blocked:
                await asyncio.Event().wait()
            return self.delegate.discover()

    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[Discovery(native)],
        query_timeout=0.01,
        max_concurrent_reads=1,
    )
    with pytest.raises(QueryTimeout):
        await admin.resources()
    blocked = False
    assert "items" in await admin.resources()


async def test_delegating_adapter_keeps_native_windows_without_bypassing_read_policies(backend):
    native, model = backend
    for number in range(3):
        await native.create(model, {"name": f"Item {number}"})
    wrapped = DelegatingAdapter(native)
    assert isinstance(wrapped, WindowAdapter)
    query = Query(limit=1, columns=("id", "name"))
    first = await wrapped.list_window(model, query)
    second = await wrapped.list_window(model, query, after=first.next_key)
    assert first.records != second.records
    assert first.has_next and second.has_previous
    previous = await wrapped.list_window(model, query, before=second.previous_key)
    assert previous.records == first.records
    with pytest.raises(ValueError):
        await wrapped.list_window(model, replace(query, columns=("not_a_column",)))

    class ReadPolicy(DelegatingAdapter):
        async def list(self, model, query):
            return await super().list(model, query)

    assert not isinstance(ReadPolicy(native), WindowAdapter)
    wrapped.list = ReadPolicy(native).list
    with pytest.raises(ValueError, match="list_window explicitly"):
        await wrapped.list_window(model, query)

    class NoWindows:
        pass

    assert not isinstance(DelegatingAdapter(NoWindows()), WindowAdapter)


async def test_deadline_waits_for_shielded_cleanup_before_releasing_the_slot():
    import time

    from quite_admin._reads import run_sync

    limits = ReadLimits(0.01, 1)
    released = False

    async def shielded():
        def worker():
            nonlocal released
            time.sleep(0.03)
            released = True

        await run_sync(worker)

    with pytest.raises(QueryTimeout):
        await limits.run(shielded)
    assert released
    assert await limits.run(lambda: 42) == 42


@pytest.mark.parametrize("orm", [False, True])
async def test_deadline_cancels_async_sql_without_poisoning_pool(tmp_path, auth, orm, caplog):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/read-cancel.db")
    adapter = SQLAlchemyAdapter(async_sessionmaker(engine)) if orm else SQLAdapter(engine)
    kwargs = {"read": True} if orm else {}
    admin = Admin(auth=auth, secret_key="s" * 32, query_timeout=0.01, max_concurrent_reads=1)

    def quick(connection):
        return connection.execute(text("SELECT 42")).scalar_one()

    def expensive(connection):
        return connection.execute(
            text(
                "WITH RECURSIVE slow(n) AS "
                "(SELECT 1 UNION ALL SELECT n+1 FROM slow WHERE n<500000) "
                "SELECT sum(n) FROM slow"
            )
        ).scalar_one()

    try:
        assert await adapter._run(quick, **kwargs) == 42
        with pytest.raises(QueryTimeout):
            await admin._read(adapter._run, expensive, **kwargs)
        assert await adapter._run(quick, **kwargs) == 42
        assert "Exception terminating connection" not in caplog.text
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "option,value",
    [
        ("query_timeout", 0),
        ("query_timeout", -1),
        ("query_timeout", True),
        ("query_timeout", float("nan")),
        ("query_timeout", float("inf")),
        ("max_concurrent_reads", 0),
        ("max_concurrent_reads", -1),
        ("max_concurrent_reads", True),
        ("max_concurrent_reads", 1.5),
    ],
)
def test_admin_rejects_invalid_read_limits(auth, option, value):
    with pytest.raises(ValueError, match=option):
        Admin(auth=auth, secret_key="s" * 32, **{option: value})
