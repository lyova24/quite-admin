import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar

from quite_admin import (
    Admin,
    Field,
    FieldOptions,
    ModelOptions,
    ModelSchema,
    OperationHooks,
    Query,
    RecordAction,
    current_operation,
)
from quite_admin.errors import ValidationError

from .helpers import csrf, login


@pytest.fixture(params=["fastapi", "litestar"])
def extension_app(request, backend, auth, tmp_path):
    adapter, model = backend
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        adapters=[adapter],
        secure_cookies=False,
        templates_dir=tmp_path,
        logger=logging.getLogger("quite_admin.extensions"),
    )
    host = FastAPI() if request.param == "fastapi" else Litestar()
    if request.param == "fastapi":
        admin.mount_fastapi(host)
    else:
        admin.mount_litestar(host)
    return admin, host, adapter, model


async def test_write_lifecycle_order_veto_and_post_commit_failure(extension_app, caplog):
    admin, host, adapter, model = extension_app
    record = await adapter.create(model, {"name": "original"})
    await adapter.create(model, {"name": "duplicate"})
    key = {"id": record["id"]}
    events = []
    native_update = adapter.update

    async def update(model, key, values):
        operation = current_operation()
        assert operation.identity.subject == "admin"
        assert operation.key == key
        events.append("adapter")
        return await native_update(model, key, values)

    adapter.update = update

    async def before(operation):
        assert current_operation() is operation
        assert operation.record["name"] == "original"
        assert operation.action == "edit"
        events.append("before")
        with pytest.raises(TypeError):
            operation.values["name"] = "silently changed"
        if operation.values.get("name") == "blocked":
            raise ValidationError({"name": "A business rule blocked this change."})

    async def after(operation, saved):
        assert current_operation() is operation
        assert (await adapter.get(model, key))["name"] == saved["name"]
        events.append("after")
        raise RuntimeError("private record contents must not reach logs")

    admin.hooks = OperationHooks(before_write=before, after_write=after)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        path = "/admin/models/items/" + adapter.describe(model).record_key(record)
        form = await client.get(path)
        assert (await client.post(path, data={"__csrf": "wrong", "name": "bad"})).status_code == 403
        assert events == []
        rejected = await client.post(path, data={"__csrf": csrf(form), "name": "blocked"})
        assert rejected.status_code == 422
        assert events == ["before"]
        assert (await adapter.get(model, key))["name"] == "original"
        events.clear()
        conflict = await client.post(path, data={"__csrf": csrf(form), "name": "duplicate"})
        assert conflict.status_code == 409
        assert events == ["before", "adapter"]
        assert (await adapter.get(model, key))["name"] == "original"
        events.clear()
        saved = await client.post(path, data={"__csrf": csrf(form), "name": "accepted"})
        assert saved.status_code == 303
        assert events == ["before", "adapter", "after"]
        assert (await adapter.get(model, key))["name"] == "accepted"
    assert current_operation() is None
    assert "quite_admin.after_write_failed" in caplog.text
    assert "private record contents" not in caplog.text


async def test_field_codec_template_and_record_action(extension_app, tmp_path):
    admin, host, adapter, model = extension_app
    record = await adapter.create(model, {"name": "original", "count": 7})
    tmp_path.joinpath("counter.html").write_text(
        '<input class="counter-widget" name="{{ field.name }}" '
        'id="field-{{ field.name }}" value="{{ values[field.name] }}">'
    )

    async def reset(operation):
        assert operation is current_operation()
        assert operation.action == "action:reset"
        assert operation.identity.subject == "admin"
        return await adapter.update(model, operation.key, {"count": 0})

    admin.configure(
        "items",
        options=ModelOptions(
            fields={
                "count": FieldOptions(
                    kind="string",
                    parser=lambda value: int(value.removeprefix("#")),
                    formatter=lambda value: "#" + str(value),
                    template="counter.html",
                )
            },
            actions=(RecordAction("reset", "Reset counter", reset),),
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        path = "/admin/models/items/" + adapter.describe(model).record_key(record)
        form = await client.get(path)
        assert 'class="counter-widget"' in form.text
        assert 'value="#7"' in form.text
        assert "Reset counter" in form.text
        saved = await client.post(path, data={"__csrf": csrf(form), "count": "#9"})
        assert saved.status_code == 303
        key = {"id": record["id"]}
        assert (await adapter.get(model, key))["count"] == 9
        action_path = path + "/actions/reset"
        assert (await client.get(action_path)).status_code == 405
        assert (await client.post(action_path, data={"__csrf": "bad"})).status_code == 403
        assert (await adapter.get(model, key))["count"] == 9
        assert (await client.post(action_path, data={"__csrf": csrf(form)})).status_code == 303
        assert (await adapter.get(model, key))["count"] == 0
        admin.configure(
            "items",
            options=ModelOptions(
                can_edit=False,
                actions=(RecordAction("reset", "Reset counter", reset),),
            ),
        )
        assert "Reset counter" not in (await client.get(path)).text
        assert (await client.post(action_path, data={"__csrf": csrf(form)})).status_code == 403
    assert current_operation() is None


def test_sensitive_and_service_fields_have_safe_defaults():
    schema = ModelSchema(
        "users",
        (
            Field("id", int, primary_key=True),
            Field("username"),
            Field("password_hash"),
            Field("access_token"),
            Field("api_key"),
            Field("is_admin", bool),
            Field("created_at"),
        ),
    )
    defaults = ModelOptions()
    assert {field.name for field in defaults.visible_fields(schema)} == {
        "id",
        "username",
        "is_admin",
        "created_at",
    }
    for name in ("password_hash", "access_token", "api_key", "is_admin", "created_at"):
        with pytest.raises(ValidationError):
            defaults.parse_values(schema, {name: "forged"}, creating=False)
    explicit = ModelOptions(
        expose_sensitive_fields=("api_key",),
        writable_protected_fields=("is_admin",),
    )
    assert explicit.parse_values(schema, {"api_key": "key", "is_admin": "true"}, False) == {
        "api_key": "key",
        "is_admin": True,
    }


async def test_create_and_delete_share_the_write_lifecycle(extension_app):
    admin, host, adapter, model = extension_app
    events = []

    def before(operation):
        assert current_operation() is operation
        events.append(("before", operation.action))
        if operation.action == "create":
            assert operation.key is None
            assert operation.record == {}
            assert operation.values["name"] == "new"
        else:
            assert operation.key["id"] == operation.record["id"]

    def after(operation, saved):
        events.append(("after", operation.action))
        assert (saved is None) == (operation.action == "delete")

    admin.hooks = OperationHooks(before_write=before, after_write=after)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        form = await client.get("/admin/models/items/new")
        saved = await client.post(
            "/admin/models/items/new",
            data={
                "__csrf": csrf(form),
                "name": "new",
            },
        )
        assert saved.status_code == 303
        path = saved.headers["location"] + "/delete"
        confirmation = await client.get(path)
        assert (await client.post(path, data={"__csrf": csrf(confirmation)})).status_code == 303
    assert events == [
        ("before", "create"),
        ("after", "create"),
        ("before", "delete"),
        ("after", "delete"),
    ]
    assert (await adapter.list(model, Query())).total == 0
    assert current_operation() is None
