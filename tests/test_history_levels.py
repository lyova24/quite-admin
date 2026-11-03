import re
from dataclasses import replace
from html import unescape

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, ModelOptions, RecordAction, SQLiteStore

from . import test_history, test_storage
from .helpers import csrf, login, revision
from .test_storage import event

history_client = test_history.history_client
store = test_storage.store


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("level", ["changes", "audit", "all"])
async def test_history_level_filters_before_append_and_keeps_changes(
    web_backend, auth, tmp_path, framework, level
):
    class RecordingStore(SQLiteStore):
        def __init__(self, path):
            super().__init__(path)
            self.appended = []

        async def append_activity(self, item):
            self.appended.append((item.action, item.outcome))
            await super().append_activity(item)

    adapter, model = web_backend
    storage = RecordingStore(tmp_path / "history.sqlite3")
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[adapter],
        storage=storage,
        secure_cookies=False,
        **({} if level == "changes" else {"history_level": level}),
    )
    assert admin.history_level == level

    async def rename(operation):
        return await adapter.update(model, operation.key, {"name": "From action"})

    admin.register(
        model,
        options=ModelOptions(
            create_fields=("name",),
            edit_fields=("name",),
            actions=(RecordAction("rename", "Rename", rename),),
        ),
    )
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/new")
        assert (
            await client.post("/admin/models/items/new", data={"__csrf": csrf(page)})
        ).status_code == 422
        if level == "changes":
            assert storage.appended == []
        created = await client.post(
            "/admin/models/items/new", data={"__csrf": csrf(page), "name": "Created"}
        )
        assert created.status_code == 303
        path = created.headers["location"]
        page = await client.get(path)
        assert (
            await client.post(
                path,
                data={
                    "__csrf": csrf(page),
                    "__revision": revision(page),
                    "name": "Edited",
                },
            )
        ).status_code == 303
        assert (await client.post(path, data={"name": "Bad CSRF"})).status_code == 403
        state = (await client.get(path + "/inline/name")).json()
        assert (
            await client.post(
                path + "/inline/name",
                data={
                    "__csrf": state["csrf"],
                    "__revision": state["revision"],
                    "name": "Inline",
                },
            )
        ).status_code == 200
        assert (await client.get("/admin/models/items/")).status_code == 200
        assert (await client.get("/admin/models/items/?export=csv&columns=name")).status_code == 200
        page = await client.get(path)
        assert (
            await client.post(path + "/actions/rename", data={"__csrf": csrf(page)})
        ).status_code == 303
        page = await client.get(path + "/delete")
        assert (await client.post(path + "/delete", data={"__csrf": csrf(page)})).status_code == 303
        page = await client.get("/admin/history?action=")
        assert page.status_code == 200
        if level == "changes":
            assert 'value="login"' not in page.text and 'value="view"' not in page.text
            assert "Show all activity" not in page.text
        elif level == "audit":
            assert 'value="login"' in page.text and 'value="view"' not in page.text
        else:
            assert 'value="view"' in page.text
        assert (await client.post("/admin/logout", data={"__csrf": csrf(page)})).status_code == 303
    writes = {
        ("create", "success"),
        ("edit", "success"),
        ("inline_edit", "success"),
        ("delete", "success"),
        ("action:rename", "success"),
    }
    audit = {
        ("login", "success"),
        ("logout", "success"),
        ("export", "success"),
        ("create", "failure"),
        ("edit", "failure"),
    }
    expected = writes | (audit if level != "changes" else set())
    assert expected <= set(storage.appended)
    assert {action for action, _ in storage.appended} - {item[0] for item in expected} <= (
        {"list", "view"} if level == "all" else set()
    )
    events = (await storage.activities(limit=1000)).events
    assert len(events) == len(storage.appended)
    edited = next(item for item in events if item.action == "inline_edit")
    assert edited.details.changes[0].before == "Edited"
    assert edited.details.changes[0].after == "Inline"


def level_events():
    kinds = [
        ("writer", "edit", "success"),
        ("failed-writer", "edit", "failure"),
        ("login-only", "login", "success"),
        ("export-only", "export", "success"),
        ("writer", "action:rename", "success"),
    ]
    kinds += [("reader-only", "view", "success")] * 55
    kinds += [("writer", "delete", "success")]
    return [
        replace(
            event(subject, "" if action == "login" else "items", action=action, outcome=outcome),
            id=f"{index:032x}",
            occurred_at="2026-11-03T12:00:00.000000Z",
        )
        for index, (subject, action, outcome) in enumerate(kinds, 1)
    ]


@pytest.mark.parametrize(
    "level,positions,actors",
    [
        ("changes", (0, 4, 60), {"writer"}),
        ("audit", (0, 1, 2, 3, 4, 60), {"writer", "failed-writer", "login-only", "export-only"}),
        (
            "all",
            tuple(range(61)),
            {"writer", "failed-writer", "login-only", "export-only", "reader-only"},
        ),
    ],
)
async def test_store_level_filters_before_keyset_paging_and_user_lookup(
    store, level, positions, actors
):
    events = level_events()
    for item in events:
        await store.append_activity(item)
    before = None
    actual = []
    while True:
        page = await store.activities(
            collections=("", "items"), history_level=level, limit=2, before=before
        )
        actual.extend(item.id for item in page.events)
        if not page.has_more:
            break
        assert len(page.events) == 2
        before = (page.events[-1].occurred_at, page.events[-1].id)
    assert actual == [events[position].id for position in reversed(positions)]
    assert {
        subject for subject, _ in await store.actors(collections=("", "items"), history_level=level)
    } == actors
    assert not await store.actors(collections=("other",), history_level=level)
    assert len((await store.activities(limit=1000)).events) == 61


@pytest.mark.parametrize("legacy", [False, True])
async def test_history_levels_filter_old_events_and_legacy_stores(
    web_admin, history_client, legacy
):
    native = web_admin.storage
    if legacy:

        class LegacyStore:
            def __getattr__(self, name):
                return getattr(native, name)

            async def activities(
                self,
                *,
                collections=None,
                subject="",
                collection=None,
                action="",
                outcome="",
                before=None,
                limit=50,
                changes_only=False,
                date_from=None,
                date_to=None,
            ):
                return await native.activities(
                    collections=collections,
                    subject=subject,
                    collection=collection,
                    action=action,
                    outcome=outcome,
                    before=before,
                    limit=limit,
                    changes_only=changes_only,
                    date_from=date_from,
                    date_to=date_to,
                )

            async def actors(self, *, collections, search="", limit=50):
                return await native.actors(collections=collections, search=search, limit=limit)

        web_admin.storage = LegacyStore()
    await login(history_client)
    events = level_events()
    for item in events:
        await native.append_activity(item)
    saved_cursor = None
    for level, expected in (
        ("all", events),
        ("audit", events[:5] + events[-1:]),
        ("changes", [events[0], events[4], events[-1]]),
    ):
        web_admin.history_level = level
        path = "/admin/history?action=&history_level=all"
        found = []
        while path:
            page = await history_client.get(path)
            assert page.status_code == 200, page.text
            found.extend(re.findall('data-activity-id="([^"]+)"', page.text))
            next_page = re.search(r'href="([^"]+)"[^>]*>Older events', page.text)
            path = unescape(next_page[1]) if next_page else None
            if level == "all" and path:
                saved_cursor = path
        assert found == [item.id for item in reversed(expected)]
        users = (await history_client.get("/admin/history/users")).json()
        assert {item["subject"] for item in users} == {item.subject for item in expected}
    assert (await history_client.get(saved_cursor)).status_code == 400
    assert len((await native.activities(limit=1000)).events) == 61


@pytest.mark.parametrize("value", [None, True, 0, 1, "debug", "", [], {}])
def test_history_level_rejects_invalid_values(auth, value):
    with pytest.raises(ValueError, match="history_level"):
        Admin(auth=auth, secret_key="s" * 32, history_level=value)
