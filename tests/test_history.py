from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar, Router

from quite_admin import (
    ActivityDetails,
    Admin,
    Document,
    FieldChange,
    ModelOptions,
    RecordAction,
    SQLiteStore,
    StorageError,
)

from .helpers import csrf, login, revision
from .test_storage import event


@pytest.fixture(params=["fastapi", "litestar"])
async def history_client(request, web_admin):
    if request.param == "fastapi":
        host = FastAPI()
        web_admin.mount_fastapi(host)
    else:
        host = Litestar(route_handlers=[web_admin.litestar_route()])
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        yield client


async def test_history_captures_crud_failures_export_actions_and_logout(
    history_client, web_admin, web_backend
):
    client = history_client
    assert (await client.get("/admin/history")).status_code == 303
    await login(client)
    home = await client.get("/admin/")
    assert 'href="/admin/history"' in home.text
    form = await client.get("/admin/models/items/new")
    invalid = await client.post("/admin/models/items/new", data={"__csrf": csrf(form)})
    assert invalid.status_code == 422
    created = await client.post(
        "/admin/models/items/new",
        data={
            "__csrf": csrf(form),
            "name": "Original name",
            "active": "true",
        },
    )
    assert created.status_code == 303
    path = created.headers["location"]
    page = await client.get(path)
    edited = await client.post(
        path,
        data={
            "__csrf": csrf(page),
            "__revision": revision(page),
            "name": "updated",
            "active": "true",
        },
    )
    assert edited.status_code == 303
    forbidden = await client.post(path, data={"name": "no-csrf"})
    assert forbidden.status_code == 403
    exported = await client.get("/admin/models/items/?export=csv&columns=name")
    assert exported.status_code == 200
    adapter, model = web_backend
    web_admin.register(
        model,
        options=replace(
            web_admin.sources[0].options[model],
            actions=(
                RecordAction(
                    "touch",
                    "Touch",
                    lambda operation: None,
                ),
            ),
        ),
    )
    page = await client.get(path)
    assert (
        await client.post(path + "/actions/touch", data={"__csrf": csrf(page)})
    ).status_code == 303
    confirmation = await client.get(path + "/delete")
    assert (
        await client.post(path + "/delete", data={"__csrf": csrf(confirmation)})
    ).status_code == 303
    assert (await client.get("/admin/models/items/")).status_code == 200
    history = await client.get("/admin/history?subject=admin&collection=items")
    assert history.status_code == 200, history.text
    assert "Original name" in history.text and "updated" in history.text
    assert 'class="activity-journal"' in history.text
    assert 'class="table-scroll"' not in history.text
    records = (await web_admin.storage.activities(subject="admin", collection="items")).events
    successful = {item.action for item in records if item.outcome == "success"}
    assert {"create", "edit", "delete", "list", "view", "export", "action:touch"} <= successful
    assert {(item.action, item.status_code) for item in records if item.outcome == "failure"} >= {
        ("create", 422),
        ("edit", 403),
    }
    assert (
        len([item for item in records if item.action == "create" and item.outcome == "success"])
        == 1
    )
    edited_event = next(
        item for item in records if item.action == "edit" and item.outcome == "success"
    )
    fields = {change.name: change for change in edited_event.details.changes}
    assert (fields["name"].before, fields["name"].after) == ("Original name", "updated")
    assert "internal" not in fields
    created_event = next(
        item for item in records if item.action == "create" and item.outcome == "success"
    )
    assert created_event.details.record_key
    assert all(not item.before_present for item in created_event.details.changes)
    deleted_event = next(item for item in records if item.action == "delete")
    assert not deleted_event.details.record_exists
    assert all(not item.after_present for item in deleted_event.details.changes)
    assert all(item.details is None for item in records if item.outcome == "failure")
    await client.post("/admin/logout", data={"__csrf": csrf(history)})
    authentication = (await web_admin.storage.activities(collection="")).events
    assert {item.action for item in authentication} == {"login", "logout"}
    assert (await client.get("/admin/history/users")).status_code == 303


async def test_history_permissions_scope_events_and_user_autocomplete(
    history_client, web_admin, web_backend
):
    client = history_client
    await login(client)
    await web_admin.storage.append_activity(event("visible-user"))
    await web_admin.storage.append_activity(event("hidden-user", "other-table"))
    users = await client.get("/admin/history/users")
    assert users.status_code == 200
    assert "visible-user" in users.text and "hidden-user" not in users.text
    adapter, model = web_backend
    web_admin.register(
        model, options=ModelOptions(permission=lambda request, identity, action: False)
    )
    history = await client.get("/admin/history")
    assert history.status_code == 200
    assert "visible-user" not in history.text and "hidden-user" not in history.text
    assert (await client.get("/admin/history?collection=items")).status_code == 400
    assert "visible-user" not in (await client.get("/admin/history/users?q=visible")).text
    web_admin.history_permission = lambda request, identity, action: False
    assert (await client.get("/admin/history")).status_code == 403
    assert (await client.get("/admin/history/users")).status_code == 403
    assert 'href="/admin/history"' not in (await client.get("/admin/")).text
    web_admin.history_permission = lambda request, identity, action: True
    assert (await client.get("/admin/history")).status_code == 200


async def test_disabled_history_skips_storage_and_capture(history_client, web_admin, monkeypatch):
    assert web_admin.history_enabled is True
    web_admin.history_enabled = False

    async def unexpected(*args, **kwargs):
        pytest.fail("Disabled history must not access storage or capture field values")

    monkeypatch.setattr(web_admin, "_storage_ready", unexpected)
    monkeypatch.setattr(web_admin, "_capture_activity_details", unexpected)
    monkeypatch.setattr(web_admin.storage, "append_activity", unexpected)
    for path in ("/admin/history", "/admin/history/users"):
        assert (await history_client.get(path)).status_code == 404
    await login(history_client)
    form = await history_client.get("/admin/models/items/new")
    assert 'href="/admin/history"' not in form.text
    created = await history_client.post(
        "/admin/models/items/new",
        data={"__csrf": csrf(form), "name": "History disabled", "active": "true"},
    )
    assert created.status_code == 303
    assert not (await web_admin.storage.activities()).events
    await web_admin.storage.save_document(Document("widget", "dashboard", "admin", {}))
    assert await web_admin.storage.get_document("widget") is not None
    for path in ("/admin/history", "/admin/history/users"):
        assert (await history_client.get(path)).status_code == 404


def test_history_flag_requires_a_boolean():
    from quite_admin import PasswordAuth

    auth = PasswordAuth.single_user("admin", "test-password")
    with pytest.raises(ValueError, match="history_enabled"):
        Admin(auth=auth, secret_key="s" * 32, history_enabled="false")
    assert Admin(auth=auth, secret_key="s" * 32, history_enabled=False).history_enabled is False


async def test_history_switches_views_without_losing_filters_or_safe_changes(
    history_client, web_admin
):
    await login(history_client)
    await web_admin.storage.append_activity(
        event(
            "admin",
            details=ActivityDetails(
                (
                    FieldChange("name", "Name", "<script>before</script>", "New value"),
                    FieldChange("internal", "Internal", "hidden-before", "hidden-after"),
                )
            ),
        )
    )
    page = await history_client.get("/admin/history?subject=admin&collection=items&outcome=success")
    assert 'class="activity-journal"' in page.text
    assert ">Journal</a>" in page.text and ">Table</a>" in page.text
    table_url = unescape(re.search(r'<a href="([^"]+)"[^>]*>Table</a>', page.text)[1])
    assert parse_qs(urlsplit(table_url).query) == {
        "subject": ["admin"],
        "collection": ["items"],
        "outcome": ["success"],
        "view": ["table"],
    }
    table = await history_client.get(table_url)
    assert table.status_code == 200
    assert 'class="history-table" aria-label="Activity history"' in table.text
    assert 'class="activity-journal"' not in table.text
    assert 'name="view" value="table"' in table.text
    assert 'href="/admin/history?view=table&amp;action=">Clear all</a>' in table.text
    assert "&lt;script&gt;before&lt;/script&gt;" in table.text and "New value" in table.text
    assert "<script>before</script>" not in table.text and "hidden-after" not in table.text
    assert table.text.count("data-activity-id=") == 1
    assert "data-history-changes open" not in table.text
    assert 'aria-current="page">Table</a>' in table.text
    journal_url = unescape(re.search(r'<a href="([^"]+)"[^>]*>Journal</a>', table.text)[1])
    assert 'class="activity-journal"' in (await history_client.get(journal_url)).text
    for query in ("view=invalid", "view=journal&view=table"):
        assert (await history_client.get("/admin/history?" + query)).status_code == 400


@pytest.mark.parametrize("view", ["journal", "table"])
async def test_history_shared_filters_exclude_dates_and_clear_preserves_period(
    history_client, web_admin, view
):
    await login(history_client)
    await web_admin.storage.append_activity(
        event("alice", occurred_at="2024-02-29T12:00:00.000000Z")
    )
    page = await history_client.get(
        "/admin/history?subject=alice&collection=items&outcome=success"
        f"&view={view}&date_mode=day&date=2024-02-29"
    )
    descriptors = json.loads(unescape(re.search(r"data-fields='([^']+)'", page.text)[1]))
    assert {item["id"] for item in descriptors} == {"subject", "collection", "action", "outcome"}
    assert all(item["operators"] == ["eq"] for item in descriptors)
    active = json.loads(unescape(re.search(r"data-conditions='([^']+)'", page.text)[1]))
    assert {item["parameters"][0] for item in active} == {
        "subject",
        "collection",
        "action",
        "outcome",
    }
    assert "data-history-filter-builder" in page.text
    assert "/assets/filters.js" in page.text
    clear_url = unescape(
        re.search(r'class="link-button" href="([^"]+)">Clear all</a>', page.text)[1]
    )
    assert parse_qs(urlsplit(clear_url).query, keep_blank_values=True) == {
        "view": [view],
        "date_mode": ["day"],
        "date": ["2024-02-29"],
        "action": [""],
    }
    cleared = await history_client.get(clear_url)
    assert cleared.status_code == 200
    assert "data-activity-id=" in cleared.text and "data-period-label>29.02.2024" in cleared.text
    assert "data-filter-edit=" not in cleared.text


@pytest.mark.parametrize("view", ["journal", "table"])
async def test_history_date_filters_are_inclusive_validated_and_preserved(
    history_client, web_admin, view
):
    await login(history_client)
    events = [
        event(occurred_at=stamp)
        for stamp in (
            "2024-02-28T23:59:59.999999Z",
            "2024-02-29T00:00:00.000000Z",
            "2024-02-29T23:59:59.999999Z",
            "2024-03-01T00:00:00.000000Z",
        )
    ]
    for item in events:
        await web_admin.storage.append_activity(item)
    path = f"/admin/history?view={view}&date_from=2024-02-29&date_to=2024-02-29"
    page = await history_client.get(path)
    assert page.status_code == 200
    assert re.findall('data-activity-id="([^"]+)"', page.text) == [events[2].id, events[1].id]
    for bound in ("from", "to"):
        assert f'name="date_{bound}" value="2024-02-29"' in page.text
    other = "Table" if view == "journal" else "Journal"
    switch_url = unescape(re.search(r'<a href="([^"]+)"[^>]*>' + other + "</a>", page.text)[1])
    switched = await history_client.get(switch_url)
    assert re.findall('data-activity-id="([^"]+)"', switched.text) == [events[2].id, events[1].id]
    assert parse_qs(urlsplit(switch_url).query)["date_to"] == ["2024-02-29"]
    single = await history_client.get(
        f"/admin/history?view={view}&date_mode=day&date=2024-02-29&date_from=invalid"
    )
    assert single.status_code == 200
    assert re.findall('data-activity-id="([^"]+)"', single.text) == [events[2].id, events[1].id]
    assert 'name="date_mode" value="day"' in single.text
    assert 'name="date" value="2024-02-29"' in single.text
    assert "data-period-label>29.02.2024</span>" in single.text
    assert 'role="dialog" aria-label="Choose period"' in single.text
    assert 'data-period-view="day"' in single.text
    single_switch = unescape(re.search(r'<a href="([^"]+)"[^>]*>' + other + "</a>", single.text)[1])
    assert parse_qs(urlsplit(single_switch).query)["date_mode"] == ["day"]
    assert parse_qs(urlsplit(single_switch).query)["date"] == ["2024-02-29"]
    assert re.findall(
        'data-activity-id="([^"]+)"', (await history_client.get(single_switch)).text
    ) == [events[2].id, events[1].id]
    any_date = await history_client.get(
        f"/admin/history?view={view}&date_mode=all&date=invalid&date_from=invalid"
    )
    assert any_date.status_code == 200
    assert 'name="date_mode" value="all"' in any_date.text
    assert len(re.findall('data-activity-id="([^"]+)"', any_date.text)) == 4
    for query in (
        "date_from=2024-02-30",
        "date_to=2024-02-30",
        "date_from=20240229",
        "date_from=0000-01-01",
        "date_to=2024-02-29T00:00:00Z",
        "date_from=2024-03-01&date_to=2024-02-29",
        "date_from=2024-02-28&date_from=2024-02-29",
        "date_to=2024-02-28&date_to=2024-02-29",
        "date_mode=invalid",
        "date_mode=day",
        "date_mode=day&date=2024-02-30",
        "date_mode=day&date=20240229",
        "date_mode=day&date=2024-02-28&date=2024-02-29",
        "date_mode=all&date_mode=day",
    ):
        assert (await history_client.get("/admin/history?" + query)).status_code == 400


@pytest.mark.parametrize("view", ["journal", "table"])
@pytest.mark.parametrize("period", ["range", "day"])
async def test_history_pagination_tampering_and_deleted_users(
    history_client, web_admin, view, period
):
    await login(history_client)
    for index in range(107):
        await web_admin.storage.append_activity(
            event(
                "departed-user",
                id=f"{index:032x}",
                occurred_at="2026-11-01T12:00:00.000000Z",
            )
        )
    await web_admin.storage.append_activity(
        event("<script>alert(1)</script>", display_name="<b>name</b>")
    )
    period_query = (
        "date_mode=range&date_from=2026-11-01&date_to=2026-11-01"
        if period == "range"
        else "date_mode=day&date=2026-11-01"
    )
    page = await history_client.get(
        f"/admin/history?subject=departed-user&collection=items&view={view}&{period_query}"
    )
    assert page.status_code == 200
    assert len(re.findall("data-activity-id=", page.text)) == 50
    next_path = re.search(r'href="([^"]+)"[^>]*>Older events', page.text)
    assert next_path
    import html

    next_url = html.unescape(next_path[1])
    assert parse_qs(urlsplit(next_url).query)["view"] == [view]
    assert parse_qs(urlsplit(next_url).query)["date_mode"] == [period]
    for key in ("date_from", "date_to") if period == "range" else ("date",):
        assert parse_qs(urlsplit(next_url).query)[key] == ["2026-11-01"]
    older = await history_client.get(next_url)
    assert len(re.findall("data-activity-id=", older.text)) == 50
    assert not set(re.findall('data-activity-id="([^"]+)"', page.text)) & set(
        re.findall('data-activity-id="([^"]+)"', older.text)
    )
    other = "Table" if view == "journal" else "Journal"
    switch_url = unescape(re.search(r'<a href="([^"]+)"[^>]*>' + other + "</a>", older.text)[1])
    switched = await history_client.get(switch_url)
    assert switched.status_code == 200
    assert re.findall('data-activity-id="([^"]+)"', switched.text) == re.findall(
        'data-activity-id="([^"]+)"', older.text
    )
    assert (
        await history_client.get(next_url.replace("departed-user", "someone"))
    ).status_code == 400
    bound = "date_from" if period == "range" else "date"
    assert (
        await history_client.get(next_url.replace(f"{bound}=2026-11-01", f"{bound}=2026-10-31"))
    ).status_code == 400
    assert (await history_client.get("/admin/history?before=forged")).status_code == 400
    assert (await history_client.get("/admin/history?subject=a&subject=b")).status_code == 400
    unsafe = await history_client.get("/admin/history")
    assert "<script>alert(1)</script>" not in unsafe.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in unsafe.text
    search = await history_client.get("/admin/history/users?q=departed")
    assert search.json() == [{"subject": "departed-user", "label": "Departed-User"}]
    assert (await history_client.get("/admin/history/users?q=" + "x" * 201)).status_code == 400


async def test_storage_is_lazy_and_history_survives_new_admin(auth, tmp_path):
    path = tmp_path / "owned" / "state.sqlite3"
    first = Admin(auth=auth, secret_key="s" * 32, storage=path, secure_cookies=False)
    assert not path.exists()
    await first.storage.append_activity(event("former-admin", "", action="logout"))
    second = Admin(
        auth=auth, secret_key="s" * 32, storage=path, secure_cookies=False, language="ru"
    )
    async with AsyncClient(transport=ASGITransport(app=second), base_url="http://test") as client:
        await login(client, "")
        response = await client.get("/history?subject=former-admin&action=")
        assert response.status_code == 200
        assert "История действий" in response.text
        assert "former-admin" in response.text and "Выйти" in response.text


async def test_store_failure_before_write_and_after_commit(auth, web_backend, tmp_path, caplog):
    class FailingStore(SQLiteStore):
        fail_initialize = True
        fail_append = False

        async def initialize(self):
            if self.fail_initialize:
                raise StorageError()
            await super().initialize()

        async def append_activity(self, event):
            if self.fail_append:
                raise StorageError()
            await super().append_activity(event)

    store = FailingStore(tmp_path / "state.sqlite3")
    adapter, model = web_backend
    instance = Admin(
        auth=auth, secret_key="s" * 32, storage=store, adapters=[adapter], secure_cookies=False
    )
    async with AsyncClient(transport=ASGITransport(app=instance), base_url="http://test") as client:
        page = await client.get("/login")
        response = await client.post(
            "/login",
            data={
                "__csrf": csrf(page),
                "username": "admin",
                "password": "correct horse battery staple",
            },
        )
        assert response.status_code == 503
        store.fail_initialize = False
        await login(client, "")
        form = await client.get("/models/items/new")
        store.fail_append = True
        with caplog.at_level(logging.WARNING, logger="quite_admin"):
            saved = await client.post(
                "/models/items/new",
                data={
                    "__csrf": csrf(form),
                    "name": "must-stay-committed",
                    "active": "true",
                },
            )
        assert saved.status_code == 303
        assert await adapter.get(
            model, adapter.describe(model).parse_key(saved.headers["location"].rsplit("/", 1)[-1])
        )
        records = [r for r in caplog.records if r.msg == "quite_admin.activity_failed"]
        assert records and records[-1].quite_admin == {"error_type": "StorageError"}


async def test_history_rechecks_field_visibility_and_captures_inline_edit(
    history_client, web_admin, web_backend
):
    adapter, model = web_backend
    record = await adapter.create(model, {"name": "Prior visible name", "active": True})
    path = "/admin/models/items/" + adapter.describe(model).record_key(record)
    await login(history_client)
    control = (await history_client.get(path + "/inline/active")).json()
    saved = await history_client.post(
        path + "/inline/active",
        data={
            "__csrf": control["csrf"],
            "__revision": control["revision"],
            "active": "false",
        },
    )
    assert saved.status_code == 200
    item = (await web_admin.storage.activities(action="inline_edit")).events[0]
    assert len(item.details.changes) == 1
    change = item.details.changes[0]
    assert (change.name, change.before, change.after) == ("active", "true", "false")
    web_admin.register(model, options=ModelOptions(exclude=("active", "id")))
    page = await history_client.get("/admin/history")
    assert "activity-diff-row" not in page.text
    assert "activity-record" not in page.text
    assert "No visible field changes." in page.text


async def test_custom_action_history_uses_database_result(history_client, web_admin, web_backend):
    adapter, model = web_backend
    record = await adapter.create(model, {"name": "Before action"})

    async def execute(operation):
        await adapter.update(model, operation.key, {"name": "Actual database value"})
        return {"name": "Not the saved value"}

    web_admin.register(
        model, options=ModelOptions(actions=(RecordAction("rename", "Rename", execute),))
    )
    await login(history_client)
    path = "/admin/models/items/" + adapter.describe(model).record_key(record)
    form = await history_client.get(path)
    result = await history_client.post(path + "/actions/rename", data={"__csrf": csrf(form)})
    assert result.status_code == 303
    item = (await web_admin.storage.activities(action="action:rename")).events[0]
    change = next(item for item in item.details.changes if item.name == "name")
    assert (change.before, change.after) == ("Before action", "Actual database value")


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_history_nested_mount_and_proxy(auth, framework):
    instance = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    if framework == "fastapi":
        child = FastAPI()
        instance.mount_fastapi(child, "/control")
        host = FastAPI()
        host.mount("/internal", child)
    else:
        host = Litestar(
            route_handlers=[
                Router(path="/internal", route_handlers=[instance.litestar_route("/control")])
            ]
        )
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        await login(client, "/proxy/internal/control")
        history = await client.get("/proxy/internal/control/history")
        assert history.status_code == 200
        descriptors = json.loads(unescape(re.search(r"data-fields='([^']+)'", history.text)[1]))
        users = next(item for item in descriptors if item["id"] == "subject")
        assert users["endpoint"] == "/proxy/internal/control/history/users"
        assert (await client.get("/proxy/internal/control/history/users")).status_code == 200


async def test_service_tables_are_hidden_in_shared_database(auth, tmp_path):
    from sqlalchemy import Column, Integer, MetaData, Table, create_engine

    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.stores.sqlalchemy import SQLAlchemyStore

    engine = create_engine(f"sqlite:///{tmp_path}/shared.sqlite3")
    metadata = MetaData()
    Table("business", metadata, Column("id", Integer, primary_key=True))
    Table("quiteadmin_other_reserved", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    store = SQLAlchemyStore(engine)
    await store.initialize()
    adapter = SQLAdapter(engine)
    assert {table.name for table in await adapter.discover()} == {"business"}
    instance = Admin(auth=auth, secret_key="s" * 32, storage=store, adapters=[adapter])
    assert set(await instance.resources()) == {"business"}
    # Explicit ORM registration cannot expose reserved service tables either.
    from quite_admin import Field, ModelSchema

    class ReservedAdapter:
        def discover(self):
            return ("quiteadmin_activity", "business")

        def describe(self, model):
            return ModelSchema(model, (Field("id", int, primary_key=True),))

    instance = Admin(auth=auth, secret_key="s" * 32, adapters=[ReservedAdapter()])
    assert set(await instance.resources()) == {"business"}
    engine.dispose()
