import asyncio
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

import pytest
from gino import Gino
from sqlalchemy import Computed, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from quite_admin import ModelOptions, Query, RelationAdapter
from quite_admin.adapters import Adapter
from quite_admin.adapters.gino import GinoAdapter
from quite_admin.errors import Conflict, NotFound


def test_scoped_discovery_explicit_empty_models_and_wrong_database():
    db = Gino()
    other = Gino()

    class Base(db.Model):
        pass

    class User(Base):
        __tablename__ = "users"
        id = db.Column(db.Integer, primary_key=True)

    class Foreign(other.Model):
        __tablename__ = "foreign"
        id = other.Column(other.Integer, primary_key=True)

    adapter = GinoAdapter(db)
    assert isinstance(adapter, Adapter)
    assert isinstance(adapter, RelationAdapter)
    assert tuple(adapter.discover()) == (User,)
    assert tuple(GinoAdapter(db, models=[]).discover()) == ()
    for wrong in (Base, Foreign, object()):
        with pytest.raises(ValueError):
            GinoAdapter(db, models=[wrong])
        with pytest.raises(ValueError):
            adapter.describe(wrong)


def test_no_primary_key_is_rejected():
    db = Gino()

    class Log(db.Model):
        __tablename__ = "logs"
        message = db.Column(db.String)

    with pytest.raises(ValueError, match="no primary key"):
        GinoAdapter(db).describe(Log)


async def test_postgresql_scalar_types_composite_identity_and_aliases(db):
    class Status(Enum):
        NEW = "new"
        DONE = "done"

    class Entry(db.Model):
        __tablename__ = "entries"
        tenant = db.Column(PGUUID(), primary_key=True)
        code = db.Column(db.String(100), primary_key=True)
        title = db.Column("db_title", db.String(100), nullable=False)
        amount = db.Column(db.Numeric(38, 18))
        payload = db.Column(JSONB)
        status = db.Column(db.Enum(Status, name="entry_status"), default=Status.NEW)
        created = db.Column(db.DateTime(timezone=True))
        day = db.Column(db.Date)
        clock = db.Column(db.Time)
        count = db.Column(db.BigInteger)
        code_length = db.Column(db.Integer, Computed("length(code)"))

    await db.gino.create_all()
    adapter = GinoAdapter(db)
    schema = adapter.describe(Entry)
    assert schema.by_name["tenant"].python_type is UUID
    assert schema.by_name["status"].python_type is Status
    assert schema.by_name["payload"].kind == "json"
    assert schema.by_name["code_length"].read_only
    assert schema.by_name["code_length"].generated
    now = datetime(2026, 10, 29, 12, 30, tzinfo=UTC)
    values = {
        "tenant": str(uuid4()),
        "code": "a/b?key=1#hello",
        "title": "Before",
        "amount": "12345678901234567890.123456789012345678",
        "payload": '[1, true, {"nested": null}]',
        "status": Status.DONE.value,
        "created": now.isoformat(),
        "day": "2026-10-29",
        "clock": "12:30:01",
        "count": str(2**63 - 1),
    }
    record = await adapter.create(Entry, ModelOptions().parse_values(schema, values, creating=True))
    assert record["amount"] == Decimal(values["amount"])
    assert record["payload"] == [1, True, {"nested": None}]
    assert record["status"] == Status.DONE
    assert record["created"] == now
    assert record["day"] == date(2026, 10, 29)
    assert record["clock"] == time(12, 30, 1)
    assert record["code_length"] == len(values["code"])
    assert record["count"] == 2**63 - 1
    assert record["title"] == "Before" and "db_title" not in record
    identity = schema.parse_key(schema.record_key(record))
    assert await adapter.get(Entry, identity) == record
    assert (await adapter.update(Entry, identity, {"title": "After", "payload": None}))[
        "title"
    ] == "After"
    assert (await adapter.list(Entry, Query(search="AFTER", search_fields=("title",)))).total == 1
    await adapter.delete(Entry, identity)
    assert await adapter.get(Entry, identity) is None


async def test_composite_fk_and_junction_with_column_aliases(db):
    class Parent(db.Model):
        __tablename__ = "parents"
        tenant = db.Column(db.String(50), primary_key=True)
        code = db.Column(db.String(50), primary_key=True)

    class Child(db.Model):
        __tablename__ = "children"
        id = db.Column(db.Integer, primary_key=True)
        tenant = db.Column("parent_tenant", db.String(50))
        code = db.Column("parent_code", db.String(50))
        __table_args__ = (
            db.ForeignKeyConstraint(
                ["parent_tenant", "parent_code"], ["parents.tenant", "parents.code"]
            ),
        )

    class Tag(db.Model):
        __tablename__ = "tags"
        tenant = db.Column(db.String(50), primary_key=True)
        code = db.Column(db.String(50), primary_key=True)

    class Junction(db.Model):
        __tablename__ = "parent_tags"
        parent_tenant = db.Column(db.String(50), primary_key=True)
        parent_code = db.Column(db.String(50), primary_key=True)
        tag_tenant = db.Column(db.String(50), primary_key=True)
        tag_code = db.Column(db.String(50), primary_key=True)
        __table_args__ = (
            db.ForeignKeyConstraint(
                ["parent_tenant", "parent_code"], ["parents.tenant", "parents.code"]
            ),
            db.ForeignKeyConstraint(["tag_tenant", "tag_code"], ["tags.tenant", "tags.code"]),
        )

    await db.gino.create_all()
    adapter = GinoAdapter(db)
    parent = await adapter.create(Parent, {"tenant": "a", "code": "b/c"})
    other = await adapter.create(Parent, {"tenant": "different", "code": "b/c"})
    tag = await adapter.create(Tag, {"tenant": "t", "code": "x"})
    relation = next(r for r in adapter.relations(Child) if r.target is Parent)
    assert relation.source_fields == ("tenant", "code")
    child = await adapter.save_relations(Child, {}, {relation.name: [parent]})
    assert (await adapter.related(Child, relation.name, {"id": child["id"]}, Query())).records == [
        parent
    ]
    await adapter.save_relations(Child, {}, {relation.name: [other]}, key={"id": child["id"]})
    assert (await adapter.get(Child, {"id": child["id"]}))["tenant"] == "different"
    many = next(r for r in adapter.relations(Parent) if r.kind == "many_to_many")
    await adapter.save_relations(Parent, {}, {many.name: [tag, tag]}, key=parent)
    assert (await adapter.related(Parent, many.name, parent, Query())).records == [tag]
    assert (await adapter.related(Parent, many.name, other, Query())).total == 0
    await adapter.save_relations(Parent, {}, {many.name: []}, key=parent)
    assert (await adapter.related(Parent, many.name, parent, Query())).total == 0
    assert await adapter.get(Tag, tag) == tag


async def test_native_create_hook_trigger_cascade_and_rollback(db):
    class Item(db.Model):
        __tablename__ = "items"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100))

        async def _create(self, **kwargs):
            blocked = self.name == "blocked"
            self.name = "model:" + self.name
            result = await super()._create(**kwargs)
            if blocked:
                raise RuntimeError("Application hook rejected the operation")
            return result

    class Child(db.Model):
        __tablename__ = "children"
        id = db.Column(db.Integer, primary_key=True)
        parent_id = db.Column(db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"))

    await db.gino.create_all()
    await db.status(
        text("""
        CREATE FUNCTION normalize_name() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.name := 'db:' || NEW.name; RETURN NEW; END $$
    """)
    )
    await db.status(
        text("""
        CREATE TRIGGER label_insert BEFORE INSERT ON items
        FOR EACH ROW EXECUTE FUNCTION normalize_name()
    """)
    )
    adapter = GinoAdapter(db)
    row = await adapter.create(Item, {"name": "hello"})
    assert row["name"] == "db:model:hello"
    with pytest.raises(RuntimeError, match="hook rejected"):
        await adapter.create(Item, {"name": "blocked"})
    assert (await adapter.list(Item, Query())).total == 1
    child = await adapter.create(Child, {"parent_id": row["id"]})
    await adapter.delete(Item, {"id": row["id"]})
    assert await adapter.get(Child, {"id": child["id"]}) is None
    assert db.bind is not None


async def test_does_not_commit_or_reuse_a_host_transaction(backend):
    adapter, model = backend
    with pytest.raises(RuntimeError, match="host rollback"):
        async with adapter.db.transaction():
            await model.create(name="uncommitted host row")
            assert (await adapter.list(model, Query())).total == 0
            row = await adapter.create(model, {"name": "admin committed row"})
            assert await adapter.get(model, {"id": row["id"]}) == row
            raise RuntimeError("host rollback")
    assert [row["name"] for row in (await adapter.list(model, Query())).records] == [
        "admin committed row"
    ]
    results = await asyncio.gather(
        *(adapter.create(model, {"name": f"parallel {n}"}) for n in range(4))
    )
    assert len({row["id"] for row in results}) == 4


async def test_invalid_relationship_selection_and_explicit_exposure(related_backend):
    adapter, models = related_backend
    parent_model, child_model = models["parents"], models["children"]
    parent = await adapter.create(parent_model, {"name": "Before"})
    key = {"id": parent["id"]}
    child = await adapter.create(child_model, {"name": "Unrelated"})
    relation = next(r for r in adapter.relations(parent_model) if r.target is child_model)
    with pytest.raises(NotFound):
        await adapter.save_relations(
            parent_model, {"name": "ROLLBACK"}, {relation.name: [{"id": -1}]}, key=key
        )
    with pytest.raises(Conflict):
        await adapter.save_relations(parent_model, {}, {"__dict__": []}, key=key)
    with pytest.raises(ValueError):
        await adapter.save_relations(parent_model, {}, {relation.name: [{}]}, key=key)
    assert await adapter.get(parent_model, key) == parent
    assert (await adapter.get(child_model, {"id": child["id"]}))["parent_id"] is None
    restricted = GinoAdapter(adapter.db, models=[parent_model])
    assert not restricted.relations(parent_model)
