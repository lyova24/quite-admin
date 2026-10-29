import base64
import hashlib
import html
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, ModelOptions
from quite_admin.diagram import schema_graph

from . import test_relations
from .helpers import login

related_backend = test_relations.related_backend


def graph_data(response):
    return json.loads(html.unescape(re.search(r"data-graph='([^']+)'", response.text).group(1)))


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_schema_uses_metadata_with_visible_fields_and_expandable_junctions(
    auth, related_backend, framework
):
    adapter, models = related_backend
    await adapter.create(models["parents"], {"name": "Record values must never enter the graph"})
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host, path="/tools/admin")
    else:
        admin.mount_litestar(host, path="/tools/admin")

    async def no_records(*args, **kwargs):
        raise AssertionError("The diagram must not load records.")

    adapter.list = no_records
    adapter.get = no_records
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        path = "/tools/admin/schema"
        assert (await client.get(path)).status_code == 303
        await login(client, "/tools/admin")
        response = await client.get(path)
        assert response.status_code == 200, response.text
        graph = graph_data(response)
        assert {node["id"] for node in graph["nodes"]} == set((await admin.resources()).keys())
        assert "Record values must never enter" not in response.text
        assert {edge["kind"] for edge in graph["edges"]} == {"o2o", "o2m", "m2m"}
        assert all(node["url"].startswith("/tools/admin/models/") for node in graph["nodes"])
        relation = next(edge for edge in graph["edges"] if edge["kind"] == "m2m")
        catalog = {node["id"]: node for node in graph["nodes"] + graph["junctions"]}
        junction = catalog[relation["junction"]]
        assert set(relation["junctionSourceFields"] + relation["junctionTargetFields"]) <= {
            field["name"] for field in junction["fields"]
        }
        assert all(
            field["linked"]
            for field in junction["fields"]
            if field["name"] in relation["junctionSourceFields"] + relation["junctionTargetFields"]
        )
        digest = (
            "sha256-"
            + base64.b64encode(
                hashlib.sha256(
                    (Path(__file__).parents[1] / "src/quite_admin/static/schema.js").read_bytes()
                ).digest()
            ).decode()
        )
        assert f'integrity="{digest}"' in response.text
        assert f"script-src '{digest}'" in response.headers["content-security-policy"]
        assert "unsafe-inline" not in response.headers["content-security-policy"]
        assert "data-schema-show-all" in response.text and "data-schema-hide-all" in response.text
        assert 'aria-current="page">Database schema' in response.text
        admin.configure(
            "tags", options=ModelOptions(permission=lambda r, i, action: action != "view")
        )
        hidden = graph_data(await client.get(path))
        assert "tags" not in {node["id"] for node in hidden["nodes"]}
        assert all(edge["kind"] != "m2m" for edge in hidden["edges"])
        admin.configure("tags", options=ModelOptions())
        foreign = next(
            field.name for field in adapter.describe(models["children"]).fields if field.foreign_key
        )
        admin.configure("children", options=ModelOptions(exclude=(foreign,)))
        hidden = graph_data(await client.get(path))
        assert foreign not in {
            field["name"]
            for node in hidden["nodes"]
            if node["id"] == "children"
            for field in node["fields"]
        }
        assert not any(
            edge["source"] == "children" or edge["target"] == "children" for edge in hidden["edges"]
        )
        # A registered restricted junction cannot be rediscovered as a synthetic table.
        if not junction["junction"]:
            admin.configure(
                junction["id"], options=ModelOptions(permission=lambda r, i, action: False)
            )
            hidden = graph_data(await client.get(path))
            assert relation["junction"] not in {
                node["id"] for node in hidden["nodes"] + hidden["junctions"]
            }
            assert not next(edge for edge in hidden["edges"] if edge["kind"] == "m2m").get(
                "junction"
            )


async def test_physical_foreign_keys_without_orm_relationships_and_unique_targets(auth, tmp_path):
    from sqlalchemy import ForeignKey, Integer, String, create_engine
    from sqlalchemy.orm import DeclarativeBase, mapped_column, sessionmaker

    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Owner(Base):
        __tablename__ = "owners"
        id = mapped_column(Integer, primary_key=True)
        code = mapped_column(String(40), unique=True)
        password_hash = mapped_column(String(100))

    class Child(Base):
        __tablename__ = "children"
        id = mapped_column(Integer, primary_key=True)
        owner_code = mapped_column("owner_db_column", ForeignKey("owners.code"), unique=True)

    engine = create_engine(f"sqlite:///{tmp_path}/metadata.db")
    adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter])
    graph = await schema_graph((await admin.resources()).values())
    assert len(graph["edges"]) == 1 and graph["edges"][0]["kind"] == "o2o"
    owners = next(node for node in graph["nodes"] if node["id"] == "owners")
    assert not any(field["name"] == "password_hash" for field in owners["fields"])
    assert next(field for field in owners["fields"] if field["name"] == "code")["linked"]
    edge = graph["edges"][0]
    assert "owner_code" in edge["sourceFields"] + edge["targetFields"]
    engine.dispose()


async def test_m2m_junction_without_a_primary_key_is_still_described(auth, tmp_path):
    from sqlalchemy import Column, ForeignKey, Integer, String, Table, create_engine
    from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker

    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    through = Table(
        "links",
        Base.metadata,
        Column("left_id", ForeignKey("lefts.id")),
        Column("right_id", ForeignKey("rights.id")),
        Column("note", String),
        Column("api_token", String),
    )

    class Left(Base):
        __tablename__ = "lefts"
        id = mapped_column(Integer, primary_key=True)
        rights = relationship("Right", secondary=through)

    class Right(Base):
        __tablename__ = "rights"
        id = mapped_column(Integer, primary_key=True)

    engine = create_engine(f"sqlite:///{tmp_path}/metadata.db")
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[SQLAlchemyAdapter(sessionmaker(engine), base=Base)],
    )
    graph = await schema_graph((await admin.resources()).values())
    junction = graph["junctions"][0]
    assert {field["name"] for field in junction["fields"]} == {"left_id", "right_id", "note"}
    assert not any(field["pk"] for field in junction["fields"])
    assert next(field for field in junction["fields"] if field["name"] == "note")["linked"] is False
    engine.dispose()


async def test_mapped_junction_aliases_respect_registered_field_policy(auth, tmp_path):
    from sqlalchemy import ForeignKey, Integer, String, create_engine
    from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, sessionmaker

    from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter

    class Base(DeclarativeBase):
        pass

    class Association(Base):
        __tablename__ = "associations"
        left_id = mapped_column("db_left", ForeignKey("lefts.id"), primary_key=True)
        right_id = mapped_column("db_right", ForeignKey("rights.id"), primary_key=True)
        note = mapped_column(String)

    class Left(Base):
        __tablename__ = "lefts"
        id = mapped_column(Integer, primary_key=True)
        rights = relationship("Right", secondary=Association.__table__)

    class Right(Base):
        __tablename__ = "rights"
        id = mapped_column(Integer, primary_key=True)

    engine = create_engine(f"sqlite:///{tmp_path}/metadata.db")
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[SQLAlchemyAdapter(sessionmaker(engine), base=Base)],
    )
    resources = tuple((await admin.resources()).values())
    graph = await schema_graph(resources)
    relation = next(edge for edge in graph["edges"] if edge["kind"] == "m2m")
    assert relation["junction"] == "associations"
    assert relation["junctionSourceFields"] == ("left_id",)
    assert relation["junctionTargetFields"] == ("right_id",)
    admin.configure("associations", options=ModelOptions(exclude=("left_id",)))
    hidden = await schema_graph((await admin.resources()).values())
    assert not next(edge for edge in hidden["edges"] if edge["kind"] == "m2m").get("junction")
    engine.dispose()
