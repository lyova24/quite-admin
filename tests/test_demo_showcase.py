from datetime import datetime, time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from examples.common import Schedule, make_demo, seed

from .helpers import csrf, login, revision


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_example_showcases_temporal_text_json_inline_and_real_history(
    tmp_path, monkeypatch, framework
):
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_STORAGE_URL", f"sqlite:///{tmp_path}/service.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    admin, engine, sessions = make_demo()
    seed(engine, sessions)
    seed(engine, sessions)  # Restarting the example must not duplicate showcase records.
    try:
        if framework == "fastapi":
            app = FastAPI()
            admin.mount_fastapi(app)
        else:
            app = Litestar(route_handlers=[admin.litestar_route()])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await login(client)
            listing = await client.get("/admin/models/schedules/")
            assert "data-inline-endpoint=" in listing.text
            assert "data-list-null" in listing.text
            assert 'data-group="Workspace"' in listing.text
            resources = await admin.resources()
            with sessions() as session:
                row = session.get(Schedule, 1)
                key = resources["schedules"].schema.record_key({"id": row.id})
            path = f"/admin/models/schedules/{key}"
            form = await client.get(path)
            assert "data-calendar-input" in form.text
            assert 'data-temporal="datetime"' in form.text
            assert 'data-temporal="time"' in form.text
            assert "data-json-editor" in form.text
            assert '<textarea id="field-description"' in form.text
            result = await client.post(
                path,
                data={
                    "__csrf": csrf(form),
                    "__revision": revision(form),
                    "title": "Updated workshop",
                    "day": "2026-11-02",
                    "starts_at": "2026-11-02T12:34:56.123456",
                    "reminder_at": "09:15:00.654321",
                    "approved": "false",
                    "description": "First line\nSecond line",
                    "settings": '{"capacity": 18}',
                },
            )
            assert result.status_code == 303, result.text
            with sessions() as session:
                row = session.get(Schedule, 1)
                assert row.starts_at == datetime(2026, 11, 2, 12, 34, 56, 123456)
                assert row.reminder_at == time(9, 15, 0, 654321)
                assert row.approved is False
                assert row.settings == {"capacity": 18}
            history = await client.get("/admin/history?collection=schedules&subject=admin")
            assert "Updated workshop" in history.text
            assert "Catalog launch" in history.text
            assert "data-history-period" in history.text
            assert "data-history-changes" in history.text
            orders = await client.get("/admin/models/orders/")
            assert "Browse records" in orders.text
            assert "8 records" not in orders.text
    finally:
        engine.dispose()
