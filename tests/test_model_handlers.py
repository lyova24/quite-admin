import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator
from pydantic import Field as PydanticField

from quite_admin import Admin, Field, ModelOptions, OperationHooks, current_operation

from .helpers import csrf, login, revision


class CreateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = PydanticField(min_length=3)
    credential: SecretStr
    confirmation: SecretStr
    internal: str = "schema default must not become a form write"

    @model_validator(mode="after")
    def matching_credentials(self):
        if self.credential != self.confirmation:
            raise ValueError("Credentials must match.")
        return self


class UpdateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = PydanticField(default=None, min_length=3)
    count: int = 999


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_model_schemas_handlers_and_native_checked_updates(backend, auth, framework, caplog):
    adapter, model = backend
    calls, hooks = [], []

    async def create(operation, payload):
        assert current_operation() is operation
        assert operation.identity.subject == "admin" and operation.action == "create"
        assert isinstance(payload, CreateInput)
        assert set(operation.values) == {"name", "credential", "confirmation"}
        calls.append(operation.action)
        saved = await adapter.create(model, {"name": payload.name})
        # Service results may contain extra values; only model columns cross back
        # into redirects, history and after hooks.
        return {**saved, "credential": payload.credential.get_secret_value()}

    def before(operation):
        hooks.append((operation.action, dict(operation.values)))

    def after(operation, saved):
        assert "credential" not in saved

    options = ModelOptions(
        input_fields=(Field("credential", kind="password"), Field("confirmation", kind="password")),
        create_fields=("name", "credential", "confirmation"),
        edit_fields=("name",),
        list_fields=("name",),
        create_schema=CreateInput,
        update_schema=UpdateInput,
        create_handler=create,
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        hooks=OperationHooks(before_write=before, after_write=after),
    )
    admin.register(model, options=options)
    host = FastAPI() if framework == "fastapi" else Litestar()
    getattr(admin, "mount_" + framework)(host)
    secret = "private-service-credential"
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        page = await client.get("/admin/models/items/new")
        form = {"__csrf": csrf(page), "name": "x", "credential": secret, "confirmation": secret}
        assert (await client.post("/admin/models/items/new", data=form)).status_code == 422
        assert calls == hooks == [] and current_operation() is None
        invalid = await client.post(
            "/admin/models/items/new", data={**form, "name": "Valid", "confirmation": "wrong"}
        )
        assert invalid.status_code == 422 and "Credentials must match." in invalid.text
        assert secret not in invalid.text and calls == []
        assert (
            await client.post(
                "/admin/models/items/new", data={**form, "name": "Valid", "internal": "forged"}
            )
        ).status_code == 422
        created = await client.post(
            "/admin/models/items/new", data={**form, "name": "  Normalized name  "}
        )
        assert created.status_code == 303, created.text
        assert calls == ["create"] and hooks[-1][1]["name"] == "Normalized name"
        location = created.headers["location"]
        schema = adapter.describe(model)
        key = schema.parse_key(location.rsplit("/", 1)[-1])
        record = await adapter.get(model, key)
        assert record["internal"] == "hidden" and record["count"] == 0
        detail = await client.get(location)
        edit = {"__csrf": csrf(detail), "__revision": revision(detail), "name": "  Native edit  "}
        assert (await client.post(location, data=edit)).status_code == 303
        assert (await adapter.get(model, key))["name"] == "Native edit"
        assert hooks[-1] == ("edit", {"name": "Native edit"})
        assert (await client.post(location, data={**edit, "name": "Stale"})).status_code == 409

        async def update(operation, payload, *, guard):
            assert isinstance(payload, UpdateInput) and guard is not None
            assert current_operation() is operation
            assert dict(operation.values) == {"name": payload.name}
            calls.append("update")
            return SimpleNamespace(
                **await adapter.save_checked(
                    model, operation.key, operation.values, operation.relations, guard=guard
                )
            )

        admin.register(model, options=replace(options, update_handler=update))
        state = (await client.get(location + "/inline/name")).json()
        inline = {
            "__csrf": state["csrf"],
            "__revision": state["revision"],
            "name": "  Service edit  ",
        }
        updated = await client.post(location + "/inline/name", data=inline)
        assert updated.status_code == 200, updated.text
        assert updated.json()["cells"]["name"]["text"] == "Service edit"
        stale = await client.post(location + "/inline/name", data={**inline, "name": "Overwrite"})
        assert stale.status_code == 409
        invalid = await client.post(location + "/inline/name", data={**inline, "name": "x"})
        assert invalid.status_code == 422 and "name" in invalid.json()["errors"]
        record = await adapter.get(model, key)
        assert record["name"] == "Service edit" and record["count"] == 0
        admin.register(model, options=replace(options, can_create=False))
        assert (await client.post("/admin/models/items/new", data=form)).status_code == 403
    assert current_operation() is None and secret not in caplog.text


async def test_create_handler_can_return_loaded_orm_instance(web_backend, auth):
    adapter, model = web_backend

    async def create(operation, payload):
        record = await adapter.create(model, payload)
        return model(**record)

    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])
    admin.register(model, options=ModelOptions(create_fields=("name",), create_handler=create))
    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        await login(client, "")
        page = await client.get("/models/items/new")
        result = await client.post("/models/items/new", data={"__csrf": csrf(page), "name": "ORM"})
        assert result.status_code == 303, result.text
        assert (await client.get(result.headers["location"])).status_code == 200


def test_model_schema_configuration_rejects_invalid_callbacks():
    from quite_admin import ModelSchema

    schema = ModelSchema("items", (Field("id", int, primary_key=True),))
    for options in (
        ModelOptions(create_schema=dict),
        ModelOptions(update_schema=object),
        ModelOptions(create_handler="not callable"),
        ModelOptions(update_handler=42),
    ):
        with pytest.raises(TypeError):
            options.validate(schema)


def test_core_import_and_default_forms_do_not_require_pydantic():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import builtins
original = builtins.__import__
def without_pydantic(name, *args, **kwargs):
    if name == 'pydantic' or name.startswith('pydantic.'):
        raise ImportError('Pydantic intentionally unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = without_pydantic
from quite_admin import Field, ModelOptions, ModelSchema
schema = ModelSchema('items', (Field('id', int, primary_key=True, generated=True), Field('name')))
options = ModelOptions()
options.validate(schema)
assert options.parse_values(schema, {'name': 'plain core'}, True) == {'name': 'plain core'}
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
