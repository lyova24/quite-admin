from contextlib import asynccontextmanager

from anyio import to_thread
from litestar import Litestar, get

from examples.common import make_demo, seed

admin, engine, sessions = make_demo()


@asynccontextmanager
async def lifespan(app: Litestar):
    await to_thread.run_sync(seed, engine, sessions)
    yield
    await to_thread.run_sync(engine.dispose)


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(route_handlers=[health, admin.litestar_route()], lifespan=[lifespan])
