from enum import Enum
from types import ModuleType
from uuid import uuid4

import peewee as pw
from sqlalchemy import JSON, Computed, ForeignKey, String, create_engine
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from tortoise import Tortoise, fields
from tortoise.models import Model

from quite_admin import ModelOptions, Query
from quite_admin.adapters.peewee import PeeweeAdapter
from quite_admin.adapters.sql import SQLAdapter
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from quite_admin.adapters.tortoise import TortoiseAdapter


async def test_sqlalchemy_composite_uuid_json_enum_computed_and_foreign_key(tmp_path):
    from uuid import UUID

    class Status(Enum):
        A = "a much longer enum value"
        B = "another value"

    class Base(DeclarativeBase):
        pass

    class Team(Base):
        __tablename__ = "teams"
        id: Mapped[int] = mapped_column(primary_key=True)

    class Entry(Base):
        __tablename__ = "entries"
        tenant: Mapped[UUID] = mapped_column(primary_key=True)
        code: Mapped[str] = mapped_column(String(100), primary_key=True)
        team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
        payload: Mapped[dict] = mapped_column(JSON)
        status: Mapped[Status] = mapped_column(SAEnum(Status))
        code_length: Mapped[int] = mapped_column(Computed("length(code)"))

    engine = create_engine(f"sqlite:///{tmp_path}/features.db")
    Base.metadata.create_all(engine)
    adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    team = await adapter.create(Team, {})
    schema = adapter.describe(Entry)
    assert schema.by_name["team_id"].foreign_key == "teams.id"
    assert schema.by_name["code_length"].generated
    values = {
        "tenant": str(uuid4()),
        "code": "a/b?key=1#hello",
        "team_id": str(team["id"]),
        "payload": "[1, true]",
        "status": Status.A.value,
    }
    parsed = ModelOptions().parse_values(schema, values, creating=True)
    record = await adapter.create(Entry, parsed)
    assert record["payload"] == [1, True]
    assert record["status"] == Status.A
    assert record["code_length"] == len(values["code"])
    key = schema.parse_key(schema.record_key(record))
    assert (await adapter.get(Entry, key))["code"] == values["code"]
    assert (await adapter.update(Entry, key, {"payload": None}))["payload"] is None
    await adapter.delete(Entry, key)
    assert await adapter.get(Entry, key) is None
    engine.dispose()


async def test_reflection_refresh_and_composite_key(tmp_path):
    from sqlalchemy import Column, Integer, MetaData, Table, text

    engine = create_engine(f"sqlite:///{tmp_path}/reflection.db")
    metadata = MetaData()
    Table(
        "entries",
        metadata,
        Column("tenant", String, primary_key=True),
        Column("code", String, primary_key=True),
        Column("value", Integer, server_default="0"),
    )
    Table("excluded", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    adapter = SQLAdapter(engine, exclude_tables=("excluded",))
    tables = tuple(await adapter.discover())
    assert len(tables) == 1
    table = tables[0]
    record = await adapter.create(table, {"tenant": "one", "code": "two/three"})
    schema = adapter.describe(table)
    assert record["value"] == 0
    key = schema.parse_key(schema.record_key(record))
    assert await adapter.get(table, key) == record
    assert (await adapter.update(table, key, {"value": 42}))["value"] == 42
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE entries ADD COLUMN note VARCHAR"))
    assert "note" not in adapter.describe(table).by_name
    await adapter.refresh()
    table = tuple(await adapter.discover())[0]
    assert "note" in adapter.describe(table).by_name
    await adapter.delete(table, key)
    assert (await adapter.list(table, Query())).total == 0
    engine.dispose()


async def test_peewee_composite_key_and_raw_fk(tmp_path):
    database = pw.SqliteDatabase(str(tmp_path / "peewee.db"), pragmas={"foreign_keys": 1})

    class Team(pw.Model):
        name = pw.TextField()

    class Entry(pw.Model):
        tenant = pw.TextField()
        code = pw.TextField()
        team = pw.ForeignKeyField(Team)

        class Meta:
            primary_key = pw.CompositeKey("tenant", "code")

    database.bind([Team, Entry])
    database.create_tables([Team, Entry])
    database.close()
    adapter = PeeweeAdapter(models=[Team, Entry])
    team = await adapter.create(Team, {"name": "Engineering"})
    record = await adapter.create(Entry, {"tenant": "one", "code": "two/three", "team": team["id"]})
    assert record["team"] == team["id"]
    schema = adapter.describe(Entry)
    assert schema.by_name["team"].foreign_key == "team.id"
    assert schema.by_name["team"].kind == "integer"
    key = schema.parse_key(schema.record_key(record))
    assert await adapter.get(Entry, key) == record
    await adapter.delete(Entry, key)
    assert await adapter.get(Entry, key) is None


async def test_tortoise_uuid_and_raw_foreign_keys():
    class Team(Model):
        name = fields.CharField(max_length=50)

        class Meta:
            table = "teams"

    class Entry(Model):
        id = fields.UUIDField(primary_key=True)
        name = fields.CharField(max_length=50)
        team = fields.ForeignKeyField("models.Team", related_name="entries")
        payload = fields.JSONField(default=dict)

    module = ModuleType("foreign_key_models")
    module.__models__ = [Team, Entry]
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": [module]})
    try:
        await Tortoise.generate_schemas()
        adapter = TortoiseAdapter()
        schema = adapter.describe(Entry)
        assert "team_id" in schema.by_name
        assert "team" not in schema.by_name
        assert schema.by_name["team_id"].foreign_key == "teams.id"
        team = await adapter.create(Team, {"name": "Engineering"})
        record = await adapter.create(
            Entry, {"name": "example", "team_id": team["id"], "payload": [1, True]}
        )
        key = schema.parse_key(schema.record_key(record))
        assert await adapter.get(Entry, key) == record
        assert (await adapter.update(Entry, key, {"payload": {"ok": True}}))["payload"] == {
            "ok": True
        }
        await adapter.delete(Entry, key)
        assert await adapter.get(Entry, key) is None
    finally:
        await Tortoise.close_connections()
