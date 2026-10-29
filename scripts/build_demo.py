"""Export fictional example metadata/data for a standalone browser demo; never a real DB."""

import argparse
import asyncio
import json
import os
import secrets
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect  # noqa: E402

from examples.common import make_demo, seed  # noqa: E402
from quite_admin import Query, __version__  # noqa: E402
from quite_admin.diagram import schema_graph  # noqa: E402
from quite_admin.i18n import RUSSIAN, Translator  # noqa: E402


async def build(output):
    with TemporaryDirectory(prefix="quite-admin-static-demo-") as temporary:
        os.environ.update(
            QUITE_ADMIN_DEMO_DB=f"sqlite:///{temporary}/demo.db",
            QUITE_ADMIN_PASSWORD=secrets.token_urlsafe(32),
            QUITE_ADMIN_SECRET=secrets.token_urlsafe(48),
            QUITE_ADMIN_LANGUAGE="en",
            QUITE_ADMIN_TITLE="Quite Admin",
        )
        admin, engine, sessions = make_demo()
        try:
            seed(engine, sessions)
            resources = await admin.resources()
            slugs = {resource.model: slug for slug, resource in resources.items()}
            collections = {}
            for slug, resource in resources.items():
                schema = resource.schema
                adapter = resource.adapter
                fields = resource.options.visible_fields(schema)
                rows = (await adapter.list(resource.model, Query(limit=10000))).records
                relations = [
                    relation
                    for relation in adapter.relations(resource.model)
                    if relation.target in slugs
                ]
                records = []
                for row in rows:
                    key = {field.name: row[field.name] for field in schema.primary_keys}
                    links = {}
                    for relation in relations:
                        target_schema = resources[slugs[relation.target]].schema
                        linked = await adapter.related(
                            resource.model, relation.name, key, Query(limit=10000)
                        )
                        links[relation.name] = [
                            target_schema.record_key(item) for item in linked.records
                        ]
                    records.append(
                        {
                            "key": schema.record_key(row),
                            "values": {
                                field.name: None
                                if row[field.name] is None
                                else field.format(row[field.name])
                                for field in fields
                            },
                            "links": links,
                        }
                    )
                collections[slug] = {
                    "label": resource.label,
                    "fields": [
                        {
                            "name": field.name,
                            "label": field.label,
                            "kind": field.kind,
                            "nullable": field.nullable,
                            "generated": field.generated,
                            "hasDefault": field.has_default,
                            "maxLength": field.max_length,
                            "choices": field.choices,
                            "primaryKey": field.primary_key,
                        }
                        for field in fields
                    ],
                    "columns": resource.options.list_fields or [field.name for field in fields[:6]],
                    "writable": {
                        "create": list(resource.options.writable_fields(schema, True)),
                        "edit": list(resource.options.writable_fields(schema, False)),
                    },
                    "unique": [
                        column.name
                        for column in inspect(resource.model).local_table.columns
                        if column.unique
                    ],
                    "relations": [
                        {
                            "name": relation.name,
                            "label": relation.label,
                            "kind": relation.kind,
                            "target": slugs[relation.target],
                            "canDetach": relation.can_detach,
                            "sourceFields": relation.source_fields,
                            "inverse": inspect(resource.model)
                            .relationships[relation.name]
                            .back_populates,
                        }
                        for relation in relations
                    ],
                    "records": records,
                }
            graph = await schema_graph(resources.values())
            for node in graph["nodes"]:
                node["url"] = "#/models/" + node["id"] + "/"
            for node in graph["junctions"]:
                node["url"] = None
            schema_pages = {}
            for language in ("en", "ru"):
                translations = Translator(language)
                schema_pages[language] = admin.templates.env.get_template(
                    "quite_admin/_schema_content.html"
                ).render(
                    graph=graph,
                    schema_messages=admin._schema_messages(translations),
                    t=translations.gettext,
                    tn=translations.ngettext,
                )
            output.mkdir(parents=True, exist_ok=True)
            for path in (ROOT / "demo").iterdir():
                if path.is_file():
                    shutil.copyfile(path, output / path.name)
            shutil.copyfile(ROOT / "src/quite_admin/static/admin.css", output / "admin.css")
            for script in ("relations.js", "schema.js"):
                shutil.copyfile(ROOT / "src/quite_admin/static" / script, output / script)
            (output / "theme.css").write_text(admin.theme.stylesheet())
            (output / "seed.json").write_text(
                json.dumps(
                    {
                        "version": __version__,
                        "title": admin.title,
                        "translations": RUSSIAN,
                        "collections": collections,
                        "schemaPages": schema_pages,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "build/docs/demo")
    args = parser.parse_args()
    asyncio.run(build(args.output))
    print(f"Standalone browser demo written to {args.output}")
