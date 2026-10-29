from decimal import Decimal

import pytest

from quite_admin import Field, ModelSchema, Query


@pytest.mark.parametrize(
    "query",
    [
        Query(order_by="name DESC; DROP TABLE items; --"),
        Query(order_by="__dict__"),
        Query(order_by="name__contains"),
        Query(search="x", search_fields=("name) OR 1=1 --",)),
        Query(search="x", search_fields=("count",)),
        Query(offset=-1),
        Query(limit=-1),
        Query(limit=10001),
        Query(limit=True),
    ],
)
async def test_rejects_unsafe_queries_before_data_access(backend, query):
    adapter, model = backend
    with pytest.raises(ValueError):
        await adapter.list(model, query)
    assert (await adapter.list(model, Query())).total == 0


async def test_search_values_are_bound_literals(backend):
    adapter, model = backend
    attack = "x' OR 1=1; DROP TABLE items; --"
    first = await adapter.create(model, {"name": attack})
    await adapter.create(model, {"name": "ordinary"})
    result = await adapter.list(model, Query(search=attack, search_fields=("name",)))
    assert result.total == 1
    assert result.records[0]["id"] == first["id"]
    assert (await adapter.list(model, Query())).total == 2


@pytest.mark.parametrize("key", [{}, {"id": None}, {"name": "ordinary"}, {"id__gt": 0}])
async def test_requires_exact_complete_primary_keys(backend, key):
    adapter, model = backend
    record = await adapter.create(model, {"name": "ordinary"})
    for operation in (adapter.get, adapter.delete):
        with pytest.raises(ValueError):
            await operation(model, key)
    with pytest.raises(ValueError):
        await adapter.update(model, key, {"name": "changed"})
    assert await adapter.get(model, {"id": record["id"]}) == record


async def test_does_not_assign_model_attributes_or_primary_keys(backend):
    adapter, model = backend
    record = await adapter.create(model, {"name": "ordinary"})
    key = {"id": record["id"]}
    for values in ({"__dict__": {}}, {"unknown": "x"}):
        with pytest.raises(ValueError):
            await adapter.create(model, values)
        with pytest.raises(ValueError):
            await adapter.update(model, key, values)
    with pytest.raises(ValueError):
        await adapter.update(model, key, {"id": record["id"] + 1})
    assert await adapter.get(model, key) == record


async def test_null_and_large_integer_round_trip(backend):
    adapter, model = backend
    value = 2**63 - 1
    record = await adapter.create(model, {"name": "large", "count": value, "note": None})
    key = {"id": record["id"]}
    assert record["count"] == value
    assert adapter.describe(model).by_name["count"].format(record["count"]) == str(value)
    assert (await adapter.get(model, key))["note"] is None
    assert (await adapter.update(model, key, {"note": ""}))["note"] == ""
    assert (await adapter.update(model, key, {"note": None}))["note"] is None


def test_decimal_never_passes_through_binary_float():
    field = Field("amount", Decimal)
    for raw in ("12345678901234567890.12345678901234567890", "1e1000"):
        assert field.parse(field.format(field.parse(raw))) == Decimal(raw)


def test_tables_without_primary_keys_fail_explicitly():
    with pytest.raises(ValueError, match="no primary key"):
        ModelSchema("logs", (Field("message"),))


async def test_reflected_composite_foreign_key_and_trigger(tmp_path):
    from sqlalchemy import (
        Column,
        ForeignKeyConstraint,
        Integer,
        MetaData,
        String,
        Table,
        create_engine,
    )

    from quite_admin.adapters.sql import SQLAdapter

    engine = create_engine(f"sqlite:///{tmp_path}/composite.db")
    metadata = MetaData()
    Table(
        "parents",
        metadata,
        Column("tenant", String, primary_key=True),
        Column("code", String, primary_key=True),
    )
    Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tenant", String),
        Column("code", String),
        Column("name", String),
        ForeignKeyConstraint(["tenant", "code"], ["parents.tenant", "parents.code"]),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER normalize_name AFTER INSERT ON children BEGIN "
            "UPDATE children SET name = upper(NEW.name) WHERE id = NEW.id; END"
        )
    adapter = SQLAdapter(engine)
    try:
        tables = {table.name: table for table in await adapter.discover()}
        parent = await adapter.create(tables["parents"], {"tenant": "a", "code": "b/c"})
        other = await adapter.create(tables["parents"], {"tenant": "other", "code": "b/c"})
        relation = next(
            r for r in adapter.relations(tables["children"]) if r.target.name == "parents"
        )
        child = await adapter.save_relations(
            tables["children"], {"name": "hello"}, {relation.name: [parent]}
        )
        assert child["name"] == "HELLO"
        key = {"id": child["id"]}
        related = await adapter.related(tables["children"], relation.name, key, Query())
        assert related.records == [parent]
        await adapter.save_relations(tables["children"], {}, {relation.name: [other]}, key=key)
        assert (await adapter.get(tables["children"], key))["tenant"] == "other"
    finally:
        engine.dispose()


@pytest.mark.parametrize("reflection", [False, True])
async def test_hooks_triggers_cascades_and_failed_hook_rollback(tmp_path, reflection):
    from sqlalchemy import (
        ForeignKey,
        Integer,
        String,
        create_engine,
        event,
    )
    from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker

    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Item(Base):
        __tablename__ = "hook_items"
        id = mapped_column(Integer, primary_key=True)
        name = mapped_column(String)
        children = relationship("Child", cascade="all, delete-orphan")

    class Child(Base):
        __tablename__ = "hook_children"
        id = mapped_column(Integer, primary_key=True)
        item_id = mapped_column(ForeignKey("hook_items.id", ondelete="CASCADE"))

    @event.listens_for(Item, "before_insert")
    def on_insert(mapper, connection, item):
        item.name = "orm:" + item.name

    @event.listens_for(Item, "before_update")
    def on_update(mapper, connection, item):
        if item.name == "blocked":
            raise RuntimeError("Application hook rejected the operation")

    engine = create_engine(f"sqlite:///{tmp_path}/hooks.db")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER label_insert AFTER INSERT ON hook_items BEGIN "
            "UPDATE hook_items SET name = 'db:' || NEW.name WHERE id = NEW.id; END"
        )
    if reflection:
        adapter = SQLAdapter(engine)
        models = {table.name: table for table in await adapter.discover()}
        model, child_model = models["hook_items"], models["hook_children"]
    else:
        adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
        model, child_model = Item, Child
    commits = []
    event.listen(engine, "commit", lambda connection: commits.append(True))
    try:
        record = await adapter.create(model, {"name": "hello"})
        assert record["name"] == ("db:hello" if reflection else "db:orm:hello")
        key = {"id": record["id"]}
        commits.clear()
        assert await adapter.get(model, key) == record
        await adapter.list(model, Query())
        assert not commits
        if not reflection:
            with pytest.raises(RuntimeError, match="hook rejected"):
                await adapter.update(model, key, {"name": "blocked"})
            assert not commits
            assert await adapter.get(model, key) == record
        child = await adapter.create(child_model, {"item_id": record["id"]})
        await adapter.delete(model, key)
        assert await adapter.get(child_model, {"id": child["id"]}) is None
    finally:
        engine.dispose()
