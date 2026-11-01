import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from quite_admin.adapters.sql import SQLAdapter
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from quite_admin.errors import QueryTimeout

from .databases import sqlalchemy_url


@pytest.mark.parametrize("mode", ["sql", "sql_async", "sqlalchemy", "sqlalchemy_async"])
async def test_deadline_interrupts_queries_and_clears_pooled_connection_state(tmp_path, mode):
    asynchronous = mode.endswith("async")
    driver = "sqlite+aiosqlite" if asynchronous else "sqlite"
    url = sqlalchemy_url(f"{driver}:///{tmp_path}/timeout.db", asynchronous=asynchronous)
    engine = create_async_engine(url) if asynchronous else create_engine(url)
    metadata = MetaData()
    table = Table("records", metadata, Column("id", Integer, primary_key=True))
    if asynchronous:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
    else:
        metadata.create_all(engine)
    if mode.startswith("sqlalchemy"):
        factory = async_sessionmaker(engine) if asynchronous else sessionmaker(engine)
        adapter = SQLAlchemyAdapter(factory, query_timeout=0.005)
    else:
        adapter = SQLAdapter(engine, query_timeout=0.005)
    if engine.dialect.name == "postgresql":
        query = text("SELECT pg_sleep(1)")
    elif engine.dialect.name == "mysql":
        query = text(
            "WITH RECURSIVE slow(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM slow WHERE n<1000) "
            "SELECT sum(a.n*b.n) FROM slow a CROSS JOIN slow b"
        )
    else:
        query = text(
            "WITH RECURSIVE slow(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM slow WHERE n<10000000) "
            "SELECT sum(n) FROM slow"
        )

    def expensive(connection):
        return connection.execute(query).scalar_one()

    try:
        kwargs = {"read": True} if mode.startswith("sqlalchemy") else {}
        with pytest.raises(QueryTimeout) as raised:
            await adapter._run(expensive, **kwargs)
        assert raised.value.status_code == 504
        assert "slow" not in str(raised.value)
        # The second operation must not inherit an expired progress handler.
        assert (
            await adapter._run(
                lambda connection: connection.execute(text("SELECT 42")).scalar_one(), **kwargs
            )
            == 42
        )
        if not mode.startswith("sqlalchemy"):
            assert (await adapter.create(table, {"id": 1}))["id"] == 1
    finally:
        if asynchronous:
            async with engine.begin() as connection:
                await connection.run_sync(metadata.drop_all)
            await engine.dispose()
        else:
            metadata.drop_all(engine)
            engine.dispose()


@pytest.mark.parametrize("seconds", [0, -1, True, float("inf"), float("nan")])
def test_invalid_query_deadlines_fail_at_configuration(seconds):
    engine = create_engine("sqlite://")
    try:
        with pytest.raises(ValueError, match="query_timeout"):
            SQLAdapter(engine, query_timeout=seconds)
        with pytest.raises(ValueError, match="query_timeout"):
            SQLAlchemyAdapter(sessionmaker(engine), query_timeout=seconds)
    finally:
        engine.dispose()
