"""Disposable copy of the Python example used by capture_screenshots.mjs."""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from anyio import to_thread
from fastapi import FastAPI
from sqlalchemy import select

from examples.common import Customer, Order, Product, Schedule, make_demo, seed

directory = Path(os.environ["QUITE_ADMIN_SCREENSHOT_DIRECTORY"])
if not directory.is_dir() or any(directory.iterdir()):
    raise RuntimeError("Screenshot fixture requires an empty temporary directory.")
os.environ.update(
    QUITE_ADMIN_DEMO_DB=f"sqlite:///{directory}/example.sqlite3",
    QUITE_ADMIN_STORAGE_URL=str(directory / "state.sqlite3"),
)

admin, engine, sessions = make_demo()


def prepare():
    seed(engine, sessions)
    with sessions.begin() as session:
        for customer in session.scalars(select(Customer)):
            customer.joined_at = datetime(2026, 11, customer.id, 9, 30)
        for order in session.scalars(select(Order)):
            order.created_at = datetime(2026, 11, order.id, 10, 15)
        for schedule in session.scalars(select(Schedule)):
            schedule.day = date(2026, 11, 10) + timedelta(days=schedule.id - 1)
            schedule.starts_at = datetime.combine(schedule.day, schedule.starts_at.time())
        session.get(Product, 1).attributes = {
            "paper": "recycled",
            "pages": 160,
            "dimensions": {"width": 14.8, "height": 21, "unit": "cm"},
            "colors": ["charcoal", "sand"],
        }


@asynccontextmanager
async def lifespan(app):
    await to_thread.run_sync(prepare)
    yield
    await to_thread.run_sync(engine.dispose)


app = FastAPI(lifespan=lifespan)
admin.mount_fastapi(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
