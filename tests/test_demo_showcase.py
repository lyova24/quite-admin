import base64
import hashlib
import re
from datetime import datetime, time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from examples.common import Schedule, make_demo, seed

from .helpers import csrf, login, revision


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("language", ["en", "ru"])
async def test_standard_home_keeps_editable_calendar_fields_without_demo_pages(
    tmp_path, monkeypatch, framework, language
):
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_STORAGE_URL", f"sqlite:///{tmp_path}/service.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("QUITE_ADMIN_LANGUAGE", language)
    admin, engine, sessions = make_demo()
    seed(engine, sessions)
    try:
        if framework == "fastapi":
            app = FastAPI()
            admin.mount_fastapi(app)
        else:
            app = Litestar(route_handlers=[admin.litestar_route()])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await login(client)
            home = await client.get("/admin/")
            assert home.status_code == 200
            assert "data-dashboard" in home.text and "data-home-shortcuts" in home.text
            assert "/assets/dashboard.css" in home.text
            assert '<header class="topbar" hidden>' in home.text
            for removed in (
                "data-demo-calendar",
                'class="demo-tour"',
                "Try the calendar",
                "Попробовать календарь",
                "Feature guide",
                "Store report",
                "/pages/showcase",
                "/pages/report",
            ):
                assert removed not in home.text
            assert not admin.pages
            for slug in ("showcase", "report"):
                assert (await client.get(f"/admin/pages/{slug}")).status_code == 404
            assert 'href="/admin/models/schedules/"' in home.text
            form = await client.get("/admin/models/schedules/new")
            assert form.status_code == 200 and csrf(form)
            labels = (
                ("Дата", "Дата и время", "Время")
                if language == "ru"
                else ("Date", "Date and time", "Time")
            )
            for name, label, marker in zip(
                ("day", "starts_at", "reminder_at"),
                labels,
                ("data-calendar-input", 'data-temporal="datetime"', 'data-temporal="time"'),
                strict=True,
            ):
                control = re.search(rf'<input\b[^>]*\bname="{name}"[^>]*>', form.text)
                assert control is not None and marker in control[0]
                assert " readonly" not in control[0] and " disabled" not in control[0]
                assert f'for="field-{name}">{label}' in form.text
            resource = (await admin.resources())["schedules"]
            assert {"day", "starts_at", "reminder_at"} <= resource.options.writable_fields(
                resource.schema, creating=True
            ).keys()
            assert form.text.count("/assets/datetime.js") == 1
            assert form.text.index("/assets/datetime.js") < form.text.index("/assets/forms.js")
            picker = await client.get("/admin/assets/datetime.js")
            assert picker.status_code == 200
            integrity = (
                "sha256-" + base64.b64encode(hashlib.sha256(picker.content).digest()).decode()
            )
            assert integrity in form.text and integrity in form.headers["content-security-policy"]
    finally:
        engine.dispose()


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_example_showcases_temporal_text_json_inline_and_real_history(
    tmp_path, monkeypatch, framework
):
    monkeypatch.setenv("QUITE_ADMIN_DEMO_DB", f"sqlite:///{tmp_path}/demo.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_STORAGE_URL", f"sqlite:///{tmp_path}/service.sqlite3")
    monkeypatch.setenv("QUITE_ADMIN_PASSWORD", "correct horse battery staple")
    monkeypatch.setenv("QUITE_ADMIN_LANGUAGE", "en")
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
            home = await client.get("/admin/")
            assert 'data-group="Workspace"' in home.text
            assert "data-home-catalog" not in listing.text
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
