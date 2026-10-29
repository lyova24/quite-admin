"""Run separately: GINO 1.x and SQLAlchemy 2.x cannot share an environment."""

import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest

pytest.importorskip("gino")

from gino import Gino  # noqa: E402

from quite_admin import PasswordAuth  # noqa: E402
from quite_admin.adapters.gino import GinoAdapter  # noqa: E402


@pytest.fixture
async def db():
    import asyncpg

    url = os.environ.get("QUITE_ADMIN_GINO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set QUITE_ADMIN_GINO_TEST_DATABASE_URL to a disposable local PostgreSQL DB.")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "postgres"} or parsed.path not in {
        "/quite_admin_gino_test",
        "/quite_admin_test",
    }:
        raise ValueError("GINO tests require a disposable local quite_admin[_gino]_test database.")
    schema = "gino_test_" + uuid4().hex
    connection = await asyncpg.connect(url)
    await connection.execute(f'CREATE SCHEMA "{schema}"')
    database = Gino()
    try:
        await database.set_bind(
            url, server_settings={"search_path": schema}, min_size=1, max_size=3
        )
        yield database
    finally:
        engine = database.pop_bind()
        if engine is not None:
            await engine.close()
        await connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await connection.close()


@pytest.fixture
async def backend(db):
    class Item(db.Model):
        __tablename__ = "items"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(120), nullable=False, unique=True)
        active = db.Column(db.Boolean, default=True, nullable=False, server_default="true")
        note = db.Column(db.String(200), nullable=True)
        internal = db.Column(db.String(100), default="hidden", server_default="hidden")
        count = db.Column(db.BigInteger, default=0, server_default="0")

    await db.gino.create_all()
    return GinoAdapter(db), Item


@pytest.fixture
async def related_backend(db):
    class Parent(db.Model):
        __tablename__ = "parents"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)

    class Child(db.Model):
        __tablename__ = "children"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        parent_id = db.Column(db.Integer, db.ForeignKey("parents.id"), nullable=True)

    class Profile(db.Model):
        __tablename__ = "profiles"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        parent_id = db.Column(
            db.Integer, db.ForeignKey("parents.id"), nullable=True, index=True, unique=True
        )

    class StrictChild(db.Model):
        __tablename__ = "strict_children"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
        parent_id = db.Column(db.Integer, db.ForeignKey("parents.id"), nullable=False)

    class Tag(db.Model):
        __tablename__ = "tags"
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)

    class Junction(db.Model):
        __tablename__ = "parent_tags"
        parent_id = db.Column(db.Integer, db.ForeignKey("parents.id"), primary_key=True)
        tag_id = db.Column(db.Integer, db.ForeignKey("tags.id"), primary_key=True)

    models = [Parent, Child, Profile, StrictChild, Tag, Junction]
    await db.gino.create_all()
    return GinoAdapter(db, models=models), {m.__tablename__: m for m in models}


@pytest.fixture
def auth():
    return PasswordAuth.single_user("admin", "correct horse battery staple")
