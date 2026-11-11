import re
from dataclasses import replace
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from quite_admin import Admin, Field, FieldOptions, ModelOptions, ModelSchema

from .helpers import login
from .test_relations import related_backend  # noqa: F401


def cell(page, name):
    return re.search(rf'<td data-list-field="{name}"[^>]*>(.*?)</td>', page.text, re.S)[1]


async def test_fk_ids_labels_links_permissions_and_raw_storage(auth, related_backend, monkeypatch):  # noqa: F811
    adapter, models = related_backend
    parent = await adapter.create(models["parents"], {"name": "User <username>"})
    fk = next(item.name for item in adapter.describe(models["children"]).fields if item.foreign_key)
    child = await adapter.create(models["children"], {"name": "Child", fk: parent["id"]})
    for index in range(3):
        await adapter.create(models["children"], {"name": f"Other {index}", fk: parent["id"]})
    native_list = adapter.list
    lookups = []

    async def tracking_list(model, query):
        if model is models["parents"]:
            lookups.append(query)
        return await native_list(model, query)

    monkeypatch.setattr(adapter, "list", tracking_list)
    admin = Admin(auth=auth, secret_key="s" * 32, adapters=[adapter], secure_cookies=False)
    # FK display is independent of form relationship editors, including FK-first tables.
    options = ModelOptions(list_fields=(fk, "name"), relations=())
    admin.register(models["children"], options=options)
    admin.register(models["parents"], options=ModelOptions(slug="people"))
    app = FastAPI()
    admin.mount_fastapi(app, path="/nested/admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client, "/nested/admin")
        url = "/nested/admin/models/children/"
        page = await client.get(url)
        assert len(lookups) == 1
        assert lookups[0].filters[0].operator == "in"
        assert lookups[0].columns == ("id",)
        target = "/nested/admin/models/people/" + adapter.describe(models["parents"]).record_key(
            parent
        )
        listing_target = target + "?" + urlencode({"return_to": url})
        assert f'href="{listing_target}"' in cell(page, fk)
        assert f">{parent['id']}</a>" in cell(page, fk)
        assert "User &lt;username&gt;" not in cell(page, fk)
        assert "record-row-link cell-open" in page.text  # no nested anchors
        admin.configure(
            "children",
            options=replace(options, fields={fk: FieldOptions(relation_label="name")}),
        )
        page = await client.get(url)
        assert "User &lt;username&gt;" in cell(page, fk)
        assert f'href="{listing_target}"' in cell(page, fk)
        assert (await adapter.get(models["children"], {"id": child["id"]}))[fk] == parent["id"]
        export = await client.get(url, params={"export": "csv", "columns": fk})
        assert "username" not in export.text
        assert str(parent["id"]) in export.text
        state = (
            await client.get(
                url + adapter.describe(models["children"]).record_key(child) + "/inline/name"
            )
        ).json()
        assert state["cells"][fk]["related"]["href"] == target
        admin.configure("parents", options=ModelOptions(exclude=("name",), slug="people"))
        assert "username" not in cell(await client.get(url), fk)
        admin.configure(
            "parents", options=ModelOptions(slug="people", permission=lambda r, i, a: a == "list")
        )
        hidden = cell(await client.get(url), fk)
        assert 'class="relation-value"' not in hidden and "username" not in hidden
        admin.configure(
            "parents",
            options=ModelOptions(slug="people", permission=lambda r, i, a: a in {"list", "edit"}),
        )
        assert f'href="{listing_target}"' in cell(await client.get(url), fk)
        await adapter.update(models["children"], {"id": child["id"]}, {fk: None})
        assert 'class="relation-value"' not in cell(await client.get(url), fk)


def test_relation_label_requires_a_foreign_key():
    schema = ModelSchema("items", (Field("id", int, primary_key=True), Field("name")))
    with pytest.raises(ValueError, match="relation_label"):
        ModelOptions(fields={"name": FieldOptions(relation_label="username")}).validate(schema)
