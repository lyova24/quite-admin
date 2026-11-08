import html
import json
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, select

from quite_admin import Admin, ModelOptions
from quite_admin.adapters.sql import SQLAdapter

from .helpers import login


@pytest.fixture
def large_schema_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/large-schema.db")
    metadata = MetaData()
    for index in range(101):
        columns = [
            Column("id", Integer, primary_key=True),
            Column("name", String(100)),
            Column("password_hash", String(100)),
        ]
        if index:
            columns.append(Column("parent_id", ForeignKey("large_000.id")))
        Table(f"large_{index:03d}", metadata, *columns)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["large_000"].insert(),
            {"id": 1, "name": "Record values stay private", "password_hash": "never show this"},
        )
    try:
        yield engine, metadata
    finally:
        engine.dispose()


def schema_graph(response):
    match = re.search(r"data-graph='([^']+)'", response.text)
    assert match is not None, response.text
    return json.loads(html.unescape(match.group(1)))


@pytest.mark.parametrize(
    ("options", "selection"),
    [
        ({}, "none"),
        ({"schema_auto_limit": False}, "all"),
        ({"schema_table_limit": 101}, "all"),
        ({"schema_table_limit": 100}, "none"),
    ],
)
async def test_initial_selection_threshold_keeps_full_authorized_catalog(
    auth, large_schema_engine, options, selection
):
    engine, metadata = large_schema_engine
    adapter = SQLAdapter(engine)
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        **options,
    )
    host = FastAPI()
    admin.mount_fastapi(host, "/admin")

    async def no_records(*args, **kwargs):
        raise AssertionError("Schema selection must not read or modify records.")

    for method in ("list", "get", "create", "update", "delete"):
        setattr(adapter, method, no_records)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        assert (await client.get("/admin/schema")).status_code == 303
        await login(client)
        response = await client.get("/admin/schema")
        assert response.status_code == 200
        assert f'data-initial-selection="{selection}"' in response.text
        assert ("data-schema-initial-notice" in response.text) is (selection == "none")
        graph = schema_graph(response)
        assert len(graph["nodes"]) == 101
        assert len(graph["edges"]) == 100
        assert {node["id"] for node in graph["nodes"]} == set(metadata.tables)
        assert all(
            field["name"] != "password_hash" for node in graph["nodes"] for field in node["fields"]
        )
        assert "Record values stay private" not in response.text
        assert "never show this" not in response.text
        assert (await client.post("/admin/schema", data={"selection": "all"})).status_code == 405
    with engine.connect() as connection:
        assert connection.execute(select(metadata.tables["large_000"].c.name)).scalar_one() == (
            "Record values stay private"
        )


async def test_threshold_counts_only_tables_with_both_list_and_view_permissions(
    auth, large_schema_engine
):
    engine, metadata = large_schema_engine
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[SQLAdapter(engine)],
    )
    admin.configure("large_100", options=ModelOptions(permission=lambda r, i, a: a != "view"))
    host = FastAPI()
    admin.mount_fastapi(host, "/admin")
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        response = await client.get("/admin/schema")
        assert 'data-initial-selection="all"' in response.text
        assert "data-schema-initial-notice" not in response.text
        graph = schema_graph(response)
        assert len(graph["nodes"]) == 100
        assert "large_100" not in {node["id"] for node in graph["nodes"]}
        assert all(edge["source"] != "large_100" for edge in graph["edges"])

        admin.configure("large_099", options=ModelOptions(permission=lambda r, i, a: a != "list"))
        small = await client.get("/admin/schema")
        assert 'data-initial-selection="all"' in small.text
        assert len(schema_graph(small)["nodes"]) == 99


async def test_guard_notice_is_translated_in_russian(auth, large_schema_engine):
    engine, _ = large_schema_engine
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        language="ru",
        secure_cookies=False,
        adapters=[SQLAdapter(engine)],
    )
    host = FastAPI()
    admin.mount_fastapi(host, "/admin")
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        response = await client.get("/admin/schema")
        assert "Таблиц слишком много для автоматического отображения." in response.text
        assert "Выберите таблицы в боковой панели" in response.text


@pytest.mark.parametrize("value", [None, 0, 1, "true", []])
def test_schema_auto_limit_requires_a_boolean(auth, value):
    with pytest.raises(ValueError, match="schema_auto_limit must be a boolean"):
        Admin(auth=auth, secret_key="s" * 32, schema_auto_limit=value)


@pytest.mark.parametrize("value", [None, 0, -1, 1.5, True, False, "100"])
def test_schema_table_limit_requires_a_positive_integer(auth, value):
    with pytest.raises(ValueError, match="schema_table_limit must be a positive integer"):
        Admin(auth=auth, secret_key="s" * 32, schema_table_limit=value)
