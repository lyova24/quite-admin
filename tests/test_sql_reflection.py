import pytest
from sqlalchemy import Boolean, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.asyncio import create_async_engine

from quite_admin import Filter, Query
from quite_admin.adapters.sql import SQLAdapter

from .databases import sqlalchemy_url


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def reflection_engine(request, tmp_path):
    asynchronous = request.param
    metadata = MetaData()
    tiny = Integer().with_variant(TINYINT(display_width=1), "mysql")
    Table(
        "reflection_types",
        metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "active",
            Boolean()
            .with_variant(Integer(), "sqlite")
            .with_variant(TINYINT(display_width=1), "mysql"),
            nullable=False,
        ),
        Column("level", tiny, nullable=False),
    )
    if asynchronous:
        engine = create_async_engine(
            sqlalchemy_url(f"sqlite+aiosqlite:///{tmp_path}/types.db", asynchronous=True)
        )
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
    else:
        engine = create_engine(sqlalchemy_url(f"sqlite:///{tmp_path}/types.db"))
        metadata.create_all(engine)
    try:
        yield engine
    finally:
        if asynchronous:
            async with engine.begin() as connection:
                await connection.run_sync(metadata.drop_all)
            await engine.dispose()
        else:
            metadata.drop_all(engine)
            engine.dispose()


async def test_explicit_boolean_type_preserves_other_integer_columns(reflection_engine):
    plain = SQLAdapter(reflection_engine, include_tables=("reflection_types",))
    (table,) = await plain.discover()
    native_boolean = reflection_engine.dialect.name == "postgresql"
    plain_kind = "boolean" if native_boolean else "integer"
    assert plain.describe(table).by_name["active"].kind == plain_kind
    raw = await plain.create(table, {"active": False, "level": 2})
    assert type(raw["active"]) is (bool if native_boolean else int)
    assert raw["level"] == 2

    typed = SQLAdapter(
        reflection_engine,
        include_tables=("reflection_types",),
        column_types={"reflection_types": {"active": Boolean()}},
    )
    (table,) = await typed.discover()
    assert typed.describe(table).by_name["active"].kind == "boolean"
    assert typed.describe(table).by_name["level"].kind == "integer"
    assert (await typed.get(table, {"id": raw["id"]}))["active"] is False
    created = await typed.create(table, {"active": True, "level": 3})
    assert created["active"] is True
    assert created["level"] == 3
    page = await typed.list(table, Query(filters=(Filter("active", "eq", True),)))
    assert page.records == [created]
    with pytest.raises(ValueError, match="Python type"):
        await typed.list(table, Query(filters=(Filter("active", "eq", 1),)))
    updated = await typed.update(table, {"id": created["id"]}, {"active": False})
    assert updated["active"] is False
    assert updated["level"] == 3
    await typed.refresh()
    (refreshed,) = await typed.discover()
    assert (await typed.get(refreshed, {"id": created["id"]}))["active"] is False
    # The override is adapter-local and does not mutate another reflected schema.
    assert plain.describe((await plain.discover())[0]).by_name["active"].kind == plain_kind


@pytest.mark.parametrize(
    "overrides",
    [{"missing": {"active": Boolean()}}, {"reflection_types": {"missing": Boolean()}}],
)
async def test_type_overrides_reject_unknown_schema_fields(reflection_engine, overrides):
    adapter = SQLAdapter(reflection_engine, column_types=overrides)
    with pytest.raises(ValueError, match="Unknown"):
        await adapter.discover()


def test_type_overrides_require_sqlalchemy_type_instances():
    with pytest.raises(TypeError, match="type instances"):
        SQLAdapter(create_engine("sqlite://"), column_types={"items": {"active": bool}})
