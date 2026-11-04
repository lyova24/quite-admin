from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar, Router
from sqlalchemy import create_engine, event

from quite_admin import Admin, Document
from quite_admin.stores.sqlalchemy import SQLAlchemyStore


@pytest.mark.parametrize("framework", ["fastapi", "litestar", "standalone"])
async def test_mount_closes_owned_storage_and_preserves_host_lifespan(auth, tmp_path, framework):
    store = SQLAlchemyStore(f"sqlite:///{tmp_path}/state.sqlite3", engine_options={"pool_size": 2})
    events = []
    event.listen(store.engine, "engine_disposed", lambda engine: events.append("storage closed"))
    admin = Admin(auth=auth, secret_key="s" * 32, storage=store)

    @asynccontextmanager
    async def lifespan(app):
        events.append("host started")
        yield {"host_state": "preserved"}
        events.append("host stopped")

    if framework == "fastapi":
        host = FastAPI(lifespan=lifespan)
        admin.mount_fastapi(host)
        admin.mount_fastapi(host, "/second-admin")
        context = host.router.lifespan_context(host)
    elif framework == "litestar":
        host = Litestar(
            lifespan=[lifespan],
            route_handlers=[Router(path="/internal", route_handlers=[admin.litestar_route()])],
        )
        context = host.lifespan()
    else:
        context = admin.app.router.lifespan_context(admin.app)
    async with context as state:
        if framework == "fastapi":
            assert state == {"host_state": "preserved"}
        await store.save_document(Document("test", "settings", "admin", {"ok": True}))
        assert "storage closed" not in events
    assert events.count("storage closed") == 1
    if framework != "standalone":
        assert "host started" in events and "host stopped" in events
        assert events.index("host stopped") < events.index("storage closed")
    assert (await store.get_document("test")).payload == {"ok": True}
    await store.aclose()


async def test_host_startup_failure_still_closes_owned_storage(auth, tmp_path):
    store = SQLAlchemyStore(f"sqlite:///{tmp_path}/startup.sqlite3")
    disposed = []
    event.listen(store.engine, "engine_disposed", lambda engine: disposed.append(True))
    admin = Admin(auth=auth, secret_key="s" * 32, storage=store)

    @asynccontextmanager
    async def startup(app):
        await store.initialize()
        raise RuntimeError("startup aborted")
        yield

    host = FastAPI(lifespan=startup)
    admin.mount_fastapi(host)
    with pytest.raises(RuntimeError, match="startup aborted"):
        async with host.router.lifespan_context(host):
            pass
    assert disposed == [True]


async def test_close_preserves_borrowed_engines(auth, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/state.sqlite3")
    disposed = []
    event.listen(engine, "engine_disposed", lambda engine: disposed.append(True))
    store = SQLAlchemyStore(engine)
    with pytest.raises(ValueError, match="borrowed engine"):
        SQLAlchemyStore(engine, engine_options={"pool_size": 2})
    admin = Admin(auth=auth, secret_key="s" * 32, storage=store)
    async with admin.lifespan():
        await store.initialize()
    await admin.aclose()
    assert disposed == []
    engine.dispose()


@pytest.mark.parametrize("prefix", ["", "/internal"])
async def test_bare_mount_wins_over_catchall_and_preserves_query(auth, prefix):
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    child = FastAPI()
    admin.mount_fastapi(child, "/tools/admin")

    @child.get("/{path:path}")
    async def catchall(path: str):
        return {"caught": path}

    host = FastAPI()
    if prefix:
        host.mount(prefix, child)
    else:
        host = child
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        path = "/proxy" + prefix + "/tools/admin"
        response = await client.get(path + "?next=%2Fmodels%2Fitems%2F")
        assert response.status_code == 307
        assert response.headers["location"] == "admin/?next=%2Fmodels%2Fitems%2F"
        followed = await client.get(path, follow_redirects=True)
        assert followed.status_code == 200
        assert followed.url.path == path + "/login"
        assert (await client.head(path)).status_code == 307
