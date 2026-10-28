from contextlib import asynccontextmanager

from anyio import to_thread
from fastapi import FastAPI

from examples.common import make_demo, seed

admin, engine, sessions = make_demo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await to_thread.run_sync(seed, engine, sessions)
    yield
    await to_thread.run_sync(engine.dispose)


app = FastAPI(title="Quite Admin demo", lifespan=lifespan)
admin.mount_fastapi(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
