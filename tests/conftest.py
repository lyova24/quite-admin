from __future__ import annotations

from types import ModuleType

import peewee as pw
import pytest
from sqlalchemy import BigInteger, Boolean, String, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from tortoise import Tortoise, fields
from tortoise.models import Model

from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters.peewee import PeeweeAdapter
from quite_admin.adapters.sql import SQLAdapter
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from quite_admin.adapters.tortoise import TortoiseAdapter

from .databases import drop_tortoise_tables, peewee_database, sqlalchemy_url, tortoise_url


@pytest.fixture(params=["sqlalchemy", "sqlalchemy_async", "sql", "sql_async", "peewee", "tortoise"])
async def backend(request, tmp_path):
    name = request.param
    if name.startswith("sql"):

        class Base(DeclarativeBase):
            pass

        class Item(Base):
            __tablename__ = "items"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(120), unique=True)
            active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
            note: Mapped[str | None] = mapped_column(String(200), nullable=True)
            internal: Mapped[str] = mapped_column(
                String(100), default="hidden", server_default="hidden"
            )
            count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

        if name.endswith("async"):
            engine = create_async_engine(
                sqlalchemy_url(f"sqlite+aiosqlite:///{tmp_path}/db.sqlite3", asynchronous=True)
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine)
        else:
            engine = create_engine(sqlalchemy_url(f"sqlite:///{tmp_path}/db.sqlite3"))
            Base.metadata.create_all(engine)
            factory = sessionmaker(engine)
        if name in {"sql", "sql_async"}:
            adapter = SQLAdapter(engine)
            table = next(iter(await adapter.discover()))
            yield adapter, table
        else:
            adapter = SQLAlchemyAdapter(factory, base=Base)
            yield adapter, Item
        if name.endswith("async"):
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
            await engine.dispose()
        else:
            Base.metadata.drop_all(engine)
            engine.dispose()
    elif name == "peewee":
        database = peewee_database(
            pw.SqliteDatabase(str(tmp_path / "db.sqlite3"), pragmas={"foreign_keys": 1})
        )

        class Base(pw.Model):
            class Meta:
                database = None

        class Item(Base):
            name = pw.CharField(max_length=120, unique=True)
            active = pw.BooleanField(default=True)
            note = pw.CharField(max_length=200, null=True)
            internal = pw.CharField(max_length=100, default="hidden")
            count = pw.BigIntegerField(default=0)

            class Meta:
                table_name = "items"

        Item.bind(database)
        database.create_tables([Item])
        database.close()
        yield PeeweeAdapter(base=Base), Item
        with database.connection_context():
            database.drop_tables([Item])
    else:

        class Item(Model):
            name = fields.CharField(max_length=120, unique=True)
            active = fields.BooleanField(default=True)
            note = fields.CharField(max_length=200, null=True)
            internal = fields.CharField(max_length=100, default="hidden")
            count = fields.BigIntField(default=0)

            class Meta:
                table = "items"

        module = ModuleType("quite_test_models")
        module.__models__ = [Item]
        await Tortoise.init(db_url=tortoise_url(), modules={"models": [module]})
        await Tortoise.generate_schemas()
        yield TortoiseAdapter(), Item
        await Tortoise.close_connections()
        drop_tortoise_tables(module.__models__)


@pytest.fixture(scope="session")
def auth():
    return PasswordAuth.single_user("admin", "correct horse battery staple")


@pytest.fixture
def admin(backend, auth):
    adapter, model = backend
    instance = Admin(auth=auth, secret_key="s" * 48, adapters=[adapter], secure_cookies=False)
    instance.register(
        model,
        options=ModelOptions(
            exclude=("internal",),
            readonly_fields=("count",),
            search_fields=("name",),
        ),
    )
    return instance
