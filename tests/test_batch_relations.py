import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, event

from quite_admin import Admin, PasswordAuth, Query, RelatedFilter
from quite_admin.relations import BatchRelationAdapter

from .helpers import login
from .test_relations import key, related_backend, relation_to, seed  # noqa: F401


async def test_batched_relationships_match_individual_reads_and_report_truncation(related_backend):  # noqa: F811
    adapter, models = related_backend
    assert isinstance(adapter, BatchRelationAdapter)
    parent, child, profile, tags = await seed(adapter, models)
    source = models["parents"]
    selections = {}
    for target, kind, records in (
        (models["children"], "one_to_many", [child]),
        (models["profiles"], "one_to_one", [profile]),
        (models["tags"], "many_to_many", tags),
    ):
        relation = relation_to(adapter, source, target, kind)
        selections[relation.name] = [key(adapter, target, record) for record in records]
    await adapter.save_relations(source, {}, selections, key=key(adapter, source, parent))
    await adapter.create(source, {"name": "No links"})
    tag_relation = relation_to(adapter, source, models["tags"], "many_to_many")
    filtered = Query(
        limit=1, related=(RelatedFilter(tag_relation.name, key(adapter, models["tags"], tags[0])),)
    )
    assert (await adapter.list_window(source, filtered)).records == (
        await adapter.list(source, filtered)
    ).records
    for model in models.values():
        records = (await adapter.list(model, Query(limit=10))).records
        keys = [key(adapter, model, record) for record in records]
        for relation in adapter.relations(model):
            batch = await adapter.related_batch(model, relation.name, keys)
            assert not batch.truncated
            for record, source_key in zip(records, keys, strict=True):
                expected = await adapter.related(
                    model, relation.name, source_key, Query(limit=1000)
                )
                token = adapter.describe(model).record_key(record)
                assert batch.records[token] == expected.records
            if "name" in adapter.describe(relation.target).by_name:
                projected = await adapter.related_batch(
                    model, relation.name, keys, columns=("name",)
                )
                assert projected.records == {
                    token: [{"name": item["name"]} for item in items]
                    for token, items in batch.records.items()
                }
            assert not (await adapter.related_batch(model, relation.name, [])).records
            limited = await adapter.related_batch(model, relation.name, keys, limit=1)
            assert limited.truncated == bool(any(batch.records.values()))
    with pytest.raises(ValueError):
        await adapter.related_batch(source, "missing", [], limit=0)
    with pytest.raises(ValueError):
        await adapter.related_batch(source, "missing", [])


async def test_export_uses_one_join_per_relation_instead_of_per_record_queries(
    tmp_path, monkeypatch
):
    from quite_admin.adapters.sql import SQLAdapter

    engine = create_engine(f"sqlite:///{tmp_path}/batch.db")
    metadata = MetaData()
    parent = Table(
        "parents", metadata, Column("id", Integer, primary_key=True), Column("name", String)
    )
    child = Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("parent_id", ForeignKey("parents.id")),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            parent.insert(), [{"id": i, "name": f"Parent {i}"} for i in range(1, 21)]
        )
        connection.execute(
            child.insert(), [{"id": i, "name": f"Child {i}", "parent_id": i} for i in range(1, 21)]
        )
    adapter = SQLAdapter(engine)
    models = {table.name: table for table in await adapter.discover()}
    relation = relation_to(adapter, models["parents"], models["children"], "one_to_many")
    admin = Admin(
        auth=PasswordAuth.single_user("admin", "correct horse battery staple"),
        secret_key="s" * 32,
        adapters=[adapter],
        secure_cookies=False,
    )
    host = FastAPI()
    admin.mount_fastapi(host)
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
            await login(client)
            response = await client.get(
                "/admin/models/parents/",
                params=[
                    ("export", "csv"),
                    ("columns", "name"),
                    ("columns", relation.name + ".name"),
                ],
            )
            assert response.status_code == 200
            assert "Child 20" in response.text
            assert len(statements) == 3  # source count, source rows, one bounded join
            from quite_admin import exports

            monkeypatch.setattr(exports, "MAX_LINKS", 1)
            response = await client.get(
                "/admin/models/parents/",
                params=[("export", "csv"), ("columns", relation.name + ".name")],
            )
            assert response.status_code == 413
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        engine.dispose()


@pytest.mark.parametrize("reflection", [False, True])
async def test_batch_join_preserves_composite_and_self_referencing_keys(tmp_path, reflection):
    from sqlalchemy import ForeignKeyConstraint
    from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker

    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Node(Base):
        __tablename__ = "nodes"
        tenant = mapped_column(String, primary_key=True)
        code = mapped_column(String, primary_key=True)
        parent_tenant = mapped_column(String, nullable=True)
        parent_code = mapped_column(String, nullable=True)
        __table_args__ = (
            ForeignKeyConstraint(["parent_tenant", "parent_code"], ["nodes.tenant", "nodes.code"]),
        )
        parent = relationship("Node", remote_side=[tenant, code], back_populates="children")
        children = relationship("Node", back_populates="parent")

    engine = create_engine(f"sqlite:///{tmp_path}/composite.db")
    Base.metadata.create_all(engine)
    adapter = (
        SQLAdapter(engine) if reflection else SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    )
    model = next(iter(await adapter.discover())) if reflection else Node
    try:
        await adapter.create(model, {"tenant": "one", "code": "parent"})
        await adapter.create(model, {"tenant": "two", "code": "parent"})
        await adapter.create(
            model,
            {"tenant": "one", "code": "child", "parent_tenant": "one", "parent_code": "parent"},
        )
        records = (await adapter.list(model, Query())).records
        keys = [key(adapter, model, record) for record in records]
        for relation in adapter.relations(model):
            batch = await adapter.related_batch(model, relation.name, keys)
            for record, source_key in zip(records, keys, strict=True):
                expected = await adapter.related(model, relation.name, source_key, Query())
                assert batch.records[adapter.describe(model).record_key(record)] == expected.records
    finally:
        engine.dispose()
