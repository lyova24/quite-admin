from html.parser import HTMLParser

import pytest
from fastapi import FastAPI
from httpx import URL, ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, FieldOptions, ModelOptions

from .helpers import csrf, login, revision
from .test_relations import related_backend, relation_to  # noqa: F401


class PickerParser(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.pickers = {}
        self.endpoints = []
        self.select = None
        self.option = None
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "div":
            self.endpoints.append(
                attributes.get("data-endpoint", self.endpoints[-1] if self.endpoints else None)
            )
        elif tag == "select":
            self.select = {
                "endpoint": self.endpoints[-1] if self.endpoints else None,
                "options": {},
                "selected": set(),
            }
            self.pickers[attributes.get("name")] = self.select
        elif tag == "option" and self.select is not None:
            self.option = (attributes, "")

    def handle_data(self, data):
        if self.option is not None:
            attrs, content = self.option
            self.option = (attrs, content + data)

    def handle_endtag(self, tag):
        if tag == "div":
            self.endpoints.pop()
        elif tag == "option" and self.option is not None:
            attrs, content = self.option
            self.select["options"][attrs.get("value", "")] = content
            if "selected" in attrs:
                self.select["selected"].add(attrs.get("value", ""))
            self.option = None
        elif tag == "select":
            self.select = None


def picker(page, name):
    assert page.status_code == 200, page.text
    found = PickerParser(page.text).pickers
    assert name in found, page.text
    assert found[name]["endpoint"], page.text
    return found[name]


async def lookup(client, endpoint, **params):
    return await client.get(URL(endpoint).copy_merge_params(params))


def configure(auth, adapter, models, framework="fastapi"):
    source, target = models["children"], models["parents"]
    fk = next(item.name for item in adapter.describe(source).fields if item.foreign_key)
    relation = relation_to(adapter, source, target, "many_to_one")
    admin = Admin(auth=auth, secret_key="s" * 48, adapters=[adapter], secure_cookies=False)
    admin.configure(
        "children",
        options=ModelOptions(fields={fk: FieldOptions(relation_label="name")}),
    )
    # A per-FK label must work without changing the target's own label or search setup.
    admin.configure("parents", options=ModelOptions(record_label="id", search_fields=()))
    app = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(app, path="/tools/admin")
    return admin, app, fk, relation


def form_selection(relation, value):
    return {
        "__relation_present__" + relation.name: "true",
        "__relation__" + relation.name: value,
    }


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_form_relation_label_and_picker_search_by_label_or_exact_id(
    auth,
    related_backend,  # noqa: F811
    framework,
):
    adapter, models = related_backend
    admin, app, fk, relation = configure(auth, adapter, models, framework)
    target, source = models["parents"], models["children"]
    alex = await adapter.create(target, {"name": "Alex Smith <safe>"})
    brown = await adapter.create(target, {"name": "alex Brown"})
    by_text = await adapter.create(target, {"name": f"Code {alex['id']}"})
    # Numeric ID lookup must be exact, even when another ID has the same prefix.
    for _ in range(10):
        await adapter.create(target, {"name": "Other parent"})
    child = await adapter.create(source, {"name": "Child", fk: alex["id"]})
    target_token = adapter.describe(target).record_key(alex)
    child_token = adapter.describe(source).record_key(child)
    name = "__relation__" + relation.name
    selected = target_token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client, "/tools/admin")
        edit_url = f"/tools/admin/models/children/{child_token}"
        form = await client.get(edit_url)
        control = picker(form, name)
        assert control["selected"] == {selected}
        assert control["options"][selected] == alex["name"]
        assert "Alex Smith &lt;safe&gt;" in form.text
        create_url = "/tools/admin/models/children/new"
        new_form = await client.get(create_url)
        new_control = picker(new_form, name)
        assert new_control["options"][selected] == alex["name"]
        for endpoint in (control["endpoint"], new_control["endpoint"]):
            assert endpoint.startswith("/tools/admin/")
            response = await lookup(client, endpoint, q="sMi")
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 1
            assert response.json()["items"] == [
                {
                    "key": selected,
                    "label": alex["name"],
                    "identity": str(alex["id"]),
                    "description": alex["name"],
                }
            ]
            response = await lookup(client, endpoint, q="Alex")
            assert {item["label"] for item in response.json()["items"]} == {
                alex["name"],
                brown["name"],
            }
            response = await lookup(client, endpoint, q=str(alex["id"]))
            assert response.json()["total"] == 2
            assert {item["label"] for item in response.json()["items"]} == {
                alex["name"],
                by_text["name"],
            }
        changed_value = adapter.describe(target).record_key(brown)
        saved = await client.post(
            edit_url,
            data={
                "__csrf": csrf(form),
                "__revision": revision(form),
                "name": "Updated child",
                **form_selection(relation, changed_value),
            },
        )
        assert saved.status_code == 303, saved.text
        assert (await adapter.get(source, {"id": child["id"]}))[fk] == brown["id"]
        created = await client.post(
            create_url,
            data={
                "__csrf": csrf(new_form),
                "name": "New child",
                **form_selection(relation, selected),
            },
        )
        assert created.status_code == 303, created.text
        new_token = created.headers["location"].rsplit("/", 1)[-1]
        created_row = await adapter.get(source, adapter.describe(source).parse_key(new_token))
        assert created_row[fk] == alex["id"]


async def test_form_relation_label_restored_after_invalid_submission(
    auth,
    related_backend,  # noqa: F811
):
    adapter, models = related_backend
    admin, app, fk, relation = configure(auth, adapter, models)
    source, target = models["children"], models["parents"]
    first = await adapter.create(target, {"name": "Original parent"})
    for index in range(30):
        await adapter.create(target, {"name": f"Parent {index:02}"})
    last = await adapter.create(target, {"name": "Selected beyond first page <safe>"})
    child = await adapter.create(source, {"name": "Child", fk: first["id"]})
    source_token = adapter.describe(source).record_key(child)
    selected = adapter.describe(target).record_key(last)
    name = "__relation__" + relation.name
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client, "/tools/admin")
        url = "/tools/admin/models/children/" + source_token
        form = await client.get(url)
        assert selected not in picker(form, name)["options"]
        rejected = await client.post(
            url,
            data={
                "__csrf": csrf(form),
                "__revision": revision(form),
                "name": "Unsaved",
                "unknown_field": "invalid",
                **form_selection(relation, selected),
            },
        )
        assert rejected.status_code == 422, rejected.text
        restored = PickerParser(rejected.text).pickers[name]
        assert restored["selected"] == {selected}
        assert restored["options"][selected] == last["name"]
        assert "Selected beyond first page &lt;safe&gt;" in rejected.text
        assert (await adapter.get(source, {"id": child["id"]}))[fk] == first["id"]


async def test_form_relation_label_respects_hidden_fields_and_permissions(
    auth,
    related_backend,  # noqa: F811
):
    adapter, models = related_backend
    admin, app, fk, relation = configure(auth, adapter, models)
    target, source = models["parents"], models["children"]
    parent = await adapter.create(target, {"name": "Hidden confidential label"})
    child = await adapter.create(source, {"name": "Child", fk: parent["id"]})
    source_token = adapter.describe(source).record_key(child)
    name = "__relation__" + relation.name
    selected = adapter.describe(target).record_key(parent)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await login(client, "/tools/admin")
        url = "/tools/admin/models/children/" + source_token
        control = picker(await client.get(url), name)
        endpoint = control["endpoint"]
        admin.configure(
            "parents",
            options=ModelOptions(record_label="id", search_fields=(), exclude=("name",)),
        )
        form = await client.get(url)
        hidden_control = picker(form, name)
        assert hidden_control["options"][selected] == str(parent["id"])
        assert "Hidden confidential label" not in form.text
        hidden_search = await lookup(client, endpoint, q="confidential")
        unrelated_search = await lookup(client, endpoint, q="nonexistent private value")
        assert hidden_search.status_code == unrelated_search.status_code == 200
        assert hidden_search.json() == unrelated_search.json()
        assert "confidential" not in hidden_search.text
        by_id = await lookup(client, endpoint, q=str(parent["id"]))
        assert by_id.json()["items"][0]["label"] == str(parent["id"])
        assert by_id.json()["items"][0]["identity"] == str(parent["id"])
        for denied_action in ("list", "view"):
            admin.configure(
                "parents",
                options=ModelOptions(
                    permission=lambda request, identity, action, denied=denied_action: (
                        action not in ({"view", "edit"} if denied == "view" else {denied})
                    )
                ),
            )
            denied = await lookup(client, endpoint, q="confidential")
            assert denied.status_code == 403
            assert "Hidden confidential label" not in denied.text
        admin.configure("parents", options=ModelOptions(record_label="id", search_fields=()))
        admin.configure(
            "children",
            options=ModelOptions(
                fields={fk: FieldOptions(relation_label="name")},
                can_edit=False,
            ),
        )
        assert (await client.get(endpoint)).status_code == 403
