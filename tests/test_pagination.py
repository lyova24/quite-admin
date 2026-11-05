import html
import re
from dataclasses import replace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, event

from quite_admin import Admin, Filter, ModelOptions, PasswordAuth, Query
from quite_admin.pagination import RecordWindow, WindowAdapter

from .helpers import csrf, login


@pytest.mark.parametrize("descending", [False, True])
async def test_keyset_pages_match_filtered_order_and_support_previous_pages(backend, descending):
    adapter, model = backend
    assert isinstance(adapter, WindowAdapter)
    for value in range(7):
        await adapter.create(model, {"name": f"Keep {value}", "count": value})
    query = Query(
        limit=2,
        descending=descending,
        search="Keep",
        search_fields=("name",),
        filters=(Filter("count", "gte", 1),),
        columns=("id", "name"),
    )
    expected = (await adapter.list(model, replace(query, limit=100))).records
    pages = []
    after = None
    for _ in range(10):
        page = await adapter.list_window(model, query, after=after)
        assert isinstance(page, RecordWindow)
        pages.append(page)
        if not page.has_next:
            break
        after = page.next_key
    assert [record for page in pages for record in page.records] == expected
    assert not pages[0].has_previous
    assert not pages[-1].has_next
    for index in range(len(pages) - 1, 0, -1):
        previous = await adapter.list_window(model, query, before=pages[index].previous_key)
        assert previous.records == pages[index - 1].records
        assert previous.has_previous == (index > 1)
    for invalid in (
        Query(offset=1),
        Query(order_by="name", columns=("id",)),
        Query(columns=("name",)),
    ):
        with pytest.raises(ValueError):
            await adapter.list_window(model, invalid)
    with pytest.raises(ValueError):
        await adapter.list_window(model, query, after={"id": 1}, before={"id": 2})


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_cursor_navigation_is_signed_filter_bound_and_permission_checked(
    backend, auth, framework
):
    adapter, model = backend
    for value in range(3):
        await adapter.create(model, {"name": f"Visible {value}"})
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    admin.configure("items", options=ModelOptions(pagination="cursor"))
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/", params={"limit": "1", "q": "Visible"})
        assert page.status_code == 200
        assert "1 on this page" in page.text
        assert "Visible 0" in page.text
        match = re.search(r'href="([^"]+)">Next', page.text)
        assert match is not None
        next_url = html.unescape(match[1])
        second = await client.get(next_url)
        assert second.status_code == 200
        assert "Visible 1" in second.text
        previous = re.search(r'href="([^"]+)">← Previous', second.text)
        assert previous is not None
        first = await client.get(html.unescape(previous[1]))
        assert first.status_code == 200
        assert "Visible 0" in first.text
        assert (await client.get(next_url + "tampered")).status_code == 400
        assert (await client.get(next_url.replace("Visible", "Hidden"))).status_code == 400
        assert (
            await client.get("/admin/models/items/", params={"sort": "name"})
        ).status_code == 200
        assert (await client.get("/admin/models/items/", params={"page": "2"})).status_code == 400
        admin.auth = PasswordAuth({**auth.users, "another": auth.users["admin"]})
        login_form = await client.get("/admin/login")
        logged_in = await client.post(
            "/admin/login",
            data={
                "__csrf": csrf(login_form),
                "username": "another",
                "password": "correct horse battery staple",
            },
        )
        assert logged_in.status_code == 303
        assert (await client.get(next_url)).status_code == 400
        admin.configure(
            "items",
            options=ModelOptions(pagination="cursor", permission=lambda r, i, action: False),
        )
        assert (await client.get(next_url)).status_code == 403


async def test_keyset_reads_execute_one_select_without_counting_or_deep_offset(tmp_path):
    from quite_admin.adapters.sql import SQLAdapter

    engine = create_engine(f"sqlite:///{tmp_path}/window.db")
    metadata = MetaData()
    table = Table(
        "records", metadata, Column("id", Integer, primary_key=True), Column("name", String)
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), [{"id": i, "name": str(i)} for i in range(1000)])
    adapter = SQLAdapter(engine)
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        page = await adapter.list_window(table, Query(limit=2), after={"id": 990})
        assert [row["id"] for row in page.records] == [991, 992]
        assert len(statements) == 1
        assert "count(" not in statements[0][0].lower()
        assert "records.id >" in statements[0][0]
        assert statements[0][1][-1] == 0  # SQLite's LIMIT syntax binds only a zero offset.
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


@pytest.mark.parametrize("reflection", [False, True])
@pytest.mark.parametrize("descending", [False, True])
async def test_composite_keyset_order_is_stable_in_both_directions(
    tmp_path, reflection, descending
):
    from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker

    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Entry(Base):
        __tablename__ = "entries"
        tenant = mapped_column(String, primary_key=True)
        code = mapped_column(Integer, primary_key=True)

    engine = create_engine(f"sqlite:///{tmp_path}/composite-window.db")
    Base.metadata.create_all(engine)
    adapter = (
        SQLAdapter(engine) if reflection else SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    )
    model = next(iter(await adapter.discover())) if reflection else Entry
    try:
        for tenant, code in (("a", 1), ("a", 2), ("b", 1), ("b", 2)):
            await adapter.create(model, {"tenant": tenant, "code": code})
        query = Query(limit=1, descending=descending)
        expected = (await adapter.list(model, replace(query, limit=100))).records
        page = await adapter.list_window(model, query)
        seen = [page.records[0]]
        previous_pages = []
        while page.has_next:
            previous_pages.append(page)
            page = await adapter.list_window(model, query, after=page.next_key)
            seen.extend(page.records)
        assert seen == expected
        for expected_page in reversed(previous_pages):
            page = await adapter.list_window(model, query, before=page.previous_key)
            assert page.records == expected_page.records
    finally:
        engine.dispose()


@pytest.mark.parametrize("order", ["count", "note"])
@pytest.mark.parametrize("descending", [False, True])
@pytest.mark.parametrize("projection", [False, True])
async def test_sorted_keysets_cover_ties_nulls_empty_values_and_backwards(
    backend, order, descending, projection
):
    from functools import cmp_to_key

    adapter, model = backend
    records = [
        await adapter.create(model, {"name": str(index), "count": index % 3, "note": note})
        for index, note in enumerate(["z", None, "a", "", None, "z", "a"])
    ]

    def compare(left, right):
        a, b = left[order], right[order]
        if (a is None) != (b is None):
            return 1 if a is None else -1
        result = 0 if a is None else (a > b) - (a < b)
        return (-result if descending else result) or (left["id"] > right["id"]) - (
            left["id"] < right["id"]
        )

    expected = sorted(records, key=cmp_to_key(compare))
    if projection:
        expected = [{"id": row["id"], order: row[order]} for row in expected]
    query = Query(
        limit=2,
        order_by=order,
        descending=descending,
        columns=("id", order) if projection else None,
    )
    pages = [await adapter.list_window(model, query)]
    while pages[-1].has_next:
        assert len(pages) < 10
        pages.append(await adapter.list_window(model, query, after=pages[-1].next_key))
    assert [row for page in pages for row in page.records] == expected
    for index in range(len(pages) - 1, 0, -1):
        previous = await adapter.list_window(model, query, before=pages[index].previous_key)
        assert previous.records == pages[index - 1].records
    with pytest.raises(ValueError):
        await adapter.list_window(model, query, after={"id": records[0]["id"]})


@pytest.mark.parametrize("descending", [False, True])
async def test_sorted_cursor_http_keeps_empty_and_null_boundaries_and_resets_on_sort(
    web_admin, web_backend, descending
):
    adapter, model = web_backend
    for index, note in enumerate(["", "a", None, "a", "z"]):
        await adapter.create(model, {"name": f"Cursor {index}", "note": note})
    web_admin.configure("items", options=ModelOptions(pagination="cursor", list_fields=("name",)))
    app = FastAPI()
    web_admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        url = "/admin/models/items/?sort=note&limit=1&direction=" + (
            "desc" if descending else "asc"
        )
        names = []
        for _ in range(6):
            page = await client.get(url)
            assert page.status_code == 200
            names.append(re.search(r'data-cell-value[^>]*title="[^"]*">(Cursor \d+)', page.text)[1])
            reset = re.search(r'<th[^>]*><a href="([^"]*sort=name[^"]*)"', page.text)
            assert reset and "after=" not in reset[1] and "before=" not in reset[1]
            next_link = re.search(r'href="([^"]+)">Next', page.text)
            if not next_link:
                break
            url = html.unescape(next_link[1])
        assert names == (
            ["Cursor 4", "Cursor 1", "Cursor 3", "Cursor 0", "Cursor 2"]
            if descending
            else ["Cursor 0", "Cursor 1", "Cursor 3", "Cursor 4", "Cursor 2"]
        )
        assert (await client.get(url.replace("sort=note", "sort=name"))).status_code == 400


@pytest.mark.parametrize("descending", [False, True])
async def test_timestamp_sort_with_uuid_identity_and_http_cursor_round_trip(
    tmp_path, auth, descending
):
    from datetime import datetime, timedelta
    from uuid import UUID

    from sqlalchemy import DateTime, Uuid
    from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker

    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Link(Base):
        __tablename__ = "links"
        id = mapped_column(Uuid(as_uuid=True), primary_key=True)
        name = mapped_column(String)
        created_at = mapped_column(DateTime, nullable=False)

    engine = create_engine(f"sqlite:///{tmp_path}/dated-links.db")
    Base.metadata.create_all(engine)
    adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    moments = [2, 0, 1, 1, 2]
    for index, day in enumerate(moments):
        await adapter.create(
            Link,
            {
                "id": UUID(int=index + 1),
                "name": f"Link {index}",
                "created_at": datetime(2026, 11, 1) + timedelta(days=day),
            },
        )
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if "FROM links" in statement:
            statements.append(statement)

    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    admin.register(
        Link, options=ModelOptions(pagination="cursor", list_fields=("name", "created_at"))
    )
    app = FastAPI()
    admin.mount_fastapi(app)
    try:
        event.listen(engine, "before_cursor_execute", capture)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await login(client)
            url = "/admin/models/links/?sort=created_at&limit=2&direction=" + (
                "desc" if descending else "asc"
            )
            pages = []
            for _ in range(4):
                page = await client.get(url)
                assert page.status_code == 200
                pages.append(re.findall(r'data-cell-value[^>]*title="[^"]*">(Link \d+)', page.text))
                next_link = re.search(r'href="([^"]+)">Next', page.text)
                if next_link is None:
                    break
                url = html.unescape(next_link[1])
            assert [name for names in pages for name in names] == (
                ["Link 0", "Link 4", "Link 2", "Link 3", "Link 1"]
                if descending
                else ["Link 1", "Link 2", "Link 3", "Link 0", "Link 4"]
            )
            previous = re.search(r'href="([^"]+)">← Previous', page.text)
            back = await client.get(html.unescape(previous[1]))
            assert (
                re.findall(r'data-cell-value[^>]*title="[^"]*">(Link \d+)', back.text) == pages[-2]
            )
        assert len(statements) == 4  # One source query per page, including Previous.
        assert all("count(" not in statement.lower() for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


async def test_existing_custom_window_adapters_keep_primary_key_contract(web_backend, auth):
    from quite_admin import DelegatingAdapter

    native, model = web_backend
    await native.create(model, {"name": "Legacy window"})

    class PrimaryKeyWindows(DelegatingAdapter):
        supports_window_sorting = False

    adapter = PrimaryKeyWindows(native)
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    admin.configure("items", options=ModelOptions(pagination="cursor"))
    app = FastAPI()
    admin.mount_fastapi(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/")
        assert page.status_code == 200
        assert "sort=id" in page.text and "sort=name" not in page.text
        assert (await client.get("/admin/models/items/?sort=name")).status_code == 400
