import pytest
from httpx import ASGITransport, AsyncClient

from quite_admin import Admin, ModelOptions, Query
from quite_admin.errors import QueryTimeout
from tests.helpers import login


async def test_read_deadline_covers_pool_acquisition_and_restores_capacity(backend, auth):
    adapter, model = backend
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        query_timeout=0.05,
        max_concurrent_reads=1,
        history_enabled=False,
    )
    admin.register(model, options=ModelOptions(pagination="cursor"))
    connections = []
    try:
        for _ in range(3):
            connections.append(await adapter.db.acquire(reuse=False, reusable=False))
        async with AsyncClient(
            transport=ASGITransport(app=admin), base_url="http://test"
        ) as client:
            await login(client, "")
            assert (await client.get("/models/items/")).status_code == 504
    finally:
        for connection in connections:
            await connection.release()
    assert (await admin._read(adapter.list_window, model, Query())).records == []
    assert await adapter.db.scalar("SELECT 42") == 42


async def test_read_deadline_cancels_blocked_postgresql_query_and_reuses_pool(backend, auth):
    adapter, model = backend
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[adapter],
        query_timeout=0.05,
        max_concurrent_reads=1,
        history_enabled=False,
    )
    async with adapter.db.acquire(reuse=False, reusable=False) as blocker:
        async with blocker.transaction():
            await blocker.status("LOCK TABLE items IN ACCESS EXCLUSIVE MODE")
            with pytest.raises(QueryTimeout):
                await admin._read(adapter.list_window, model, Query())
            # The blocked read returned its connection. The host's ordinary
            # queries still run while the admin's table remains locked.
            assert await adapter.db.scalar("SELECT 42") == 42
    assert (await admin._read(adapter.list_window, model, Query())).records == []
