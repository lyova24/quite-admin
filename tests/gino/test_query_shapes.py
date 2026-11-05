"""Compile the native GINO paths without requiring a running PostgreSQL server."""

from contextlib import asynccontextmanager
from datetime import UTC

import pytest
from gino import Gino
from sqlalchemy.dialects import postgresql

from quite_admin import Query
from quite_admin.adapters.gino import GinoAdapter


async def test_projected_window_and_batch_compile_with_legacy_sqlalchemy():
    db = Gino()

    class Parent(db.Model):
        __tablename__ = "parents"
        id = db.Column("parent_key", db.Integer, primary_key=True)
        name = db.Column(db.String)

    class Child(db.Model):
        __tablename__ = "children"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String)
        parent_id = db.Column(db.Integer, db.ForeignKey("parents.parent_key"))

    statements = []

    class Connection:
        async def scalar(self, statement):
            pytest.fail("Window and batch reads must not count records")

        async def all(self, statement):
            compiled = statement.compile(dialect=postgresql.dialect())
            statements.append((str(compiled), compiled.params))
            if "qa_parent_0" in str(compiled):
                return [{"qa_parent_0": 1, "qa_target_0": 10, "qa_target_1": "Child"}]
            return [{"id": 2, "name": "Second"}]

    @asynccontextmanager
    async def acquire(**kwargs):
        yield Connection()

    db.acquire = acquire
    adapter = GinoAdapter(db, models=[Parent, Child])
    window = await adapter.list_window(
        Parent, Query(limit=1, columns=("id", "name")), after={"id": 1}
    )
    assert window.records == [{"id": 2, "name": "Second"}]
    assert "parents.parent_key >" in statements[0][0]
    assert "AS id" in statements[0][0]
    relation = next(item for item in adapter.relations(Parent) if item.target is Child)
    batch = await adapter.related_batch(Parent, relation.name, [{"id": 1}], columns=("name",))
    token = adapter.describe(Parent).record_key({"id": 1})
    assert batch.records[token] == [{"name": "Child"}]
    assert "JOIN children" in statements[-1][0]


async def test_timestamp_and_uuid_window_compiles_without_count_or_offset():
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    db = Gino()

    class Link(db.Model):
        __tablename__ = "links"
        id = db.Column(PGUUID(as_uuid=False), primary_key=True)
        created_at = db.Column(db.DateTime(timezone=True), nullable=False)

    statements = []
    moment = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    ids = [UUID(int=index) for index in range(1, 4)]

    class Connection:
        async def scalar(self, statement):
            pytest.fail("Sorted keyset reads must not count records")

        async def all(self, statement):
            compiled = statement.compile(dialect=postgresql.dialect())
            statements.append((str(compiled), compiled.params))
            return [{"id": key, "created_at": moment} for key in ids[1:]]

    @asynccontextmanager
    async def acquire(**kwargs):
        yield Connection()

    db.acquire = acquire
    adapter = GinoAdapter(db, models=[Link])
    result = await adapter.list_window(
        Link,
        Query(limit=1, order_by="created_at", descending=True, columns=("id", "created_at")),
        after={"id": ids[0], "created_at": moment},
    )
    assert result.next_key == {"id": ids[1], "created_at": moment}
    sql = statements[0][0]
    assert "links.created_at <" in sql and "links.created_at =" in sql
    assert "links.id >" in sql
    assert "ORDER BY links.created_at DESC, links.id ASC" in sql
    assert "count(" not in sql.lower() and "OFFSET" not in sql
