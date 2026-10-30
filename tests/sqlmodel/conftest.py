"""Real SQLModel table/relationship mappings, isolated from the global SQLModel registry."""

import pytest
from sqlalchemy import BigInteger, Column, String, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import registry, sessionmaker
from sqlmodel import Field, Relationship, SQLModel

from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from tests.databases import sqlalchemy_url


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def async_mode(request):
    return request.param


@pytest.fixture
async def sqlmodel_factory(async_mode, tmp_path):
    async def build(base):
        if async_mode:
            engine = create_async_engine(
                sqlalchemy_url(f"sqlite+aiosqlite:///{tmp_path}/sqlmodel.db", asynchronous=True)
            )
            engines.append((engine, base))
            async with engine.begin() as connection:
                await connection.run_sync(base.metadata.create_all)
            factory = async_sessionmaker(engine)
        else:
            engine = create_engine(sqlalchemy_url(f"sqlite:///{tmp_path}/sqlmodel.db"))
            engines.append((engine, base))
            base.metadata.create_all(engine)
            factory = sessionmaker(engine)
        return SQLAlchemyAdapter(factory, base=base)

    engines = []
    yield build
    for engine, base in engines:
        if async_mode:
            async with engine.begin() as connection:
                await connection.run_sync(base.metadata.drop_all)
            await engine.dispose()
        else:
            base.metadata.drop_all(engine)
            engine.dispose()
        base._sa_registry.dispose()


@pytest.fixture
async def backend(sqlmodel_factory):
    class Base(SQLModel, registry=registry()):
        pass

    class Item(Base, table=True):
        __tablename__ = "items"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(sa_column=Column(String(120), nullable=False, unique=True))
        active: bool = Field(default=True)
        note: str | None = Field(default=None, max_length=200)
        internal: str = Field(default="hidden", max_length=100)
        count: int = Field(default=0, sa_type=BigInteger)

    return await sqlmodel_factory(Base), Item


@pytest.fixture
async def related_backend(sqlmodel_factory):
    class Base(SQLModel, registry=registry()):
        pass

    class Junction(Base, table=True):
        __tablename__ = "parent_tags"
        parent_id: int = Field(foreign_key="parents.id", primary_key=True)
        tag_id: int = Field(foreign_key="tags.id", primary_key=True)

    class Parent(Base, table=True):
        __tablename__ = "parents"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)
        children: list["Child"] = Relationship(back_populates="parent")
        profile: "Profile" = Relationship(sa_relationship_kwargs={"uselist": False})
        strict_children: list["StrictChild"] = Relationship()
        tags: list["Tag"] = Relationship(link_model=Junction)

    class Child(Base, table=True):
        __tablename__ = "children"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)
        parent_id: int | None = Field(default=None, foreign_key="parents.id")
        parent: Parent | None = Relationship(back_populates="children")

    class Profile(Base, table=True):
        __tablename__ = "profiles"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)
        parent_id: int | None = Field(default=None, foreign_key="parents.id", unique=True)

    class StrictChild(Base, table=True):
        __tablename__ = "strict_children"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)
        parent_id: int = Field(foreign_key="parents.id")

    class Tag(Base, table=True):
        __tablename__ = "tags"
        id: int | None = Field(default=None, primary_key=True)
        name: str = Field(max_length=100)

    models = (Parent, Child, Profile, StrictChild, Tag, Junction)
    return await sqlmodel_factory(Base), {model.__tablename__: model for model in models}
