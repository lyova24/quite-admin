from datetime import date, datetime, time
from types import ModuleType

import peewee as pw
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from sqlalchemy import JSON, Date, DateTime, Integer, String, Text, Time, create_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker
from tortoise import Tortoise, fields
from tortoise.models import Model

from quite_admin import Admin, ModelOptions
from quite_admin.adapters.peewee import PeeweeAdapter
from quite_admin.adapters.sql import SQLAdapter
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from quite_admin.adapters.tortoise import TortoiseAdapter

from .helpers import csrf, login


@pytest.fixture(params=["sql", "sqlalchemy", "peewee", "tortoise"])
async def typed_backend(request, tmp_path):
    if request.param.startswith("sql"):

        class Base(DeclarativeBase):
            pass

        class Entry(Base):
            __tablename__ = "entries"
            id = mapped_column(primary_key=True, type_=Integer)
            short = mapped_column(String(20))
            body = mapped_column(Text)
            payload = mapped_column(JSON)
            day = mapped_column(Date)
            moment = mapped_column(DateTime)
            clock = mapped_column(Time)

        engine = create_engine(f"sqlite:///{tmp_path}/forms.db")
        Base.metadata.create_all(engine)
        adapter = (
            SQLAdapter(engine)
            if request.param == "sql"
            else SQLAlchemyAdapter(sessionmaker(engine), base=Base)
        )
        model = tuple(await adapter.discover())[0] if request.param == "sql" else Entry
        yield adapter, model
        engine.dispose()
    elif request.param == "peewee":
        db = pw.SqliteDatabase(str(tmp_path / "forms.db"))

        class Entry(pw.Model):
            short = pw.CharField(max_length=20)
            body = pw.TextField()
            day = pw.DateField()
            moment = pw.DateTimeField()
            clock = pw.TimeField()

            class Meta:
                database = db
                table_name = "entries"

        db.create_tables([Entry])
        db.close()
        yield PeeweeAdapter(models=[Entry]), Entry
        with db.connection_context():
            db.drop_tables([Entry])
    else:

        class Entry(Model):
            short = fields.CharField(max_length=20)
            body = fields.TextField()
            payload = fields.JSONField()
            day = fields.DateField()
            moment = fields.DatetimeField()
            clock = fields.TimeField()

            class Meta:
                table = "entries"

        module = ModuleType("typed_models")
        module.__models__ = [Entry]
        await Tortoise.init(db_url=f"sqlite://{tmp_path}/forms.db", modules={"models": [module]})
        await Tortoise.generate_schemas()
        yield TortoiseAdapter(), Entry
        await Tortoise.close_connections()


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_type_specific_controls_submit_and_preserve_invalid_values(
    typed_backend, auth, framework
):
    adapter, model = typed_backend
    schema = adapter.describe(model)
    assert schema.by_name["body"].multiline
    assert not schema.by_name["short"].multiline
    admin = Admin(auth=auth, secret_key="s" * 48, adapters=[adapter], secure_cookies=False)
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/entries/new")
        assert '<textarea id="field-body"' in page.text
        assert 'name="short"' in page.text and 'maxlength="20"' in page.text
        assert 'data-temporal="datetime"' in page.text and 'data-temporal="time"' in page.text
        assert 'type="date"' in page.text
        assert "forms.js" in page.text and "sha256-" in page.headers["content-security-policy"]
        data = {
            "__csrf": csrf(page),
            "short": "One",
            "body": "First\nSecond",
            "day": "2026-11-01",
            "moment": "2026-11-01T12:34:56.123456",
            "clock": "12:34:56.123456",
        }
        if "payload" in schema.by_name:
            assert "data-json-editor" in page.text
            data["payload"] = '{"large":9007199254740993,"text":"</textarea><script>bad</script>"}'
            invalid = await client.post(
                "/admin/models/entries/new", data={**data, "payload": '{"broken":'}
            )
            assert invalid.status_code == 422
            assert '{"broken":' in invalid.text.replace("&#34;", '"')
        response = await client.post("/admin/models/entries/new", data=data)
        assert response.status_code == 303, response.text
        from quite_admin import Query

        record = (await adapter.list(model, Query())).records[0]
        assert record["body"] == "First\nSecond" and record["day"] == date(2026, 11, 1)
        assert record["moment"].replace(tzinfo=None) == datetime(2026, 11, 1, 12, 34, 56, 123456)
        assert record["clock"].replace(tzinfo=None) == time(12, 34, 56, 123456)
        if "payload" in schema.by_name:
            assert record["payload"]["large"] == 9007199254740993
        admin.configure("entries", options=ModelOptions(permission=lambda r, i, a: a != "edit"))
        readonly = await client.get("/admin/models/entries/" + schema.record_key(record))
        assert readonly.status_code == 200
        assert "data-temporal=" not in readonly.text and "data-json-editor" not in readonly.text
        assert "forms.js" not in readonly.text
