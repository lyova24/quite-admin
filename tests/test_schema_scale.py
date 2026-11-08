from sqlalchemy import Column, Integer, MetaData, Table, create_engine

from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters._sql_metadata import SQLRelationMetadata
from quite_admin.adapters.sql import SQLAdapter
from quite_admin.diagram import schema_graph


async def test_relation_snapshot_is_reused_and_refresh_tracks_fk_and_unique_changes(
    tmp_path, monkeypatch
):
    auth = PasswordAuth.single_user("admin", "schema-scale-test-password")
    engine = create_engine(f"sqlite:///{tmp_path}/schema-scale.db")
    metadata = MetaData()
    Table("owners", metadata, Column("id", Integer, primary_key=True))
    Table(
        "children", metadata, Column("id", Integer, primary_key=True), Column("owner_id", Integer)
    )
    metadata.create_all(engine)
    adapter = SQLAdapter(engine)
    original = {model.name: model for model in await adapter.discover()}
    admin = Admin(auth=auth, secret_key="s" * 32)
    admin.add_adapter(adapter, discover=False)
    for name, model in original.items():
        admin.register(model, options=ModelOptions(label=f"Registered {name}"))
    scans = 0
    describe = SQLRelationMetadata._links_many

    def count_scans(self, models):
        nonlocal scans
        scans += 1
        return describe(self, models)

    monkeypatch.setattr(SQLRelationMetadata, "_links_many", count_scans)
    try:
        for foreign_key, unique, expected in (
            (False, False, None),
            (True, False, "o2m"),
            (True, True, "o2o"),
            (False, True, None),
        ):
            with engine.begin() as connection:
                connection.exec_driver_sql("DROP TABLE children")
                reference = " REFERENCES owners(id)" if foreign_key else ""
                constraint = ", UNIQUE(owner_id)" if unique else ""
                connection.exec_driver_sql(
                    "CREATE TABLE children (id INTEGER PRIMARY KEY, owner_id INTEGER"
                    + reference
                    + constraint
                    + ")"
                )
            await adapter.refresh()
            before = scans
            resources = await admin.resources()
            assert resources["children"].model is not original["children"]
            assert resources["children"].label == "Registered children"
            for _ in range(3):
                graph = await schema_graph(resources.values())
                assert [edge["kind"] for edge in graph["edges"]] == ([expected] if expected else [])
            assert scans == before + 1, "each metadata snapshot must be scanned once"
            # Cached physical metadata must never cache per-resource field policy.
            admin.configure("children", options=ModelOptions(exclude=("owner_id",)))
            assert not (await schema_graph((await admin.resources()).values()))["edges"]
            admin.configure("children", options=ModelOptions(label="Registered children"))
    finally:
        engine.dispose()
