import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMINT, TINYINT
from sqlalchemy.exc import DataError

from quite_admin import Admin, Field
from quite_admin.errors import ValidationError

from .helpers import csrf, login, revision


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
@pytest.mark.parametrize("value", [-(2**63) - 1, 2**63])
async def test_integer_overflow_returns_validation_errors_and_keeps_storage_usable(
    backend, auth, framework, value
):
    adapter, model = backend
    schema = adapter.describe(model)
    field = schema.by_name["count"]
    assert (field.minimum, field.maximum) == (-(2**63), 2**63 - 1)
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    record = await adapter.create(model, {"name": "original", "count": 1})
    key = {"id": record["id"]}
    path = "/admin/models/items/" + schema.record_key(record)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        form = await client.get("/admin/models/items/new")
        response = await client.post(
            "/admin/models/items/new",
            data={"__csrf": csrf(form), "name": "overflow", "count": str(value)},
        )
        assert response.status_code == 422
        assert str(value) in response.text
        form = await client.get(path)
        response = await client.post(
            path,
            data={"__csrf": csrf(form), "__revision": revision(form), "count": str(value)},
        )
        assert response.status_code == 422
        assert (await adapter.get(model, key))["count"] == 1
        response = await client.get("/admin/models/items/", params={"f.count.eq": str(value)})
        assert response.status_code == 422
        response = await client.post(
            path,
            data={"__csrf": csrf(form), "__revision": revision(form), "count": "2"},
        )
        assert response.status_code == 303
        assert (await adapter.get(model, key))["count"] == 2
    with pytest.raises(ValidationError):
        await adapter.create(model, {"name": "overflow", "count": value})
    with pytest.raises(ValidationError):
        await adapter.update(model, key, {"count": value})


@pytest.mark.parametrize(
    ("type_", "minimum", "maximum"),
    [
        (TINYINT(), -128, 127),
        (MEDIUMINT(), -(2**23), 2**23 - 1),
        (BIGINT(unsigned=True), 0, 2**64 - 1),
    ],
)
def test_reflected_integer_ranges_include_mysql_unsigned_types(type_, minimum, maximum):
    from quite_admin.adapters.sql import SQLAdapter

    engine = create_engine("sqlite://")
    try:
        table = Table(
            "ranges", MetaData(), Column("id", Integer, primary_key=True), Column("n", type_)
        )
        field = SQLAdapter(engine).describe(table).by_name["n"]
        assert field.parse(str(minimum)) == minimum
        assert field.parse(str(maximum)) == maximum
        for value in (minimum - 1, maximum + 1):
            with pytest.raises(ValueError):
                field.parse(str(value))
    finally:
        engine.dispose()


def test_custom_integer_fields_remain_unbounded_without_explicit_limits():
    assert Field("unbounded", int).parse(str(2**100)) == 2**100
    with pytest.raises(ValueError):
        Field("invalid", int, minimum=2, maximum=1)


async def test_driver_data_errors_are_sanitized_and_transactions_recover(tmp_path):
    from quite_admin.adapters.sql import SQLAdapter

    engine = create_engine(f"sqlite:///{tmp_path}/errors.db")
    metadata = MetaData()
    table = Table("records", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    adapter = SQLAdapter(engine)

    def fail(connection):
        connection.execute(table.insert(), {"id": 1})
        raise DataError("private statement", {}, ValueError("private record contents"))

    try:
        with pytest.raises(ValidationError) as raised:
            await adapter._run(fail, write=True)
        assert raised.value.errors == {"__all__": "The database rejected these values."}
        assert await adapter.get(table, {"id": 1}) is None
        assert (await adapter.create(table, {"id": 1}))["id"] == 1
    finally:
        engine.dispose()
