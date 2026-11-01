import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import LargeBinary, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from quite_admin import Admin, ModelOptions, Query
from quite_admin.adapters.sql import SQLAdapter
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

from .helpers import login


@pytest.mark.parametrize("window", [False, True])
async def test_list_metadata_work_does_not_grow_with_page_size(backend, monkeypatch, window):
    adapter, model = backend
    for index in range(6):
        await adapter.create(model, {"name": f"Item {index}"})
    describe = adapter.describe
    calls = 0

    def tracked(model):
        nonlocal calls
        calls += 1
        return describe(model)

    monkeypatch.setattr(adapter, "describe", tracked)
    read = adapter.list_window if window else adapter.list
    small = await read(model, Query(limit=1))
    small_calls = calls
    calls = 0
    large = await read(model, Query(limit=5))
    assert len(small.records) == 1
    assert len(large.records) == 5
    assert large.records[0] == small.records[0]
    assert [record["name"] for record in large.records] == [f"Item {i}" for i in range(5)]
    assert calls == small_calls > 0


@pytest.mark.parametrize("reflection", [False, True])
async def test_projection_prevents_loading_unselected_values_in_queries_and_web(
    tmp_path, auth, reflection
):
    class UnreadableBlob(TypeDecorator):
        impl = LargeBinary
        cache_ok = True

        def process_result_value(self, value, dialect):
            raise AssertionError("An unselected BLOB reached the application")

    class Base(DeclarativeBase):
        pass

    class Entry(Base):
        __tablename__ = "entries"
        id = mapped_column(primary_key=True, type_=String)
        name = mapped_column(String, nullable=False)
        payload = mapped_column(UnreadableBlob())

    engine = create_engine(f"sqlite:///{tmp_path}/projection.db")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(), {"id": "one", "name": "Visible", "payload": b"unselected"}
        )
    adapter = (
        SQLAdapter(engine, column_types={"entries": {"payload": UnreadableBlob()}})
        if reflection
        else SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    )
    model = next(iter(await adapter.discover())) if reflection else Entry
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    admin.register(model, options=ModelOptions(list_fields=("name",)))
    host = FastAPI()
    admin.mount_fastapi(host)
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        page = await adapter.list(model, Query(columns=("name",), order_by="id"))
        assert page.records == [{"name": "Visible"}]
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
            response = await client.get("/admin/models/entries/")
            assert response.status_code == 200
            assert "Visible" in response.text
            response = await client.get(
                "/admin/models/entries/", params={"export": "csv", "columns": "name"}
            )
            assert response.status_code == 200
            assert "Visible" in response.text
        assert statements and all("entries.payload" not in statement for statement in statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()
