import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, Filter, ModelOptions, Query, RelationAdapter
from quite_admin.errors import Conflict

from .helpers import csrf, login, revision


@pytest.fixture(params=["sqlalchemy", "sqlalchemy_async", "sql", "sql_async", "peewee", "tortoise"])
async def related_backend(request, tmp_path):
    from types import ModuleType

    import peewee as pw
    from sqlalchemy import Column, ForeignKey, Integer, String, Table, create_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker
    from tortoise import Tortoise, fields
    from tortoise.models import Model

    from quite_admin.adapters.peewee import PeeweeAdapter
    from quite_admin.adapters.sql import SQLAdapter
    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
    from quite_admin.adapters.tortoise import TortoiseAdapter

    from .databases import drop_tortoise_tables, peewee_database, sqlalchemy_url, tortoise_url

    mode = request.param
    if mode.startswith("sql"):

        class Base(DeclarativeBase):
            pass

        junction = Table(
            "parent_tags",
            Base.metadata,
            Column("parent_id", ForeignKey("parents.id"), primary_key=True),
            Column("tag_id", ForeignKey("tags.id"), primary_key=True),
        )

        class Parent(Base):
            __tablename__ = "parents"
            id = mapped_column(Integer, primary_key=True)
            name = mapped_column(String(100))
            children = relationship("Child", back_populates="parent")
            profile = relationship("Profile", uselist=False)
            strict_children = relationship("StrictChild")
            tags = relationship("Tag", secondary=junction)

        class Child(Base):
            __tablename__ = "children"
            id = mapped_column(Integer, primary_key=True)
            name = mapped_column(String(100))
            parent_id = mapped_column(ForeignKey("parents.id"), nullable=True)
            parent = relationship(Parent, back_populates="children")

        class Profile(Base):
            __tablename__ = "profiles"
            id = mapped_column(Integer, primary_key=True)
            name = mapped_column(String(100))
            parent_id = mapped_column(
                ForeignKey("parents.id"), nullable=True, unique=True, index=True
            )

        class StrictChild(Base):
            __tablename__ = "strict_children"
            id = mapped_column(Integer, primary_key=True)
            name = mapped_column(String(100))
            parent_id = mapped_column(ForeignKey("parents.id"), nullable=False)

        class Tag(Base):
            __tablename__ = "tags"
            id = mapped_column(Integer, primary_key=True)
            name = mapped_column(String(100))

        if mode.endswith("async"):
            engine = create_async_engine(
                sqlalchemy_url(f"sqlite+aiosqlite:///{tmp_path}/relations.db", asynchronous=True)
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine)
        else:
            engine = create_engine(sqlalchemy_url(f"sqlite:///{tmp_path}/relations.db"))
            Base.metadata.create_all(engine)
            factory = sessionmaker(engine)
        if mode in {"sql", "sql_async"}:
            adapter = SQLAdapter(engine)
            models = {adapter.describe(table).name: table for table in await adapter.discover()}
        else:
            adapter = SQLAlchemyAdapter(factory, base=Base)
            models = {model.__tablename__: model for model in adapter.discover()}
        yield adapter, models
        if mode.endswith("async"):
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
            await engine.dispose()
        else:
            Base.metadata.drop_all(engine)
            engine.dispose()
    elif mode == "peewee":
        db = peewee_database(
            pw.SqliteDatabase(str(tmp_path / "relations.db"), pragmas={"foreign_keys": 1})
        )

        class Base(pw.Model):
            class Meta:
                database = db

        class Tag(Base):
            name = pw.CharField()

            class Meta:
                table_name = "tags"

        class Parent(Base):
            name = pw.CharField()
            tags = pw.ManyToManyField(Tag, backref="parents")

            class Meta:
                table_name = "parents"

        class Child(Base):
            name = pw.CharField()
            parent = pw.ForeignKeyField(Parent, null=True, backref="children")

            class Meta:
                table_name = "children"

        class Profile(Base):
            name = pw.CharField()
            parent = pw.ForeignKeyField(Parent, null=True, unique=True, backref="profile")

            class Meta:
                table_name = "profiles"

        class StrictChild(Base):
            name = pw.CharField()
            parent = pw.ForeignKeyField(Parent, backref="strict_children")

            class Meta:
                table_name = "strict_children"

        all_models = [Parent, Child, Tag, Profile, StrictChild, Parent.tags.get_through_model()]
        db.create_tables(all_models)
        db.close()
        yield PeeweeAdapter(models=all_models), {m._meta.table_name: m for m in all_models}
        with db.connection_context():
            db.drop_tables(all_models)
    else:

        class Parent(Model):
            name = fields.CharField(max_length=100)
            tags = fields.ManyToManyField("models.Tag", related_name="parents")

            class Meta:
                table = "parents"

        class Tag(Model):
            name = fields.CharField(max_length=100)

            class Meta:
                table = "tags"

        class Child(Model):
            name = fields.CharField(max_length=100)
            parent = fields.ForeignKeyField("models.Parent", null=True, related_name="children")

            class Meta:
                table = "children"

        class Profile(Model):
            name = fields.CharField(max_length=100)
            parent = fields.OneToOneField("models.Parent", null=True, related_name="profile")

            class Meta:
                table = "profiles"

        class StrictChild(Model):
            name = fields.CharField(max_length=100)
            parent = fields.ForeignKeyField("models.Parent", related_name="strict_children")

            class Meta:
                table = "strict_children"

        module = ModuleType("related_models")
        module.__models__ = [Parent, Child, Tag, Profile, StrictChild]
        await Tortoise.init(db_url=tortoise_url(), modules={"models": [module]})
        await Tortoise.generate_schemas()
        try:
            yield TortoiseAdapter(), {m._meta.db_table: m for m in module.__models__}
        finally:
            await Tortoise.close_connections()
            drop_tortoise_tables(module.__models__)


def key(adapter, model, row):
    schema = adapter.describe(model)
    return schema.parse_key(schema.record_key(row))


def relation_to(adapter, source, target, kind):
    return next(r for r in adapter.relations(source) if r.target is target and r.kind == kind)


@pytest.mark.parametrize("index_kind", ["unique", "composite", "nonunique", "partial"])
def test_reflected_relationship_cardinality_respects_index_scope(index_kind):
    from sqlalchemy import (
        Column,
        ForeignKey,
        Index,
        Integer,
        MetaData,
        String,
        Table,
        create_engine,
    )

    from quite_admin.adapters.sql import SQLAdapter

    metadata = MetaData()
    parent = Table("parents", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", ForeignKey("parents.id")),
        Column("name", String),
    )
    Index(
        "child_parent",
        child.c.parent_id,
        *([child.c.name] if index_kind == "composite" else []),
        unique=index_kind != "nonunique",
        **({"sqlite_where": child.c.name == "selected"} if index_kind == "partial" else {}),
    )
    adapter = SQLAdapter(create_engine("sqlite://"))
    expected = "one_to_one" if index_kind == "unique" else "one_to_many"
    relation_to(adapter, parent, child, expected)
    relation_to(adapter, child, parent, "one_to_one" if expected == "one_to_one" else "many_to_one")


async def seed(adapter, models):
    parent = await adapter.create(models["parents"], {"name": "Before"})
    child = await adapter.create(models["children"], {"name": "A child"})
    profile = await adapter.create(models["profiles"], {"name": "A profile"})
    tags = [await adapter.create(models["tags"], {"name": name}) for name in ("Red", "Blue")]
    return parent, child, profile, tags


async def test_relationship_contract_and_atomic_rollback(related_backend):
    adapter, models = related_backend
    assert isinstance(adapter, RelationAdapter)
    parent, child, profile, tags = await seed(adapter, models)
    model = models["parents"]
    parent_key = key(adapter, model, parent)
    children = relation_to(adapter, model, models["children"], "one_to_many")
    tag_relation = relation_to(adapter, model, models["tags"], "many_to_many")
    profile_relation = relation_to(adapter, model, models["profiles"], "one_to_one")
    saved = await adapter.save_relations(
        model,
        {"name": "After"},
        {
            children.name: [key(adapter, models["children"], child)],
            tag_relation.name: [key(adapter, models["tags"], tag) for tag in tags],
            profile_relation.name: [key(adapter, models["profiles"], profile)],
        },
        key=parent_key,
    )
    assert saved["name"] == "After"
    for relation, count in ((children, 1), (tag_relation, 2), (profile_relation, 1)):
        assert (await adapter.related(model, relation.name, parent_key, Query())).total == count
    replacement = await adapter.create(models["profiles"], {"name": "Replacement"})
    for row in (replacement, profile):
        await adapter.save_relations(
            model,
            {},
            {profile_relation.name: [key(adapter, models["profiles"], row)]},
            key=parent_key,
        )
    required_field = next(
        f for f in adapter.describe(models["strict_children"]).fields if f.foreign_key
    )
    strict = await adapter.create(
        models["strict_children"], {"name": "Required", required_field.name: parent["id"]}
    )
    required = relation_to(adapter, model, models["strict_children"], "one_to_many")
    with pytest.raises(Conflict):
        await adapter.save_relations(
            model, {"name": "MUST ROLL BACK"}, {required.name: []}, key=parent_key
        )
    assert (await adapter.get(model, parent_key))["name"] == "After"
    assert await adapter.get(
        models["strict_children"], key(adapter, models["strict_children"], strict)
    )
    await adapter.save_relations(
        model,
        {},
        {children.name: [], tag_relation.name: [], profile_relation.name: []},
        key=parent_key,
    )
    for relation in (children, tag_relation, profile_relation):
        assert (await adapter.related(model, relation.name, parent_key, Query())).total == 0
    assert await adapter.get(models["children"], key(adapter, models["children"], child))
    assert await adapter.get(models["tags"], key(adapter, models["tags"], tags[0]))


async def test_create_with_forward_and_collection_relationships(related_backend):
    adapter, models = related_backend
    parent, child, profile, tags = await seed(adapter, models)
    parent_model = models["parents"]
    tags_relation = relation_to(adapter, parent_model, models["tags"], "many_to_many")
    created = await adapter.save_relations(
        parent_model,
        {"name": "New with tags"},
        {tags_relation.name: [key(adapter, models["tags"], tags[0])]},
    )
    parent_key = key(adapter, parent_model, created)
    assert (await adapter.related(parent_model, tags_relation.name, parent_key, Query())).total == 1
    child_model = models["children"]
    forward = relation_to(adapter, child_model, parent_model, "many_to_one")
    new_child = await adapter.save_relations(
        child_model, {"name": "New child"}, {forward.name: [parent_key]}
    )
    related = await adapter.related(
        child_model, forward.name, key(adapter, child_model, new_child), Query()
    )
    assert related.records[0]["id"] == created["id"]


async def test_related_queries_share_filter_sort_and_projection_contract(related_backend):
    adapter, models = related_backend
    parent, child, profile, tags = await seed(adapter, models)
    model = models["parents"]
    relation = relation_to(adapter, model, models["tags"], "many_to_many")
    parent_key = key(adapter, model, parent)
    await adapter.save_relations(
        model,
        {},
        {relation.name: [key(adapter, models["tags"], tag) for tag in tags]},
        key=parent_key,
    )
    result = await adapter.related(
        model, relation.name, parent_key, Query(order_by="name", columns=("name",), limit=1)
    )
    assert result.total == 2
    assert result.records == [{"name": "Blue"}]
    result = await adapter.related(
        model,
        relation.name,
        parent_key,
        Query(filters=(Filter("name", "eq", "Red"),), columns=("name",)),
    )
    assert result.total == 1
    assert result.records == [{"name": "Red"}]


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_inline_relationship_fields_share_the_record_save(auth, related_backend, framework):
    adapter, models = related_backend
    parent, child, profile, tags = await seed(adapter, models)
    model = models["parents"]
    children = relation_to(adapter, model, models["children"], "one_to_many")
    tag_relation = relation_to(adapter, model, models["tags"], "many_to_many")
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        token = adapter.describe(model).record_key(parent)
        path = f"/admin/models/parents/{token}"
        form = await client.get(path)
        assert form.status_code == 200, form.text
        assert f'name="__relation__{tag_relation.name}"' in form.text
        assert "Red" in form.text and "A child" in form.text
        response = await client.post(
            path,
            data={
                "__csrf": csrf(form),
                "__revision": revision(form),
                "name": "Changed together",
                "__relation_present__" + children.name: "true",
                "__relation__" + children.name: adapter.describe(models["children"]).record_key(
                    child
                ),
                "__relation_present__" + tag_relation.name: "true",
                "__relation__" + tag_relation.name: [
                    adapter.describe(models["tags"]).record_key(tag) for tag in tags
                ],
            },
        )
        assert response.status_code == 303, response.text
        assert (await adapter.get(model, key(adapter, model, parent)))["name"] == "Changed together"
        assert (
            await adapter.related(model, tag_relation.name, key(adapter, model, parent), Query())
        ).total == 2
        child_model = models["children"]
        forward = relation_to(adapter, child_model, model, "many_to_one")
        create_form = await client.get("/admin/models/children/new")
        assert f'name="__relation__{forward.name}"' in create_form.text
        assert f'name="{forward.source_fields[0]}"' not in create_form.text
        created_child = await client.post(
            "/admin/models/children/new",
            data={
                "__csrf": csrf(create_form),
                "name": "Created through the same form",
                "__relation_present__" + forward.name: "true",
                "__relation__" + forward.name: token,
            },
        )
        assert created_child.status_code == 303, created_child.text
        admin.configure("parents", options=ModelOptions(readonly_relations=(tag_relation.name,)))
        rejected = await client.post(
            path,
            data={
                "__csrf": csrf(form),
                "name": "Forbidden mutation",
                "__relation_present__" + tag_relation.name: "true",
            },
        )
        assert rejected.status_code == 422
        assert (await adapter.get(model, key(adapter, model, parent)))["name"] == "Changed together"


@pytest.mark.parametrize(
    "kind,target_name",
    [("one_to_many", "children"), ("one_to_one", "profiles"), ("many_to_many", "tags")],
)
async def test_checked_relationship_changes_are_atomic(related_backend, kind, target_name):
    from quite_admin import WriteGuard
    from quite_admin.concurrency import StaleRecord
    from tests.test_concurrency import fingerprint

    adapter, models = related_backend
    parent, child, profile, tags = await seed(adapter, models)
    model, target = models["parents"], models[target_name]
    relation = relation_to(adapter, model, target, kind)
    parent_key = key(adapter, model, parent)
    fields = tuple(f.name for f in adapter.describe(model).fields if f.kind != "unsupported")
    guard = WriteGuard(
        fingerprint({name: parent[name] for name in fields}),
        {relation.name: fingerprint([])},
        fields,
        fingerprint,
    )
    selected = {"children": child, "profiles": profile, "tags": tags[0]}[target_name]
    await adapter.save_relations(
        model, {}, {relation.name: [key(adapter, target, selected)]}, key=parent_key
    )
    with pytest.raises(StaleRecord):
        await adapter.save_checked(
            model, parent_key, {"name": "Must roll back"}, {relation.name: []}, guard=guard
        )
    assert (await adapter.get(model, parent_key))["name"] == parent["name"]
    assert (await adapter.related(model, relation.name, parent_key, Query())).total == 1
    current = await adapter.get(model, parent_key)
    guard = WriteGuard(
        fingerprint({name: current[name] for name in fields}),
        {relation.name: fingerprint([adapter.describe(target).record_key(selected)])},
        fields,
        fingerprint,
    )
    saved = await adapter.save_checked(
        model, parent_key, {"name": "Accepted"}, {relation.name: []}, guard=guard
    )
    assert saved["name"] == "Accepted"
    assert (await adapter.related(model, relation.name, parent_key, Query())).total == 0
