import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import Admin, DelegatingAdapter, Field, FieldOptions, ModelOptions, ModelSchema
from quite_admin.errors import ValidationError

from .helpers import csrf, login


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_input_fields_use_native_schema_and_never_expose_secrets(
    backend, auth, framework, caplog
):
    native, model = backend
    calls = []

    class Service(DelegatingAdapter):
        async def create(self, model, values):
            calls.append(dict(values))
            if values["credential"] != values["confirmation"]:
                raise ValidationError({"confirmation": "Values must match."})
            return await self.delegate.create(model, {"name": values["name"]})

    adapter = Service(native)
    options = ModelOptions(
        input_fields=(
            Field("credential", kind="password"),
            Field("confirmation", kind="password"),
            Field("delivery_note", nullable=True),
        ),
        create_fields=("name", "credential", "confirmation", "delivery_note"),
        edit_fields=("name",),
        fields={"credential": FieldOptions(label="New credential", help_text="Keep it private")},
    )
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])
    admin.register(model, options=options)
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)
    secret = "unique-private-input-value"
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/new")
        assert page.status_code == 200
        assert 'type="password" autocomplete="new-password" required' in page.text
        assert "New credential" in page.text and "Keep it private" in page.text
        form = {
            "__csrf": csrf(page),
            "name": "Created through service",
            "credential": secret,
            "confirmation": "different",
            "delivery_note": "also form only",
        }
        denied = await client.post("/admin/models/items/new", data={**form, "__csrf": "wrong"})
        assert denied.status_code == 403 and calls == []
        invalid = await client.post("/admin/models/items/new", data=form)
        assert invalid.status_code == 422 and "Values must match." in invalid.text
        assert secret not in invalid.text
        assert 'value="different"' not in invalid.text
        empty = await client.post("/admin/models/items/new", data={**form, "credential": ""})
        assert empty.status_code == 422 and len(calls) == 1
        saved = await client.post("/admin/models/items/new", data={**form, "confirmation": secret})
        assert saved.status_code == 303, saved.text
        assert calls[-1]["credential"] == secret
        detail = await client.get(saved.headers["location"])
        listing = await client.get("/admin/models/items/", params={"q": "Created"})
        assert detail.status_code == listing.status_code == 200
        for response in (detail, listing, await client.get("/admin/schema")):
            for name in ("credential", "confirmation", "delivery_note"):
                assert name not in response.text
            assert secret not in response.text
        exported = await client.get(
            "/admin/models/items/", params={"export": "csv", "columns": "name"}
        )
        assert exported.status_code == 200 and "Created through service" in exported.text
        for name in ("credential", "delivery_note"):
            assert (
                await client.get("/admin/models/items/", params={"export": "csv", "columns": name})
            ).status_code == 400
        admin.register(model, options=ModelOptions(**{**options.__dict__, "can_edit": False}))
        readonly = await client.get(saved.headers["location"])
        assert readonly.status_code == 200 and 'name="credential"' not in readonly.text
    events = await admin.storage.activities(collections=("items",))
    payload = json.dumps([event.__dict__ for event in events.events], default=str)
    assert secret not in payload and "delivery_note" not in payload
    assert secret not in caplog.text
    assert "credential" not in native.describe(model).by_name


def test_input_field_configuration_and_password_overrides():
    schema = ModelSchema("users", (Field("id", int, primary_key=True), Field("name")))
    for options in (
        ModelOptions(input_fields=(Field("name"),)),
        ModelOptions(input_fields=(Field("extra"), Field("extra"))),
        ModelOptions(input_fields=(Field("extra", primary_key=True),)),
        ModelOptions(input_fields=(Field("extra", foreign_key="users.id"),)),
        *(
            ModelOptions(input_fields=(Field("extra"),), **{option: ("extra",)})
            for option in ("list_fields", "search_fields", "filter_fields", "list_editable")
        ),
    ):
        with pytest.raises(ValueError):
            options.validate(schema)
    options = ModelOptions(
        input_fields=(Field("credential"),),
        fields={"credential": FieldOptions(kind="password")},
    )
    options.validate(schema)
    assert options.form_fields(schema, True)[-1].kind == "password"
    assert "credential" not in {item.name for item in options.visible_fields(schema)}
    with pytest.raises(ValueError):
        options.form_fields(schema, True)[-1].parse("")
