from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from quite_admin import Activity, Document, SQLiteStore, StorageConflict, StorageError
from quite_admin.activity import ActivityDetails, FieldChange
from quite_admin.storage import create_store
from quite_admin.stores.sqlalchemy import SQLAlchemyStore

from .databases import server_url, sqlalchemy_url


@pytest.fixture(params=["native", "sqlalchemy", "async"])
async def store(request, tmp_path):
    if request.param == "native":
        yield SQLiteStore(tmp_path / "state.sqlite3")
        return
    url = sqlalchemy_url(f"sqlite:///{tmp_path}/state.sqlite3")
    if request.param == "async":
        url = sqlalchemy_url(f"sqlite+aiosqlite:///{tmp_path}/state.sqlite3", asynchronous=True)
        engine = create_async_engine(url)
    else:
        engine = create_engine(url)
    namespace = uuid4().hex
    instance = SQLAlchemyStore(engine, namespace=namespace)
    yield instance
    if request.param == "async":
        await engine.dispose()
    else:
        engine.dispose()


def event(subject="alice", collection="items", **changes):
    return replace(
        Activity.new(
            subject=subject,
            display_name=subject.title(),
            collection=collection,
            action="edit",
            outcome="success",
            status_code=303,
        ),
        **changes,
    )


async def test_documents_are_versioned_persistent_and_optimistically_locked(store):
    await store.initialize()
    assert await store.get_document("sales") is None
    document = Document("sales", "dashboard", "alice", {"widgets": [{"title": "Выручка"}]})
    first = await store.save_document(document)
    assert first.revision == 1
    assert await store.get_document("sales") == first
    with pytest.raises(StorageConflict):
        await store.save_document(document)
    updated = await store.save_document(
        replace(document, payload={"widgets": []}), expected_revision=1
    )
    assert updated.revision == 2
    with pytest.raises(StorageConflict):
        await store.save_document(document, expected_revision=1)
    assert await store.documents("dashboard", owner="alice") == (updated,)
    assert await store.documents("dashboard", owner="Alice") == ()
    assert await store.documents("dashboard", after="sales") == ()
    assert await store.documents("dashboard", owner="bob") == ()
    with pytest.raises(StorageConflict):
        await store.delete_document("sales", expected_revision=1)
    await store.delete_document("sales", expected_revision=2)
    assert await store.get_document("sales") is None


async def test_document_size_json_and_exact_keys(store):
    with pytest.raises(ValueError):
        await store.save_document(Document("x", "dashboard", "", {"value": float("nan")}))
    with pytest.raises(ValueError):
        await store.save_document(Document("x", "dashboard", "", {"x": "a" * 1048576}))
    # More than MySQL TEXT's 64 KiB; still below the store's documented limit.
    payload = {"text": "я" * 40000}
    await store.save_document(Document("name", "dashboard", "", payload))
    await store.save_document(Document("Name", "dashboard", "", {}))
    assert (await store.get_document("name")).payload == payload
    assert (await store.get_document("Name")).payload == {}


async def test_activity_filters_keyset_ties_and_exact_case(store):
    events = [
        event("alice"),
        event("Alice"),
        event("bob", "secrets"),
        event("alice", "Items"),
        event("alice", "", action="login"),
    ]
    stamp = "2026-11-01T12:00:00.000000Z"
    events = [replace(item, occurred_at=stamp) for item in events]
    for item in events:
        await store.append_activity(item)
    scoped = await store.activities(collections=("items",), subject="alice")
    assert scoped.events == (events[0],)
    assert (await store.activities(collections=())).events == ()
    all_events = []
    before = None
    while True:
        page = await store.activities(before=before, limit=2)
        all_events.extend(page.events)
        if not page.has_more:
            break
        last = page.events[-1]
        before = last.occurred_at, last.id
    assert {item.id for item in all_events} == {item.id for item in events}
    assert len(all_events) == len(events)
    assert (await store.activities(collection="")).events == (events[-1],)
    assert (await store.activities(action="delete")).events == ()
    assert set(await store.actors(collections=("items",), search="ali")) == {
        ("Alice", "Alice"),
        ("alice", "Alice"),
    }
    assert await store.actors(collections=("items",), search="%") == ()


async def test_activity_details_roundtrip_and_change_filter(store):
    details = ActivityDetails(
        changes=(
            FieldChange("name", "Name", "Старое <value>", "Новое"),
            FieldChange("note", "Note", None, "", before_present=False),
        ),
        record_key="1",
        omitted=2,
    )
    changed = event(details=details)
    legacy = event(action="action:touch")
    await store.append_activity(changed)
    await store.append_activity(legacy)
    await store.append_activity(event(action="list"))
    page = await store.activities(changes_only=True)
    assert {item.id for item in page.events} == {changed.id, legacy.id}
    assert next(item for item in page.events if item.id == changed.id) == changed
    assert next(item for item in page.events if item.id == legacy.id).details is None
    assert not (await store.activities(collection="another", changes_only=True)).events


async def test_activity_date_range_includes_whole_utc_days_and_works_with_pagination(store):
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
        await store.append_activity(item)
    day = date(2024, 2, 29)
    assert (await store.activities(date_from=day, date_to=day)).events == tuple(events[1:3][::-1])
    assert (await store.activities(date_from=day)).events == tuple(events[1:][::-1])
    assert (await store.activities(date_to=day)).events == tuple(events[:3][::-1])
    first = await store.activities(date_from=day, date_to=day, limit=1)
    assert first.events == (events[2],) and first.has_more
    second = await store.activities(
        date_from=day, date_to=day, limit=1, before=(events[2].occurred_at, events[2].id)
    )
    assert second.events == (events[1],) and not second.has_more
    await store.append_activity(event("bob", occurred_at=events[2].occurred_at))
    assert (await store.activities(subject="alice", date_from=day, date_to=day)).events == tuple(
        events[1:3][::-1]
    )
    last = event(occurred_at="9999-12-31T23:59:59.999999Z")
    await store.append_activity(last)
    assert (await store.activities(date_from=date.max, date_to=date.max)).events == (last,)
    for bounds in (
        {"date_from": "2024-02-29"},
        {"date_to": datetime(2024, 2, 29)},
        {"date_from": date(2024, 3, 1), "date_to": day},
    ):
        with pytest.raises(ValueError):
            await store.activities(**bounds)


async def test_schema_one_upgrade_preserves_existing_events(tmp_path):
    path = tmp_path / "schema-one.sqlite3"
    store = SQLiteStore(path)
    original = event()
    await store.append_activity(original)
    await store.save_document(Document("saved", "dashboard", "alice", {"widgets": []}))
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE quiteadmin_activity_details")
        connection.execute("UPDATE quiteadmin_meta SET version = 1")
    upgraded = SQLiteStore(path)
    await upgraded.initialize()
    assert (await upgraded.activities()).events == (original,)
    assert (await upgraded.get_document("saved")).payload == {"widgets": []}
    changed = event(details=ActivityDetails((FieldChange("name", "Name", "before", "after"),)))
    await upgraded.append_activity(changed)
    assert changed in (await upgraded.activities()).events
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM quiteadmin_meta").fetchone()[0] == 2


async def test_namespace_isolation_and_same_host_concurrent_initialization(tmp_path):
    path = tmp_path / "new" / "state.sqlite3"
    stores = [SQLiteStore(path, namespace="app") for _ in range(8)]
    await asyncio.gather(*(instance.append_activity(event()) for instance in stores))
    assert len((await stores[0].activities()).events) == 8
    other = SQLiteStore(path, namespace="App")
    assert not (await other.activities()).events
    assert not (path.stat().st_mode & 0o077)
    with sqlite3.connect(path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index') "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert names and all(name.startswith("quiteadmin_") for name in names)
        connection.execute("UPDATE quiteadmin_meta SET version = 999")
    with pytest.raises(StorageError, match="unavailable"):
        await SQLiteStore(path).initialize()


async def test_store_selection_errors_and_reopen(tmp_path, monkeypatch):
    monkeypatch.delenv("QUITE_ADMIN_STORAGE_URL")
    monkeypatch.chdir(tmp_path)
    default = create_store(None)
    assert default.path == tmp_path / ".quite-admin/state.sqlite3"
    await default.append_activity(event())
    assert len((await create_store(None).activities()).events) == 1
    assert create_store("sqlite:///relative.sqlite3").path == tmp_path / "relative.sqlite3"
    monkeypatch.setenv("QUITE_ADMIN_STORAGE_URL", f"sqlite:///{tmp_path}/configured.sqlite3")
    assert create_store(None).path == tmp_path / "configured.sqlite3"
    with pytest.raises(ValueError):
        SQLiteStore(":memory:")
    with pytest.raises(ValueError):
        create_store("sqlite:///state.sqlite3?mode=ro")
    with pytest.raises(StorageError, match="unavailable"):
        await SQLiteStore(tmp_path).initialize()


async def test_sqlalchemy_url_and_concurrent_bootstrap(tmp_path):
    url = sqlalchemy_url(f"sqlite:///{tmp_path}/server.sqlite3")
    rendered = url if isinstance(url, str) else url.render_as_string(hide_password=False)
    namespace = uuid4().hex
    stores = [SQLAlchemyStore(rendered, namespace=namespace) for _ in range(4)]
    await asyncio.gather(*(item.append_activity(event()) for item in stores))
    assert len((await stores[0].activities()).events) == 4
    inspector = inspect(stores[0].engine)
    assert {"quiteadmin_meta", "quiteadmin_documents", "quiteadmin_activity"} <= set(
        inspector.get_table_names()
    )
    if server_url() is None:
        fresh = SQLAlchemyStore(str(url), namespace="other")
        assert not (await fresh.activities()).events


def test_sqlite_initialization_and_writes_across_processes(tmp_path):
    script = """
import asyncio, sys
from quite_admin import Activity, SQLiteStore
assert 'sqlalchemy' not in sys.modules
async def run():
    store = SQLiteStore(sys.argv[1])
    for _ in range(10):
        await store.append_activity(Activity.new(subject='worker', display_name='Worker',
            collection='items', action='edit', outcome='success', status_code=303))
asyncio.run(run())
"""
    path = tmp_path / "multiprocess.sqlite3"
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    for child in children:
        _, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, stderr.decode()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM quiteadmin_activity").fetchone()[0] == 40


async def test_actor_index_refreshes_names_without_leaking_other_collections(store):
    await store.append_activity(event("known-user", display_name="Old name"))
    await store.append_activity(event("known-user", display_name="New name"))
    await store.append_activity(event("private-user", "hidden", display_name="Private"))
    assert await store.actors(collections=("items",), search="New") == (("known-user", "New name"),)
    assert not await store.actors(collections=("items",), search="Private")
