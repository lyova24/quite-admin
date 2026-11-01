"""Compile the native GINO paths without requiring a running PostgreSQL server."""

from contextlib import asynccontextmanager

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
