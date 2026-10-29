import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar, Router
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from quite_admin import Admin, Field, ModelOptions, ModelSchema, Page, RecordPage
from quite_admin.adapters.base import Adapter
from quite_admin.auth import LoginThrottle, PasswordAuth, hash_password, verify_password

from .helpers import csrf, login


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_nested_mount_and_reverse_proxy_prefix(auth, framework, backend):
    adapter, model = backend
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False, adapters=[adapter])
    if framework == "fastapi":
        host = FastAPI()
        child = FastAPI()
        admin.mount_fastapi(child, "/control")
        host.mount("/internal", child)
    else:
        host = Litestar(
            route_handlers=[
                Router(path="/internal", route_handlers=[admin.litestar_route("/control")])
            ]
        )
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        await login(client, "/proxy/internal/control")
        response = await client.get("/proxy/internal/control/")
        assert response.status_code == 200, response.text
        assert "/proxy/internal/control/assets/admin.css" in response.text
        record = await adapter.create(model, {"name": "A nested record"})
        key = adapter.describe(model).record_key(record)
        page = await client.get(f"/proxy/internal/control/models/items/{key}")
        assert '<nav class="breadcrumbs" aria-label="Breadcrumbs">' in page.text
        assert '<a href="/proxy/internal/control/">Overview</a>' in page.text
        assert '<a href="/proxy/internal/control/models/items/">Items</a>' in page.text
        assert '<span aria-current="page">A nested record</span>' in page.text
        confirmation = await client.get(f"/proxy/internal/control/models/items/{key}/delete")
        assert (
            f'<a href="/proxy/internal/control/models/items/{key}">A nested record</a>'
            in confirmation.text
        )
        result = await client.post(
            "/proxy/internal/control/logout", data={"__csrf": csrf(response)}
        )
        assert result.headers["location"] == "/proxy/internal/control/login"


async def test_secure_cookie_flags_and_revocation():
    auth = PasswordAuth.single_user("admin", "correct horse battery staple")
    admin = Admin(auth=auth, secret_key="s" * 32)
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="https://test") as client:
        initial = await client.get("/admin/login")
        cookie = initial.headers["set-cookie"]
        for flag in ("httponly", "secure", "samesite=lax"):
            assert flag in cookie.lower()
        previous_token = csrf(initial)
        await login(client)
        dashboard = await client.get("/admin/")
        assert csrf(dashboard) != previous_token
        auth.users.clear()
        assert (await client.get("/admin/")).status_code == 303


def test_password_hashing_and_throttling():
    encoded = hash_password("secret")
    assert encoded != hash_password("secret")
    assert verify_password("secret", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("secret", "bad hash")
    throttle = LoginThrottle(attempts=2, max_clients=2)
    assert throttle.attempt("ip") == 0
    assert throttle.attempt("ip") == 0
    assert throttle.attempt("ip") > 0
    throttle.reset("ip")
    assert throttle.attempt("ip") == 0


async def test_no_orm_required_and_registration_only(auth, tmp_path):
    class CustomAdapter:
        """Stand-in for a third-party ORM / repository with no library dependencies."""

        def discover(self):
            raise AssertionError("Explicit registration must not call discover()")

        def describe(self, model):
            return ModelSchema("objects", (Field("id", str, primary_key=True), Field("title")))

        async def list(self, model, query):
            return RecordPage([{"id": "external/one", "title": "External object"}], 1)

        async def get(self, model, key):
            return {"id": key["id"], "title": "External object"}

        async def create(self, model, values):
            return dict(values)

        async def update(self, model, key, values):
            return {**key, **values}

        async def delete(self, model, key):
            pass

    adapter = CustomAdapter()
    assert isinstance(adapter, Adapter)
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    admin.register(object(), adapter=adapter, options=ModelOptions(can_create=False))
    admin.configure("objects", options=ModelOptions(label="External store", can_create=False))
    host = FastAPI()
    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await login(client)
        response = await client.get("/admin/models/objects/")
        assert response.status_code == 200, response.text
        assert "External store" in response.text
        assert "External object" in response.text
        assert "Create record" not in response.text


def test_invalid_config_and_duplicate_pages(auth):
    with pytest.raises(ValueError, match="32 bytes"):
        Admin(auth=auth, secret_key="short")
    admin = Admin(auth=auth, secret_key="s" * 32)
    with pytest.raises(ValueError, match="adapter explicitly"):
        admin.register(object())
    admin.add_page(Page("report", "Report", "report.html"))
    with pytest.raises(ValueError, match="unique"):
        admin.add_page(Page("report", "Report", "report.html"))


async def test_host_session_is_preserved(auth):
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    host = FastAPI()
    host.add_middleware(SessionMiddleware, secret_key="host-secret", session_cookie="host_session")

    @host.get("/host-login")
    async def host_login(request: Request):
        request.session["host_user"] = "alice"
        return {"ok": True}

    @host.get("/host-session")
    async def host_session(request: Request):
        return dict(request.session)

    admin.mount_fastapi(host)
    async with AsyncClient(transport=ASGITransport(app=host), base_url="http://test") as client:
        await client.get("/host-login")
        await login(client)
        response = await client.get("/host-session")
        assert response.json() == {"host_user": "alice"}
        dashboard = await client.get("/admin/")
        await client.post("/admin/logout", data={"__csrf": csrf(dashboard)})
        assert (await client.get("/host-session")).json() == {"host_user": "alice"}


async def test_form_size_and_duplicate_fields(auth):
    admin = Admin(auth=auth, secret_key="s" * 32, secure_cookies=False)
    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        initial = await client.get("/login")
        headers = {"content-type": "application/x-www-form-urlencoded"}
        duplicate = await client.post(
            "/login",
            content=(f"__csrf={csrf(initial)}&username=a&username=b&password=bad"),
            headers=headers,
        )
        assert duplicate.status_code == 422
        malformed = await client.post("/login", data={"__csrf": "☃"})
        assert malformed.status_code == 403
        oversized = await client.post("/login", content="x=" + "x" * (1024 * 1024), headers=headers)
        assert oversized.status_code == 413
